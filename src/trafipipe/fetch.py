from __future__ import annotations

from typing import Optional
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


def _limit_bytes(data: bytes, max_bytes: Optional[int]) -> bytes:
    if max_bytes is None:
        return data
    return data[:max_bytes]


def _httpx_client(headers, timeout, proxies):
    if proxies is None:
        return httpx.Client(headers=headers, timeout=timeout, follow_redirects=True)
    try:
        return httpx.Client(
            headers=headers, timeout=timeout, follow_redirects=True, proxies=proxies
        )
    except TypeError:
        proxy_value = None
        if isinstance(proxies, dict):
            proxy_value = proxies.get("https://") or proxies.get("http://")
        else:
            proxy_value = proxies
        return httpx.Client(
            headers=headers, timeout=timeout, follow_redirects=True, proxy=proxy_value
        )


def fetch_html(url: str, config: FetchConfig) -> str:
    headers = {"User-Agent": config.user_agent}
    headers.update(config.headers or {})

    if _HAS_HTTPX:
        proxies = config.proxy.to_httpx() if config.proxy else None
        try:
            with _httpx_client(headers, config.timeout, proxies) as client:
                resp = client.get(url)
        except Exception as exc:
            raise FetchError(f"httpx fetch failed: {exc}") from exc

        if resp.status_code >= 400:
            raise FetchError(f"httpx status {resp.status_code} for {url}")

        text = resp.text
        if config.max_bytes is not None:
            raw = resp.content
            raw = _limit_bytes(raw, config.max_bytes)
            text = raw.decode(resp.encoding or "utf-8", errors="replace")
        return text

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
