# trafi-pipeline

基于 trafilatura 的“组合式”网页正文抽取管线：先抓取/渲染，再抽取；支持列表页发现详情页，再批量抽取。

## 特性
- 自动渲染策略：`auto | always | never`，正文过短或抓取失败时可自动切换渲染
- 列表页爬取：按深度与页数限制发现详情页链接
- 代理支持：抓取/渲染分别配置代理
- 图片处理：保留图片、追加图片列表、或原位插入（Markdown）
- 元数据：标题、来源站点、耗时等

## 安装
```bash
pip install trafi-pipeline
```

可选依赖：
```bash
pip install "trafi-pipeline[http]"      # 使用 httpx
pip install "trafi-pipeline[render]"    # 使用 Playwright 进行渲染
```

首次使用 Playwright 需要安装浏览器：
```bash
python -m playwright install chromium
```

## 快速开始
```python
from trafipipe import Pipeline, PipelineConfig

pipeline = Pipeline(PipelineConfig())
result = pipeline.extract_url("https://example.com/article")
print(result.text)
```

返回字段（`ExtractResult`）：
- `text`：正文
- `title`：标题
- `source`：来源站点
- `images`：图片 URL 列表
- `used_render`：是否使用渲染
- `elapsed_ms`：耗时（毫秒）
- `fetch_ms`：抓取耗时（毫秒）
- `render_ms`：渲染耗时（毫秒）
- `extract_ms`：正文抽取耗时（毫秒）
- `image_ms`：图片收集耗时（毫秒）
- `error`：错误信息（如有）

## 常见配置
### 代理与渲染
```python
from trafipipe import Pipeline, PipelineConfig, ProxyConfig

cfg = PipelineConfig()
cfg.fetch.proxy = ProxyConfig(http="http://user:pass@host:port", https="http://user:pass@host:port")
cfg.render.proxy = ProxyConfig(server="http://user:pass@host:port")
cfg.render.extra_headers = {
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://mp.weixin.qq.com/",
}
cfg.render.cookies = [
    {"name": "your_cookie", "value": "xxx", "domain": ".mp.weixin.qq.com", "path": "/"}
]
cfg.render.reuse_context = True  # 批量渲染时复用 context 以提速

pipeline = Pipeline(cfg)
result = pipeline.extract_url("https://example.com/article")
```

### 图片保留与输出格式
```python
cfg = PipelineConfig()
cfg.extract.keep_images = True
cfg.extract.append_images = True   # 在正文末尾追加 [Images] 列表
cfg.extract.inline_images = False  # 设为 True 时输出 Markdown 并原位插入图片
cfg.extract.output_format = "txt"  # "txt" 或 "md"
```

说明：
- 当 `inline_images=True` 且 `output_format="txt"` 时，会把 `![](url)` 转为 `[Image] url`。

### 微信文章图片（mp.weixin.qq.com）
```python
from trafipipe import Pipeline, PipelineConfig

cfg = PipelineConfig()
cfg.extract.keep_images = True
cfg.extract.append_images = True
cfg.render.mode = "auto"  # 如图片仍缺失可改为 "always"
cfg.render.extra_headers = {"Referer": "https://mp.weixin.qq.com/"}
cfg.render.cookies = [
    {"name": "your_cookie", "value": "xxx", "domain": ".mp.weixin.qq.com", "path": "/"}
]

result = Pipeline(cfg).extract_url("https://mp.weixin.qq.com/s/xxxxxx")
print(result.images)
```

### 列表页发现链接并抽取
```python
from trafipipe import Pipeline, PipelineConfig

cfg = PipelineConfig()
cfg.crawl.max_pages = 50
cfg.crawl.max_depth = 2
cfg.crawl.max_workers = 4  # 并发抓取列表页

pipeline = Pipeline(cfg)
urls = pipeline.crawl(["https://example.com/list"])
results = [pipeline.extract_url(u) for u in urls]
```

## CLI
```bash
trafipipe extract https://example.com/article
trafipipe crawl https://example.com/list --max-pages 50 --max-depth 2 --workers 4
```

## 开发
```bash
pip install -e ".[dev]"
pytest
ruff check .
```

## 性能基准
```bash
python doc/benchmark.py --file doc/urls.txt --render auto --repeat 1
python doc/benchmark.py --file doc/urls.txt --format csv --summary > report.csv
python doc/benchmark.py --file doc/urls.txt --format json --summary > report.json
```

## 发布到 PyPI
```bash
python -m build
python -m twine upload dist/*
```

> 发布前请更新 `pyproject.toml` 的包名与作者信息。
