from decimal import ROUND_HALF_UP, Decimal
import stripe
from django.conf import settings
from ..models import Discount, Tax

def _product_data_for_item(item):
    data = {"name": item.name}
    if item.description:
        data["description"] = item.description
    return data

# получение секретного ключа для заданной валюты
def _secret_for_currency(currency: str) -> str:
    cur = (currency or getattr(settings, "DEFAULT_CURRENCY", "usd")).lower()

    if hasattr(settings, "get_stripe_secret_for"):
        return settings.get_stripe_secret_for(cur)

    keys = getattr(settings, "STRIPE_KEYS", None)
    if isinstance(keys, dict):
        pair = keys.get(cur) or keys.get(getattr(settings, "DEFAULT_CURRENCY", "usd"), {})
        if isinstance(pair, dict) and pair.get("secret"):
            return pair["secret"]

    legacy = getattr(settings, "STRIPE_SECRET_KEY", "")
    if legacy:
        return legacy

    raise RuntimeError(f"Не удалось получить Stripe secret key для валюты '{cur}'")

# минимальная сумма заказа в центах
def _min_charge_for_currency(currency: str) -> int:
    cur = (currency or "usd").lower()
    table = {
        "usd": 50,
        "eur": 50,
        "gbp": 30,
    }
    return table.get(cur, 50) # дефолт 50

# грубая оценка total после order-скидки, чтобы отсеять суммы ниже минимума до запроса в Stripe
# налоги здесь не учитываем умышленно (pre-check)
def _apply_order_discount_cents(amount_cents: int, order) -> int:
    d = getattr(order, "discount", None)
    if not d or not getattr(d, "active", False):
        return amount_cents
    off = int(
        (Decimal(amount_cents) * Decimal(int(d.percent_off)) / Decimal(100))
        .quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )
    return amount_cents - off

# создание Stripe Checkout Session для одного товара
def create_checkout_session_for_item(item):
    currency = (item.currency or "usd").lower()
    secret = _secret_for_currency(currency)

    unit_amount = int(item.price)
    min_needed = _min_charge_for_currency(currency)
    if unit_amount < min_needed:
        raise ValueError(
            f"Цена {unit_amount/100:.2f} {currency.upper()} меньше минимального "
            f"({min_needed/100:.2f} {currency.upper()})."
        )

    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[{
            "price_data": {
                "currency": currency,
                "product_data": _product_data_for_item(item),
                "unit_amount": unit_amount,
            },
            "quantity": 1,
        }],
        success_url=settings.SUCCESS_URL,
        cancel_url=settings.CANCEL_URL,
        api_key=secret,  # ключ под валюту товара
    )
    return session

# создание Stripe Checkout Session для заказа
def create_checkout_session_for_order(order):
    items_qs = order.items.all()
    if not items_qs.exists():
        raise ValueError("Заказ не содержит товаров")

    currencies = {i.currency.lower() for i in items_qs}
    if len(currencies) > 1:
        raise ValueError("Смешанные валюты не поддерживаются в одном чеке")

    currency = next(iter(currencies))
    secret = _secret_for_currency(currency)

    # предварительная проверка минимума (после скидки заказа)
    subtotal = sum(int(i.price) for i in items_qs)
    est_total = _apply_order_discount_cents(subtotal, order)
    min_needed = _min_charge_for_currency(currency)
    if est_total < min_needed:
        raise ValueError(
            f"Общая сумма {est_total/100:.2f} {currency.upper()} меньше минимального "
            f"({min_needed/100:.2f} {currency.upper()}). Увеличьте цены или уменьшите скидку."
        )

    # список tax_rate ids (только активные)
    tax_rate_ids = [ensure_stripe_tax_rate(t, api_key=secret) for t in getattr(order, "taxes", []).filter(active=True)]

    line_items = [{
        "price_data": {
            "currency": currency,
            "product_data": _product_data_for_item(item),
            "unit_amount": int(item.price),
        },
        "quantity": 1,
        **({"tax_rates": tax_rate_ids} if tax_rate_ids else {}),
    } for item in items_qs]

    params = dict(
        mode="payment",
        line_items=line_items,
        client_reference_id=str(order.id),
        metadata={"order_id": str(order.id)},
        success_url=settings.SUCCESS_URL,
        cancel_url=settings.CANCEL_URL,
        api_key=secret,  # ключ под валюту заказа
    )

    # применяем скидку
    if getattr(order, "discount", None) and order.discount and order.discount.active:
        coupon_id = ensure_stripe_coupon(order.discount, api_key=secret)
        params["discounts"] = [{"coupon": coupon_id}]

    session = stripe.checkout.Session.create(**params)
    return session

# гарантируем наличие купона в Stripe и возвращаем его id
def ensure_stripe_coupon(discount: Discount, api_key: str | None = None) -> str:
    if discount.stripe_coupon_id and discount.active:
        return discount.stripe_coupon_id

    coupon = stripe.Coupon.create(
        percent_off=int(discount.percent_off),
        duration="once",
        name=discount.name,
        api_key=api_key or _secret_for_currency(getattr(settings, "DEFAULT_CURRENCY", "usd")),
    )
    discount.stripe_coupon_id = coupon.id
    discount.save(update_fields=["stripe_coupon_id"])
    return coupon.id

# гарантируем наличие TaxRate в Stripe и возвращаем его id
def ensure_stripe_tax_rate(tax: Tax, api_key: str | None = None) -> str:
    if tax.stripe_tax_rate_id and tax.active:
        return tax.stripe_tax_rate_id

    txr = stripe.TaxRate.create(
        display_name=tax.display_name,
        percentage=float(tax.percentage),
        inclusive=bool(tax.inclusive),
        active=True,
        api_key=api_key or _secret_for_currency(getattr(settings, "DEFAULT_CURRENCY", "usd")),
    )
    tax.stripe_tax_rate_id = txr.id
    tax.active = True
    tax.save(update_fields=["stripe_tax_rate_id", "active"])
    return txr.id