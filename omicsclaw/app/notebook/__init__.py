"""Native notebook backend for OmicsClaw app/web frontends.

Provides the shared `/notebook/*` FastAPI router used by OmicsClaw-App and
any browser/Electron surface that targets `omicsclaw.app.server`.
"""

from .router import router

__all__ = ["router"]
