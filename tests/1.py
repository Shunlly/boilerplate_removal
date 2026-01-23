from trafipipe import Pipeline, PipelineConfig

cfg = PipelineConfig()
cfg.extract.keep_images = True
cfg.extract.inline_images = True   # 关键
cfg.extract.append_images = False  # 避免重复追加
cfg.extract.output_format = "md"

r = Pipeline(cfg).extract_url("https://mil.huanqiu.com/article/4PcbLh4GZUP")
print(r.text)
print(r.images)
print(r.source)
print(r.time)
