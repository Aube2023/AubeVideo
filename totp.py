"""2FA TOTP (RFC 6238) — sans dépendance externe."""
import os
import hmac
import hashlib
import struct
import time
import base64
import secrets
from urllib.parse import quote


def generate_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def totp(secret: str, step: int = 30, digits: int = 6, t: float = None) -> str:
    """Calcule le code TOTP pour l'instant t (par défaut maintenant)."""
    key = base64.b32decode(secret + "=" * ((8 - len(secret) % 8) % 8))
    counter = int((t or time.time()) // step)
    msg = struct.pack(">Q", counter)
    h = hmac.new(key, msg, hashlib.sha1).digest()
    o = h[-1] & 0x0F
    code = (struct.unpack(">I", h[o:o+4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(code).zfill(digits)


def verify(secret: str, code: str, window: int = 1) -> bool:
    """Vérifie avec tolérance de ±window * 30s."""
    if not code or not secret or not code.isdigit():
        return False
    now = time.time()
    for w in range(-window, window + 1):
        if hmac.compare_digest(totp(secret, t=now + w * 30), code):
            return True
    return False


def provisioning_uri(secret: str, account: str, issuer: str = "AubeVideo") -> str:
    label = f"{issuer}:{account}"
    params = f"secret={secret}&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30"
    return f"otpauth://totp/{quote(label)}?{params}"
