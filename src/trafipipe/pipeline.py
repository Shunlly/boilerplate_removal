from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Iterable, List, Optional

from .config import PipelineConfig
from .crawl import crawl_urls
from .exceptions import FetchError, RenderError
from .extract import (
    collect_huanqiu_images,
    collect_images,
    extract_from_html,
    extract_metadata_from_html,
)
from .fetch import fetch_html
from .render import render_html


@dataclass
class ExtractResult:
    url: str
    text: Optional[str]
    used_render: bool = False
    error: Optional[str] = None
    images: List[str] = field(default_factory=list)
    title: Optional[str] = None
    source: Optional[str] = None
    elapsed_ms: Optional[float] = None


def _should_render(text: Optional[str], cfg: PipelineConfig) -> bool:
    mode = cfg.render.mode
    if mode == "never":
        return False
    if mode == "always":
        return True
    if not text:
        return True
    return len(text.strip()) < cfg.extract.min_text_len


class Pipeline:
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config

    def extract_url(self, url: str) -> ExtractResult:
        start = time.monotonic()

        def _build_result(text, used_render, html, images, error=None):
            elapsed_ms = (time.monotonic() - start) * 1000.0
            meta = extract_metadata_from_html(html, url) if html else {}
            return ExtractResult(
                url=url,
                text=text,
                used_render=used_render,
                error=error,
                images=images,
                title=meta.get("title"),
                source=meta.get("source"),
                elapsed_ms=elapsed_ms,
            )

        if self.config.render.mode == "always":
            try:
                rendered = render_html(url, self.config.render, self.config.fetch.user_agent)
                text = extract_from_html(rendered, url, self.config.extract)
                images = []
                if self.config.extract.keep_images:
                    if url and "huanqiu.com" in url:
                        images = collect_huanqiu_images(rendered, url)
                    else:
                        images = collect_images(rendered, url)
                    if (
                        text
                        and images
                        and self.config.extract.append_images
                        and not self.config.extract.inline_images
                    ):
                        text = text + "\n\n[Images]\n" + "\n".join(images)
                return _build_result(text, True, rendered, images)
            except RenderError as exc:
                return _build_result(None, True, None, [], error=str(exc))

        try:
            html = fetch_html(url, self.config.fetch)
        except FetchError as exc:
            if self.config.render.mode != "never":
                try:
                    rendered = render_html(url, self.config.render, self.config.fetch.user_agent)
                    text = extract_from_html(rendered, url, self.config.extract)
                    images = []
                    if self.config.extract.keep_images:
                        if url and "huanqiu.com" in url:
                            images = collect_huanqiu_images(rendered, url)
                        else:
                            images = collect_images(rendered, url)
                        if (
                            text
                            and images
                            and self.config.extract.append_images
                            and not self.config.extract.inline_images
                        ):
                            text = text + "\n\n[Images]\n" + "\n".join(images)
                    return _build_result(text, True, rendered, images)
                except RenderError as render_exc:
                    return _build_result(None, True, None, [], error=str(render_exc))
            return _build_result(None, False, None, [], error=str(exc))

        text = extract_from_html(html, url, self.config.extract)
        images = []
        if self.config.extract.keep_images:
            if url and "huanqiu.com" in url:
                images = collect_huanqiu_images(html, url)
            else:
                images = collect_images(html, url)
            if (
                text
                and images
                and self.config.extract.append_images
                and not self.config.extract.inline_images
            ):
                text = text + "\n\n[Images]\n" + "\n".join(images)
        if _should_render(text, self.config):
            try:
                rendered = render_html(url, self.config.render, self.config.fetch.user_agent)
                text = extract_from_html(rendered, url, self.config.extract)
                images = []
                if self.config.extract.keep_images:
                    if url and "huanqiu.com" in url:
                        images = collect_huanqiu_images(rendered, url)
                    else:
                        images = collect_images(rendered, url)
                    if (
                        text
                        and images
                        and self.config.extract.append_images
                        and not self.config.extract.inline_images
                    ):
                        text = text + "\n\n[Images]\n" + "\n".join(images)
                return _build_result(text, True, rendered, images)
            except RenderError as exc:
                return _build_result(text, False, html, images, error=str(exc))

        return _build_result(text, False, html, images)

    def crawl(self, start_urls: Iterable[str]) -> List[str]:
        return crawl_urls(start_urls, self.config.fetch, self.config.crawl)

    def crawl_and_extract(self, start_urls: Iterable[str]) -> List[ExtractResult]:
        results: List[ExtractResult] = []
        for url in self.crawl(start_urls):
            results.append(self.extract_url(url))
        return results
