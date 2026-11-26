"""Persistent shell profiles.

Profiles live in ``$WEBSHELL_MAG_HOME`` (default ``~/.webshell-mag``), with a
project-local fallback when the home directory is not writable.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from . import secure


def config_home() -> Path:
    override = os.environ.get("WEBSHELL_MAG_HOME")
    if override:
        path = Path(override).expanduser()
    else:
        path = Path.home() / ".webshell-mag"
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return path
    except OSError:
        fallback = Path.cwd() / ".webshell-mag"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


@dataclass
class ShellConfig:
    """Everything needed to talk to one remote shell."""

    name: str = "new-shell"
    url: str = "http://127.0.0.1/shell.php"
    proto: str = "v1"  # v1 (SM4-CBC + b64) | v2 (HKDF + HMAC + carriers)
    key: str = ""
    iv: str = ""
    secret: str = ""
    salt: str = ""
    carrier: str = "form"  # form | raw | json | cookie | multipart | bin
    pad_bucket: int = 0
    rpad: int = 0
    ts_window: int = 300
    jitter: float = 0.0
    min_interval: float = 0.0
    chunk_kb: int = 512
    concurrency: int = 4
    pass_param: str = "data"
    method: str = "POST"
    body_mode: str = "form"  # form | raw
    timeout: float = 20.0
    transport: str = "requests"  # requests | curl_cffi
    impersonate: str = "chrome"  # curl_cffi browser fingerprint
    charset: str = "utf-8"
    proxy: str = ""
    verify_ssl: bool = False
    user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
    headers: dict[str, str] = field(default_factory=dict)
    remark: str = ""
    os_type: str = "linux"
    cwd: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    group: str = "default"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ShellConfig":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})


class ShellStore:
    """Tiny JSON store, optionally encrypted with a master passphrase."""

    def __init__(self, path: Path | None = None, passphrase: str | None = None) -> None:
        self.path = path or (config_home() / "shells.json")
        self.passphrase = passphrase

    def set_passphrase(self, passphrase: str | None) -> None:
        self.passphrase = passphrase

    def is_encrypted(self) -> bool:
        try:
            return secure.is_encrypted(self.path.read_bytes())
        except OSError:
            return False

    def _read_payload(self) -> dict[str, Any]:
        raw = self.path.read_bytes()
        if secure.is_encrypted(raw):
            if not self.passphrase:
                raise secure.StoreLocked("store is encrypted; passphrase required")
            return secure.decrypt_json(json.loads(raw.decode("utf-8")), self.passphrase)
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise secure.StoreError(f"corrupted store: {exc}") from exc

    def load(self) -> list[ShellConfig]:
        if not self.path.exists():
            return []
        payload = self._read_payload()
        shells = []
        for item in payload.get("shells", []):
            try:
                shells.append(ShellConfig.from_dict(item))
            except (TypeError, ValueError):
                continue
        return shells

    def save(self, shells: list[ShellConfig]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "shells": [s.to_dict() for s in shells]}
        if self.passphrase:
            data = secure.encrypt_json(payload, self.passphrase)
            text = json.dumps(data, indent=2)
        else:
            text = json.dumps(payload, indent=2, ensure_ascii=False)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(text, encoding="utf-8")
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        tmp.replace(self.path)
