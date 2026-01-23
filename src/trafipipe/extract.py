from __future__ import annotations

import json
import re
from html import escape, unescape
from html.parser import HTMLParser
from typing import List, Optional
from urllib.parse import urljoin

from trafilatura import extract

from .config import ExtractConfig

_HUANQIU_PATTERNS = [
    re.compile(
        r'<textarea[^>]*class="[^"]*article-content[^"]*"[^>]*>(.*?)</textarea>',
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"<textarea[^>]*class='[^']*article-content[^']*'[^>]*>(.*?)</textarea>",
        re.IGNORECASE | re.DOTALL,
    ),
]

_HUANQIU_BLOCK_MARKERS = [
    "adblock",
    "adblock plus",
    "白名单",
    "插件已阻拦",
    "移除相关插件",
    "系统提示",
    "为体验更好的服务",
]


def _normalize_output_format(fmt: str) -> str:
    val = (fmt or "txt").strip().lower()
    if val in {"md", "markdown"}:
        return "markdown"
    if val in {"txt", "text"}:
        return "txt"
    return val


def _markdown_to_text_with_images(md: str) -> str:
    text = re.sub(r"!\[[^\]]*\]\(([^)]+)\)", r"[Image] \1", md)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", text)
    for token in ("**", "__", "*", "_", "`", "~~"):
        text = text.replace(token, "")
    return text


def extract_metadata_from_html(html: str, url: Optional[str]) -> dict:
    try:
        payload = extract(
            html,
            url=url,
            with_metadata=True,
            output_format="json",
            include_images=False,
            include_links=False,
            include_comments=False,
        )
        if not payload:
            return {}
        data = json.loads(payload)
    except Exception:
        return {}
    return {
        "title": data.get("title"),
        "source": data.get("source") or data.get("source-hostname") or data.get("hostname"),
    }


def _extract_title(html: str) -> Optional[str]:
    m = re.search(
        r'<textarea[^>]*class="[^"]*article-title[^"]*"[^>]*>(.*?)</textarea>',
        html,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        return unescape(m.group(1)).strip()
    m = re.search(
        r'<meta[^>]+property=["\\\']og:title["\\\'][^>]+content=["\\\'](.*?)["\\\']',
        html,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        return unescape(m.group(1)).strip()
    m = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if m:
        return unescape(m.group(1)).strip()
    return None


def _extract_huanqiu(html: str, url: Optional[str], config: ExtractConfig) -> Optional[str]:
    if not url or "huanqiu.com" not in url:
        return None
    fmt = _normalize_output_format(config.output_format)
    title = _extract_title(html)
    for pattern in _HUANQIU_PATTERNS:
        match = pattern.search(html)
        if not match:
            continue
        inner = unescape(match.group(1))
        head = f"<head><title>{escape(title)}</title></head>" if title else ""
        wrapped = f"<html>{head}<body>{inner}</body></html>"
        output_format = "markdown" if config.inline_images else fmt
        include_images = config.include_images or config.inline_images
        text = extract(
            wrapped,
            url=url,
            with_metadata=config.with_metadata,
            favor_precision=config.favor_precision,
            favor_recall=config.favor_recall,
            include_tables=config.include_tables,
            include_links=config.include_links,
            include_images=include_images,
            include_comments=config.include_comments,
            output_format=output_format,
        )
        if config.inline_images and fmt == "txt" and text:
            return _markdown_to_text_with_images(text)
        return text
    return None


class _ImageCollector(HTMLParser):
    def __init__(self, base_url: Optional[str]) -> None:
        super().__init__()
        self.base_url = base_url
        self.images: List[str] = []

    def handle_starttag(self, tag, attrs):
        if tag != "img":
            return
        src = None
        for key, value in attrs:
            if key in {"src", "data-src", "data-original", "data-lazy-src", "data-echo"} and value:
                src = value
                break
        if not src:
            return
        if self.base_url:
            src = urljoin(self.base_url, src)
        self.images.append(src)


def collect_images(html: str, url: Optional[str]) -> List[str]:
    collector = _ImageCollector(url)
    collector.feed(html)
    # preserve order but drop duplicates
    seen = set()
    images = []
    for img in collector.images:
        if img in seen:
            continue
        seen.add(img)
        images.append(img)
    return images


def collect_huanqiu_images(html: str, url: Optional[str]) -> List[str]:
    if not url or "huanqiu.com" not in url:
        return []
    for pattern in _HUANQIU_PATTERNS:
        match = pattern.search(html)
        if not match:
            continue
        inner = unescape(match.group(1))
        return collect_images(inner, url)
    return []


def extract_from_html(html: str, url: Optional[str], config: ExtractConfig) -> Optional[str]:
    fmt = _normalize_output_format(config.output_format)
    output_format = "markdown" if config.inline_images else fmt
    include_images = config.include_images or config.inline_images
    text = extract(
        html,
        url=url,
        with_metadata=config.with_metadata,
        favor_precision=config.favor_precision,
        favor_recall=config.favor_recall,
        include_tables=config.include_tables,
        include_links=config.include_links,
        include_images=include_images,
        include_comments=config.include_comments,
        output_format=output_format,
    )
    if config.inline_images and fmt == "txt" and text:
        text = _markdown_to_text_with_images(text)
    if url and "huanqiu.com" in url:
        if not text or len(text.strip()) < config.min_text_len:
            return _extract_huanqiu(html, url, config) or text
        lowered = text.lower()
        if any(marker in lowered for marker in _HUANQIU_BLOCK_MARKERS):
            return _extract_huanqiu(html, url, config) or text
    return text
