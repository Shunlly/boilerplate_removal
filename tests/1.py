from trafipipe import Pipeline, PipelineConfig

cfg = PipelineConfig()
cfg.render.mode = "always"
cfg.render.wait_selector = "article"
# cfg.extract.keep_images = True
# cfg.extract.keep_videos = True
cfg.extract.inline_images = True   # 关键
cfg.extract.inline_videos = True   # 关键
cfg.extract.output_format = "md"
# cfg.render.extra_headers = {"Referer": "https://x.com/"}

r = Pipeline(cfg).extract_url("https://www.wondercv.com/jianlimoban/")
print(r.text)
# print(r.videos)
print(r.elapsed_ms)
