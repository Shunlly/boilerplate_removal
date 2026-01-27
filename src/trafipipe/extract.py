from __future__ import annotations

import re
from html import escape, unescape
from html.parser import HTMLParser
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

from trafilatura import bare_extraction, extract_metadata as trafi_extract_metadata
from trafilatura.core import determine_returnstring
from trafilatura.settings import Extractor

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

_OG_TITLE_RE = re.compile(
    r'<meta[^>]+property=["\\\']og:title["\\\'][^>]+content=["\\\'](.*?)["\\\']',
    re.IGNORECASE | re.DOTALL,
)
_HTML_TITLE_RE = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_WECHAT_SRCSET_RE = re.compile(
    r'<img[^>]+(?:data-srcset|srcset)=["\'](.*?)["\']',
    re.IGNORECASE | re.DOTALL,
)
_WECHAT_SRC_RE = re.compile(
    r'<img[^>]+(?:data-src|data-backup-src|data-original|data-actualsrc|data-actual-src|data-croporisrc|src)=["\'](.*?)["\']',
    re.IGNORECASE | re.DOTALL,
)
_STYLE_URL_RE = re.compile(r"url\\(([^)]+)\\)", re.IGNORECASE)
_ABS_URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
_IMG_TAG_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
_IMG_ATTR_RE = re.compile(
    r'([^\s=/>]+)(?:\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^\s>]+)))?'
)

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
        doc = trafi_extract_metadata(html, default_url=url)
    except Exception:
        return {}
    source = doc.url or doc.sitename or doc.hostname or url
    return {"title": doc.title, "source": source}


def _build_extractor(
    url: Optional[str], config: ExtractConfig, output_format: str, include_images: bool
) -> Extractor:
    return Extractor(
        output_format=output_format,
        precision=config.favor_precision,
        recall=config.favor_recall,
        comments=config.include_comments,
        links=config.include_links,
        images=include_images,
        tables=config.include_tables,
        url=url,
        with_metadata=config.with_metadata,
    )


def _run_trafilatura(
    html: str, url: Optional[str], config: ExtractConfig, output_format: str
) -> Tuple[Optional[str], Optional[object]]:
    include_images = config.include_images or config.inline_images
    options = _build_extractor(url, config, output_format, include_images)
    doc = bare_extraction(html, options=options)
    if not doc:
        return None, None
    text = determine_returnstring(doc, options)
    if (
        config.inline_images
        and _normalize_output_format(config.output_format) == "txt"
        and output_format == "markdown"
        and text
    ):
        text = _markdown_to_text_with_images(text)
    return text, doc


def _meta_from_document(doc: Optional[object], url: Optional[str]) -> Dict[str, Optional[str]]:
    if not doc:
        return {}
    title = getattr(doc, "title", None)
    source = getattr(doc, "url", None) or getattr(doc, "sitename", None) or getattr(
        doc, "hostname", None
    ) or url
    return {"title": title, "source": source}


def _extract_title(html: str) -> Optional[str]:
    m = re.search(
        r'<textarea[^>]*class="[^"]*article-title[^"]*"[^>]*>(.*?)</textarea>',
        html,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        return unescape(m.group(1)).strip()
    m = _OG_TITLE_RE.search(html)
    if m:
        return unescape(m.group(1)).strip()
    m = _HTML_TITLE_RE.search(html)
    if m:
        return unescape(m.group(1)).strip()
    return None


def _extract_huanqiu(
    html: str, url: Optional[str], config: ExtractConfig, output_format: str
) -> Tuple[Optional[str], Optional[object]]:
    if not url or "huanqiu.com" not in url:
        return None, None
    title = _extract_title(html)
    for pattern in _HUANQIU_PATTERNS:
        match = pattern.search(html)
        if not match:
            continue
        inner = unescape(match.group(1))
        head = f"<head><title>{escape(title)}</title></head>" if title else ""
        wrapped = f"<html>{head}<body>{inner}</body></html>"
        return _run_trafilatura(wrapped, url, config, output_format)
    return None, None


_IMG_ATTRS = {
    "src",
    "data-src",
    "data-original",
    "data-lazy-src",
    "data-echo",
    "data-backup-src",
    "data-actualsrc",
    "data-actual-src",
    "data-origin-src",
    "data-croporisrc",
    "data-image",
    "data-img",
    "data-image-src",
}

_IMG_SRCSET_ATTRS = {
    "srcset",
    "data-srcset",
}

_INLINE_IMAGE_ATTR_PRIORITY = [
    "data-src",
    "data-actualsrc",
    "data-actual-src",
    "data-original",
    "data-backup-src",
    "data-origin-src",
    "data-croporisrc",
    "data-lazy-src",
    "data-image-src",
    "data-img",
    "data-image",
    "data-srcset",
    "srcset",
]

_VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


def _is_placeholder(src: str) -> bool:
    lowered = src.strip().lower()
    return (
        not lowered
        or lowered.startswith("data:")
        or lowered == "about:blank"
        or lowered.endswith("spacer.gif")
    )


def _normalize_image_url(value: str, base_url: Optional[str]) -> Optional[str]:
    src = (value or "").strip()
    if _is_placeholder(src):
        return None
    if base_url:
        src = urljoin(base_url, src)
    return src


def _parse_srcset(value: str) -> List[str]:
    urls: List[str] = []
    for item in (value or "").split(","):
        item = item.strip()
        if not item:
            continue
        url = item.split()[0]
        if url:
            urls.append(url)
    return urls


def _parse_img_attributes(tag: str) -> Dict[str, Optional[str]]:
    match = re.match(r"<img\b(.*?)(/?)\s*>", tag, re.IGNORECASE | re.DOTALL)
    if not match:
        return {}
    attrs_raw = match.group(1) or ""
    attrs: Dict[str, Optional[str]] = {}
    for attr_match in _IMG_ATTR_RE.finditer(attrs_raw):
        name = attr_match.group(1)
        value = attr_match.group(2) or attr_match.group(3) or attr_match.group(4)
        if not name:
            continue
        attrs[name.lower()] = value
    return attrs


def _parse_tag_attributes(tag: str) -> Dict[str, Optional[str]]:
    match = re.match(r"<[a-zA-Z0-9]+\b(.*?)(/?)\s*>", tag, re.IGNORECASE | re.DOTALL)
    if not match:
        return {}
    attrs_raw = match.group(1) or ""
    attrs: Dict[str, Optional[str]] = {}
    for attr_match in _IMG_ATTR_RE.finditer(attrs_raw):
        name = attr_match.group(1)
        value = attr_match.group(2) or attr_match.group(3) or attr_match.group(4)
        if not name:
            continue
        attrs[name.lower()] = value
    return attrs


def _pick_inline_image_url(
    attrs: Dict[str, Optional[str]], base_url: Optional[str]
) -> Optional[str]:
    candidate = None
    for key in _INLINE_IMAGE_ATTR_PRIORITY:
        value = attrs.get(key)
        if not value:
            continue
        if key in _IMG_SRCSET_ATTRS:
            parsed = _parse_srcset(value)
            candidate = parsed[0] if parsed else None
        else:
            candidate = value
        if candidate:
            break
    if not candidate:
        candidate = attrs.get("src")
    if not candidate:
        return None
    candidate = unescape(candidate)
    return _normalize_image_url(candidate, base_url)


def _img_tag_to_markdown(tag: str, base_url: Optional[str]) -> str:
    attrs = _parse_img_attributes(tag)
    if not attrs:
        return tag
    url = _pick_inline_image_url(attrs, base_url)
    if not url:
        return tag
    safe_url = escape(url, quote=False)
    return f"![]({safe_url})"


def _rewrite_img_tag(tag: str) -> str:
    match = re.match(r"<img\b(.*?)(/?)\s*>", tag, re.IGNORECASE | re.DOTALL)
    if not match:
        return tag
    attrs_raw = match.group(1) or ""
    self_closing = bool(match.group(2)) or tag.rstrip().endswith("/>")

    attrs: List[List[Optional[str]]] = []
    index: Dict[str, int] = {}
    for attr_match in _IMG_ATTR_RE.finditer(attrs_raw):
        name = attr_match.group(1)
        value = attr_match.group(2) or attr_match.group(3) or attr_match.group(4)
        if not name:
            continue
        lower = name.lower()
        attrs.append([name, value])
        if lower not in index:
            index[lower] = len(attrs) - 1

    def _get_value(key: str) -> Optional[str]:
        idx = index.get(key)
        if idx is None:
            return None
        return attrs[idx][1]

    def _set_value(key: str, value: str) -> None:
        idx = index.get(key)
        if idx is None:
            attrs.append([key, value])
            index[key] = len(attrs) - 1
        else:
            attrs[idx][1] = value

    candidate = None
    for key in _INLINE_IMAGE_ATTR_PRIORITY:
        value = _get_value(key)
        if not value:
            continue
        if key in _IMG_SRCSET_ATTRS:
            parsed = _parse_srcset(value)
            candidate = parsed[0] if parsed else None
        else:
            candidate = value
        if candidate:
            break

    if candidate:
        src_value = _get_value("src")
        if not src_value or _is_placeholder(src_value) or src_value != candidate:
            _set_value("src", candidate)

    formatted_attrs: List[str] = []
    for name, value in attrs:
        if value is None:
            formatted_attrs.append(name)
        else:
            safe = str(value).replace('"', "&quot;")
            formatted_attrs.append(f'{name}="{safe}"')

    attr_text = " " + " ".join(formatted_attrs) if formatted_attrs else ""
    closing = " />" if self_closing else ">"
    return f"<img{attr_text}{closing}"


def _rewrite_img_tags(html: str) -> str:
    return _IMG_TAG_RE.sub(lambda m: _rewrite_img_tag(m.group(0)), html)


def _inline_markdown_images(html: str, base_url: Optional[str]) -> str:
    return _IMG_TAG_RE.sub(lambda m: _img_tag_to_markdown(m.group(0), base_url), html)


def _promote_inline_images(html: str, url: Optional[str]) -> str:
    html_for_images = html
    if url and "mp.weixin.qq.com" in url:
        content = _extract_wechat_content(html)
        if content:
            title = _extract_title(html)
            head = f"<head><title>{escape(title)}</title></head>" if title else ""
            html_for_images = f"<html>{head}<body>{content}</body></html>"
    html_for_images = _rewrite_img_tags(html_for_images)
    return _inline_markdown_images(html_for_images, url)


def _collect_style_urls(html: str, base_url: Optional[str]) -> List[str]:
    urls: List[str] = []
    for match in _STYLE_URL_RE.findall(html):
        if isinstance(match, tuple):
            match = next((item for item in match if item), "")
        value = str(match).strip().strip("'\"")
        normalized = _normalize_image_url(value, base_url)
        if normalized:
            urls.append(normalized)
    return urls


_IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".bmp",
    ".tiff",
    ".tif",
    ".avif",
    ".svg",
}


def _looks_like_image_url(url: str) -> bool:
    lowered = url.lower()
    if any(lowered.endswith(ext) for ext in _IMAGE_EXTENSIONS):
        return True
    if "wx_fmt=" in lowered:
        return True
    return False


def _collect_image_urls_from_text(html: str, base_url: Optional[str]) -> List[str]:
    urls: List[str] = []
    for match in _ABS_URL_RE.findall(html):
        if not _looks_like_image_url(match):
            continue
        normalized = _normalize_image_url(match, base_url)
        if normalized:
            urls.append(normalized)
    return urls


class _ImageCollector(HTMLParser):
    def __init__(self, base_url: Optional[str]) -> None:
        super().__init__()
        self.base_url = base_url
        self.images: List[str] = []

    def handle_starttag(self, tag, attrs):
        if tag != "img":
            return
        attr_map = {key: value for key, value in attrs}

        for key in _IMG_SRCSET_ATTRS:
            if key in attr_map and attr_map[key]:
                for candidate in _parse_srcset(attr_map[key]):
                    normalized = _normalize_image_url(candidate, self.base_url)
                    if normalized:
                        self.images.append(normalized)

        for key in _IMG_ATTRS:
            if key in attr_map and attr_map[key]:
                normalized = _normalize_image_url(attr_map[key], self.base_url)
                if normalized:
                    self.images.append(normalized)
                break


def collect_images(html: str, url: Optional[str]) -> List[str]:
    collector = _ImageCollector(url)
    collector.feed(html)
    collector.images.extend(_collect_image_urls_from_text(html, url))
    collector.images.extend(_collect_style_urls(html, url))
    # preserve order but drop duplicates
    seen = set()
    images = []
    for img in collector.images:
        if img in seen:
            continue
        seen.add(img)
        images.append(img)
    return images


_VIDEO_EXTENSIONS = {
    ".mp4",
    ".m3u8",
    ".webm",
    ".mov",
    ".m4v",
    ".mpeg",
    ".mpg",
    ".ogv",
}

_VIDEO_META_KEYS = {
    "og:video",
    "og:video:url",
    "og:video:secure_url",
    "twitter:player:stream",
    "twitter:player",
}

_VIDEO_TAGS = {"video", "source"}
_VIDEO_ATTRS = {"src", "data-src", "data-original", "data-url"}

_VIDEO_BLOCK_RE = re.compile(r"<video\b[^>]*>.*?</video>", re.IGNORECASE | re.DOTALL)
_VIDEO_TAG_RE = re.compile(r"<video\b[^>]*>", re.IGNORECASE | re.DOTALL)
_SOURCE_TAG_RE = re.compile(r"<source\b[^>]*>", re.IGNORECASE | re.DOTALL)


def _is_placeholder_media(src: str) -> bool:
    lowered = src.strip().lower()
    return (
        _is_placeholder(src)
        or lowered.startswith("blob:")
        or lowered.startswith("mediastream:")
        or lowered.startswith("javascript:")
    )


def _normalize_media_url(value: str, base_url: Optional[str]) -> Optional[str]:
    src = (value or "").strip()
    if not src or _is_placeholder_media(src):
        return None
    if base_url:
        src = urljoin(base_url, src)
    return src


def _extract_media_urls_from_tag(
    tag: str, base_url: Optional[str]
) -> List[str]:
    attrs = _parse_tag_attributes(tag)
    urls: List[str] = []
    for key in _VIDEO_ATTRS:
        value = attrs.get(key)
        if not value:
            continue
        normalized = _normalize_media_url(value, base_url)
        if normalized:
            urls.append(normalized)
            break
    return urls


def _inline_video_placeholders(html: str, base_url: Optional[str]) -> str:
    def _format(urls: List[str]) -> str:
        if not urls:
            return ""
        seen = set()
        lines = []
        for url in urls:
            if url in seen:
                continue
            seen.add(url)
            safe_url = escape(url, quote=False)
            lines.append(f"[Video] {safe_url}")
        return "\n".join(lines)

    def _replace_block(match: re.Match) -> str:
        block = match.group(0)
        urls = []
        urls.extend(_extract_media_urls_from_tag(block, base_url))
        for src_tag in _SOURCE_TAG_RE.finditer(block):
            urls.extend(_extract_media_urls_from_tag(src_tag.group(0), base_url))
        formatted = _format(urls)
        return formatted or block

    def _replace_tag(match: re.Match) -> str:
        tag = match.group(0)
        urls = _extract_media_urls_from_tag(tag, base_url)
        formatted = _format(urls)
        return formatted or tag

    html = _VIDEO_BLOCK_RE.sub(_replace_block, html)
    html = _VIDEO_TAG_RE.sub(_replace_tag, html)
    return html


def _looks_like_video_url(url: str) -> bool:
    lowered = url.lower()
    base = lowered.split("?", 1)[0].split("#", 1)[0]
    if any(base.endswith(ext) for ext in _VIDEO_EXTENSIONS):
        return True
    if "video.twimg.com" in lowered:
        return True
    if "twimg.com" in lowered and "/video/" in lowered:
        return True
    return False


def _collect_video_urls_from_text(html: str, base_url: Optional[str]) -> List[str]:
    urls: List[str] = []
    for match in _ABS_URL_RE.findall(html):
        if not _looks_like_video_url(match):
            continue
        normalized = _normalize_media_url(match, base_url)
        if normalized:
            urls.append(normalized)
    return urls


class _VideoCollector(HTMLParser):
    def __init__(self, base_url: Optional[str]) -> None:
        super().__init__()
        self.base_url = base_url
        self.videos: List[str] = []

    def handle_starttag(self, tag, attrs):
        tag_lower = tag.lower()
        attr_map = {key.lower(): value for key, value in attrs}

        if tag_lower == "meta":
            key = attr_map.get("property") or attr_map.get("name")
            if key and key.lower() in _VIDEO_META_KEYS:
                content = attr_map.get("content")
                normalized = _normalize_media_url(content, self.base_url)
                if normalized:
                    self.videos.append(normalized)
            return

        if tag_lower not in _VIDEO_TAGS:
            return

        for key in _VIDEO_ATTRS:
            value = attr_map.get(key)
            if not value:
                continue
            normalized = _normalize_media_url(value, self.base_url)
            if normalized:
                self.videos.append(normalized)
            break


def collect_videos(html: str, url: Optional[str]) -> List[str]:
    collector = _VideoCollector(url)
    collector.feed(html)
    collector.videos.extend(_collect_video_urls_from_text(html, url))
    # preserve order but drop duplicates
    seen = set()
    videos = []
    for vid in collector.videos:
        if vid in seen:
            continue
        seen.add(vid)
        videos.append(vid)
    return filter_videos_for_url(url, videos)


def _hostname(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def filter_videos_for_url(url: Optional[str], videos: List[str]) -> List[str]:
    if not url or not videos:
        return videos
    host = _hostname(url)
    if host.endswith("x.com") or host.endswith("twitter.com"):
        allowed_hosts = {"video.twimg.com"}
        filtered = []
        for vid in videos:
            vhost = _hostname(vid)
            if vhost in allowed_hosts:
                filtered.append(vid)
        return filtered
    return videos


class _WechatContentCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self._capture = False
        self._depth = 0
        self._parts: List[str] = []

    def handle_starttag(self, tag, attrs):
        tag_lower = tag.lower()
        if not self._capture:
            if tag_lower == "div" and any(
                key.lower() == "id" and value == "js_content" for key, value in attrs
            ):
                self._capture = True
                self._depth = 1
            return

        start = self.get_starttag_text() or f"<{tag}>"
        self._parts.append(start)
        if tag_lower not in _VOID_TAGS:
            self._depth += 1

    def handle_startendtag(self, tag, attrs):
        if not self._capture:
            return
        start = self.get_starttag_text() or f"<{tag} />"
        self._parts.append(start)

    def handle_endtag(self, tag):
        if not self._capture:
            return
        tag_lower = tag.lower()
        if tag_lower in _VOID_TAGS:
            return
        self._depth -= 1
        if self._depth <= 0:
            self._capture = False
            return
        self._parts.append(f"</{tag}>")

    def handle_data(self, data):
        if self._capture:
            self._parts.append(data)

    def handle_entityref(self, name):
        if self._capture:
            self._parts.append(f"&{name};")

    def handle_charref(self, name):
        if self._capture:
            self._parts.append(f"&#{name};")

    def get_html(self) -> Optional[str]:
        html = "".join(self._parts).strip()
        return html or None


def _extract_wechat_content(html: str) -> Optional[str]:
    parser = _WechatContentCollector()
    parser.feed(html)
    return parser.get_html()


class _DivClassCollector(HTMLParser):
    def __init__(self, class_name: str) -> None:
        super().__init__(convert_charrefs=False)
        self._class_name = class_name
        self._capture = False
        self._depth = 0
        self._parts: List[str] = []

    def _has_class(self, attrs) -> bool:
        for key, value in attrs:
            if key.lower() == "class" and value:
                classes = value.split()
                return self._class_name in classes
        return False

    def handle_starttag(self, tag, attrs):
        tag_lower = tag.lower()
        if not self._capture:
            if tag_lower == "div" and self._has_class(attrs):
                self._capture = True
                self._depth = 1
                start = self.get_starttag_text() or f"<{tag}>"
                self._parts.append(start)
            return

        start = self.get_starttag_text() or f"<{tag}>"
        self._parts.append(start)
        if tag_lower not in _VOID_TAGS:
            self._depth += 1

    def handle_startendtag(self, tag, attrs):
        if not self._capture:
            return
        start = self.get_starttag_text() or f"<{tag} />"
        self._parts.append(start)

    def handle_endtag(self, tag):
        if not self._capture:
            return
        tag_lower = tag.lower()
        if tag_lower in _VOID_TAGS:
            return
        self._depth -= 1
        if self._depth <= 0:
            self._capture = False
            return
        self._parts.append(f"</{tag}>")

    def handle_data(self, data):
        if self._capture:
            self._parts.append(data)

    def handle_entityref(self, name):
        if self._capture:
            self._parts.append(f"&{name};")

    def handle_charref(self, name):
        if self._capture:
            self._parts.append(f"&#{name};")

    def get_html(self) -> Optional[str]:
        html = "".join(self._parts).strip()
        return html or None


def _extract_div_by_class(html: str, class_name: str) -> Optional[str]:
    parser = _DivClassCollector(class_name)
    parser.feed(html)
    return parser.get_html()


def _narrow_book118_html(html: str, url: Optional[str]) -> str:
    if not url or "book118.com" not in url:
        return html
    content = _extract_div_by_class(html, "article")
    if content:
        title = _extract_title(html)
        head = f"<head><title>{escape(title)}</title></head>" if title else ""
        return f"<html>{head}<body>{content}</body></html>"
    return html


def _collect_wechat_images(html: str, url: Optional[str]) -> List[str]:
    if not url or "mp.weixin.qq.com" not in url:
        return []

    segment = _extract_wechat_content(html) or html
    segment = unescape(segment)

    images: List[str] = []

    for srcset in _WECHAT_SRCSET_RE.findall(segment):
        for candidate in _parse_srcset(srcset):
            normalized = _normalize_image_url(candidate, url)
            if normalized:
                images.append(normalized)

    for src in _WECHAT_SRC_RE.findall(segment):
        normalized = _normalize_image_url(src, url)
        if normalized:
            images.append(normalized)

    images.extend(_collect_style_urls(segment, url))
    images.extend(_collect_image_urls_from_text(segment, url))

    # preserve order but drop duplicates
    seen = set()
    deduped = []
    for img in images:
        if img in seen:
            continue
        seen.add(img)
        deduped.append(img)
    return deduped


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


def extract_text_and_metadata(
    html: str, url: Optional[str], config: ExtractConfig
) -> Tuple[Optional[str], Dict[str, Optional[str]]]:
    fmt = _normalize_output_format(config.output_format)
    output_format = "markdown" if config.inline_images else fmt

    html_for_extract = _narrow_book118_html(html, url)
    if config.inline_images:
        html_for_extract = _promote_inline_images(html_for_extract, url)
    if config.inline_videos:
        html_for_extract = _inline_video_placeholders(html_for_extract, url)

    text, doc = _run_trafilatura(html_for_extract, url, config, output_format)
    meta = _meta_from_document(doc, url) if config.with_metadata else {}

    if url and "huanqiu.com" in url:
        needs_fallback = not text or len(text.strip()) < config.min_text_len
        if not needs_fallback and text:
            lowered = text.lower()
            needs_fallback = any(marker in lowered for marker in _HUANQIU_BLOCK_MARKERS)
        if needs_fallback:
            fallback_text, fallback_doc = _extract_huanqiu(
                html, url, config, output_format
            )
            if fallback_text:
                text = fallback_text
                if config.with_metadata and not doc and fallback_doc:
                    meta = _meta_from_document(fallback_doc, url)

    if config.with_metadata and not meta and doc is None:
        meta = extract_metadata_from_html(html, url)

    return text, meta


def extract_from_html(html: str, url: Optional[str], config: ExtractConfig) -> Optional[str]:
    text, _ = extract_text_and_metadata(html, url, config)
    return text
