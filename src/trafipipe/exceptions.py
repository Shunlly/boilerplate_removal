from typing import Optional


class TrafiPipeError(Exception):
    pass


class FetchError(TrafiPipeError):
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class RenderError(TrafiPipeError):
    pass


class RenderUnavailable(RenderError):
    pass
