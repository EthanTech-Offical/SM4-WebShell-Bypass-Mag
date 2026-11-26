"""Best-effort text decoding for shell output.

Windows targets often emit GBK/CP936 while the GUI renders UTF-8.  The PHP
payload normalises command output already; this helper covers raw byte paths
(stream output, downloaded text) where no JSON string conversion happened.
"""

from __future__ import annotations

FALLBACKS = ("utf-8", "gb18030", "big5", "shift_jis", "latin-1")


def decode_bytes(data: bytes, charset: str = "utf-8") -> str:
    if not data:
        return ""
    order = [charset] if charset else []
    order += [enc for enc in FALLBACKS if enc != charset]
    for encoding in order:
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", "replace")
