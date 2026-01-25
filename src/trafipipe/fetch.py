from __future__ import annotations

import atexit
from typing import Dict, Optional, Tuple
from urllib.request import ProxyHandler, Request, build_opener
from urllib.error import URLError, HTTPError

from .config import FetchConfig
from .exceptions import FetchError

try:
    import httpx

    _HAS_HTTPX = True
except Exception:
    httpx = None
    _HAS_HTTPX = False


_HTTPX_CLIENTS: Dict[Tuple[Tuple[Tuple[str, str], ...], Optional[str]], "httpx.Client"] = {}


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


def fetch_html(url: str, config: FetchConfig) -> str:
    headers = {"User-Agent": config.user_agent}
    headers.update(config.headers or {})

    if _HAS_HTTPX:
        proxies = config.proxy.to_httpx() if config.proxy else None
        try:
            client = _httpx_client(proxies)
            if config.max_bytes is None:
                resp = client.get(url, headers=headers, timeout=config.timeout)
                if resp.status_code >= 400:
                    raise FetchError(f"httpx status {resp.status_code} for {url}")
                return resp.text

            with client.stream(
                "GET", url, headers=headers, timeout=config.timeout
            ) as resp:
                if resp.status_code >= 400:
                    raise FetchError(f"httpx status {resp.status_code} for {url}")
                raw = _read_limited(resp, config.max_bytes)
                encoding = resp.encoding or "utf-8"
                return raw.decode(encoding, errors="replace")
        except Exception as exc:
            raise FetchError(f"httpx fetch failed: {exc}") from exc

    proxies = config.proxy.to_urllib() if config.proxy else None
    opener = build_opener(ProxyHandler(proxies or {}))
    req = Request(url, headers=headers)
    try:
        with opener.open(req, timeout=config.timeout) as resp:
            raw = resp.read(config.max_bytes or None)
            charset = resp.headers.get_content_charset() or "utf-8"
            return raw.decode(charset, errors="replace")
    except (HTTPError, URLError) as exc:
        raise FetchError(f"urllib fetch failed: {exc}") from exc
