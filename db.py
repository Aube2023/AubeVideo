"""AubeVideo - gestionnaire de connexion PostgreSQL + helpers de requêtes communes."""
import os
import psycopg2
import psycopg2.extras
from contextlib import contextmanager

# DATABASE_URL prioritaire (Render / Railway / Fly / Heroku fournissent cette variable).
# Sinon on retombe sur les variables AUBEVIDEO_DB_*.
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

DB_NAME = os.environ.get("AUBEVIDEO_DB", "aubevideo")
DB_USER = os.environ.get("AUBEVIDEO_DB_USER", "aubevideo_user")
DB_PASS = os.environ.get("AUBEVIDEO_DB_PASS", "aubevideo_pass")
DB_HOST = os.environ.get("AUBEVIDEO_DB_HOST", "localhost")
DB_PORT = int(os.environ.get("AUBEVIDEO_DB_PORT", "5432"))

# SSL requis par la plupart des Postgres managés (Render, etc.). Désactivable en local.
DB_SSLMODE = os.environ.get("AUBEVIDEO_DB_SSLMODE", "" if not DATABASE_URL else "require")

VISIBILITIES = ("public", "unlisted", "private")


def normalize_visibility(value, default="public"):
    """Retourne `value` si valide, sinon `default`."""
    return value if value in VISIBILITIES else default


def get_connection():
    if DATABASE_URL:
        # psycopg2 accepte directement l'URL postgres://… (gère le SSL via sslmode).
        dsn = DATABASE_URL
        if "sslmode=" not in dsn and DB_SSLMODE:
            sep = "&" if "?" in dsn else "?"
            dsn = f"{dsn}{sep}sslmode={DB_SSLMODE}"
        return psycopg2.connect(dsn)
    kwargs = {
        "dbname": DB_NAME,
        "user": DB_USER,
        "host": DB_HOST,
        "port": DB_PORT,
    }
    if DB_PASS:
        kwargs["password"] = DB_PASS
    if DB_SSLMODE:
        kwargs["sslmode"] = DB_SSLMODE
    return psycopg2.connect(**kwargs)


@contextmanager
def db_cursor(commit=False, dict_cursor=True):
    conn = get_connection()
    cur = None
    try:
        cur = conn.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor if dict_cursor else None
        )
        yield cur
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        if cur is not None:
            cur.close()
        conn.close()


def init_db(schema_path="schema.sql"):
    with open(schema_path, "r", encoding="utf-8") as f:
        sql = f.read()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
    finally:
        conn.close()


def ensure_user(username, display_name=None, email=None):
    """Crée l'utilisateur dans la DB s'il n'existe pas (après auth PAM)."""
    with db_cursor(commit=True) as cur:
        cur.execute("SELECT id FROM users WHERE username = %s", (username,))
        row = cur.fetchone()
        if row:
            return row["id"]
        cur.execute(
            """INSERT INTO users (username, display_name, email)
               VALUES (%s, %s, %s) RETURNING id""",
            (username, display_name or username, email),
        )
        return cur.fetchone()["id"]


# ---------- Helpers vidéo (anti-duplication) ----------
_VIDEO_WITH_USER_SQL = """
    SELECT v.*, u.username, u.display_name, u.avatar_url,
           u.subscriber_count, u.bio
    FROM videos v JOIN users u ON v.user_id = u.id
    WHERE v.id = %s
"""


def fetch_video(cur, video_id, with_user=False, include_removed=False):
    """Charge une vidéo (avec ou sans jointure user). None si introuvable.

    `include_removed=False` filtre les vidéos modérées (is_removed = TRUE).
    """
    if with_user:
        sql = _VIDEO_WITH_USER_SQL
    else:
        sql = "SELECT * FROM videos WHERE id = %s"
    if not include_removed:
        sql += " AND v.is_removed = FALSE" if with_user else " AND is_removed = FALSE"
    cur.execute(sql, (video_id,))
    return cur.fetchone()
