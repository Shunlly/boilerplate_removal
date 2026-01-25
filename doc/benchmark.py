from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

from trafipipe import Pipeline, PipelineConfig


def _load_urls(file_path: str | None, inline: list[str]) -> list[str]:
    urls: list[str] = []
    if file_path:
        for line in Path(file_path).read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            urls.append(line)
    urls.extend(u.strip() for u in inline if u.strip())
    return urls


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    values_sorted = sorted(values)
    k = int(math.ceil((p / 100.0) * len(values_sorted))) - 1
    k = max(0, min(k, len(values_sorted) - 1))
    return values_sorted[k]


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _summary(records: list[dict]) -> dict:
    ok_count = sum(1 for r in records if not r.get("error"))
    total = len(records)
    used_render = sum(1 for r in records if r.get("used_render"))

    def _collect(key: str) -> list[float]:
        return [v for r in records if (v := r.get(key)) is not None]

    fields = ["elapsed_ms", "fetch_ms", "render_ms", "extract_ms", "image_ms"]
    stats = {}
    for key in fields:
        values = _collect(key)
        stats[key] = {
            "count": len(values),
            "avg": _avg(values),
            "p95": _percentile(values, 95.0),
        }

    return {
        "total": total,
        "ok": ok_count,
        "error": total - ok_count,
        "used_render": used_render,
        "stats": stats,
    }


def _write_records(
    records: list[dict], fmt: str, output: str | None, summary: dict | None
) -> None:
    if fmt == "json":
        payload = {"results": records}
        if summary is not None:
            payload["summary"] = summary
        text = json.dumps(payload, ensure_ascii=False)
        if output:
            Path(output).write_text(text, encoding="utf-8")
        else:
            print(text)
        return

    if output:
        out = open(output, "w", encoding="utf-8", newline="")
        close_out = True
    else:
        out = sys.stdout
        close_out = False

    try:
        delimiter = "\t" if fmt == "tsv" else ","
        writer = csv.writer(out, delimiter=delimiter, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(
            [
                "run",
                "url",
                "ok",
                "used_render",
                "elapsed_ms",
                "fetch_ms",
                "render_ms",
                "extract_ms",
                "image_ms",
                "text_len",
                "images_count",
                "error",
            ]
        )
        for r in records:
            writer.writerow(
                [
                    r.get("run"),
                    r.get("url"),
                    int(bool(r.get("ok"))),
                    int(bool(r.get("used_render"))),
                    r.get("elapsed_ms"),
                    r.get("fetch_ms"),
                    r.get("render_ms"),
                    r.get("extract_ms"),
                    r.get("image_ms"),
                    r.get("text_len"),
                    r.get("images_count"),
                    r.get("error") or "",
                ]
            )
    finally:
        if close_out:
            out.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark trafipipe extraction timings")
    parser.add_argument("urls", nargs="*", help="URLs to extract")
    parser.add_argument("--file", help="path to a file containing URLs (one per line)")
    parser.add_argument("--render", choices=["auto", "always", "never"], default="auto")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--render-timeout", type=float, default=20.0)
    parser.add_argument("--max-bytes", type=int, default=200000)
    parser.add_argument("--keep-images", action="store_true")
    parser.add_argument("--reuse-context", action="store_true")
    parser.add_argument("--format", choices=["tsv", "csv", "json"], default="tsv")
    parser.add_argument("--output", help="write results to a file instead of stdout")
    parser.add_argument("--summary", action="store_true", help="print summary stats")

    args = parser.parse_args()
    urls = _load_urls(args.file, args.urls)
    if not urls:
        parser.error("no urls provided")

    cfg = PipelineConfig()
    cfg.render.mode = args.render
    cfg.fetch.timeout = args.timeout
    cfg.render.timeout = args.render_timeout
    cfg.fetch.max_bytes = args.max_bytes
    cfg.extract.keep_images = args.keep_images
    cfg.render.reuse_context = args.reuse_context

    pipeline = Pipeline(cfg)

    records: list[dict] = []
    run = 0
    for _ in range(max(1, args.repeat)):
        run += 1
        for url in urls:
            result = pipeline.extract_url(url)
            ok = "0" if result.error else "1"
            text_len = len(result.text or "")
            images_count = len(result.images or [])
            error = result.error or ""
            records.append(
                {
                    "run": run,
                    "url": url,
                    "ok": ok == "1",
                    "used_render": result.used_render,
                    "elapsed_ms": result.elapsed_ms,
                    "fetch_ms": result.fetch_ms,
                    "render_ms": result.render_ms,
                    "extract_ms": result.extract_ms,
                    "image_ms": result.image_ms,
                    "text_len": text_len,
                    "images_count": images_count,
                    "error": error,
                }
            )

    summary = _summary(records) if args.summary else None
    _write_records(records, args.format, args.output, summary)

    if args.summary and args.format != "json":
        print(json.dumps(summary, ensure_ascii=False), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
