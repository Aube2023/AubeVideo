"""AubeVideo - gestionnaire de connexion PostgreSQL."""
import os
import psycopg2
import psycopg2.extras
from contextlib import contextmanager

DB_NAME = os.environ.get("AUBEVIDEO_DB", "aubevideo")
DB_USER = os.environ.get("AUBEVIDEO_DB_USER", "aubevideo_user")
DB_PASS = os.environ.get("AUBEVIDEO_DB_PASS", "aubevideo_pass")
DB_HOST = os.environ.get("AUBEVIDEO_DB_HOST", "localhost")
DB_PORT = int(os.environ.get("AUBEVIDEO_DB_PORT", "5432"))


def get_connection():
    return psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        host=DB_HOST,
        port=DB_PORT,
    )


@contextmanager
def db_cursor(commit=False, dict_cursor=True):
    conn = get_connection()
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
