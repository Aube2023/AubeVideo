"""Tip jar via Stripe Checkout — dons aux créateurs.

Nécessite:
  - AUBEVIDEO_STRIPE_SK (clé secrète)
  - AUBEVIDEO_STRIPE_WH (webhook secret)
  - AUBEVIDEO_PUBLIC_URL (ex: https://video.aubeetoilee.com)

Si la clé Stripe manque, les fonctions retournent gracieusement None / False.
"""
import os
from db import db_cursor

try:
    import stripe
    stripe.api_key = os.environ.get("AUBEVIDEO_STRIPE_SK", "")
    STRIPE_OK = bool(stripe.api_key)
except Exception:
    STRIPE_OK = False

PUBLIC_URL = os.environ.get("AUBEVIDEO_PUBLIC_URL", "http://localhost:5017")
WEBHOOK_SECRET = os.environ.get("AUBEVIDEO_STRIPE_WH", "")


def create_checkout(from_user, to_user_id, to_display, amount_cents, message=""):
    if not STRIPE_OK:
        return None
    with db_cursor(commit=True) as cur:
        cur.execute(
            """INSERT INTO tips (from_user, to_user, amount_cents, message, status)
               VALUES (%s, %s, %s, %s, 'pending') RETURNING id""",
            (from_user, to_user_id, amount_cents, message),
        )
        tip_id = cur.fetchone()["id"]
    try:
        s = stripe.checkout.Session.create(
            mode="payment",
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "eur",
                    "product_data": {"name": f"Don à {to_display} sur AubeVideo"},
                    "unit_amount": amount_cents,
                },
                "quantity": 1,
            }],
            success_url=f"{PUBLIC_URL}/tip/success?tip={tip_id}",
            cancel_url=f"{PUBLIC_URL}/tip/cancel?tip={tip_id}",
            metadata={"tip_id": str(tip_id)},
        )
        with db_cursor(commit=True) as cur:
            cur.execute("UPDATE tips SET stripe_session_id = %s WHERE id = %s",
                        (s.id, tip_id))
        return s.url
    except Exception:
        return None


def handle_webhook(payload, signature):
    if not STRIPE_OK or not WEBHOOK_SECRET:
        return False
    try:
        event = stripe.Webhook.construct_event(payload, signature, WEBHOOK_SECRET)
    except Exception:
        return False
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        tip_id = session.get("metadata", {}).get("tip_id")
        if tip_id:
            with db_cursor(commit=True) as cur:
                cur.execute(
                    "UPDATE tips SET status = 'paid' WHERE id = %s",
                    (tip_id,),
                )
    return True
