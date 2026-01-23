# trafilatura 正文抽取方案（JS 渲染站点 + 列表/信息流）

## 目标
- 让 trafilatura 在「强依赖前端渲染（JS）正文」和「列表/信息流页面」场景下稳定产出正文
- 优先提高成功率与结构化质量，必要时引入无头浏览器与链接发现机制

## 一、JS 渲染正文站点方案
**核心思路**：先用无头浏览器拿到完整渲染 HTML，再交给 trafilatura 提取。

### 流程
1) 无头浏览器打开页面并等待正文元素出现
2) 获取渲染后的 HTML（包含真实正文）
3) 将 HTML 作为 `filecontent` 传给 `trafilatura.extract(...)`
4) 视质量调整抽取参数

### 参数建议
- `with_metadata=True`：保留标题/作者/日期等
- `favor_precision=True`：减少噪音（正文更干净）
- `include_tables=True`：需要表格时开启
- `include_comments=False`：默认不抽评论

### 示例（逻辑示意）
```python
html = rendered_html  # 由无头浏览器获取
text = trafilatura.extract(
    html,
    url=page_url,
    with_metadata=True,
    favor_precision=True,
    include_tables=True,
    include_comments=False
)
```

### 适用场景
- SPA / CSR / 仅渲染后才出现正文
- 需要滚动加载正文的站点

---

## 二、列表/信息流页面方案
**核心思路**：列表页不直接做“正文抽取”，只做链接发现；对详情页做正文抽取。

### 方案 A：Feed / Sitemap 优先
- 先找 RSS/Atom/JSON Feed
- 若无 Feed，再找 Sitemap
- 提取 URL 后逐一进入详情页抽取正文

### 方案 B：Crawl 兜底
- 作为实验性兜底方案（对规模化站点需谨慎）

### 方案 C：信息流/无限滚动
- 用无头浏览器滚动加载并提取新增链接
- 或直接调用其 XHR/JSON 接口拿详情页链接

---

## 三、组合式通用流程（推荐落地版）
1) **发现链接**
   - 无 Feed / Sitemap / API：使用 Crawl 或自定义站点抓取逻辑生成详情页 URL 列表

2) **抓取 HTML**
   - 先做一次普通请求拿初始 HTML
   - 若正文不在初始 HTML：无头浏览器渲染后取 HTML

3) **正文抽取**
   - `trafilatura.extract(html, url=..., favor_precision/recall, include_* ...)`

4) **质量控制**
   - `with_metadata=True` 方便后续筛选
   - 可加 `only_with_metadata=True` 进行严格过滤

---

## 选择建议
- 站点正文在源码中：直接 trafilatura 抽取
- 站点正文仅渲染后出现：无头浏览器 -> trafilatura
- 列表/信息流页面：链接发现 -> 详情页抽取

## 组合式判断条件（简化版）
- **详情页正文是否在初始 HTML 中**：不在则走无头浏览器渲染
- **无公开 API / Feed / Sitemap**：链接发现以 Crawl 或自定义抓取为主

## 提速优化清单
### 抓取层
- 先做轻量请求判断是否需要渲染，能直抓就别上无头浏览器
- 复用连接（keep-alive），设置较短超时与快速失败策略
- URL 去重与过滤，避免重复抓取与低价值路径

### 渲染层（无头浏览器）
- 复用 browser/context/page，避免频繁启动
- 拦截图片/字体/视频等静态资源请求
- 等待正文 selector 出现，避免固定 sleep
- 并发渲染限流，避免资源争用

### 抽取层（trafilatura）
- 优先 `favor_precision=True` 降噪
- 关闭不需要的内容抽取（comments/images/links）

### 管道层
- 并发处理（线程/协程/队列）并按站点分组调度
- 结果缓存与增量抓取（仅处理新增或更新 URL）

## 代理接入方案（可选）
说明：在调用阶段可按需开启代理；不启用时保持默认直连。

### 网络请求层代理
- 适用场景：抓取 HTML、列表页、Crawl
- 方式：在 HTTP 客户端（requests/httpx）配置代理

### 无头浏览器代理
- 适用场景：JS 渲染页
- 方式：在浏览器或上下文创建时配置代理

---

## 模块化与 PyPI 发布（开发版）
目标：将组合式流程做成可复用模块，并支持发布到 PyPI（可选）。

### 模块结构建议
- `PipelineConfig`：统一配置（抓取/渲染/抽取/抓取链接）
- `Pipeline`：核心入口（`extract_url` / `crawl` / `crawl_and_extract`）
- 可选依赖：`render`（Playwright）、`http`（httpx）

### 关键选项（建议暴露）
- `render.mode`：`auto | always | never`
- `extract.min_text_len`：用于判断“初始 HTML 是否已有正文”
- `proxy`：请求层与渲染层代理均为可选项

### 发布流程（简化）
1) 更新 `pyproject.toml` 元信息（包名/作者/版本）
2) `python -m build`
3) `python -m twine upload dist/*`

---

## 你可以补充的信息（便于我给出更精细方案）
- 是否有 RSS/Atom/Sitemap
- 是否无限滚动
- 详情页正文是否在初始 HTML 中
- 是否有公开 API
