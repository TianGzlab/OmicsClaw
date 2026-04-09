"""FastAPI Router for autoagent harness evolution.

Provides SSE-based streaming endpoints for the harness evolution loop.
All endpoints are prefixed with ``/autoagent``.

Mount this router in the main app server with a single line:

    from omicsclaw.autoagent.api import router as autoagent_router
    app.include_router(autoagent_router)
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, SecretStr

from omicsclaw.autoagent.errors import OptimizationCancelled
from omicsclaw.autoagent.search_space import build_method_surface

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/autoagent", tags=["autoagent"])

_sessions: dict[str, "OptimizeSessionRuntime"] = {}

# Completed sessions are kept for this many seconds so /status and
# /results can still query them, then reaped to prevent memory leak.
from collections import deque

from omicsclaw.autoagent.constants import (
    API_RATE_LIMIT_PER_MINUTE,
    SESSION_TTL_SECONDS as _SESSION_TTL_SECONDS,
)

# Simple sliding-window rate limiter for /start endpoint.
_start_timestamps: deque[float] = deque()
_rate_lock = threading.Lock()


def _check_rate_limit() -> None:
    """Raise HTTP 429 if /start request rate exceeds the limit."""
    now = time.monotonic()
    cutoff = now - 60.0
    with _rate_lock:
        while _start_timestamps and _start_timestamps[0] < cutoff:
            _start_timestamps.popleft()
        if len(_start_timestamps) >= API_RATE_LIMIT_PER_MINUTE:
            raise HTTPException(
                429,
                detail=f"Rate limit exceeded: max {API_RATE_LIMIT_PER_MINUTE} optimization starts per minute.",
            )
        _start_timestamps.append(now)


@dataclass
class OptimizeSessionRuntime:
    session_id: str
    loop: asyncio.AbstractEventLoop
    # Queue is created via __post_init__ to guarantee it belongs to the
    # running event loop.  Do NOT use default_factory=asyncio.Queue here.
    queue: asyncio.Queue[dict[str, Any]] = field(init=False)

    def __post_init__(self) -> None:
        self.queue = asyncio.Queue()
    cancel_event: threading.Event = field(default_factory=threading.Event)
    status: str = "running"
    result: dict[str, Any] | None = None
    error: str | None = None
    worker: threading.Thread | None = None
    finished_at: float = 0.0  # time.monotonic() when terminal state reached
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _finished_enqueued: bool = False
    _terminal_event: str | None = None

    def emit(self, event_type: str, data: dict[str, Any]) -> None:
        if event_type in {"done", "error"}:
            with self._lock:
                if self._terminal_event is None:
                    self._terminal_event = event_type
                else:
                    return
        self._submit_to_loop(
            self._enqueue_event,
            {"type": event_type, "data": data},
        )

    def request_cancel(self) -> str:
        with self._lock:
            if self.status in {"done", "error", "cancelled"}:
                return self.status
            self.cancel_event.set()
            self.status = "cancelling"
            return self.status

    def mark_done(self, result: dict[str, Any]) -> None:
        with self._lock:
            if not isinstance(result, dict) or "success" not in result:
                logger.warning(
                    "mark_done received malformed result (missing 'success' key), wrapping"
                )
                result = {"success": False, "error": "Malformed result", "raw": result}
            self.result = result
            self.status = "done"
            self.finished_at = time.monotonic()
        self._finish()

    def mark_cancelled(self, message: str = "Optimization cancelled") -> None:
        with self._lock:
            self.error = message
            self.status = "cancelled"
            self.finished_at = time.monotonic()
        self._finish()

    def mark_error(self, message: str, emit_event: bool = True) -> None:
        should_emit = False
        with self._lock:
            self.error = message
            self.status = "error"
            self.finished_at = time.monotonic()
            if emit_event and self._terminal_event is None:
                self._terminal_event = "error"
                should_emit = True
        if should_emit:
            self._submit_to_loop(
                self._enqueue_event,
                {"type": "error", "data": {"message": message}},
            )
        self._finish()

    def snapshot(self) -> tuple[str, dict[str, Any] | None, str | None]:
        with self._lock:
            return self.status, self.result, self.error

    def _finish(self) -> None:
        self._submit_to_loop(self._enqueue_finished)

    def _submit_to_loop(self, callback: Any, *args: Any) -> None:
        """Schedule queue mutation onto the owning event loop thread."""
        try:
            self.loop.call_soon_threadsafe(callback, *args)
        except RuntimeError:
            logger.warning(
                "Optimize session %s dropped an event because the event loop is closed",
                self.session_id,
            )

    def _enqueue_finished(self) -> None:
        with self._lock:
            if self._finished_enqueued:
                return
            self._finished_enqueued = True
        self._enqueue_event({"type": "_finished", "data": {}})

    def _enqueue_event(self, event: dict[str, Any]) -> None:
        try:
            self.queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("Optimize event queue full for session %s", self.session_id)


def _resolve_session_id(candidate: str | None) -> str:
    session_id = (candidate or "").strip()
    if session_id:
        return session_id
    return str(uuid.uuid4()).replace("-", "")[:12]


def _reap_finished_sessions() -> int:
    """Remove sessions that reached a terminal state more than TTL ago.

    Called opportunistically on each ``/start`` request so no background
    task is needed.  Returns the number of reaped sessions.
    """
    now = time.monotonic()
    to_remove: list[str] = []
    for sid, rt in _sessions.items():
        if rt.finished_at > 0 and (now - rt.finished_at) > _SESSION_TTL_SECONDS:
            to_remove.append(sid)
    for sid in to_remove:
        _sessions.pop(sid, None)
    if to_remove:
        logger.debug("Reaped %d finished optimize session(s)", len(to_remove))
    return len(to_remove)


def _run_optimization_session(runtime: OptimizeSessionRuntime, req: "OptimizeRequest") -> None:
    from omicsclaw.autoagent import run_harness_evolution

    try:
        result = run_harness_evolution(
            skill_name=req.skill,
            method=req.method,
            input_path=req.input_path,
            cwd=req.cwd,
            output_dir=req.output_dir,
            max_iterations=req.max_iterations,
            fixed_params=req.fixed_params if req.fixed_params else None,
            evolution_goal=req.evolution_goal,
            surface_level=req.surface_level,
            explicit_files=req.explicit_files if req.explicit_files else None,
            auto_promote=req.auto_promote,
            llm_provider=req.provider_id or req.provider,
            llm_model=req.llm_model,
            llm_provider_config=(
                req.provider_config.to_llm_config()
                if req.provider_config is not None
                else None
            ),
            demo=req.demo,
            on_event=runtime.emit,
            cancel_event=runtime.cancel_event,
        )
    except OptimizationCancelled as exc:
        runtime.mark_cancelled(str(exc))
        return
    except Exception as exc:  # pragma: no cover - defensive server boundary
        logger.exception("Optimize session %s crashed", runtime.session_id)
        runtime.mark_error(str(exc))
        return

    if result.get("success") is False:
        runtime.mark_error(str(result.get("error") or "Harness evolution failed"))
        return

    runtime.mark_done(result)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ProviderConfig(BaseModel):
    provider: str = ""
    api_key: SecretStr = SecretStr("")
    base_url: str = ""
    model: str = ""

    def to_llm_config(self) -> dict[str, str]:
        """Export as plain dict with the api_key revealed (for internal use)."""
        return {
            "provider": self.provider,
            "api_key": self.api_key.get_secret_value(),
            "base_url": self.base_url,
            "model": self.model,
        }


class OptimizeRequest(BaseModel):
    session_id: str = ""
    skill: str
    method: str
    input_path: str = ""
    cwd: str = ""
    output_dir: str = ""
    max_iterations: int = Field(default=10, ge=1, le=100)
    max_trials: int | None = Field(default=None, exclude=True)  # deprecated alias
    fixed_params: dict[str, Any] = Field(default_factory=dict)
    evolution_goal: str = ""
    surface_level: int = Field(default=2, ge=1, le=4)
    explicit_files: list[str] = Field(default_factory=list)
    auto_promote: bool = False
    provider: str = ""  # legacy fallback
    provider_id: str = ""
    provider_config: ProviderConfig | None = None
    llm_model: str = ""
    demo: bool = False

    def model_post_init(self, __context: Any) -> None:
        if self.max_trials is not None:
            logger.warning(
                "Deprecated field 'max_trials=%d' received; "
                "use 'max_iterations' instead. Mapping to max_iterations.",
                self.max_trials,
            )
            # Only apply if max_iterations was left at the default
            if self.max_iterations == 10:
                self.max_iterations = min(max(self.max_trials, 1), 100)


class OptimizeStatusResponse(BaseModel):
    session_id: str
    status: str  # "running" | "cancelling" | "cancelled" | "done" | "error" | "not_found"
    result: dict[str, Any] | None = None
    error: str | None = None


class SaveConfigRequest(BaseModel):
    cwd: str
    skill: str
    method: str
    best_score: float | None = None
    improvement_pct: float = 0.0
    patches_accepted: int = 0
    accepted_files: list[str] = Field(default_factory=list)
    accepted_patch_commits: list[str] = Field(default_factory=list)
    evolution_goal: str = ""


# ---------------------------------------------------------------------------
# Catalog helpers
# ---------------------------------------------------------------------------

def _clean_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _build_optimizable_methods(
    skill_name: str,
    param_hints: object,
) -> list[dict[str, Any]]:
    if not isinstance(param_hints, dict):
        return []

    methods: list[dict[str, Any]] = []
    for method_name, hints in param_hints.items():
        if not isinstance(hints, dict):
            continue
        surface = build_method_surface(skill_name, str(method_name).strip(), hints)
        if not surface.tunable:
            continue
        methods.append({
            "name": surface.method,
            "params": [param.name for param in surface.tunable],
            "defaults": {param.name: param.default for param in surface.tunable},
            "tips": [param.tip for param in surface.tunable if param.tip],
            "fixed_params": [param.to_dict() for param in surface.fixed],
        })
    return methods


def _collect_skill_aliases(
    registry: Any,
    canonical_skill: str,
) -> list[str]:
    aliases: list[str] = []
    seen: set[str] = set()
    for alias, info in getattr(registry, "skills", {}).items():
        resolved = str(info.get("alias", alias))
        if resolved != canonical_skill or alias == canonical_skill or alias in seen:
            continue
        seen.add(alias)
        aliases.append(alias)
    return aliases


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/start")
async def optimize_start(req: OptimizeRequest):
    """Start a harness evolution run.

    Returns an SSE stream with events:
    - trial_start, trial_complete, trial_judgment, reasoning, progress, done, error
    """
    _check_rate_limit()
    _reap_finished_sessions()
    session_id = _resolve_session_id(req.session_id)
    if session_id in _sessions:
        raise HTTPException(409, detail=f"Session '{session_id}' already exists")

    loop = asyncio.get_running_loop()
    runtime = OptimizeSessionRuntime(session_id=session_id, loop=loop)
    worker = threading.Thread(
        target=_run_optimization_session,
        args=(runtime, req.model_copy(update={"session_id": session_id})),
        name=f"optimize-{session_id}",
        daemon=True,
    )
    runtime.worker = worker
    _sessions[session_id] = runtime
    worker.start()

    async def event_generator():
        # Emit session_id first
        yield f"event: status\ndata: {json.dumps({'session_id': session_id})}\n\n"

        try:
            while True:
                try:
                    event = await asyncio.wait_for(runtime.queue.get(), timeout=600)
                except asyncio.TimeoutError:
                    yield f"event: keep_alive\ndata: \n\n"
                    continue

                if event["type"] == "_finished":
                    break

                yield (
                    f"event: {event['type']}\n"
                    f"data: {json.dumps(event['data'], default=str)}\n\n"
                )

                if event["type"] in ("done", "error"):
                    break
        except asyncio.CancelledError:
            runtime.request_cancel()
            raise

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/status/{session_id}")
async def optimize_status(session_id: str):
    """Check the status of an optimization session."""
    _reap_finished_sessions()
    runtime = _sessions.get(session_id)
    if runtime is None:
        return OptimizeStatusResponse(session_id=session_id, status="not_found")

    status, result, error = runtime.snapshot()
    return OptimizeStatusResponse(
        session_id=session_id,
        status=status,
        result=result,
        error=error,
    )


@router.post("/abort/{session_id}")
async def optimize_abort(session_id: str):
    """Abort a running optimization session."""
    _reap_finished_sessions()
    runtime = _sessions.get(session_id)
    if runtime is None:
        raise HTTPException(404, detail=f"Session '{session_id}' not found")

    status = runtime.request_cancel()
    return {"status": status, "session_id": session_id}


@router.get("/results/{session_id}")
async def optimize_results(session_id: str):
    """Get the results of a completed optimization session."""
    _reap_finished_sessions()
    runtime = _sessions.get(session_id)
    if runtime is None:
        raise HTTPException(404, detail=f"No results for session '{session_id}'")

    status, result, error = runtime.snapshot()
    if result is None or status != "done":
        if status in {"cancelled", "cancelling"}:
            raise HTTPException(409, detail=error or f"Session '{session_id}' was cancelled")
        if status == "error":
            raise HTTPException(409, detail=error or f"Session '{session_id}' failed")
        raise HTTPException(404, detail=f"No results for session '{session_id}'")
    return result


@router.post("/promote/{session_id}")
async def promote_session(session_id: str):
    """Manually promote accepted patches from sandbox to source tree.

    Only works for completed sessions whose promotion was skipped.
    """
    from pathlib import Path
    from omicsclaw.autoagent import _check_protected_branch
    from omicsclaw.autoagent.harness_workspace import HarnessWorkspace, PromotionResult

    project_root = Path(__file__).resolve().parents[2]
    branch_warning = _check_protected_branch(project_root) or ""

    _reap_finished_sessions()
    runtime = _sessions.get(session_id)
    if runtime is None:
        raise HTTPException(404, detail=f"Session '{session_id}' not found")

    status, result, error = runtime.snapshot()
    if status != "done" or result is None:
        raise HTTPException(
            409,
            detail=f"Session must be in 'done' state to promote (current: {status})",
        )

    promotion = result.get("promotion", {})
    if isinstance(promotion, dict) and promotion.get("status") not in ("skipped",):
        raise HTTPException(
            409,
            detail=f"Promotion status is '{promotion.get('status', 'unknown')}'; "
                   f"only 'skipped' sessions can be manually promoted.",
        )

    output_dir = result.get("output_dir", "")
    accepted_files = result.get("accepted_files", [])
    if not output_dir or not accepted_files:
        return PromotionResult(
            status="not_needed",
            message="No accepted files to promote.",
        ).to_dict()

    sandbox_repo = Path(output_dir) / "sandbox_repo"
    if not sandbox_repo.is_dir():
        raise HTTPException(
            404,
            detail=f"Sandbox repo not found at {sandbox_repo}",
        )

    # Reconstruct a minimal workspace for promotion
    project_root = Path(__file__).resolve().parents[2]
    workspace = HarnessWorkspace(project_root, Path(output_dir))
    workspace._created = True
    workspace.repo_root = sandbox_repo

    # Recover accepted commit from sandbox
    try:
        import subprocess
        accepted_commit = subprocess.run(
            ["git", "rev-parse", "accepted"],
            capture_output=True, text=True, cwd=sandbox_repo, timeout=5,
        ).stdout.strip()
        workspace.accepted_commit = accepted_commit

        baseline_commit = subprocess.run(
            ["git", "rev-list", "--max-parents=0", "HEAD"],
            capture_output=True, text=True, cwd=sandbox_repo, timeout=5,
        ).stdout.strip().split("\n")[0]
        workspace.baseline_commit = baseline_commit
    except Exception as exc:
        raise HTTPException(500, detail=f"Failed to read sandbox state: {exc}")

    try:
        promo_result = workspace.promote_accepted_state(accepted_files)
    except Exception as exc:
        raise HTTPException(500, detail=f"Promotion failed: {exc}")

    # Update the session result with new promotion state
    result["promotion"] = promo_result.to_dict()

    response = promo_result.to_dict()
    if branch_warning:
        response["branch_warning"] = branch_warning
    return response


@router.post("/save-config")
async def save_evolved_config(req: SaveConfigRequest):
    """Write harness evolution summary to .omicsclaw/evolved/<skill>_<method>.json."""
    from datetime import datetime, timezone
    from pathlib import Path

    cwd = Path(req.cwd).resolve()
    if not cwd.is_dir():
        raise HTTPException(400, detail=f"Directory does not exist: {cwd}")

    config_dir = cwd / ".omicsclaw" / "evolved"
    config_dir.mkdir(parents=True, exist_ok=True)

    config_path = config_dir / f"{req.skill}_{req.method}.json"
    config_data = {
        "skill": req.skill,
        "method": req.method,
        "best_score": req.best_score,
        "improvement_pct": req.improvement_pct,
        "patches_accepted": req.patches_accepted,
        "accepted_files": req.accepted_files,
        "accepted_patch_commits": req.accepted_patch_commits,
        "evolution_goal": req.evolution_goal,
        "evolved_at": datetime.now(timezone.utc).isoformat(),
    }
    config_path.write_text(json.dumps(config_data, indent=2, default=str) + "\n")

    return {
        "path": str(config_path),
        "relative_path": f".omicsclaw/evolved/{req.skill}_{req.method}.json",
    }


@router.get("/skills")
async def optimizable_skills():
    """List all skills that support auto-evolution, with methods and param_hints."""
    from omicsclaw.autoagent.metrics_registry import get_metrics_for_skill

    # Load skill registry for param_hints
    try:
        from omicsclaw.core.registry import registry

        registry.load_all()
        primary_skills = registry.iter_primary_skills()
    except Exception as exc:
        logger.warning("Failed to load skill registry for optimize catalog: %s", exc)
        return {"skills": [], "total": 0}

    skills: list[dict[str, Any]] = []

    for skill_name, info in sorted(primary_skills, key=lambda item: item[0]):
        methods = _build_optimizable_methods(skill_name, info.get("param_hints", {}))
        if not methods:
            continue

        metrics = get_metrics_for_skill(skill_name)
        if not metrics:
            continue

        # Metric summaries
        metric_items = [
            {"name": k, "direction": v.direction, "weight": v.weight, "description": v.description}
            for k, v in metrics.items()
        ]

        skills.append({
            "skill": skill_name,
            "canonical_skill": skill_name,
            "aliases": _collect_skill_aliases(registry, skill_name),
            "description": info.get("description", ""),
            "domain": info.get("domain", ""),
            "methods": methods,
            "metrics": metric_items,
        })

    return {"skills": skills, "total": len(skills)}


@router.get("/branch-status")
async def branch_status():
    """Return the source project's git branch and protection status.

    The frontend must use this instead of checking its own workingDirectory,
    because harness evolution operates on the OmicsClaw source tree — which
    may be a different repo from the user's data project.
    """
    from pathlib import Path
    from omicsclaw.autoagent import _check_protected_branch

    project_root = Path(__file__).resolve().parents[2]
    git_dir = project_root / ".git"
    if not git_dir.exists():
        return {"is_repo": False, "branch": "", "protected": False, "reason": "", "project_root": str(project_root)}

    try:
        import subprocess
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, cwd=project_root, timeout=5,
        ).stdout.strip()
    except Exception:
        return {"is_repo": True, "branch": "", "protected": False, "reason": "", "project_root": str(project_root)}

    error = _check_protected_branch(project_root)
    return {
        "is_repo": True,
        "branch": branch,
        "protected": error is not None,
        "reason": error or "",
        "project_root": str(project_root),
    }
