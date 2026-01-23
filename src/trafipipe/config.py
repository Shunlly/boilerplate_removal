from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence


@dataclass
class ProxyConfig:
    http: Optional[str] = None
    https: Optional[str] = None
    server: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None

    def to_httpx(self) -> Optional[Dict[str, str]]:
        server = self.server
        if server:
            return {"http://": server, "https://": server}
        if self.http or self.https:
            proxies = {}
            if self.http:
                proxies["http://"] = self.http
            if self.https:
                proxies["https://"] = self.https
            return proxies
        return None

    def to_urllib(self) -> Optional[Dict[str, str]]:
        server = self.server
        if server:
            return {"http": server, "https": server}
        if self.http or self.https:
            proxies = {}
            if self.http:
                proxies["http"] = self.http
            if self.https:
                proxies["https"] = self.https
            return proxies
        return None

    def to_playwright(self) -> Optional[Dict[str, str]]:
        server = self.server or self.https or self.http
        if not server:
            return None
        proxy = {"server": server}
        if self.username:
            proxy["username"] = self.username
        if self.password:
            proxy["password"] = self.password
        return proxy


@dataclass
class FetchConfig:
    timeout: float = 15.0
    user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    headers: Dict[str, str] = field(default_factory=dict)
    proxy: Optional[ProxyConfig] = None
    max_bytes: Optional[int] = 2_000_000


@dataclass
class RenderConfig:
    mode: str = "auto"  # auto | always | never
    timeout: float = 20.0
    wait_selector: Optional[str] = None
    ignore_wait_timeout: bool = True
    block_resources: bool = True
    extra_headers: Dict[str, str] = field(default_factory=dict)
    cookies: List[Dict[str, str]] = field(default_factory=list)
    proxy: Optional[ProxyConfig] = None


@dataclass
class ExtractConfig:
    with_metadata: bool = True
    favor_precision: bool = True
    favor_recall: bool = False
    include_tables: bool = True
    include_links: bool = False
    include_images: bool = False
    include_comments: bool = False
    keep_images: bool = False
    append_images: bool = False
    inline_images: bool = False
    output_format: str = "txt"
    min_text_len: int = 200


@dataclass
class CrawlConfig:
    max_pages: int = 100
    max_depth: int = 2
    same_host_only: bool = True
    allow_domains: Optional[List[str]] = None
    allow_patterns: Sequence[str] = field(default_factory=list)
    deny_patterns: Sequence[str] = field(default_factory=list)
    strip_query: bool = True


@dataclass
class PipelineConfig:
    fetch: FetchConfig = field(default_factory=FetchConfig)
    render: RenderConfig = field(default_factory=RenderConfig)
    extract: ExtractConfig = field(default_factory=ExtractConfig)
    crawl: CrawlConfig = field(default_factory=CrawlConfig)
