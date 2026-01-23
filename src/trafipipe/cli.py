from __future__ import annotations

import argparse
import sys

from .config import PipelineConfig, ProxyConfig
from .pipeline import Pipeline


def _build_config(args) -> PipelineConfig:
    cfg = PipelineConfig()
    if args.proxy:
        cfg.fetch.proxy = ProxyConfig(http=args.proxy, https=args.proxy)
        cfg.render.proxy = ProxyConfig(server=args.proxy)
    if args.render:
        cfg.render.mode = args.render
    if args.wait_selector:
        cfg.render.wait_selector = args.wait_selector
    if args.min_text_len is not None:
        cfg.extract.min_text_len = args.min_text_len
    if args.max_pages is not None:
        cfg.crawl.max_pages = args.max_pages
    if args.max_depth is not None:
        cfg.crawl.max_depth = args.max_depth
    if args.allow:
        cfg.crawl.allow_patterns = args.allow
    if args.deny:
        cfg.crawl.deny_patterns = args.deny
    return cfg


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="trafipipe")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_extract = sub.add_parser("extract", help="extract a single url")
    p_extract.add_argument("url")
    p_extract.add_argument("--render", choices=["auto", "always", "never"], default="auto")
    p_extract.add_argument("--wait-selector")
    p_extract.add_argument("--proxy")
    p_extract.add_argument("--min-text-len", type=int)

    p_crawl = sub.add_parser("crawl", help="crawl and list urls")
    p_crawl.add_argument("url", nargs="+")
    p_crawl.add_argument("--max-pages", type=int)
    p_crawl.add_argument("--max-depth", type=int)
    p_crawl.add_argument("--allow", nargs="*")
    p_crawl.add_argument("--deny", nargs="*")
    p_crawl.add_argument("--proxy")

    args = parser.parse_args(argv)
    cfg = _build_config(args)
    pipeline = Pipeline(cfg)

    if args.cmd == "extract":
        result = pipeline.extract_url(args.url)
        if result.error:
            print(result.error, file=sys.stderr)
        if result.text:
            print(result.text)
        return 0

    if args.cmd == "crawl":
        urls = pipeline.crawl(args.url)
        for u in urls:
            print(u)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
