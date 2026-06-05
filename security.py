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

# Rate limit : Redis si disponible (partagé entre workers), sinon mémoire (fallback).
_rate_store = defaultdict(deque)
_LOGIN_ATTEMPTS = defaultdict(deque)

try:
    import redis as _redis_lib
    _REDIS_URL = os.environ.get("REDIS_URL", "").strip()
    _redis = _redis_lib.from_url(_REDIS_URL) if _REDIS_URL else None
    if _redis is not None:
        _redis.ping()
except Exception:
    _redis = None


def _sliding_window_hit(key, limit, window):
    """Fenêtre glissante. Renvoie (bloqué: bool, retry_after: int).

    Utilise Redis (ZSET) si dispo pour un comptage partagé entre workers,
    sinon retombe sur un deque en mémoire (par worker).
    """
    now = time.time()
    if _redis is not None:
        try:
            member = f"{now:.6f}-{secrets.token_hex(4)}"
            p = _redis.pipeline()
            p.zremrangebyscore(key, 0, now - window)
            p.zadd(key, {member: now})
            p.zcard(key)
            p.expire(key, int(window) + 1)
            _, _, count, _ = p.execute()
            if count > limit:
                oldest = _redis.zrange(key, 0, 0, withscores=True)
                ra = int(oldest[0][1] + window - now) if oldest else int(window)
                return True, max(1, ra)
            return False, 0
        except Exception:
            pass  # Redis indisponible -> fallback mémoire
    q = _rate_store[key]
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= limit:
        return True, int(window - (now - q[0]))
    q.append(now)
    return False, 0


def generate_csrf_token() -> str:
    """Génère (ou récupère) le token CSRF stocké en session."""
    token = session.get("_csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf"] = token
    return token


def validate_csrf_token(token) -> bool:
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
        # API v1 mobile/SPA : authentification Bearer => pas de CSRF
        # (les tokens API ne sont pas transmis automatiquement par le navigateur)
        if request.path.startswith("/api/v1/") and \
           request.headers.get("Authorization", "").lower().startswith("bearer "):
            return
        # Endpoint de login API : pas de session => pas de CSRF non plus
        if request.path == "/api/v1/auth/login":
            return
        # Stripe webhook signé : pas de CSRF (vérification dédiée côté handler)
        if request.path == "/stripe/webhook":
            return
        # Les endpoints de stream/thumb sont en GET donc OK.
        # Upload POST multipart -> token via form
        # JSON API session -> token via header
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
            if per == "user":
                who = session.get("user_id") or request.remote_addr or "anon"
            else:
                who = request.remote_addr or "anon"
            key = f"rl:{f.__name__}:{who}"
            blocked, retry_after = _sliding_window_hit(key, limit, window)
            if blocked:
                return jsonify({
                    "error": "trop de requêtes, réessayez plus tard",
                    "retry_after": retry_after,
                }), 429
            return f(*args, **kwargs)
        return wrapped
    return deco


def throttle_login(username: str, max_attempts: int = 10, window: int = 300) -> bool:
    """True si on autorise la tentative, False si bloqué."""
    key = f"login:{username}:{request.remote_addr}"
    blocked, _ = _sliding_window_hit(key, max_attempts, window)
    return not blocked


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
    allowed_origins = os.environ.get(
        "AUBEVIDEO_CORS_ORIGINS", "*"
    ).split(",")

    @app.after_request
    def _apply(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault("Permissions-Policy",
                                 "camera=(), microphone=(), geolocation=()")
        # Embeds: autorise l'iframe externe (pas de X-Frame / CSP frame-ancestors libre)
        is_embed = request.path.startswith("/embed/")
        is_api = request.path.startswith("/api/v1/")
        if is_embed:
            resp.headers.setdefault("Content-Security-Policy", "frame-ancestors *")
        elif is_api:
            # CORS pour clients mobiles / extensions / autres origines
            origin = request.headers.get("Origin", "")
            if "*" in allowed_origins or origin in allowed_origins:
                resp.headers.setdefault("Access-Control-Allow-Origin", origin or "*")
                resp.headers.setdefault("Vary", "Origin")
            resp.headers.setdefault("Access-Control-Allow-Headers",
                                    "Authorization, Content-Type, X-CSRF-Token")
            resp.headers.setdefault("Access-Control-Allow-Methods",
                                    "GET, POST, PUT, PATCH, DELETE, OPTIONS")
            resp.headers.setdefault("Access-Control-Max-Age", "86400")
        else:
            resp.headers.setdefault("X-Frame-Options", "DENY")
            resp.headers.setdefault("Content-Security-Policy", csp)
        if request.is_secure or request.headers.get("X-Forwarded-Proto") == "https":
            resp.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return resp

    @app.before_request
    def _cors_preflight():
        if request.method == "OPTIONS" and request.path.startswith("/api/v1/"):
            return ("", 204)


def configure_session(app):
    """Durcit la configuration de session Flask."""
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("AUBEVIDEO_HTTPS", "0") == "1",
        PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 30,  # 30 jours
    )
