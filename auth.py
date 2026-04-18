"""AubeVideo - Authentification PAM partagée (SSO écosystème L'Aube Étoilée).

Ne JAMAIS reset les mots de passe Linux : auth partagée entre AubeMail,
AubeDocs, AubeDrive, AubeData, AubeCRM, AubeDriver, AubeNews, AubeVideo.
"""
import os
from functools import wraps
from flask import session, redirect, url_for, jsonify, request

DEV_MODE = os.environ.get("AUBEVIDEO_DEV_MODE", "0") == "1"

try:
    import pam
    _PAM = pam.pam()
    PAM_AVAILABLE = True
except Exception:
    _PAM = None
    PAM_AVAILABLE = False


def pam_authenticate(username: str, password: str) -> bool:
    """Vérifie les credentials via PAM (user Linux système).

    En DEV_MODE (AUBEVIDEO_DEV_MODE=1) : accepte n'importe quel user/mdp
    non vides — pour tests locaux macOS sans PAM système.
    """
    if not username or not password:
        return False
    if DEV_MODE:
        return True
    if not PAM_AVAILABLE:
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
