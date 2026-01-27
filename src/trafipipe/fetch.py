from __future__ import annotations

import atexit
from dataclasses import dataclass
import re
from typing import Dict, Optional, Tuple
from urllib.request import ProxyHandler, Request, build_opener
from urllib.error import URLError, HTTPError

from .config import FetchConfig
from .exceptions import FetchError


@dataclass
class FetchResult:
    html: str
    status_code: int

try:
    import httpx

    _HAS_HTTPX = True
except Exception:
    httpx = None
    _HAS_HTTPX = False


_HTTPX_CLIENTS: Dict[Tuple[Tuple[Tuple[str, str], ...], Optional[str]], "httpx.Client"] = {}

_META_CHARSET_RE = re.compile(
    br'<meta[^>]+charset=["\']?\s*([A-Za-z0-9._-]+)',
    re.IGNORECASE,
)
_META_HTTP_EQUIV_RE = re.compile(
    br'<meta[^>]+http-equiv=["\']?content-type["\']?[^>]*content=["\'][^"\']*charset=([A-Za-z0-9._-]+)',
    re.IGNORECASE,
)


def _normalize_encoding(value: str) -> str:
    enc = (value or "").strip().strip('"').strip("'").lower()
    if not enc:
        return ""
    if enc in {"utf8"}:
        return "utf-8"
    if enc in {"gb2312", "gbk"}:
        return "gb18030"
    return enc


def _detect_encoding(raw: bytes, header_encoding: Optional[str]) -> str:
    if header_encoding:
        return _normalize_encoding(header_encoding)
    head = raw[:16384]
    match = _META_CHARSET_RE.search(head)
    if match:
        enc = _normalize_encoding(match.group(1).decode("ascii", errors="ignore"))
        if enc:
            return enc
    match = _META_HTTP_EQUIV_RE.search(head)
    if match:
        enc = _normalize_encoding(match.group(1).decode("ascii", errors="ignore"))
        if enc:
            return enc
    try:
        from charset_normalizer import from_bytes  # type: ignore

        best = from_bytes(raw).best()
        if best and best.encoding:
            return _normalize_encoding(best.encoding)
    except Exception:
        pass
    return "utf-8"


def _proxy_key(proxies) -> Tuple[Tuple[str, str], ...]:
    if isinstance(proxies, dict):
        return tuple(sorted((str(k), str(v)) for k, v in proxies.items()))
    return tuple()


def _httpx_client(proxies) -> "httpx.Client":
    key = (_proxy_key(proxies), str(proxies) if not isinstance(proxies, dict) else None)
    client = _HTTPX_CLIENTS.get(key)
    if client is not None:
        return client

    if proxies is None:
        client = httpx.Client(follow_redirects=True)
    else:
        try:
            client = httpx.Client(follow_redirects=True, proxies=proxies)
        except TypeError:
            proxy_value = None
            if isinstance(proxies, dict):
                proxy_value = proxies.get("https://") or proxies.get("http://")
            else:
                proxy_value = proxies
            client = httpx.Client(follow_redirects=True, proxy=proxy_value)

    _HTTPX_CLIENTS[key] = client
    return client


def _close_httpx_clients() -> None:
    for client in _HTTPX_CLIENTS.values():
        try:
            client.close()
        except Exception:
            pass
    _HTTPX_CLIENTS.clear()


atexit.register(_close_httpx_clients)


def _read_limited(response, max_bytes: int) -> bytes:
    if max_bytes <= 0:
        return b""
    buf = bytearray()
    for chunk in response.iter_bytes():
        if not chunk:
            continue
        remaining = max_bytes - len(buf)
        if remaining <= 0:
            break
        if len(chunk) > remaining:
            buf.extend(chunk[:remaining])
            break
        buf.extend(chunk)
    return bytes(buf)


def _decode_response(raw: bytes, header_encoding: Optional[str]) -> str:
    encoding = _detect_encoding(raw, header_encoding)
    try:
        return raw.decode(encoding, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def fetch_html(url: str, config: FetchConfig) -> FetchResult:
    headers = {"User-Agent": config.user_agent}
    headers.update(config.headers or {})

    if _HAS_HTTPX:
        proxies = config.proxy.to_httpx() if config.proxy else None
        try:
            client = _httpx_client(proxies)
            if config.max_bytes is None:
                resp = client.get(url, headers=headers, timeout=config.timeout)
                if resp.status_code >= 400:
                    raise FetchError(
                        f"httpx status {resp.status_code} for {url}",
                        status_code=resp.status_code,
                    )
                raw = resp.content
                text = _decode_response(raw, resp.encoding)
                return FetchResult(text, resp.status_code)

            with client.stream(
                "GET", url, headers=headers, timeout=config.timeout
            ) as resp:
                if resp.status_code >= 400:
                    raise FetchError(
                        f"httpx status {resp.status_code} for {url}",
                        status_code=resp.status_code,
                    )
                raw = _read_limited(resp, config.max_bytes)
                text = _decode_response(raw, resp.encoding)
                return FetchResult(text, resp.status_code)
        except Exception as exc:
            raise FetchError(f"httpx fetch failed: {exc}") from exc

    proxies = config.proxy.to_urllib() if config.proxy else None
    opener = build_opener(ProxyHandler(proxies or {}))
    req = Request(url, headers=headers)
    try:
        with opener.open(req, timeout=config.timeout) as resp:
            raw = resp.read(config.max_bytes or None)
            charset = resp.headers.get_content_charset()
            status = resp.getcode() or 200
            text = _decode_response(raw, charset)
            return FetchResult(text, int(status))
    except (HTTPError, URLError) as exc:
        status_code = getattr(exc, "code", None)
        raise FetchError(
            f"urllib fetch failed: {exc}",
            status_code=status_code if isinstance(status_code, int) else None,
        ) from exc
