from __future__ import annotations

import re
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Iterable, List, Optional, Sequence
from urllib.parse import urljoin, urlparse, urldefrag

from .config import CrawlConfig, FetchConfig
from .fetch import fetch_html


class _LinkCollector(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.links: List[str] = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        for key, value in attrs:
            if key == "href" and value:
                self.links.append(urljoin(self.base_url, value))


def _normalize_url(url: str, strip_query: bool) -> str:
    url, _ = urldefrag(url)
    if strip_query:
        parsed = urlparse(url)
        url = parsed._replace(query="").geturl()
    return url


def _compile(patterns: Sequence[str]) -> List[re.Pattern]:
    return [re.compile(p) for p in patterns]


def _is_allowed(url: str, allow: List[re.Pattern], deny: List[re.Pattern]) -> bool:
    if allow and not any(p.search(url) for p in allow):
        return False
    if deny and any(p.search(url) for p in deny):
        return False
    return True


def _host(url: str) -> str:
    return urlparse(url).netloc


def _is_http_url(url: str) -> bool:
    return url.startswith("http://") or url.startswith("https://")


def crawl_urls(
    start_urls: Iterable[str],
    fetch_config: FetchConfig,
    crawl_config: CrawlConfig,
) -> List[str]:
    allow_patterns = _compile(crawl_config.allow_patterns)
    deny_patterns = _compile(crawl_config.deny_patterns)

    start_urls = list(start_urls)
    if not start_urls:
        return []

    allowed_domains = set(crawl_config.allow_domains or [])
    if crawl_config.same_host_only and not allowed_domains:
        allowed_domains.add(_host(start_urls[0]))

    def domain_ok(u: str) -> bool:
        if not allowed_domains:
            return True
        return _host(u) in allowed_domains

    queue = deque()
    queued = set()
    visited = set()
    results: List[str] = []

    def _enqueue(raw_url: str, depth: int) -> None:
        if not raw_url:
            return
        url = _normalize_url(raw_url, crawl_config.strip_query)
        if not _is_http_url(url):
            return
        if url in visited or url in queued:
            return
        if not domain_ok(url):
            return
        if not _is_allowed(url, allow_patterns, deny_patterns):
            return
        queued.add(url)
        queue.append((url, depth))

    for u in start_urls:
        _enqueue(u, 0)

    max_workers = max(1, int(crawl_config.max_workers or 1))
    executor = ThreadPoolExecutor(max_workers=max_workers) if max_workers > 1 else None

    try:
        while queue and len(visited) < crawl_config.max_pages:
            if executor is None:
                url, depth = queue.popleft()
                queued.discard(url)

                if url in visited:
                    continue

                visited.add(url)
                results.append(url)

                if depth >= crawl_config.max_depth:
                    continue

                try:
                    html = fetch_html(url, fetch_config)
                except Exception:
                    continue

                parser = _LinkCollector(url)
                parser.feed(html)
                for link in parser.links:
                    _enqueue(link, depth + 1)
                continue

            batch = []
            while (
                queue
                and len(batch) < max_workers
                and len(visited) < crawl_config.max_pages
            ):
                url, depth = queue.popleft()
                queued.discard(url)

                if url in visited:
                    continue

                visited.add(url)
                results.append(url)

                if depth >= crawl_config.max_depth:
                    continue

                batch.append((url, depth))

            futures = {
                executor.submit(fetch_html, url, fetch_config): (url, depth)
                for url, depth in batch
            }
            for future in as_completed(futures):
                url, depth = futures[future]
                try:
                    html = future.result()
                except Exception:
                    continue

                parser = _LinkCollector(url)
                parser.feed(html)
                for link in parser.links:
                    _enqueue(link, depth + 1)
    finally:
        if executor is not None:
            executor.shutdown(wait=True)

    return results
