"""Encrypted-at-rest store for shell profiles.

A shell profile contains the SM4 secret — leaving it in plaintext JSON means
anyone who reads ``~/.webshell-mag/shells.json`` owns every shell.

Format (JSON):

    {
      "wsm": 1,
      "kdf": {"algo": "pbkdf2-sha256", "iter": 210000, "salt": "<hex>"},
      "iv": "<hex>",
      "ct": "<base64>",
      "mac": "<hex>"
    }

Keys: PBKDF2-HMAC-SHA256(passphrase, salt, 210k) -> 48 bytes
      enc_key = okm[:16] (SM4-128), mac_key = okm[16:]
Body: SM4-CBC(PKCS#7) with a random IV, authenticated with
      HMAC-SHA256(mac_key, header || iv || ct).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from typing import Any

from .crypto import sm4

MAGIC = b"WSM\x01"
DEFAULT_ITERATIONS = 210_000
HEADER = b"wshell-mag/store/v1"


class StoreError(Exception):
    pass


class StoreLocked(StoreError):
    """Wrong or missing passphrase."""


@dataclass
class KdfParams:
    algo: str = "pbkdf2-sha256"
    iterations: int = DEFAULT_ITERATIONS
    salt: bytes = b""

    def to_dict(self) -> dict[str, Any]:
        return {"algo": self.algo, "iter": self.iterations, "salt": self.salt.hex()}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KdfParams":
        return cls(
            algo=str(data.get("algo", "pbkdf2-sha256")),
            iterations=int(data.get("iter", DEFAULT_ITERATIONS)),
            salt=bytes.fromhex(str(data.get("salt", ""))),
        )


def derive(passphrase: str, params: KdfParams) -> tuple[bytes, bytes]:
    if not passphrase:
        raise StoreError("empty passphrase")
    okm = hashlib.pbkdf2_hmac(
        "sha256", passphrase.encode("utf-8"), params.salt, params.iterations, dklen=48
    )
    return okm[:16], okm[16:]


def encrypt_json(obj: Any, passphrase: str, iterations: int = DEFAULT_ITERATIONS) -> dict[str, Any]:
    params = KdfParams(iterations=iterations, salt=os.urandom(16))
    enc_key, mac_key = derive(passphrase, params)
    plain = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    iv = os.urandom(16)
    ct = sm4.cbc_encrypt(plain, enc_key, iv)
    mac = hmac.new(mac_key, HEADER + iv + ct, hashlib.sha256).digest()
    return {
        "wsm": 1,
        "kdf": params.to_dict(),
        "iv": iv.hex(),
        "ct": base64.b64encode(ct).decode("ascii"),
        "mac": mac.hex(),
    }


def decrypt_json(blob: dict[str, Any], passphrase: str) -> Any:
    try:
        if int(blob.get("wsm", 0)) != 1:
            raise StoreError("unsupported store version")
        params = KdfParams.from_dict(blob.get("kdf") or {})
        iv = bytes.fromhex(str(blob["iv"]))
        ct = base64.b64decode(str(blob["ct"]))
        mac = bytes.fromhex(str(blob["mac"]))
    except (KeyError, ValueError, TypeError) as exc:
        raise StoreError(f"malformed store file: {exc}") from exc
    if len(iv) != 16 or not ct:
        raise StoreError("malformed store file")

    enc_key, mac_key = derive(passphrase, params)
    expected = hmac.new(mac_key, HEADER + iv + ct, hashlib.sha256).digest()
    if not hmac.compare_digest(expected, mac):
        raise StoreLocked("wrong passphrase (or corrupted store)")
    try:
        plain = sm4.cbc_decrypt(ct, enc_key, iv)
    except sm4.SM4Error as exc:
        raise StoreLocked("wrong passphrase (or corrupted store)") from exc
    try:
        return json.loads(plain.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StoreError("store payload is not valid JSON") from exc


def is_encrypted(raw: bytes) -> bool:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    return isinstance(data, dict) and int(data.get("wsm", 0)) == 1
