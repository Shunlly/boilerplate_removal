# trafi-pipeline

一个围绕 trafilatura 的“组合式”抽取管线：
- 对 JS 渲染正文的站点：先渲染再抽取
- 对列表/信息流页面：先发现详情页链接，再抽取正文
- 代理可选开启

## 安装
```bash
pip install trafi-pipeline
```

可选依赖：
```bash
pip install "trafi-pipeline[http]"      # 使用 httpx
pip install "trafi-pipeline[render]"    # 使用 Playwright 渲染
```
Playwright 首次使用需要安装浏览器：
```bash
python -m playwright install chromium
```

## 快速使用
```python
from trafipipe import Pipeline, PipelineConfig

pipeline = Pipeline(PipelineConfig())
result = pipeline.extract_url("https://example.com/article")
print(result.text)
```

带代理与自动渲染：
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

pipeline = Pipeline(cfg)
result = pipeline.extract_url("https://example.com/article")
```

批量测试集（WeChat Cookie 走环境变量，避免写入代码）：
```bash
WECHAT_COOKIE="key=value; key2=value2" \
WECHAT_REFERER="https://mp.weixin.qq.com/" \
PYTHONPATH=src python scripts/run_dataset.py
```

保留图片（可选）：
```python
cfg = PipelineConfig()
cfg.extract.keep_images = True
cfg.extract.append_images = True  # 默认 True，会在正文末尾附上图片 URL 列表
result = Pipeline(cfg).extract_url("https://example.com/article")
print(result.images)  # 结构化图片列表
```

按原位置插入图片（可选）：
```python
cfg = PipelineConfig()
cfg.extract.keep_images = True
cfg.extract.inline_images = True  # 输出为 markdown，图片以 ![](url) 形式就地插入
cfg.extract.append_images = False  # 避免重复追加
result = Pipeline(cfg).extract_url("https://example.com/article")
```

输出格式（可选）：
```python
cfg = PipelineConfig()
cfg.extract.output_format = "md"   # 或 "txt"
```

说明：
- `inline_images=True` 且 `output_format="txt"` 时，会把 `![](url)` 转为 `[Image] url` 的纯文本形式。

元数据字段（ExtractResult）：
- `title`：标题
- `source`：来源站点/来源名（trafilatura 元数据）
- `elapsed_ms`：本次抽取耗时（毫秒）

## CLI
```bash
trafipipe extract https://example.com/article
trafipipe crawl https://example.com/list --max-pages 50 --max-depth 2
```

## 发布到 PyPI
```bash
python -m build
python -m twine upload dist/*
```

> 备注：发布前请修改 `pyproject.toml` 中的作者信息和包名。
