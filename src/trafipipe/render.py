from __future__ import annotations

import atexit
from typing import List, Tuple

from .config import RenderConfig
from .exceptions import RenderError, RenderUnavailable

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

    _HAS_PLAYWRIGHT = True
except Exception:
    sync_playwright = None
    PlaywrightTimeoutError = None
    _HAS_PLAYWRIGHT = False

_PLAYWRIGHT = None
_BROWSER = None
_BROWSER_PROXY = None
_CONTEXT = None
_CONTEXT_KEY = None

_MEDIA_EXTENSIONS = (
    ".mp4",
    ".m3u8",
    ".webm",
    ".mov",
    ".m4v",
    ".mpeg",
    ".mpg",
    ".ogv",
)


def _close_browser() -> None:
    global _PLAYWRIGHT, _BROWSER, _BROWSER_PROXY, _CONTEXT, _CONTEXT_KEY
    if _CONTEXT is not None:
        try:
            _CONTEXT.close()
        except Exception:
            pass
        _CONTEXT = None
        _CONTEXT_KEY = None
    if _BROWSER is not None:
        try:
            _BROWSER.close()
        except Exception:
            pass
        _BROWSER = None
    _BROWSER_PROXY = None
    if _PLAYWRIGHT is not None:
        try:
            _PLAYWRIGHT.stop()
        except Exception:
            pass
        _PLAYWRIGHT = None


def _get_browser(proxy):
    global _PLAYWRIGHT, _BROWSER, _BROWSER_PROXY
    if _BROWSER is not None and _BROWSER_PROXY == proxy:
        return _BROWSER
    _close_browser()
    _PLAYWRIGHT = sync_playwright().start()
    _BROWSER = _PLAYWRIGHT.chromium.launch(headless=True, proxy=proxy)
    _BROWSER_PROXY = proxy
    return _BROWSER


atexit.register(_close_browser)


def _cookies_key(cookies):
    if not cookies:
        return ()
    normalized = []
    for cookie in cookies:
        if not cookie:
            continue
        items = tuple(sorted((str(k), str(v)) for k, v in cookie.items()))
        normalized.append(items)
    return tuple(sorted(normalized))


def _headers_key(headers):
    if not headers:
        return ()
    return tuple(sorted((str(k), str(v)) for k, v in headers.items()))


def _proxy_key(proxy):
    if not proxy:
        return ()
    return tuple(sorted((str(k), str(v)) for k, v in proxy.items()))


def _context_key(config: RenderConfig, user_agent: str, proxy):
    return (
        user_agent,
        _headers_key(config.extra_headers),
        _cookies_key(config.cookies),
        _proxy_key(proxy),
        bool(config.block_resources),
    )


def _get_context(browser, config: RenderConfig, user_agent: str, proxy):
    global _CONTEXT, _CONTEXT_KEY
    if not getattr(config, "reuse_context", False):
        context = browser.new_context(
            user_agent=user_agent,
            extra_http_headers=config.extra_headers or None,
        )
        if config.cookies:
            context.add_cookies(config.cookies)
        if config.block_resources:
            def _route_handler(route, request):
                if request.resource_type in {"image", "media", "font"}:
                    route.abort()
                else:
                    route.continue_()

            context.route("**/*", _route_handler)
        return context

    key = _context_key(config, user_agent, proxy)
    if _CONTEXT is not None and _CONTEXT_KEY == key:
        return _CONTEXT

    if _CONTEXT is not None:
        try:
            _CONTEXT.close()
        except Exception:
            pass

    context = browser.new_context(
        user_agent=user_agent,
        extra_http_headers=config.extra_headers or None,
    )
    if config.cookies:
        context.add_cookies(config.cookies)
    if config.block_resources:
        def _route_handler(route, request):
            if request.resource_type in {"image", "media", "font"}:
                route.abort()
            else:
                route.continue_()

        context.route("**/*", _route_handler)

    _CONTEXT = context
    _CONTEXT_KEY = key
    return context


def _looks_like_media_url(url: str) -> bool:
    lowered = url.lower()
    base = lowered.split("?", 1)[0].split("#", 1)[0]
    if any(base.endswith(ext) for ext in _MEDIA_EXTENSIONS):
        return True
    if "video.twimg.com" in lowered:
        return True
    if "twimg.com" in lowered and "/video/" in lowered:
        return True
    return False


def _render_html(
    url: str, config: RenderConfig, user_agent: str, capture_media: bool
) -> Tuple[str, List[str]]:
    if not _HAS_PLAYWRIGHT:
        raise RenderUnavailable("playwright is not installed")

    proxy = config.proxy.to_playwright() if config.proxy else None
    media_urls: List[str] = []

    try:
        browser = _get_browser(proxy)
        context = _get_context(browser, config, user_agent, proxy)
        page = context.new_page()
        try:
            if capture_media:
                seen = set()

                def _on_request(request):
                    req_url = request.url
                    if request.resource_type == "media" or _looks_like_media_url(req_url):
                        if req_url in seen:
                            return
                        seen.add(req_url)
                        media_urls.append(req_url)

                page.on("request", _on_request)

            page.goto(
                url, wait_until="domcontentloaded", timeout=int(config.timeout * 1000)
            )
            if config.wait_selector:
                try:
                    page.wait_for_selector(
                        config.wait_selector, timeout=int(config.timeout * 1000)
                    )
                except Exception as exc:
                    is_timeout = (
                        PlaywrightTimeoutError is not None
                        and isinstance(exc, PlaywrightTimeoutError)
                    )
                    if not (is_timeout and config.ignore_wait_timeout):
                        raise

            content = page.content()
        finally:
            try:
                page.close()
            except Exception:
                pass
            if not getattr(config, "reuse_context", False):
                try:
                    context.close()
                except Exception:
                    pass
        return content, media_urls
    except Exception as exc:
        raise RenderError(f"render failed: {exc}") from exc


def render_html(url: str, config: RenderConfig, user_agent: str) -> str:
    content, _ = _render_html(url, config, user_agent, capture_media=False)
    return content


def render_html_with_media(
    url: str, config: RenderConfig, user_agent: str
) -> Tuple[str, List[str]]:
    return _render_html(url, config, user_agent, capture_media=True)
