from .config import (
    ProxyConfig,
    FetchConfig,
    RenderConfig,
    ExtractConfig,
    CrawlConfig,
    PipelineConfig,
)

__all__ = [
    "ProxyConfig",
    "FetchConfig",
    "RenderConfig",
    "ExtractConfig",
    "CrawlConfig",
    "PipelineConfig",
    "Pipeline",
    "ExtractResult",
]

try:  # Avoid hard import on optional deps at package import time.
    from .pipeline import Pipeline, ExtractResult
except Exception as exc:  # pragma: no cover - handled by optional deps in runtime
    raise ImportError(
        "Failed to import trafipipe Pipeline. "
        "Ensure required dependencies are installed, e.g. `pip install trafilatura` "
        "and run with the project source (`PYTHONPATH=src`) or install with `pip install -e .`."
    ) from exc
