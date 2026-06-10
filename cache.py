"""Cache (Redis si disponible, sinon mémoire)."""
import os
import time
import json
import threading

try:
    import redis
    _r = redis.Redis.from_url(
        os.environ.get("AUBEVIDEO_REDIS", "redis://localhost:6379/0"),
        socket_connect_timeout=1, decode_responses=True,
    )
    _r.ping()
    _REDIS_OK = True
except Exception:
    _r = None
    _REDIS_OK = False

_mem = {}
_lock = threading.Lock()

# Le Redis du serveur est partagé entre services : on namespace nos clés.
_PREFIX = os.environ.get("AUBEVIDEO_CACHE_PREFIX", "aubevideo:")


def get(key):
    key = _PREFIX + key
    if _REDIS_OK:
        try:
            v = _r.get(key)
            return json.loads(v) if v else None
        except Exception:
            return None
    with _lock:
        ent = _mem.get(key)
        if not ent:
            return None
        if ent["exp"] < time.time():
            _mem.pop(key, None)
            return None
        return ent["v"]


def set(key, value, ttl=60):
    key = _PREFIX + key
    if _REDIS_OK:
        try:
            _r.setex(key, ttl, json.dumps(value, default=str))
            return
        except Exception:
            pass
    with _lock:
        _mem[key] = {"v": value, "exp": time.time() + ttl}


def delete(key):
    key = _PREFIX + key
    if _REDIS_OK:
        try:
            _r.delete(key)
        except Exception:
            pass
    _mem.pop(key, None)


def cached(key_fn, ttl=60):
    def deco(f):
        def wrapper(*args, **kwargs):
            key = key_fn(*args, **kwargs)
            hit = get(key)
            if hit is not None:
                return hit
            val = f(*args, **kwargs)
            set(key, val, ttl)
            return val
        return wrapper
    return deco
