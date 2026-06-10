"""Web Push (VAPID) — notifications navigateur.

Dépendance optionnelle : pywebpush. Si absent, les envois sont silencieusement ignorés.
"""
import os
import json
import base64
import secrets
import threading
from db import db_cursor

try:
    from pywebpush import webpush, WebPushException
    PYWEBPUSH_OK = True
except Exception:
    PYWEBPUSH_OK = False

VAPID_PRIVATE = os.environ.get("AUBEVIDEO_VAPID_PRIVATE", "")
VAPID_PUBLIC = os.environ.get("AUBEVIDEO_VAPID_PUBLIC", "")
VAPID_CLAIMS_EMAIL = os.environ.get("AUBEVIDEO_VAPID_EMAIL", "mailto:admin@aubeetoilee.com")


def public_key_b64():
    return VAPID_PUBLIC


def save_subscription(user_id, subscription):
    with db_cursor(commit=True) as cur:
        cur.execute(
            """INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (endpoint) DO UPDATE SET user_id = EXCLUDED.user_id""",
            (user_id,
             subscription.get("endpoint"),
             subscription.get("keys", {}).get("p256dh", ""),
             subscription.get("keys", {}).get("auth", "")),
        )


def remove_subscription(user_id, endpoint):
    with db_cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM push_subscriptions WHERE user_id = %s AND endpoint = %s",
            (user_id, endpoint),
        )


def _send_batch(subs, data):
    """Boucle d'envoi synchrone — à exécuter hors requête HTTP (thread)."""
    sent = 0
    dead = []
    for s in subs:
        try:
            webpush(
                subscription_info={
                    "endpoint": s["endpoint"],
                    "keys": {"p256dh": s["p256dh"], "auth": s["auth"]},
                },
                data=data,
                vapid_private_key=VAPID_PRIVATE,
                vapid_claims={"sub": VAPID_CLAIMS_EMAIL},
            )
            sent += 1
        except WebPushException as e:
            if getattr(e.response, "status_code", None) in (404, 410):
                dead.append(s["endpoint"])
        except Exception:
            pass
    if dead:  # purge groupée des abonnements expirés (1 requête au lieu de N)
        try:
            with db_cursor(commit=True) as cur:
                cur.execute(
                    "DELETE FROM push_subscriptions WHERE endpoint = ANY(%s)",
                    (dead,),
                )
        except Exception:
            pass
    return sent


def send_to_user(user_id, title, body, url="/"):
    """Envoie les notifications en arrière-plan (webpush = HTTP bloquant).

    Retourne le nombre d'abonnements ciblés (l'envoi réel est asynchrone).
    """
    if not PYWEBPUSH_OK or not VAPID_PRIVATE:
        return 0
    with db_cursor() as cur:
        cur.execute(
            "SELECT endpoint, p256dh, auth FROM push_subscriptions WHERE user_id = %s",
            (user_id,),
        )
        subs = cur.fetchall()
    if not subs:
        return 0
    data = json.dumps({"title": title, "body": body, "url": url})
    threading.Thread(target=_send_batch, args=(subs, data), daemon=True).start()
    return len(subs)
