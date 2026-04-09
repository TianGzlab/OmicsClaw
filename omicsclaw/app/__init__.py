"""Desktop/web app backend entrypoints for OmicsClaw."""

__all__ = ["DEFAULT_APP_API_HOST", "DEFAULT_APP_API_PORT", "app", "main"]


def __getattr__(name: str):
    if name in __all__:
        from . import server as _server

        return getattr(_server, name)
    raise AttributeError(name)
