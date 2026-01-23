from __future__ import annotations

import re
from collections import deque
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

    queue = deque([(u, 0) for u in start_urls])
    visited = set()
    results: List[str] = []

    while queue and len(visited) < crawl_config.max_pages:
        url, depth = queue.popleft()
        url = _normalize_url(url, crawl_config.strip_query)

        if url in visited:
            continue
        if not domain_ok(url):
            continue
        if not _is_allowed(url, allow_patterns, deny_patterns):
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
            queue.append((link, depth + 1))

    return results
