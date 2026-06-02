"""AubeVideo - tokens API Bearer pour clients mobiles / intégrations.

Stockage : hash SHA-256 du token en DB. Le token clair n'est renvoyé qu'à la
création. Format de transport : Authorization: Bearer <token>.
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Optional

from flask import request, jsonify, g

from db import db_cursor


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


TOKEN_TTL_DAYS = 365  # 1 an de validité par défaut


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_token(user_id: int, device: str = "", platform: str = "") -> str:
    """Crée un nouveau token et retourne la valeur claire (à transmettre une fois)."""
    raw = "av_" + secrets.token_urlsafe(40)
    h = _hash(raw)
    expires = _utcnow() + timedelta(days=TOKEN_TTL_DAYS)
    with db_cursor(commit=True) as cur:
        cur.execute(
            """INSERT INTO api_tokens (user_id, token_hash, device, platform, expires_at)
               VALUES (%s, %s, %s, %s, %s)""",
            (user_id, h, device[:128], platform[:32], expires),
        )
    return raw


def revoke_token(token: str) -> bool:
    h = _hash(token)
    with db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM api_tokens WHERE token_hash = %s", (h,))
        return cur.rowcount > 0


def revoke_all_for_user(user_id: int) -> int:
    with db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM api_tokens WHERE user_id = %s", (user_id,))
        return cur.rowcount


def resolve_token(token: Optional[str]):
    """Renvoie (user_id, token_id) si valide, sinon (None, None)."""
    if not token:
        return None, None
    h = _hash(token)
    with db_cursor(commit=True) as cur:
        cur.execute(
            """SELECT id, user_id, expires_at FROM api_tokens
               WHERE token_hash = %s""",
            (h,),
        )
        row = cur.fetchone()
        if not row:
            return None, None
        if row["expires_at"] and row["expires_at"] < _utcnow():
            cur.execute("DELETE FROM api_tokens WHERE id = %s", (row["id"],))
            return None, None
        cur.execute(
            "UPDATE api_tokens SET last_used_at = CURRENT_TIMESTAMP WHERE id = %s",
            (row["id"],),
        )
        return row["user_id"], row["id"]


def _bearer():
    """Extrait le token Bearer de l'en-tête Authorization."""
    auth = request.headers.get("Authorization", "")
    if not auth.lower().startswith("bearer "):
        return None
    return auth.split(" ", 1)[1].strip()


def api_auth_required(f):
    """Décorateur : exige un token Bearer valide. Pose g.user_id."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        tok = _bearer()
        uid, _ = resolve_token(tok)
        if not uid:
            return jsonify({"error": "non authentifié"}), 401
        g.user_id = uid
        return f(*args, **kwargs)
    return wrapper


def api_auth_optional(f):
    """Décorateur : pose g.user_id si token valide, None sinon. Pas d'erreur."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        tok = _bearer()
        uid, _ = resolve_token(tok)
        g.user_id = uid
        return f(*args, **kwargs)
    return wrapper


def list_tokens(user_id: int):
    with db_cursor() as cur:
        cur.execute(
            """SELECT id, device, platform, created_at, last_used_at, expires_at
               FROM api_tokens WHERE user_id = %s
               ORDER BY last_used_at DESC NULLS LAST, created_at DESC""",
            (user_id,),
        )
        return cur.fetchall()
