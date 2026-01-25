from __future__ import annotations

from dataclasses import dataclass, field
import re
import time
from typing import Iterable, List, Optional
from urllib.parse import urlparse

from .config import PipelineConfig
from .crawl import crawl_urls
from .exceptions import FetchError, RenderError
from .extract import (
    collect_huanqiu_images,
    collect_images,
    collect_videos,
    filter_videos_for_url,
    _collect_wechat_images,
    extract_text_and_metadata,
    extract_metadata_from_html,
)
from .fetch import fetch_html
from .render import render_html_with_media


@dataclass
class ExtractResult:
    url: str
    text: Optional[str]
    used_render: bool = False
    error: Optional[str] = None
    images: List[str] = field(default_factory=list)
    videos: List[str] = field(default_factory=list)
    title: Optional[str] = None
    source: Optional[str] = None
    elapsed_ms: Optional[float] = None
    fetch_ms: Optional[float] = None
    render_ms: Optional[float] = None
    extract_ms: Optional[float] = None
    image_ms: Optional[float] = None
    video_ms: Optional[float] = None


def _should_render(text: Optional[str], cfg: PipelineConfig) -> bool:
    mode = cfg.render.mode
    if mode == "never":
        return False
    if mode == "always":
        return True
    if not text:
        return True
    return len(text.strip()) < cfg.extract.min_text_len


def _hostname(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


_X_SIGNUP_MARKERS = {
    "New to X?",
}

_X_TRAILING_TOKENS = {
    "·",
    "Views",
    "View",
    "Replies",
    "Reposts",
    "Likes",
}

_X_VIEW_RE = re.compile(r"^\d[\d,]*(?:\.\d+)?[KMB]?$")


def _strip_x_boilerplate(text: str) -> str:
    if not text:
        return text
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        stripped = line.strip()
        lowered = stripped.lower()
        if stripped in _X_SIGNUP_MARKERS or lowered.startswith("sign up now"):
            lines = lines[:idx]
            break
    while lines and not lines[-1].strip():
        lines.pop()
    while lines:
        stripped = lines[-1].strip()
        if not stripped:
            lines.pop()
            continue
        if stripped in _X_TRAILING_TOKENS:
            lines.pop()
            continue
        if stripped.endswith("Views"):
            lines.pop()
            continue
        if _X_VIEW_RE.match(stripped):
            lines.pop()
            continue
        break
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def _clean_text_for_url(text: Optional[str], url: str) -> Optional[str]:
    if not text:
        return text
    host = _hostname(url)
    if host.endswith("x.com") or host.endswith("twitter.com"):
        return _strip_x_boilerplate(text)
    return text


def _append_videos_to_text(text: str, videos: List[str], url: str) -> str:
    block = "\n\n[Videos]\n" + "\n".join(videos)
    host = _hostname(url)
    if host.endswith("x.com") or host.endswith("twitter.com"):
        for marker in ("New to X?", "Sign up now", "Sign up"):
            idx = text.find(marker)
            if idx != -1:
                head = text[:idx].rstrip()
                tail = text[idx:]
                return head + block + "\n\n" + tail
    return text + block


class Pipeline:
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config

    def _extract_with_images(
        self, html: str, url: str, media_urls: Optional[List[str]] = None
    ):
        extract_start = time.monotonic()
        text, meta = extract_text_and_metadata(html, url, self.config.extract)
        text = _clean_text_for_url(text, url)
        extract_ms = (time.monotonic() - extract_start) * 1000.0
        images = []
        image_ms = None
        if self.config.extract.keep_images or self.config.extract.inline_images:
            image_start = time.monotonic()
            if url and "huanqiu.com" in url:
                images = collect_huanqiu_images(html, url)
            elif url and "mp.weixin.qq.com" in url:
                images = _collect_wechat_images(html, url)
                seen = set(images)
                for img in collect_images(html, url):
                    if img in seen:
                        continue
                    seen.add(img)
                    images.append(img)
            else:
                images = collect_images(html, url)
            if (
                text
                and images
                and self.config.extract.append_images
                and not self.config.extract.inline_images
            ):
                text = text + "\n\n[Images]\n" + "\n".join(images)
            image_ms = (time.monotonic() - image_start) * 1000.0
        videos = []
        video_ms = None
        include_videos = (
            self.config.extract.keep_videos
            or self.config.extract.append_videos
            or self.config.extract.inline_images
        )
        if include_videos:
            video_start = time.monotonic()
            videos = collect_videos(html, url)
            if media_urls:
                media_urls = filter_videos_for_url(url, media_urls)
                seen = set(videos)
                for media_url in media_urls:
                    if media_url in seen:
                        continue
                    seen.add(media_url)
                    videos.append(media_url)
            should_append = (
                self.config.extract.append_videos or self.config.extract.inline_images
            )
            if text and videos and should_append:
                text = _append_videos_to_text(text, videos, url)
            video_ms = (time.monotonic() - video_start) * 1000.0
        return text, images, videos, meta, extract_ms, image_ms, video_ms

    def extract_url(self, url: str) -> ExtractResult:
        start = time.monotonic()

        def _build_result(
            text,
            used_render,
            html,
            images,
            videos,
            *,
            meta=None,
            error=None,
            fetch_ms=None,
            render_ms=None,
            extract_ms=None,
            image_ms=None,
            video_ms=None,
        ):
            elapsed_ms = (time.monotonic() - start) * 1000.0
            if meta is None:
                meta = (
                    extract_metadata_from_html(html, url)
                    if html and self.config.extract.with_metadata
                    else {}
                )
            return ExtractResult(
                url=url,
                text=text,
                used_render=used_render,
                error=error,
                images=images,
                videos=videos,
                title=meta.get("title"),
                source=meta.get("source"),
                elapsed_ms=elapsed_ms,
                fetch_ms=fetch_ms,
                render_ms=render_ms,
                extract_ms=extract_ms,
                image_ms=image_ms,
                video_ms=video_ms,
            )

        if self.config.render.mode == "always":
            try:
                render_start = time.monotonic()
                rendered, media_urls = render_html_with_media(
                    url, self.config.render, self.config.fetch.user_agent
                )
                render_ms = (time.monotonic() - render_start) * 1000.0
                text, images, videos, meta, extract_ms, image_ms, video_ms = (
                    self._extract_with_images(rendered, url, media_urls=media_urls)
                )
                return _build_result(
                    text,
                    True,
                    rendered,
                    images,
                    videos,
                    meta=meta,
                    render_ms=render_ms,
                    extract_ms=extract_ms,
                    image_ms=image_ms,
                    video_ms=video_ms,
                )
            except RenderError as exc:
                render_ms = (time.monotonic() - render_start) * 1000.0
                return _build_result(
                    None, True, None, [], [], error=str(exc), render_ms=render_ms
                )

        fetch_ms = None
        try:
            fetch_start = time.monotonic()
            html = fetch_html(url, self.config.fetch)
            fetch_ms = (time.monotonic() - fetch_start) * 1000.0
        except FetchError as exc:
            if fetch_ms is None:
                fetch_ms = (time.monotonic() - fetch_start) * 1000.0
            if self.config.render.mode != "never":
                try:
                    render_start = time.monotonic()
                    rendered, media_urls = render_html_with_media(
                        url, self.config.render, self.config.fetch.user_agent
                    )
                    render_ms = (time.monotonic() - render_start) * 1000.0
                    text, images, videos, meta, extract_ms, image_ms, video_ms = (
                        self._extract_with_images(rendered, url, media_urls=media_urls)
                    )
                    return _build_result(
                        text,
                        True,
                        rendered,
                        images,
                        videos,
                        meta=meta,
                        fetch_ms=fetch_ms,
                        render_ms=render_ms,
                        extract_ms=extract_ms,
                        image_ms=image_ms,
                        video_ms=video_ms,
                    )
                except RenderError as render_exc:
                    render_ms = (time.monotonic() - render_start) * 1000.0
                    return _build_result(
                        None,
                        True,
                        None,
                        [],
                        [],
                        error=str(render_exc),
                        fetch_ms=fetch_ms,
                        render_ms=render_ms,
                    )
            return _build_result(
                None, False, None, [], [], error=str(exc), fetch_ms=fetch_ms
            )

        text, images, videos, meta, extract_ms, image_ms, video_ms = (
            self._extract_with_images(html, url)
        )
        if _should_render(text, self.config):
            try:
                render_start = time.monotonic()
                rendered, media_urls = render_html_with_media(
                    url, self.config.render, self.config.fetch.user_agent
                )
                render_ms = (time.monotonic() - render_start) * 1000.0
                text, images, videos, meta, extract_ms, image_ms, video_ms = (
                    self._extract_with_images(rendered, url, media_urls=media_urls)
                )
                return _build_result(
                    text,
                    True,
                    rendered,
                    images,
                    videos,
                    meta=meta,
                    fetch_ms=fetch_ms,
                    render_ms=render_ms,
                    extract_ms=extract_ms,
                    image_ms=image_ms,
                    video_ms=video_ms,
                )
            except RenderError as exc:
                render_ms = (time.monotonic() - render_start) * 1000.0
                return _build_result(
                    text,
                    False,
                    html,
                    images,
                    videos,
                    meta=meta,
                    error=str(exc),
                    fetch_ms=fetch_ms,
                    render_ms=render_ms,
                    extract_ms=extract_ms,
                    image_ms=image_ms,
                    video_ms=video_ms,
                )

        return _build_result(
            text,
            False,
            html,
            images,
            videos,
            meta=meta,
            fetch_ms=fetch_ms,
            extract_ms=extract_ms,
            image_ms=image_ms,
            video_ms=video_ms,
        )

    def crawl(self, start_urls: Iterable[str]) -> List[str]:
        return crawl_urls(start_urls, self.config.fetch, self.config.crawl)

    def crawl_and_extract(self, start_urls: Iterable[str]) -> List[ExtractResult]:
        results: List[ExtractResult] = []
        for url in self.crawl(start_urls):
            results.append(self.extract_url(url))
        return results
