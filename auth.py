"""AubeVideo - Authentification.

Deux modes complémentaires :
  1. Inscription self-service email + mot de passe (hashé, comme YouTube).
  2. SSO PAM partagé de l'écosystème L'Aube Étoilée (fallback, si dispo).

Ne JAMAIS reset les mots de passe Linux : l'auth PAM est partagée entre
AubeMail, AubeDocs, AubeDrive, AubeData, AubeCRM, AubeDriver, AubeNews, AubeVideo.
"""
import os
import re
from functools import wraps
from flask import session, redirect, url_for, jsonify, request, abort
from werkzeug.security import generate_password_hash, check_password_hash

from db import db_cursor
import aubemail_sso

DEV_MODE = os.environ.get("AUBEVIDEO_DEV_MODE", "0") == "1"
# Autoriser le fallback PAM (SSO écosystème). Désactivé par défaut en prod cloud.
PAM_LOGIN_ENABLED = os.environ.get("AUBEVIDEO_PAM_LOGIN", "1") == "1"

USERNAME_RE = re.compile(r"^[a-z0-9_]{3,30}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

try:
    import pam
    _PAM = pam.pam()
    PAM_AVAILABLE = True
except Exception:
    _PAM = None
    PAM_AVAILABLE = False


# ---------- Inscription / mot de passe local ----------
def normalize_username(username: str) -> str:
    return (username or "").strip().lower()


def validate_registration(username, email, password):
    """Renvoie (ok, message_erreur). Validation des champs d'inscription."""
    username = normalize_username(username)
    email = (email or "").strip().lower()
    if not USERNAME_RE.match(username):
        return False, ("Le nom d'utilisateur doit faire 3 à 30 caractères "
                       "(lettres minuscules, chiffres, _).")
    if not EMAIL_RE.match(email):
        return False, "Adresse e-mail invalide."
    if len(password or "") < 8:
        return False, "Le mot de passe doit faire au moins 8 caractères."
    return True, ""


def register_user(username, email, password, display_name=None):
    """Crée un compte local. Renvoie (user_id, None) ou (None, message_erreur)."""
    username = normalize_username(username)
    email = (email or "").strip().lower()
    ok, err = validate_registration(username, email, password)
    if not ok:
        return None, err
    pw_hash = generate_password_hash(password)
    with db_cursor(commit=True) as cur:
        cur.execute("SELECT 1 FROM users WHERE LOWER(username) = %s", (username,))
        if cur.fetchone():
            return None, "Ce nom d'utilisateur est déjà pris."
        cur.execute("SELECT 1 FROM users WHERE LOWER(email) = %s", (email,))
        if cur.fetchone():
            return None, "Un compte existe déjà avec cet e-mail."
        cur.execute(
            """INSERT INTO users (username, display_name, email, password_hash)
               VALUES (%s, %s, %s, %s) RETURNING id""",
            (username, display_name or username, email, pw_hash),
        )
        return cur.fetchone()["id"], None


def authenticate_local(identifier, password):
    """Vérifie un login email/username + mot de passe local.

    Renvoie le dict user (id, username, is_banned, totp_enabled) si OK, sinon None.
    """
    if not identifier or not password:
        return None
    identifier = identifier.strip().lower()
    with db_cursor() as cur:
        cur.execute(
            """SELECT id, username, password_hash, is_banned, totp_enabled
               FROM users
               WHERE LOWER(username) = %s OR LOWER(email) = %s
               LIMIT 1""",
            (identifier, identifier),
        )
        row = cur.fetchone()
    if not row or not row["password_hash"]:
        # check_password_hash sur un faux hash pour limiter l'oracle temporel.
        check_password_hash(
            "pbkdf2:sha256:600000$x$0000000000000000000000000000000000000000"
            "000000000000000000000000", password)
        return None
    if not check_password_hash(row["password_hash"], password):
        return None
    return dict(row)


def set_password(user_id, password):
    """Définit/réinitialise le mot de passe local d'un utilisateur."""
    if len(password or "") < 8:
        return False, "Le mot de passe doit faire au moins 8 caractères."
    with db_cursor(commit=True) as cur:
        cur.execute("UPDATE users SET password_hash = %s WHERE id = %s",
                    (generate_password_hash(password), user_id))
    return True, ""


# ---------- SSO AubeMail (identité partagée de l'écosystème) ----------
def _unique_username(cur, base):
    """Dérive un nom d'utilisateur valide et unique depuis un email/nom."""
    base = re.sub(r"[^a-z0-9_]", "_", (base or "").lower()).strip("_")
    if len(base) < 3:
        base = base + "user"
    base = base[:24] or "user"
    candidate, i = base, 1
    while True:
        cur.execute("SELECT 1 FROM users WHERE LOWER(username) = %s", (candidate,))
        if not cur.fetchone():
            return candidate
        i += 1
        candidate = f"{base}{i}"[:30]


def authenticate_aubemail(identifier, password):
    """Login via un compte AubeMail. Provisionne/relie le compte AubeVideo
    (par email) à la première connexion. Renvoie un dict user ou None."""
    am = aubemail_sso.authenticate(identifier, password)
    if not am:
        return None
    with db_cursor(commit=True) as cur:
        cur.execute(
            "SELECT id, username, is_banned, totp_enabled FROM users WHERE LOWER(email) = %s LIMIT 1",
            (am["email"],),
        )
        row = cur.fetchone()
        if not row:
            username = _unique_username(cur, am["email"].split("@")[0])
            cur.execute(
                """INSERT INTO users (username, display_name, email, avatar_url)
                   VALUES (%s, %s, %s, %s)
                   RETURNING id, username, is_banned, totp_enabled""",
                (username, am.get("display_name") or username,
                 am["email"], am.get("avatar_url") or ""),
            )
            row = cur.fetchone()
    return dict(row)


# ---------- PAM (SSO écosystème, fallback) ----------
def pam_authenticate(username: str, password: str) -> bool:
    """Vérifie les credentials via PAM (user Linux système).

    En DEV_MODE (AUBEVIDEO_DEV_MODE=1) : accepte n'importe quel user/mdp
    non vides — pour tests locaux macOS sans PAM système.
    """
    if not username or not password:
        return False
    if not PAM_LOGIN_ENABLED:
        return False
    if DEV_MODE:
        return True
    if not PAM_AVAILABLE:
        return False
    try:
        return bool(_PAM.authenticate(username, password, service="login"))
    except Exception:
        return False


# ---------- Session / autorisations ----------
def current_user():
    """Retourne le dict user en session ou None."""
    uid = session.get("user_id")
    if not uid:
        return None
    return {
        "id": uid,
        "username": session.get("username"),
        "display_name": session.get("display_name"),
    }


def is_admin(uid=None) -> bool:
    """Vrai si l'utilisateur est admin.

    Pour l'utilisateur courant (uid omis ou == session) : lit le cache session.
    Pour un autre uid : interroge la DB sans toucher au cache (sinon on
    écraserait le statut du user connecté avec celui d'un autre).
    """
    session_uid = session.get("user_id")
    if uid is None:
        uid = session_uid
    if not uid:
        return False
    if uid == session_uid and "is_admin" in session:
        return bool(session["is_admin"])
    with db_cursor() as cur:
        cur.execute("SELECT is_admin FROM users WHERE id = %s", (uid,))
        r = cur.fetchone()
    val = bool(r and r["is_admin"])
    if uid == session_uid:
        session["is_admin"] = val
    return val


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "authentification requise"}), 401
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    """login_required + is_admin. Renvoie 403 sinon."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login", next=request.path))
        if not is_admin():
            abort(403)
        return f(*args, **kwargs)
    return wrapper
