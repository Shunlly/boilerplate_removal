from __future__ import annotations

import csv
import datetime as dt
import hashlib
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

from trafipipe import Pipeline, PipelineConfig

try:
    from openpyxl import Workbook  # type: ignore
except Exception:
    Workbook = None


def _read_urls(path: Path) -> List[str]:
    urls: List[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        url = line.split()[0].strip()
        if url:
            urls.append(url)
    return urls


_SAFE_CHARS_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _slug_for_url(url: str, max_len: int = 80) -> str:
    parsed = urlparse(url)
    raw = (parsed.netloc + parsed.path).strip("/")
    if not raw:
        raw = "url"
    raw = raw.replace("/", "_")
    raw = _SAFE_CHARS_RE.sub("_", raw).strip("_.-")
    if len(raw) > max_len:
        raw = raw[:max_len].rstrip("_.-")
    digest = hashlib.md5(url.encode("utf-8")).hexdigest()[:8]
    return f"{raw}_{digest}"


def _build_config(
    *,
    render: str,
    wait_selector: Optional[str],
    block_resources: bool,
    reuse_context: bool,
    referer: Optional[str],
    keep_images: bool,
    inline_images: bool,
    keep_videos: bool,
    append_videos: bool,
) -> PipelineConfig:
    cfg = PipelineConfig()
    cfg.render.mode = render
    cfg.render.wait_selector = wait_selector
    cfg.render.block_resources = block_resources
    cfg.render.reuse_context = reuse_context
    if referer:
        cfg.render.extra_headers = {"Referer": referer}
    cfg.extract.output_format = "md"
    cfg.extract.keep_images = keep_images
    cfg.extract.inline_images = inline_images
    cfg.extract.keep_videos = keep_videos
    cfg.extract.append_videos = append_videos
    return cfg


def _write_md(path: Path, text: Optional[str]) -> None:
    content = text or ""
    path.write_text(content, encoding="utf-8")


def _summaries(rows: List[Dict[str, object]]) -> Dict[str, object]:
    total = len(rows)
    ok = sum(1 for r in rows if r.get("status") == "ok")
    err = sum(1 for r in rows if r.get("status") == "error")
    empty = sum(1 for r in rows if r.get("status") == "empty")
    elapsed = [r["elapsed_ms"] for r in rows if isinstance(r.get("elapsed_ms"), (int, float))]
    avg_elapsed = sum(elapsed) / len(elapsed) if elapsed else 0.0
    return {
        "total": total,
        "ok": ok,
        "error": err,
        "empty": empty,
        "avg_elapsed_ms": avg_elapsed,
    }


def _write_report(path: Path, rows: List[Dict[str, object]], meta: Dict[str, str]) -> None:
    summary = _summaries(rows)
    lines = [
        "# Batch Extract Report",
        "",
        f"- run_at: {meta['run_at']}",
        f"- input: {meta['input']}",
        f"- output_dir: {meta['output_dir']}",
        f"- render: {meta['render']}",
        f"- inline_images: {meta['inline_images']}",
        f"- keep_videos: {meta['keep_videos']}",
        f"- total: {summary['total']}",
        f"- ok: {summary['ok']}",
        f"- error: {summary['error']}",
        f"- empty: {summary['empty']}",
        f"- avg_elapsed_ms: {summary['avg_elapsed_ms']:.2f}",
        "",
        "## Results",
        "",
        "| idx | status | url | md_file | text_len | images | videos | error |",
        "| --- | ------ | --- | ------- | -------- | ------ | ------ | ----- |",
    ]
    for row in rows:
        err = str(row.get("error") or "")
        if len(err) > 120:
            err = err[:117] + "..."
        lines.append(
            f"| {row.get('idx')} | {row.get('status')} | {row.get('url')} | "
            f"{row.get('md_file')} | {row.get('text_len')} | "
            f"{row.get('images')} | {row.get('videos')} | {err} |"
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_excel(path: Path, rows: List[Dict[str, object]]) -> Tuple[Path, bool]:
    headers = [
        "idx",
        "status",
        "url",
        "md_file",
        "title",
        "source",
        "text_len",
        "images",
        "videos",
        "used_render",
        "elapsed_ms",
        "fetch_ms",
        "render_ms",
        "extract_ms",
        "image_ms",
        "video_ms",
        "error",
    ]

    if Workbook is None:
        csv_path = path.with_suffix(".csv")
        with csv_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for row in rows:
                writer.writerow([row.get(h, "") for h in headers])
        return csv_path, False

    wb = Workbook()
    ws = wb.active
    ws.title = "results"
    ws.append(headers)
    for row in rows:
        ws.append([row.get(h, "") for h in headers])
    wb.save(path)
    return path, True


def run_batch(
    *,
    input_path: Path,
    out_dir: Optional[Path],
    render: str = "auto",
    wait_selector: Optional[str] = None,
    block_resources: bool = True,
    reuse_context: bool = False,
    referer: Optional[str] = None,
    keep_images: bool = True,
    inline_images: bool = True,
    keep_videos: bool = True,
    append_videos: bool = False,
    limit: Optional[int] = None,
    sleep_seconds: float = 0.0,
) -> Path:
    input_path = input_path.expanduser().resolve()
    urls = _read_urls(input_path)
    if limit:
        urls = urls[:limit]
    if not urls:
        raise SystemExit("no urls found")

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = out_dir.resolve() if out_dir else Path("outputs") / f"run-{stamp}"
    md_dir = out_dir / "md"
    md_dir.mkdir(parents=True, exist_ok=True)

    cfg = _build_config(
        render=render,
        wait_selector=wait_selector,
        block_resources=block_resources,
        reuse_context=reuse_context,
        referer=referer,
        keep_images=keep_images,
        inline_images=inline_images,
        keep_videos=keep_videos,
        append_videos=append_videos,
    )
    pipeline = Pipeline(cfg)

    rows: List[Dict[str, object]] = []
    for idx, url in enumerate(urls, start=1):
        slug = _slug_for_url(url)
        md_name = f"{idx:04d}_{slug}.md"
        md_path = md_dir / md_name
        result = pipeline.extract_url(url)
        _write_md(md_path, result.text)

        status = "ok" if result.text else ("error" if result.error else "empty")
        rows.append(
            {
                "idx": idx,
                "status": status,
                "url": url,
                "md_file": md_path.relative_to(out_dir).as_posix(),
                "title": result.title,
                "source": result.source,
                "text_len": len(result.text) if result.text else 0,
                "images": len(result.images) if result.images else 0,
                "videos": len(result.videos) if result.videos else 0,
                "used_render": result.used_render,
                "elapsed_ms": result.elapsed_ms,
                "fetch_ms": result.fetch_ms,
                "render_ms": result.render_ms,
                "extract_ms": result.extract_ms,
                "image_ms": result.image_ms,
                "video_ms": result.video_ms,
                "error": result.error,
            }
        )

        if sleep_seconds:
            time.sleep(sleep_seconds)

    report_path = out_dir / "report.md"
    excel_path = out_dir / "report.xlsx"
    meta = {
        "run_at": stamp,
        "input": str(input_path),
        "output_dir": str(out_dir),
        "render": render,
        "inline_images": str(inline_images),
        "keep_videos": str(keep_videos),
    }
    _write_report(report_path, rows, meta)
    final_excel, is_xlsx = _write_excel(excel_path, rows)

    print(f"done: {len(rows)} urls")
    print(f"md_dir: {md_dir}")
    print(f"report: {report_path}")
    if is_xlsx:
        print(f"excel: {final_excel}")
    else:
        print(f"excel: openpyxl not installed, wrote csv instead: {final_excel}")

    return out_dir


if __name__ == "__main__":
    # Fill these variables, then run in the IDE.
    input_path = Path("urls.txt")
    out_dir = None  # e.g. Path("outputs/my-run")

    render = "always"
    wait_selector = "article"
    block_resources = True
    reuse_context = False
    referer = None  # e.g. "https://x.com/"

    keep_images = True
    inline_images = True
    keep_videos = True
    append_videos = False

    limit = None
    sleep_seconds = 0.0

    run_batch(
        input_path=input_path,
        out_dir=out_dir,
        render=render,
        wait_selector=wait_selector,
        block_resources=block_resources,
        reuse_context=reuse_context,
        referer=referer,
        keep_images=keep_images,
        inline_images=inline_images,
        keep_videos=keep_videos,
        append_videos=append_videos,
        limit=limit,
        sleep_seconds=sleep_seconds,
    )
