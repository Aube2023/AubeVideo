"""AubeVideo - sécurité (CSRF, rate limit, headers, limites de tentatives)."""
import os
import hmac
import hashlib
import secrets
import time
from functools import wraps
from collections import deque, defaultdict
from flask import session, request, abort, jsonify

CSRF_KEY = os.environ.get("AUBEVIDEO_CSRF_KEY", "change-me-csrf-" + secrets.token_hex(16))

# Rate limit en mémoire (suffit pour un seul worker — pour multi-worker utiliser Redis)
_rate_store = defaultdict(deque)

_LOGIN_ATTEMPTS = defaultdict(deque)


def generate_csrf_token() -> str:
    """Génère (ou récupère) le token CSRF stocké en session."""
    token = session.get("_csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf"] = token
    return token


def validate_csrf_token(token: str) -> bool:
    expected = session.get("_csrf")
    if not expected or not token:
        return False
    return hmac.compare_digest(expected, token)


def csrf_protect(app):
    """Active la protection CSRF sur les méthodes à effet de bord."""
    @app.before_request
    def _check_csrf():
        if request.method in ("GET", "HEAD", "OPTIONS", "TRACE"):
            return
        # Les endpoints de stream/thumb sont en GET donc OK.
        # Upload POST multipart -> token via form
        # JSON API -> token via header
        token = (request.form.get("_csrf")
                 or request.headers.get("X-CSRF-Token")
                 or request.headers.get("X-CSRFToken"))
        if not validate_csrf_token(token):
            if request.path.startswith("/api/"):
                return jsonify({"error": "jeton CSRF invalide"}), 403
            abort(403, description="Jeton CSRF invalide.")

    @app.context_processor
    def _inject_csrf():
        return {"csrf_token": generate_csrf_token}


def rate_limit(limit: int = 60, window: int = 60, per: str = "user"):
    """Décorateur : limit requêtes par fenêtre (secondes). Clé = user_id ou IP."""
    def deco(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            now = time.time()
            if per == "user":
                key = session.get("user_id") or request.remote_addr or "anon"
            else:
                key = request.remote_addr or "anon"
            key = f"{f.__name__}:{key}"
            q = _rate_store[key]
            while q and now - q[0] > window:
                q.popleft()
            if len(q) >= limit:
                return jsonify({
                    "error": "trop de requêtes, réessayez plus tard",
                    "retry_after": int(window - (now - q[0])),
                }), 429
            q.append(now)
            return f(*args, **kwargs)
        return wrapped
    return deco


def throttle_login(username: str, max_attempts: int = 10, window: int = 300) -> bool:
    """True si on autorise la tentative, False si bloqué."""
    now = time.time()
    key = f"login:{username}:{request.remote_addr}"
    q = _LOGIN_ATTEMPTS[key]
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= max_attempts:
        return False
    q.append(now)
    return True


def security_headers(app):
    """Ajoute les headers de sécurité à toutes les réponses."""
    csp = (
        "default-src 'self'; "
        "img-src 'self' data: https:; "
        "media-src 'self' blob:; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )

    @app.after_request
    def _apply(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault("Permissions-Policy",
                                 "camera=(), microphone=(), geolocation=()")
        # Embeds: autorise l'iframe externe (pas de X-Frame / CSP frame-ancestors libre)
        is_embed = request.path.startswith("/embed/")
        if not is_embed:
            resp.headers.setdefault("X-Frame-Options", "DENY")
            resp.headers.setdefault("Content-Security-Policy", csp)
        else:
            resp.headers.setdefault("Content-Security-Policy", "frame-ancestors *")
        if request.is_secure or request.headers.get("X-Forwarded-Proto") == "https":
            resp.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return resp


def configure_session(app):
    """Durcit la configuration de session Flask."""
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("AUBEVIDEO_HTTPS", "0") == "1",
        PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 30,  # 30 jours
    )
