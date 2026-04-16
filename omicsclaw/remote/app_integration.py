"""Single integration point used by ``omicsclaw/app/server.py``.

Adds one call to ``server.py`` (``register_remote_routers(app)``) instead of
seven ``include_router`` lines, keeping the legacy file untouched.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI

from omicsclaw.remote.auth import require_bearer_token
from omicsclaw.remote.routers import (
    artifacts,
    connections,
    datasets,
    env,
    jobs,
    sessions,
)


def register_remote_routers(app: FastAPI) -> None:
    """Mount the remote control-plane routers onto ``app``.

    Every router shares the same bearer-token dependency — no back-door
    endpoints. The gate is a no-op when ``OMICSCLAW_REMOTE_AUTH_TOKEN`` is
    unset (local-dev / single-user SSH-tunnel default).
    """
    deps = [Depends(require_bearer_token)]
    app.include_router(connections.router, dependencies=deps)
    app.include_router(env.router, dependencies=deps)
    app.include_router(datasets.router, dependencies=deps)
    app.include_router(jobs.router, dependencies=deps)
    app.include_router(artifacts.router, dependencies=deps)
    app.include_router(sessions.router, dependencies=deps)
