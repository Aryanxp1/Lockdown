"""Password hashing, session tokens, signatures and rate limiting.

Standard library only. Passwords use scrypt when the local OpenSSL supports it
and PBKDF2-HMAC-SHA256 otherwise, both with a per-user random salt. Nothing in
the portal stores or logs a password or a raw session token.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from . import config, db

# --- passwords ----------------------------------------------------------

_PBKDF2 = "pbkdf2-sha256"
_SCRYPT = "scrypt"


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    encoded = _scrypt_hash(password, salt)
    if encoded is None:
        encoded = _pbkdf2_hash(password, salt)
    return encoded


def _scrypt_hash(password: str, salt: bytes) -> str | None:
    try:
        digest = hashlib.scrypt(password.encode("utf-8"), salt=salt,
                                n=config.SCRYPT_N, r=8, p=1, dklen=32)
    except (ValueError, AttributeError, TypeError):
        return None
    return "%s$%d$%s$%s" % (_SCRYPT, config.SCRYPT_N, salt.hex(), digest.hex())


def _pbkdf2_hash(password: str, salt: bytes) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt,
                                 config.PBKDF2_ITERATIONS, dklen=32)
    return "%s$%d$%s$%s" % (_PBKDF2, config.PBKDF2_ITERATIONS, salt.hex(), digest.hex())


def verify_password(stored: str | None, password: str) -> bool:
    if not stored or not password:
        return False
    try:
        scheme, iterations, salt_hex, digest_hex = stored.split("$", 3)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
        if scheme == _SCRYPT:
            candidate = hashlib.scrypt(password.encode("utf-8"), salt=salt,
                                       n=int(iterations), r=8, p=1, dklen=len(expected))
        elif scheme == _PBKDF2:
            candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt,
                                            int(iterations), dklen=len(expected))
        else:
            return False
    except (ValueError, TypeError, AttributeError):
        return False
    return hmac.compare_digest(candidate, expected)


# --- tokens and signatures ---------------------------------------------

def random_token(nbytes: int = 24) -> str:
    return secrets.token_urlsafe(nbytes)


def token_hash(token: str) -> str:
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def constant_time_eq(left: str, right: str) -> bool:
    return hmac.compare_digest((left or "").encode("utf-8"), (right or "").encode("utf-8"))


def portal_secret() -> str:
    """Server secret, generated once and persisted so signatures stay valid."""
    secret = db.setting("portal_secret")
    if not secret:
        secret = secrets.token_hex(32)
        db.set_setting("portal_secret", secret)
    return secret


def sign(message: str, secret: str | None = None, prefix: str = "") -> str:
    key = (secret or portal_secret()).encode("utf-8")
    digest = hmac.new(key, message.encode("utf-8"), hashlib.sha256).hexdigest()
    return (prefix + digest) if prefix else digest


def verify_signature(message: str, signature: str, secret: str | None = None) -> bool:
    return constant_time_eq(sign(message, secret), signature or "")


def short_code(payload: str, length: int = 12) -> str:
    """A short, checkable code (certificates, review receipts)."""
    digest = hashlib.sha256((payload + portal_secret()).encode("utf-8")).hexdigest()
    return digest[:length].upper()


# --- rate limiting ------------------------------------------------------

def rate_limit(bucket: str, limit: int, window_seconds: int) -> tuple[bool, int]:
    """Fixed-window limiter in SQLite. Returns (allowed, remaining)."""
    from .timeutil import now, now_iso
    stamp = now()
    window = int(stamp.timestamp()) // max(1, window_seconds) * max(1, window_seconds)
    from .timeutil import iso
    import datetime as _dt
    window_start = iso(_dt.datetime.fromtimestamp(window, _dt.timezone.utc))
    with db.tx():
        row = db.one("SELECT hits FROM rate_limits WHERE bucket = ? AND window_start = ?",
                     (bucket, window_start))
        hits = row["hits"] if row else 0
        if hits >= limit:
            return False, 0
        if row:
            db.update("rate_limits", {"hits": hits + 1, "last_at": now_iso()},
                      "bucket = ? AND window_start = ?", (bucket, window_start))
        else:
            db.insert("rate_limits", {"bucket": bucket, "window_start": window_start,
                                      "hits": 1, "first_at": now_iso(), "last_at": now_iso()})
    return True, max(0, limit - hits - 1)


def ip_hash(ip: str) -> str:
    return sign("ip:" + (ip or "0.0.0.0"))[:24]
