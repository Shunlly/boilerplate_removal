class TrafiPipeError(Exception):
    pass


class FetchError(TrafiPipeError):
    pass


class RenderError(TrafiPipeError):
    pass


class RenderUnavailable(RenderError):
    pass
