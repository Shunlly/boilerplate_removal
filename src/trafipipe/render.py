from __future__ import annotations

from .config import RenderConfig
from .exceptions import RenderError, RenderUnavailable

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

    _HAS_PLAYWRIGHT = True
except Exception:
    sync_playwright = None
    PlaywrightTimeoutError = None
    _HAS_PLAYWRIGHT = False


def render_html(url: str, config: RenderConfig, user_agent: str) -> str:
    if not _HAS_PLAYWRIGHT:
        raise RenderUnavailable("playwright is not installed")

    proxy = config.proxy.to_playwright() if config.proxy else None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, proxy=proxy)
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

            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=int(config.timeout * 1000))
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
            context.close()
            browser.close()
            return content
    except Exception as exc:
        raise RenderError(f"render failed: {exc}") from exc
