"""SSO AubeMail — authentifie un compte AubeVideo avec ses identifiants AubeMail.

Lecture seule sur la base `aubemail_db` (table `aubemail_users`, mots de passe
bcrypt). Activé via AUBEMAIL_SSO=1. Silencieux/désactivé si la base ou bcrypt
sont absents (ex. déploiement cloud sans l'écosystème).
"""
import os
import psycopg2
import psycopg2.extras

try:
    import bcrypt
    _BCRYPT = True
except Exception:
    _BCRYPT = False

ENABLED = os.environ.get("AUBEMAIL_SSO", "0") == "1"

# La base AubeMail tourne sur le même PostgreSQL ; on réutilise les identifiants
# AubeVideo (à qui on a accordé SELECT sur aubemail_users).
_DB = {
    "dbname": os.environ.get("AUBEMAIL_DB", "aubemail_db"),
    "user": os.environ.get("AUBEVIDEO_DB_USER", "aubevideo_user"),
    "password": os.environ.get("AUBEVIDEO_DB_PASS", ""),
    "host": os.environ.get("AUBEVIDEO_DB_HOST", "127.0.0.1"),
    "port": int(os.environ.get("AUBEVIDEO_DB_PORT", "5432")),
}


def available() -> bool:
    return ENABLED and _BCRYPT


def authenticate(email, password):
    """Vérifie un compte AubeMail. Renvoie un dict (email, display_name,
    avatar_url) si OK, sinon None. Jamais d'exception propagée."""
    if not available():
        return None
    email = (email or "").strip().lower()
    if "@" not in email or not password:
        return None
    try:
        conn = psycopg2.connect(**_DB)
    except Exception:
        return None
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """SELECT email, password_hash, display_name, avatar_url,
                          COALESCE(is_active, TRUE) AS is_active
                   FROM aubemail_users WHERE LOWER(email) = %s LIMIT 1""",
                (email,),
            )
            row = cur.fetchone()
    except Exception:
        return None
    finally:
        conn.close()

    if not row or not row.get("password_hash") or not row.get("is_active"):
        return None
    pw_hash = row["password_hash"]
    try:
        if not bcrypt.checkpw(password.encode("utf-8"), pw_hash.encode("utf-8")):
            return None
    except Exception:
        return None
    return {
        "email": row["email"].lower(),
        "display_name": row.get("display_name") or row["email"].split("@")[0],
        "avatar_url": row.get("avatar_url") or "",
    }
