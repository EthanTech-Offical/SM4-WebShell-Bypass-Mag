"""v2 authenticated envelope.

    blob = iv(16) || ts(4, BE) || nonce(8) || ciphertext || tag(32)

* ``iv``       random per request, never reused
* ``ts``       freshness, server rejects outside the skew window
* ``nonce``    replay cache key on the server
* ``tag``      HMAC-SHA256(mac_key, iv || ts || nonce || ciphertext)

The timestamp and nonce are covered by the MAC, so they are authenticated even
though they travel in clear.  Encryption is SM4-CBC with PKCS#7; the classic
"no integrity, fixed IV" problems of v1 disappear.
"""

from __future__ import annotations

import hmac
import os
import struct
import time

from . import kdf, sm4

IV_LEN = 16
TS_LEN = 4
NONCE_LEN = 8
TAG_LEN = 32
HEADER_LEN = IV_LEN + TS_LEN + NONCE_LEN
MIN_LEN = HEADER_LEN + sm4.BLOCK_SIZE + TAG_LEN
MAX_SKEW = 300
_DEFAULT_PAD_BUCKETS = (512, 1024, 2048, 4096, 8192, 16384)


class EnvelopeError(ValueError):
    pass


class BadTag(EnvelopeError):
    pass


class Expired(EnvelopeError):
    pass


def keys_for(secret_hex: str, salt_hex: str) -> tuple[bytes, bytes]:
    return kdf.derive(secret_hex, salt_hex)


def _tag(mac_key: bytes, header: bytes, cipher: bytes) -> bytes:
    return hmac.new(mac_key, header + cipher, "sha256").digest()


def seal(
    plaintext: bytes,
    secret_hex: str,
    salt_hex: str,
    *,
    ts: int | None = None,
    nonce: bytes | None = None,
    iv: bytes | None = None,
) -> bytes:
    enc_key, mac_key = keys_for(secret_hex, salt_hex)
    iv = iv or os.urandom(IV_LEN)
    ts = int(time.time()) if ts is None else int(ts)
    nonce = nonce or os.urandom(NONCE_LEN)
    if len(iv) != IV_LEN or len(nonce) != NONCE_LEN:
        raise EnvelopeError("iv/nonce length mismatch")
    header = iv + struct.pack(">I", ts & 0xFFFFFFFF) + nonce
    cipher = sm4.cbc_encrypt(plaintext, enc_key, iv)
    tag = _tag(mac_key, header, cipher)
    return header + cipher + tag


def open_(
    blob: bytes,
    secret_hex: str,
    salt_hex: str,
    *,
    now: float | None = None,
    skew: int = MAX_SKEW,
    expected_ts: int | None = None,
) -> bytes:
    if len(blob) < MIN_LEN:
        raise EnvelopeError("blob too short")
    iv = blob[:IV_LEN]
    ts = struct.unpack(">I", blob[IV_LEN:HEADER_LEN - NONCE_LEN])[0]
    nonce = blob[HEADER_LEN - NONCE_LEN:HEADER_LEN]
    tag = blob[-TAG_LEN:]
    cipher = blob[HEADER_LEN:-TAG_LEN]
    if not cipher or len(cipher) % sm4.BLOCK_SIZE:
        raise EnvelopeError("ciphertext is not block aligned")

    enc_key, mac_key = keys_for(secret_hex, salt_hex)
    expected = _tag(mac_key, blob[:HEADER_LEN], cipher)
    if not hmac.compare_digest(expected, tag):
        raise BadTag("HMAC mismatch")

    current = time.time() if now is None else now
    if skew > 0 and abs(current - ts) > skew:
        raise Expired(f"timestamp outside ±{skew}s window")
    if expected_ts is not None and ts != expected_ts:
        raise Expired("timestamp does not match the request")

    return sm4.cbc_decrypt(cipher, enc_key, iv)


def maybe_pad(payload: dict, buckets: tuple[int, ...] | None = _DEFAULT_PAD_BUCKETS) -> dict:
    """Grow the JSON payload with random filler so ciphertexts hit a common size.

    Random padding removes the "request size maps 1:1 to the command" side
    channel used by traffic baselines, without changing the protocol.
    """
    if not buckets:
        return payload
    import json

    def size(d: dict) -> int:
        return len(json.dumps(d, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))

    current = size(payload)
    for bucket in buckets:
        if current >= bucket:
            continue
        # inserted text is  ,"pd":"<filler>"  -> 8 chars of framing + the filler
        need = bucket - current - 8
        if need < 8:
            continue
        raw_len = (need * 3 + 3) // 4  # base64 grows 4 chars per 3 bytes
        pad = os.urandom(raw_len)
        import base64 as _b64

        payload["pd"] = _b64.b64encode(pad).decode("ascii")
        if size(payload) >= bucket:
            break
        payload.pop("pd", None)
    return payload


def strip_padding(payload: dict) -> dict:
    payload.pop("pd", None)
    return payload


def parse_header(blob: bytes) -> dict[str, object]:
    if len(blob) < MIN_LEN:
        raise EnvelopeError("blob too short")
    return {
        "iv": blob[:IV_LEN].hex(),
        "ts": struct.unpack(">I", blob[IV_LEN:HEADER_LEN - NONCE_LEN])[0],
        "nonce": blob[HEADER_LEN - NONCE_LEN:HEADER_LEN].hex(),
        "size": len(blob),
    }
