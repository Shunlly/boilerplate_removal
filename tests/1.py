import datetime

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

print(datetime.datetime.now())
r = Pipeline(cfg).extract_url("https://linux.do")
print(r.text)
# print(r.videos)
print(r.elapsed_ms/1000, "s")
print(datetime.datetime.now())
