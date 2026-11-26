"""HTTP transport backends.

``requests`` is always available; ``curl_cffi`` is optional and gives us a real
browser TLS fingerprint (JA3/JA4) plus HTTP/2, which is the single biggest
tell of a Python client on the wire.

Contract: every backend performs exactly one request and returns a
:class:`TransportResponse`; failures raise :class:`TransportError`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import requests


class TransportError(Exception):
    """Network / protocol level failure (retryable at the caller)."""


@dataclass
class TransportResponse:
    status: int
    text: str
    content: bytes
    headers: dict[str, str] = field(default_factory=dict)


class Transport:
    name = "base"

    def request(
        self,
        method: str,
        url: str,
        *,
        body: bytes | None,
        headers: dict[str, str],
        timeout: float,
        proxy: str = "",
        verify: bool = False,
    ) -> TransportResponse:  # pragma: no cover - interface
        raise NotImplementedError

    def close(self) -> None:  # pragma: no cover - interface
        pass


class RequestsTransport(Transport):
    name = "requests"

    def __init__(self, config: Any | None = None) -> None:
        self._session = requests.Session()

    def request(self, method, url, *, body, headers, timeout, proxy="", verify=False):
        proxies = {"http": proxy, "https": proxy} if proxy else None
        try:
            resp = self._session.request(
                method=method,
                url=url,
                data=body if body is not None else b"",
                headers=headers,
                timeout=timeout,
                verify=verify,
                proxies=proxies,
                allow_redirects=True,
            )
        except requests.RequestException as exc:
            raise TransportError(str(exc)) from exc
        return TransportResponse(
            status=resp.status_code,
            text=resp.text,
            content=resp.content,
            headers={k.lower(): v for k, v in resp.headers.items()},
        )

    def close(self) -> None:
        try:
            self._session.close()
        except Exception:
            pass


class CurlCffiTransport(Transport):
    """Browser-identical TLS/HTTP2 fingerprint via curl_cffi."""

    name = "curl_cffi"

    def __init__(self, config: Any | None = None) -> None:
        try:
            from curl_cffi import requests as curl_requests  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover - depends on install
            raise TransportError(
                "curl_cffi 未安装：uv pip install curl_cffi（或 uv sync --extra tls）"
            ) from exc
        self._curl = curl_requests
        impersonate = getattr(config, "impersonate", "") or "chrome"
        try:
            self._session = curl_requests.Session(impersonate=impersonate)
        except Exception as exc:  # invalid fingerprint name
            raise TransportError(f"无法启用指纹 {impersonate}: {exc}") from exc

    def request(self, method, url, *, body, headers, timeout, proxy="", verify=False):
        kwargs: dict[str, Any] = {
            "headers": headers,
            "timeout": timeout,
            "allow_redirects": True,
            "verify": verify,
        }
        if body:
            kwargs["content"] = body
        if proxy:
            kwargs["proxies"] = {"http": proxy, "https": proxy}
        try:
            resp = self._session.request(method, url, **kwargs)
        except Exception as exc:  # curl_cffi raises its own RequestException tree
            raise TransportError(f"{type(exc).__name__}: {exc}") from exc
        headers_out = {str(k).lower(): str(v) for k, v in dict(resp.headers).items()}
        content = resp.content or b""
        text = content.decode(resp.encoding or "utf-8", "replace") if content else ""
        return TransportResponse(status=resp.status_code, text=text, content=content, headers=headers_out)

    def close(self) -> None:
        try:
            self._session.close()
        except Exception:
            pass


def available_transports() -> list[str]:
    names = ["requests"]
    try:
        import curl_cffi  # noqa: F401, PLC0415

        names.append("curl_cffi")
    except ImportError:
        pass
    return names


def impersonation_targets() -> list[str]:
    try:
        from curl_cffi.requests import BrowserType  # noqa: PLC0415

        return [browser.value for browser in BrowserType]
    except Exception:
        return ["chrome", "chrome131", "safari170"]


def make_transport(config: Any) -> Transport:
    backend = getattr(config, "transport", "requests") or "requests"
    if backend == "curl_cffi":
        return CurlCffiTransport(config)
    return RequestsTransport(config)
