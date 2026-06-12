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


def presence_touch(key, member, window=30):
    """Marque `member` présent et renvoie le nombre de présents.

    Fenêtre glissante : un membre compte tant qu'il s'est manifesté il y a
    moins de `window` secondes (sorted set Redis, dict en fallback mémoire).
    """
    key = _PREFIX + key
    now = time.time()
    if _REDIS_OK:
        try:
            p = _r.pipeline()
            p.zadd(key, {str(member): now})
            p.zremrangebyscore(key, "-inf", now - window)
            p.zcard(key)
            p.expire(key, window * 2)
            return p.execute()[2]
        except Exception:
            pass
    with _lock:
        ent = _mem.setdefault(key, {"v": {}, "exp": now + window * 2})
        ent["v"] = {m: t for m, t in ent["v"].items() if t > now - window}
        ent["v"][str(member)] = now
        ent["exp"] = now + window * 2
        return len(ent["v"])


def presence_count(key, window=30):
    """Nombre de présents, sans se marquer soi-même présent."""
    key = _PREFIX + key
    now = time.time()
    if _REDIS_OK:
        try:
            _r.zremrangebyscore(key, "-inf", now - window)
            return _r.zcard(key)
        except Exception:
            return 0
    with _lock:
        ent = _mem.get(key)
        if not ent:
            return 0
        return sum(1 for t in ent["v"].values() if t > now - window)


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
