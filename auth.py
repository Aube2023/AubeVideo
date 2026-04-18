"""AubeVideo - Authentification PAM partagée (SSO écosystème L'Aube Étoilée).

Ne JAMAIS reset les mots de passe Linux : auth partagée entre AubeMail,
AubeDocs, AubeDrive, AubeData, AubeCRM, AubeDriver, AubeNews, AubeVideo.
"""
from functools import wraps
from flask import session, redirect, url_for, jsonify, request

try:
    import pam
    _PAM = pam.pam()
    PAM_AVAILABLE = True
except Exception:
    _PAM = None
    PAM_AVAILABLE = False


def pam_authenticate(username: str, password: str) -> bool:
    """Vérifie les credentials via PAM (user Linux système)."""
    if not PAM_AVAILABLE or not username or not password:
        return False
    try:
        return bool(_PAM.authenticate(username, password, service="login"))
    except Exception:
        return False


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


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "authentification requise"}), 401
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return wrapper
