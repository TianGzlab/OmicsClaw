"""Research pipeline controller — multi-agent orchestration using deepagents.

This is the core module that builds and runs the multi-agent research
pipeline. It uses deepagents' ``create_deep_agent()`` with sub-agents
configured from ``config.yaml``.

The pipeline follows these stages:
    intake → plan → research → execute → analyze → write → review

If the reviewer requests revisions, the pipeline loops back to
the writing (or execution) stage.
"""

from __future__ import annotations

import json
import logging
import os
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from omicsclaw.common.manifest import StepRecord
from omicsclaw.agents.plan_state import (
    PLAN_STATUS_APPROVED,
    PLAN_STATUS_PENDING_APPROVAL,
    PlanStateSnapshot,
    build_plan_result_payload,
    load_plan_state_from_metadata,
    save_plan_state_to_metadata,
    sync_plan_state_metadata,
)
from omicsclaw.agents.pipeline_result import (
    CompletionRunResult,
    PipelineRunResult,
    PlanRunResult,
)
from omicsclaw.core.provider_registry import get_langchain_llm
from omicsclaw.core.llm_timeout import build_llm_timeout_policy
from omicsclaw.runtime.task_store import (
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
    TASK_STATUS_IN_PROGRESS,
    TASK_STATUS_PENDING,
    TASK_STATUS_SKIPPED,
    TaskRecord,
    TaskStore,
)
from omicsclaw.runtime.hooks import build_default_lifecycle_hook_runtime
from omicsclaw.runtime.verification import (
    ARTIFACT_KIND_DIR,
    COMPLETION_STATUS_AWAITING_APPROVAL,
    COMPLETION_STATUS_FAILED,
    COMPLETION_STATUS_INCOMPLETE,
    COMPLETION_STATUS_PARTIAL,
    WORKSPACE_KIND_ANALYSIS_RUN,
    ArtifactRequirement,
    build_completion_report,
    update_workspace_manifest,
    write_completion_report,
)
from omicsclaw.version import __version__

logger = logging.getLogger(__name__)
_OMICSCLAW_ROOT = Path(__file__).resolve().parents[2]

# Suppress noisy HTTP logs from Langchain/OpenAI/httpx
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

PIPELINE_TASK_STORE_FILENAME = ".pipeline_tasks.json"
PIPELINE_CHECKPOINT_FILENAME = ".pipeline_checkpoint.json"
PIPELINE_STAGE_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "id": "intake",
        "title": "Intake",
        "description": "Parse paper/idea, build workspace",
        "owner": "orchestrator",
        "dependencies": [],
    },
    {
        "id": "plan",
        "title": "Plan",
        "description": "Generate experiment plan (plan.md)",
        "owner": "planner-agent",
        "dependencies": ["intake"],
    },
    {
        "id": "research",
        "title": "Research",
        "description": "Literature review for methods and baselines",
        "owner": "research-agent",
        "dependencies": ["plan"],
    },
    {
        "id": "execute",
        "title": "Execute",
        "description": "Run OmicsClaw skills in notebook",
        "owner": "coding-agent",
        "dependencies": ["research"],
    },
    {
        "id": "analyze",
        "title": "Analyze",
        "description": "Compute metrics, generate plots",
        "owner": "analysis-agent",
        "dependencies": ["execute"],
    },
    {
        "id": "write",
        "title": "Write",
        "description": "Draft final report (final_report.md)",
        "owner": "writing-agent",
        "dependencies": ["analyze"],
    },
    {
        "id": "review",
        "title": "Review",
        "description": "Peer review of the report",
        "owner": "reviewer-agent",
        "dependencies": ["write"],
    },
)

PIPELINE_STAGE_IDS = [stage["id"] for stage in PIPELINE_STAGE_DEFINITIONS]
PIPELINE_STAGE_INDEX = {
    stage_id: idx for idx, stage_id in enumerate(PIPELINE_STAGE_IDS)
}
PIPELINE_STAGE_DETAILS = {
    stage["id"]: stage for stage in PIPELINE_STAGE_DEFINITIONS
}
PIPELINE_AGENT_STAGE_MAP = {
    "planner-agent": "plan",
    "research-agent": "research",
    "coding-agent": "execute",
    "analysis-agent": "analyze",
    "writing-agent": "write",
    "reviewer-agent": "review",
}
PIPELINE_VERSION = __version__


def _task_summary(task: TaskRecord) -> str:
    return str(task.metadata.get("summary", "")).strip()


def _stage_started(task_store: TaskStore, stage_id: str) -> bool:
    task = task_store.get(stage_id)
    return bool(task and task.status != TASK_STATUS_PENDING)


def _get_plan_status(task_store: TaskStore) -> str:
    return _get_plan_state(task_store).status


def _set_plan_pending_approval(task_store: TaskStore) -> None:
    plan_state = _get_plan_state(task_store)
    plan_state.mark_pending_approval()
    save_plan_state_to_metadata(task_store.metadata, plan_state)


def _pipeline_task_store_path(workspace: Path) -> Path:
    return Path(workspace) / PIPELINE_TASK_STORE_FILENAME


def _checkpoint_path(workspace: Path) -> Path:
    return Path(workspace) / PIPELINE_CHECKPOINT_FILENAME


def _resolve_input_mode(pdf_path: str | None, h5ad_path: str | None) -> str:
    if pdf_path and h5ad_path:
        return "B"
    if pdf_path:
        return "A"
    return "C"


def _artifact_manifest_requirements(workspace: Path) -> list[ArtifactRequirement]:
    requirements: list[ArtifactRequirement] = []
    seen: set[str] = set()
    for base_name in ("artifacts", "figures", "tables", "figure_data"):
        base = Path(workspace) / base_name
        if not base.exists():
            continue
        for manifest_path in sorted(base.rglob("manifest.json")):
            rel_path = str(manifest_path.relative_to(workspace))
            if rel_path in seen:
                continue
            seen.add(rel_path)
            requirements.append(
                ArtifactRequirement(
                    name=f"{base_name}_manifest",
                    path=rel_path,
                    required=False,
                    description="Optional figure/table manifest discovered in the pipeline workspace.",
                )
            )
    return requirements


def _pipeline_workspace_requirements(
    workspace: Path,
    task_store: TaskStore,
    *,
    mode: str,
    awaiting_plan_approval: bool,
) -> list[ArtifactRequirement]:
    requirements = [
        ArtifactRequirement(
            name="research_request",
            path="research_request.md",
            description="Normalized research request captured during intake.",
        ),
        ArtifactRequirement(
            name="todos_projection",
            path="todos.md",
            description="Projected task store snapshot for the pipeline workspace.",
        ),
        ArtifactRequirement(
            name="workspace_manifest",
            path="manifest.json",
            description="Workspace lineage and verification ledger.",
        ),
    ]
    if mode in {"A", "B"}:
        requirements.append(
            ArtifactRequirement(
                name="paper_bundle",
                path="paper",
                kind=ARTIFACT_KIND_DIR,
                description="Structured paper extraction for PDF-backed runs.",
            )
        )
    if (
        awaiting_plan_approval
        or _stage_started(task_store, "plan")
        or any(_stage_started(task_store, stage) for stage in ("research", "execute", "analyze", "write", "review"))
    ):
        requirements.append(
            ArtifactRequirement(
                name="plan_markdown",
                path="plan.md",
                description="Planner output required for downstream execution.",
            )
        )
    if any(_stage_started(task_store, stage) for stage in ("execute", "analyze", "write", "review")):
        requirements.append(
            ArtifactRequirement(
                name="analysis_notebook",
                path="analysis.ipynb",
                description="Notebook used by the coding/analysis stages.",
            )
        )
        requirements.append(
            ArtifactRequirement(
                name="artifacts_dir",
                path="artifacts",
                kind=ARTIFACT_KIND_DIR,
                required=False,
                description="Optional directory for plots, tables, and intermediate outputs.",
            )
        )
    if _stage_started(task_store, "write") or _stage_started(task_store, "review"):
        requirements.append(
            ArtifactRequirement(
                name="final_report",
                path="final_report.md",
                description="Paper-ready report assembled by the writing stage.",
            )
        )
    if _stage_started(task_store, "review"):
        requirements.append(
            ArtifactRequirement(
                name="review_report",
                path="review_report.json",
                description="Structured reviewer output for the final report.",
            )
        )
    requirements.extend(_artifact_manifest_requirements(workspace))
    return requirements


def _review_report_validation(review_path: Path) -> tuple[list[str], list[str]]:
    if not review_path.exists():
        return [], []
    try:
        payload = json.loads(review_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return [], ["review_report.json is not valid JSON"]

    warnings: list[str] = []
    if bool(payload.get("revision_required", False)):
        warnings.append("review_report.json requests further revisions")
    if not str(payload.get("overall_assessment", "")).strip():
        warnings.append("review_report.json is missing overall_assessment")
    return warnings, []


def _build_pipeline_task_store(
    *,
    mode: str = "",
    has_pdf: bool | None = None,
) -> TaskStore:
    metadata: dict[str, Any] = {}
    if mode:
        metadata["mode"] = mode
    if has_pdf is not None:
        metadata["has_pdf"] = bool(has_pdf)

    store = TaskStore(kind="research_pipeline", metadata=metadata)
    for stage in PIPELINE_STAGE_DEFINITIONS:
        store.add_task(
            TaskRecord(
                id=stage["id"],
                title=stage["title"],
                description=stage["description"],
                owner=stage["owner"],
                dependencies=list(stage["dependencies"]),
            )
        )
    return store


def _coerce_pipeline_task_store(
    task_store: TaskStore | None,
    *,
    mode: str = "",
    has_pdf: bool | None = None,
) -> TaskStore:
    store = task_store or _build_pipeline_task_store(mode=mode, has_pdf=has_pdf)
    store.kind = "research_pipeline"

    if mode:
        store.metadata["mode"] = mode
    if has_pdf is not None:
        store.metadata["has_pdf"] = bool(has_pdf)

    canonical_tasks: list[TaskRecord] = []
    existing_ids = set(store.task_ids())
    for stage in PIPELINE_STAGE_DEFINITIONS:
        task = store.get(stage["id"])
        if task is None:
            task = TaskRecord(
                id=stage["id"],
                title=stage["title"],
                description=stage["description"],
                owner=stage["owner"],
                dependencies=list(stage["dependencies"]),
            )
        else:
            task.title = stage["title"]
            task.description = stage["description"]
            if not task.owner:
                task.owner = stage["owner"]
            if not task.dependencies:
                task.dependencies = list(stage["dependencies"])
        canonical_tasks.append(task)

    extras = [task for task in store.tasks if task.id not in PIPELINE_STAGE_IDS]
    store.tasks = canonical_tasks + extras
    if not existing_ids:
        return store
    return store


def _write_task_projection(workspace: Path, task_store: TaskStore) -> None:
    workspace = Path(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    store = _coerce_pipeline_task_store(task_store)
    _sync_plan_state_metadata(store, workspace)
    store.save(_pipeline_task_store_path(workspace))
    todos_path = workspace / "todos.md"
    todos_path.write_text(
        store.render_markdown(title="# Research Pipeline Progress"),
        encoding="utf-8",
    )
    logger.info("Updated task projection at %s", todos_path)


def _get_plan_state(task_store: TaskStore) -> PlanStateSnapshot:
    return load_plan_state_from_metadata(task_store.metadata)


def _sync_plan_state_metadata(
    task_store: TaskStore,
    workspace: Path,
) -> PlanStateSnapshot:
    return sync_plan_state_metadata(task_store.metadata, workspace)


@dataclass
class PipelineState:
    """Tracks pipeline progress across stages."""

    current_stage: str = "intake"
    completed_stages: list[str] = field(default_factory=list)
    stage_outputs: dict[str, str] = field(default_factory=dict)
    review_iterations: int = 0
    max_review_iterations: int = 3
    error: str = ""
    # Graph memory integration (optional)
    memory_client: Any = None
    task_store: TaskStore = field(default_factory=_build_pipeline_task_store)

    def __post_init__(self):
        self.task_store = _coerce_pipeline_task_store(self.task_store)
        if self.completed_stages or self.stage_outputs:
            self._hydrate_from_legacy_fields()
        self._sync_legacy_views(preferred_stage=self.current_stage)

    def record_stage(self, stage: str, output_summary: str = ""):
        """Backward-compatible shim for marking a stage complete."""
        self.mark_stage_completed(stage, summary=output_summary)

    def configure_pipeline(self, *, mode: str, has_pdf: bool) -> None:
        self.task_store = _coerce_pipeline_task_store(
            self.task_store,
            mode=mode,
            has_pdf=has_pdf,
        )
        self._sync_legacy_views(preferred_stage=self.current_stage)

    def _hydrate_from_legacy_fields(self) -> None:
        if any(task.status != TASK_STATUS_PENDING for task in self.task_store.tasks):
            return
        for stage in self.completed_stages:
            if stage in PIPELINE_STAGE_INDEX:
                self.task_store.set_task_status(
                    stage,
                    TASK_STATUS_COMPLETED,
                    summary=self.stage_outputs.get(stage, ""),
                )
        if (
            self.current_stage in PIPELINE_STAGE_INDEX
            and self.current_stage not in self.completed_stages
        ):
            self.task_store.set_task_status(
                self.current_stage,
                TASK_STATUS_IN_PROGRESS,
                summary=self.stage_outputs.get(self.current_stage, ""),
            )

    def _sync_legacy_views(self, *, preferred_stage: str = "intake") -> None:
        self.completed_stages = self.task_store.completed_task_ids()
        self.stage_outputs = {
            task.id: _task_summary(task)
            for task in self.task_store.tasks
            if _task_summary(task)
        }
        active = self.task_store.active_task()
        if active is not None:
            self.current_stage = active.id
            return
        for stage_id in reversed(PIPELINE_STAGE_IDS):
            task = self.task_store.get(stage_id)
            if task is not None and task.status != TASK_STATUS_PENDING:
                self.current_stage = stage_id
                return
        self.current_stage = (
            preferred_stage if preferred_stage in PIPELINE_STAGE_INDEX else "intake"
        )

    def _transition_previous_stage(self, next_stage: str) -> None:
        active = self.task_store.active_task()
        if active is None or active.id == next_stage:
            return
        if active.id in PIPELINE_STAGE_INDEX and PIPELINE_STAGE_INDEX[active.id] != PIPELINE_STAGE_INDEX[next_stage]:
            self.task_store.set_task_status(
                active.id,
                TASK_STATUS_COMPLETED,
                summary=_task_summary(active),
                owner=active.owner,
            )

    def mark_stage_in_progress(
        self,
        stage: str,
        *,
        summary: str = "",
        artifact_ref: str = "",
        owner: str = "",
    ) -> None:
        self.task_store = _coerce_pipeline_task_store(self.task_store)
        self._transition_previous_stage(stage)
        self.task_store.set_task_status(
            stage,
            TASK_STATUS_IN_PROGRESS,
            summary=summary,
            artifact_ref=artifact_ref,
            owner=owner or PIPELINE_STAGE_DETAILS[stage]["owner"],
        )
        self._sync_legacy_views(preferred_stage=stage)
        logger.info("Stage '%s' in progress", stage)

    def mark_stage_completed(
        self,
        stage: str,
        *,
        summary: str = "",
        artifact_ref: str = "",
        owner: str = "",
    ) -> None:
        self.task_store = _coerce_pipeline_task_store(self.task_store)
        self.task_store.set_task_status(
            stage,
            TASK_STATUS_COMPLETED,
            summary=summary,
            artifact_ref=artifact_ref,
            owner=owner or PIPELINE_STAGE_DETAILS[stage]["owner"],
        )
        self._sync_legacy_views(preferred_stage=stage)
        logger.info(
            "Stage '%s' completed (%d/%d stages done)",
            stage, len(self.completed_stages), 7,
        )

    def mark_stage_skipped(self, stage: str, *, summary: str = "") -> None:
        self.task_store = _coerce_pipeline_task_store(self.task_store)
        self.task_store.set_task_status(
            stage,
            TASK_STATUS_SKIPPED,
            summary=summary,
            owner=PIPELINE_STAGE_DETAILS[stage]["owner"],
        )
        self._sync_legacy_views(preferred_stage=stage)

    def mark_stage_failed(self, stage: str, *, summary: str = "") -> None:
        self.task_store = _coerce_pipeline_task_store(self.task_store)
        self.task_store.set_task_status(
            stage,
            TASK_STATUS_FAILED,
            summary=summary,
            owner=PIPELINE_STAGE_DETAILS[stage]["owner"],
        )
        self._sync_legacy_views(preferred_stage=stage)

    def is_stage_done(self, stage: str) -> bool:
        """Check whether a stage has already been completed."""
        task = self.task_store.get(stage)
        return bool(task and task.status in {TASK_STATUS_COMPLETED, TASK_STATUS_SKIPPED})

    def should_stop_review(self) -> bool:
        """Return True when the review loop should be forcibly terminated."""
        return self.review_iterations >= self.max_review_iterations

    def checkpoint(self, workspace: Path):
        """Write a checkpoint file to workspace for crash recovery."""
        workspace = Path(workspace)
        self.task_store = _coerce_pipeline_task_store(self.task_store)
        _write_task_projection(workspace, self.task_store)
        ckpt = {
            "current_stage": self.current_stage,
            "completed_stages": self.completed_stages,
            "stage_outputs": self.stage_outputs,
            "review_iterations": self.review_iterations,
            "task_store_path": PIPELINE_TASK_STORE_FILENAME,
            "task_store": self.task_store.to_dict(),
        }
        ckpt_path = _checkpoint_path(workspace)
        ckpt_path.write_text(json.dumps(ckpt, indent=2), encoding="utf-8")
        logger.debug("Checkpoint saved: %s", ckpt_path)

    @classmethod
    def load_checkpoint(cls, workspace: Path) -> "PipelineState | None":
        """Load a previously saved checkpoint for crash recovery.

        Returns None if no checkpoint exists or it is corrupted.
        """
        workspace = Path(workspace)
        ckpt_path = _checkpoint_path(workspace)
        task_store = TaskStore.load(_pipeline_task_store_path(workspace))

        if not ckpt_path.exists():
            if task_store is None:
                return None
            state = cls(task_store=task_store)
            logger.info(
                "Recovered pipeline state from task store: stages=%s",
                state.completed_stages,
            )
            return state
        try:
            data = json.loads(ckpt_path.read_text(encoding="utf-8"))
            if task_store is None and isinstance(data.get("task_store"), dict):
                try:
                    task_store = TaskStore.from_dict(data["task_store"])
                except (TypeError, KeyError, ValueError):
                    task_store = None
            state = cls(
                current_stage=data.get("current_stage", "intake"),
                completed_stages=data.get("completed_stages", []),
                stage_outputs=data.get("stage_outputs", {}),
                review_iterations=data.get("review_iterations", 0),
                task_store=task_store or _build_pipeline_task_store(),
            )
            logger.info(
                "Loaded checkpoint: stages=%s, review_iter=%d",
                state.completed_stages, state.review_iterations,
            )
            return state
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning("Corrupted checkpoint at %s: %s", ckpt_path, e)
            return None

    async def persist_stage(self, stage: str, output: str):
        """Persist stage output to graph memory if client is available."""
        if self.memory_client is None:
            return
        try:
            await self.memory_client.remember(
                uri=f"session://pipeline/{stage}",
                content=output[:5000],  # Cap content size
                disclosure=f"Output from pipeline stage: {stage}",
            )
        except Exception as e:
            logger.warning(f"Failed to persist stage {stage} to memory: {e}")


def _generate_todos(
    workspace: Path,
    mode: str,
    has_pdf: bool,
    task_store: TaskStore | None = None,
) -> TaskStore:
    """Project the structured pipeline task state into todos.md."""
    workspace = Path(workspace)
    store = task_store or TaskStore.load(_pipeline_task_store_path(workspace))
    store = _coerce_pipeline_task_store(store, mode=mode, has_pdf=has_pdf)
    _write_task_projection(workspace, store)
    return store



# =========================================================================
# Config loading
# =========================================================================


def _load_agent_config() -> dict[str, Any]:
    """Load sub-agent config from config.yaml."""
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _resolve_prompt_refs(config: dict[str, Any]) -> dict[str, Any]:
    """Resolve system_prompt_ref → actual prompt text."""
    from .prompts import build_prompt_refs

    refs = build_prompt_refs()
    for agent_name, agent_def in config.items():
        ref = agent_def.get("system_prompt_ref")
        if ref and ref in refs:
            agent_def["system_prompt"] = refs[ref]
            del agent_def["system_prompt_ref"]
    return config


# =========================================================================
# Agent builder
# =========================================================================


def _build_subagent_configs(
    agent_config: dict[str, Any],
    tool_registry: dict,
    get_llm_fn: Callable[[str | None], Any] | None = None,
) -> list[dict[str, Any]]:
    """Convert our YAML config into deepagents subagent format.

    Parameters
    ----------
    agent_config : dict
        Parsed config.yaml content.
    tool_registry : dict
        Mapping of tool name -> tool object.
    get_llm_fn : callable, optional
        ``pipeline._get_llm(agent_name)`` — when provided, each subagent
        receives its own LLM resolved from per-agent env vars.

    Returns
    -------
    list of dicts in deepagents subagent format
    """
    from .middleware import ToolErrorHandlerMiddleware

    subagents = []
    for agent_name, agent_def in agent_config.items():
        tool_names = agent_def.get("tools", [])
        tools = [tool_registry[t] for t in tool_names if t in tool_registry]

        subagent: dict[str, Any] = {
            "name": agent_name,
            "description": agent_def.get("description", ""),
            "tools": tools,
        }
        if "system_prompt" in agent_def:
            subagent["system_prompt"] = agent_def["system_prompt"]

        if "skills" in agent_def:
            subagent["skills"] = agent_def["skills"]
        else:
            subagent["skills"] = ["/skills/"]

        subagent["middleware"] = [ToolErrorHandlerMiddleware()]

        # Per-agent LLM override (only if env vars are set for this agent)
        if get_llm_fn is not None:
            tag = agent_name.split("-")[0].upper()
            if os.getenv(f"OC_{tag}_MODEL") or os.getenv(f"OC_{tag}_PROVIDER"):
                subagent["model"] = get_llm_fn(agent_name)

        subagents.append(subagent)
    return subagents


# =========================================================================
# Research Pipeline
# =========================================================================


class ResearchPipeline:
    """Multi-agent research pipeline using deepagents/LangGraph.

    Parameters
    ----------
    workspace_dir : str, optional
        Directory for pipeline workspace. Auto-created if needed.
    provider : str, optional
        LLM provider (uses .env default if empty).
    model : str, optional
        LLM model name override.
    """

    STAGES = PIPELINE_STAGE_IDS

    def __init__(
        self,
        workspace_dir: str | None = None,
        provider: str = "",
        model: str = "",
    ):
        from .tools import build_tool_registry
        from .prompts import get_system_prompt

        # Workspace
        if workspace_dir:
            self.workspace = Path(workspace_dir).resolve()
        else:
            self.workspace = Path.cwd() / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)

        # Config
        self.agent_config = _resolve_prompt_refs(_load_agent_config())
        self.tool_registry = build_tool_registry()
        self.system_prompt = get_system_prompt(workspace=str(self.workspace))
        self.state = PipelineState()
        self.hook_runtime = build_default_lifecycle_hook_runtime(_OMICSCLAW_ROOT)
        self.state.task_store.attach_lifecycle_runtime(
            self.hook_runtime,
            context={
                "workspace": str(self.workspace),
                "plan_kind": "research_pipeline",
                "source": "research_pipeline",
            },
        )

        # Notebook session — coding-agent uses this for experiment execution
        self.notebook_path = str(self.workspace / "analysis.ipynb")
        self._nb_session = None  # lazy-init on first run

        # LLM settings
        self.provider = provider
        self.model = model

    def _get_llm(self, agent_name: str | None = None):
        """Build an LLM instance from provider/model settings.

        Resolution order (most specific wins):

        Per-agent (only when *agent_name* is provided):
            ``OC_{AGENT}_PROVIDER``  /  ``OC_{AGENT}_MODEL``
            e.g. ``OC_PLANNER_PROVIDER=deepseek``, ``OC_CODING_MODEL=claude-sonnet-4-5``

        Pipeline-level:
            1. Constructor ``provider``/``model`` args
            2. ``OC_LLM_PROVIDER`` / ``OC_LLM_MODEL``

        Global:
            3. ``LLM_PROVIDER`` / ``OMICSCLAW_MODEL``
            4. Auto-detect from provider-specific API key env vars
            5. Provider-specific default
        """
        # --- per-agent env vars ---
        agent_provider = None
        agent_model = None
        if agent_name:
            # "planner-agent" → "PLANNER", "coding-agent" → "CODING"
            tag = agent_name.split("-")[0].upper()
            agent_provider = os.getenv(f"OC_{tag}_PROVIDER")
            agent_model = os.getenv(f"OC_{tag}_MODEL")

        requested_provider = (
            agent_provider
            or self.provider
            or os.getenv("OC_LLM_PROVIDER")
            or os.getenv("LLM_PROVIDER", "")
        )
        requested_model = (
            agent_model
            or self.model
            or os.getenv("OC_LLM_MODEL")
            or os.getenv("OMICSCLAW_MODEL")
        )
        timeout_policy = build_llm_timeout_policy(log=logger)
        return get_langchain_llm(
            provider=requested_provider or "",
            model=requested_model or "",
            base_url=str(os.getenv("LLM_BASE_URL", "") or ""),
            temperature=0.3,
            timeout=timeout_policy.as_httpx_timeout(),
            anthropic_timeout=timeout_policy.as_anthropic_timeout(),
        )

    def _build_agent(self):
        """Build the deepagents agent with OmicsClaw sub-agents.

        Architecture (adapted from EvoScientist):
        - CompositeBackend routes /skills/ to read-only skills directory
        - ToolErrorHandlerMiddleware on orchestrator + all sub-agents
        - skills=["/skills/"] enables deepagents skill discovery
        """
        from deepagents import create_deep_agent
        from deepagents.backends import CompositeBackend

        from .backends import create_sandbox_backend, create_skills_backend
        from .middleware import ToolErrorHandlerMiddleware

        llm = self._get_llm()

        # Workspace backend (sandboxed read/write + shell)
        ws_backend = create_sandbox_backend(str(self.workspace))

        # Skills backend (read-only, maps /skills/ → OmicsClaw skills/)
        project_root = str(Path(__file__).resolve().parent.parent.parent)
        sk_backend = create_skills_backend(project_root)

        # Composite backend — like EvoScientist's multi-route FS
        backend = CompositeBackend(
            default=ws_backend,
            routes={
                "/skills/": sk_backend,
            },
        )

        subagents = _build_subagent_configs(
            self.agent_config, self.tool_registry,
            get_llm_fn=self._get_llm,
        )

        # Orchestrator middleware — error handler for main agent tools
        middleware = [ToolErrorHandlerMiddleware()]

        agent = create_deep_agent(
            model=llm,
            backend=backend,
            system_prompt=self.system_prompt,
            subagents=subagents,
            middleware=middleware,
            skills=["/skills/"],
        )
        return agent

    async def run(
        self,
        idea: str,
        pdf_path: str | None = None,
        h5ad_path: str | None = None,
        on_stage: Callable[[str, str], None] | None = None,
        resume: bool = False,
        from_stage: str | None = None,
        skip_stages: list[str] | None = None,
        plan_only: bool = False,
    ) -> dict[str, Any]:
        """Execute the full research pipeline.

        Parameters
        ----------
        idea : str
            User's research idea / hypothesis (always required).
        pdf_path : str, optional
            Path to the scientific paper PDF (Mode A/B).
            If omitted, runs in Mode C (idea-only).
        h5ad_path : str, optional
            Path to user-provided h5ad file (Mode B).
        on_stage : callable, optional
            Progress callback ``(stage_name, status_message)``.
        resume : bool, optional
            If True, attempt to resume from a previous checkpoint.
        from_stage : str, optional
            Start from this stage (e.g., "execute"). All prior stages are
            marked as completed. Requires workspace to have necessary artifacts.
        skip_stages : list[str], optional
            Skip these stages entirely (e.g., ["research"]). Useful for
            workflows that don't need literature search.
        plan_only : bool, optional
            If True, stop after generating ``plan.md`` and wait for an
            explicit plan approval before continuing with later stages.

        Returns
        -------
        dict with keys: success, report_path, review_path, workspace, error
        """
        def _notify_stage(stage: str, status: str):
            if on_stage:
                on_stage(stage, status)
            logger.info("[%s] %s", stage, status)

        mode = _resolve_input_mode(pdf_path, h5ad_path)
        intake_payload: dict[str, Any] = {
            "mode": mode,
            "title": "",
            "geo_accessions": [],
        }
        awaiting_plan_approval = False
        review_cap_reached = False
        final_output = ""

        def _finalize_pipeline_workspace(
            *,
            success: bool,
            warnings: list[str] | None = None,
            errors: list[str] | None = None,
        ) -> tuple[str, str, dict[str, Any], list[str]]:
            local_warnings = [str(item) for item in (warnings or []) if str(item).strip()]
            local_errors = [str(item) for item in (errors or []) if str(item).strip()]
            review_path = self.workspace / "review_report.json"
            review_warnings, review_errors = _review_report_validation(review_path)
            local_warnings.extend(item for item in review_warnings if item not in local_warnings)
            local_errors.extend(item for item in review_errors if item not in local_errors)

            requirements = _pipeline_workspace_requirements(
                self.workspace,
                self.state.task_store,
                mode=mode,
                awaiting_plan_approval=awaiting_plan_approval,
            )
            report_path = self.workspace / "final_report.md"
            notebook_path = Path(self.notebook_path)
            manifest_metadata = {
                "mode": mode,
                "paper_input": bool(pdf_path),
                "h5ad_input": bool(h5ad_path),
                "awaiting_plan_approval": awaiting_plan_approval,
                "review_cap_reached": review_cap_reached,
                "completed_stages": list(self.state.completed_stages),
                "review_iterations": self.state.review_iterations,
                "intake": dict(intake_payload),
            }
            manifest_path = update_workspace_manifest(
                self.workspace,
                workspace_kind=WORKSPACE_KIND_ANALYSIS_RUN,
                workspace_purpose="research_pipeline",
                requirements=requirements,
                step=StepRecord(
                    skill="research-pipeline",
                    version=PIPELINE_VERSION,
                    input_file=pdf_path or h5ad_path or "",
                    output_file=str(
                        report_path
                        if report_path.exists()
                        else notebook_path
                        if notebook_path.exists()
                        else self.workspace
                    ),
                    params={
                        "mode": mode,
                        "paper_input": bool(pdf_path),
                        "h5ad_input": bool(h5ad_path),
                        "completed_stages": list(self.state.completed_stages),
                        "review_iterations": self.state.review_iterations,
                    },
                ),
                isolation_mode="workspace_dir",
                metadata=manifest_metadata,
            )

            completion_status = ""
            if local_errors or not success:
                completion_status = COMPLETION_STATUS_FAILED
            elif awaiting_plan_approval:
                completion_status = COMPLETION_STATUS_AWAITING_APPROVAL
            elif review_cap_reached:
                completion_status = COMPLETION_STATUS_PARTIAL
            elif self.state.is_stage_done("review") and report_path.exists() and review_path.exists():
                completion_status = ""
            elif self.state.is_stage_done("write") or report_path.exists():
                completion_status = COMPLETION_STATUS_PARTIAL
            else:
                completion_status = COMPLETION_STATUS_INCOMPLETE

            completion_report = build_completion_report(
                self.workspace,
                workspace_kind=WORKSPACE_KIND_ANALYSIS_RUN,
                workspace_purpose="research_pipeline",
                requirements=requirements,
                status=completion_status,
                warnings=local_warnings,
                errors=local_errors,
                manifest_path=str(manifest_path),
                metadata=manifest_metadata,
            )
            completion_report_path = write_completion_report(
                self.workspace,
                completion_report,
                hook_runtime=self.hook_runtime,
                hook_context={
                    "workspace": str(self.workspace),
                    "source": "research_pipeline",
                },
            )
            update_workspace_manifest(
                self.workspace,
                workspace_kind=WORKSPACE_KIND_ANALYSIS_RUN,
                workspace_purpose="research_pipeline",
                requirements=requirements,
                completion_report=completion_report,
                isolation_mode="workspace_dir",
                metadata=manifest_metadata,
                append_step=False,
            )
            return (
                str(manifest_path),
                str(completion_report_path),
                completion_report.to_dict(),
                local_warnings,
            )

        try:
            # ── Parameter validation ──────────────────────────────────
            skip_stages = skip_stages or []

            # Validate from_stage
            if from_stage and from_stage not in self.STAGES:
                raise ValueError(
                    f"Invalid from_stage '{from_stage}'. "
                    f"Must be one of: {', '.join(self.STAGES)}"
                )

            # Validate skip_stages
            invalid_skips = [s for s in skip_stages if s not in self.STAGES]
            if invalid_skips:
                raise ValueError(
                    f"Invalid skip_stages: {', '.join(invalid_skips)}. "
                    f"Must be from: {', '.join(self.STAGES)}"
                )

            # from_stage and skip_stages are mutually exclusive with resume
            if resume and (from_stage or skip_stages):
                raise ValueError(
                    "Cannot use --resume with --from-stage or --skip. "
                    "Use one approach at a time."
                )

            if plan_only and from_stage and from_stage not in ("intake", "plan"):
                raise ValueError(
                    "--plan-only cannot start after the plan stage. "
                    "Use /resume-task research after approving the plan."
                )

            if plan_only and "plan" in skip_stages:
                raise ValueError("--plan-only cannot be combined with --skip plan.")

            self.state.configure_pipeline(mode=mode, has_pdf=bool(pdf_path))

            # ── Stage control: from_stage ─────────────────────────────
            if from_stage:
                # Mark all stages before from_stage as completed
                from_idx = self.STAGES.index(from_stage)
                for stage in self.STAGES[:from_idx]:
                    if stage not in skip_stages:
                        self.state.mark_stage_skipped(
                            stage,
                            summary=f"Skipped (--from-stage={from_stage})",
                        )

                _notify_stage(
                    "from_stage",
                    f"Starting from '{from_stage}' "
                    f"(marked {from_idx} prior stages as completed)"
                )

            # ── Stage control: skip_stages ────────────────────────────
            if skip_stages:
                for stage in skip_stages:
                    self.state.mark_stage_skipped(
                        stage,
                        summary="Skipped (--skip)",
                    )

                _notify_stage(
                    "skip_stages",
                    f"Skipping stages: {', '.join(skip_stages)}"
                )

            # ── Checkpoint resume ─────────────────────────────────────
            skip_intake = False
            if resume:
                loaded = PipelineState.load_checkpoint(self.workspace)
                if loaded is not None:
                    loaded.configure_pipeline(mode=mode, has_pdf=bool(pdf_path))
                    self.state = loaded
                    self.state.task_store.attach_lifecycle_runtime(
                        self.hook_runtime,
                        context={
                            "workspace": str(self.workspace),
                            "plan_kind": "research_pipeline",
                            "source": "research_pipeline",
                        },
                    )
                    completed = ", ".join(loaded.completed_stages) or "none"
                    _notify_stage(
                        "resume",
                        f"Resuming from checkpoint "
                        f"(completed: {completed})",
                    )
                    if loaded.is_stage_done("intake"):
                        skip_intake = True

            plan_status = _get_plan_status(self.state.task_store)
            if (
                plan_status == PLAN_STATUS_PENDING_APPROVAL
                and not plan_only
                and (resume or (from_stage and from_stage not in ("intake", "plan")))
            ):
                raise ValueError(
                    "Plan approval required before continuing past the planning stage. "
                    "Review plan.md and run /approve-plan first."
                )

            self.state.checkpoint(self.workspace)

            # ── Stage 1: Intake ────────────────────────────────────────
            # Check if intake should be skipped (resume, from_stage, or explicit skip)
            if skip_intake or self.state.is_stage_done("intake"):
                _notify_stage("intake", "Skipped (already completed)")
            else:
                self.state.mark_stage_in_progress(
                    "intake",
                    summary="Preparing intake context",
                )
                if pdf_path:
                    _notify_stage("intake", "Parsing PDF and assembling context...")
                else:
                    _notify_stage("intake", "Assembling idea-only context (Mode C)...")

                from .intake import prepare_intake

                intake = prepare_intake(
                    idea=idea,
                    pdf_path=pdf_path,
                    h5ad_path=h5ad_path,
                    output_dir=str(self.workspace),
                )
                self.state.mark_stage_completed(
                    "intake",
                    summary="Prepared intake context",
                    artifact_ref=intake.paper_md_path,
                )
                self.state.checkpoint(self.workspace)

            # For resume/from_stage/skip, re-create a minimal intake result from workspace
            if skip_intake or self.state.is_stage_done("intake"):
                from .intake import IntakeResult
                intake = IntakeResult.from_workspace(
                    str(self.workspace), idea=idea,
                    pdf_path=pdf_path, h5ad_path=h5ad_path,
                )
            intake_payload = {
                "mode": intake.input_mode,
                "title": intake.paper_title,
                "geo_accessions": list(intake.geo_accessions),
            }

            # ── Stage 2–7: Agent-driven stages ────────────────────────
            # Register workspace so notebook_create resolves relative paths
            from .tools import set_workspace_dir
            set_workspace_dir(str(self.workspace))

            _notify_stage("agent", "Building multi-agent graph...")
            agent = self._build_agent()
            existing_plan_path = self.workspace / "plan.md"
            plan_mtime_before = (
                existing_plan_path.stat().st_mtime_ns
                if existing_plan_path.exists()
                else None
            )

            # Construct the initial prompt for the orchestrator
            initial_prompt = self._build_initial_prompt(intake)

            # Append stage control context
            if resume and self.state.completed_stages:
                completed = self.state.completed_stages
                pending = [s for s in self.STAGES if s not in completed]
                initial_prompt += (
                    f"\n\n## ⚡ Resume Context\n"
                    f"This pipeline is being RESUMED from a previous run.\n"
                    f"- **Already completed**: {', '.join(completed)}\n"
                    f"- **Remaining stages**: {', '.join(pending)}\n"
                    f"Skip the completed stages and continue from "
                    f"'{pending[0]}' if stages remain.\n"
                    f"Review existing outputs in the workspace before "
                    f"proceeding.\n"
                )
            elif from_stage or skip_stages:
                completed = self.state.completed_stages
                pending = [s for s in self.STAGES if s not in completed]
                context_lines = []

                if from_stage:
                    context_lines.append(
                        f"This pipeline is starting from stage '{from_stage}'."
                    )

                if skip_stages:
                    context_lines.append(
                        f"The following stages are SKIPPED: {', '.join(skip_stages)}"
                    )

                context_lines.extend([
                    f"- **Already completed/skipped**: {', '.join(completed)}",
                    f"- **Remaining stages**: {', '.join(pending)}",
                    "Review existing outputs in the workspace before proceeding.",
                ])

                initial_prompt += (
                    f"\n\n## ⚡ Stage Control Context\n"
                    + "\n".join(context_lines) + "\n"
                )

            if plan_only:
                initial_prompt += (
                    "\n\n## 🧭 Plan Approval Gate\n"
                    "This run is operating in PLAN-ONLY mode.\n"
                    "- Complete intake and planning only.\n"
                    "- Produce `plan.md` in the workspace.\n"
                    "- Do NOT start research, execution, analysis, writing, or review.\n"
                    "- Stop immediately after the plan is written so the user can review it.\n"
                )
            elif _get_plan_status(self.state.task_store) == PLAN_STATUS_APPROVED:
                initial_prompt += (
                    "\n\n## ✅ Approved Plan Context\n"
                    "The user has explicitly approved `plan.md`.\n"
                    "Continue with the remaining stages after planning.\n"
                )

            _notify_stage("pipeline", "Running research pipeline...")

            # Stream the agent execution
            # Default recursion_limit=25 is far too low for a multi-agent
            # pipeline with 6 sub-agents and multiple tool calls per stage.
            recursion_limit = int(
                os.getenv("OC_RECURSION_LIMIT", "500")
            )
            config = {
                "recursion_limit": recursion_limit,
                "configurable": {
                    "thread_id": f"research-{self.workspace.name}",
                },
            }
            pending_write_path = ""
            async for event in agent.astream_events(
                {"messages": [("human", initial_prompt)]},
                config=config,
                version="v2",
            ):
                kind = event.get("event", "")
                if kind == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if chunk and hasattr(chunk, "content"):
                        content = chunk.content
                        if isinstance(content, str):
                            final_output += content
                elif kind == "on_tool_start":
                    tool_name = event.get("name", "")
                    task_input = event.get("data", {}).get("input", {})
                    
                    if tool_name == "task":
                        # Sub-agent delegation — track pipeline stage
                        agent_name = task_input.get("subagent", "sub-agent")
                        task_desc = task_input.get("task_description", "")
                        desc = (task_desc[:50] + "...") if len(task_desc) > 50 else task_desc
                        _notify_stage(
                            agent_name.replace("-agent", ""),
                            f"Delegating task: [italic]{desc}[/italic]"
                        )
                        stage = PIPELINE_AGENT_STAGE_MAP.get(agent_name)
                        if stage:
                            self.state.mark_stage_in_progress(
                                stage,
                                summary=desc,
                                owner=agent_name,
                            )
                            if stage == "review":
                                self.state.review_iterations += 1
                                # ── Review cap enforcement ────────
                                if self.state.should_stop_review():
                                    self.state.checkpoint(self.workspace)
                                    _notify_stage(
                                        "review",
                                        f"Review iteration cap reached "
                                        f"({self.state.max_review_iterations}). "
                                        f"Stopping pipeline."
                                    )
                                    review_cap_reached = True
                                    break
                            self.state.checkpoint(self.workspace)
                    elif tool_name == "execute":
                        cmd = task_input.get("command", "")
                        _notify_stage("shell", f"Running: [dim]{cmd[:60]}{'...' if len(cmd) > 60 else ''}[/dim]")
                    elif tool_name == "notebook_create":
                        _notify_stage("notebook", f"Creating notebook...")
                    elif tool_name == "write_file":
                        path = task_input.get("file_path", "")
                        pending_write_path = path
                        _notify_stage("file", f"Writing [dim]{Path(path).name}[/dim]...")
                    elif tool_name == "read_file":
                        path = task_input.get("file_path", "")
                        _notify_stage("file", f"Reading [dim]{Path(path).name}[/dim]...")
                    elif tool_name == "tavily_search":
                        q = task_input.get("query", "")
                        _notify_stage("search", f"Searching web for: [dim]'{q}'[/dim]")
                    elif tool_name == "skill_search":
                        q = task_input.get("query", "")
                        _notify_stage("search", f"Searching local skills for: [dim]'{q}'[/dim]")
                    elif tool_name not in ("__start__", "agent"):
                        _notify_stage("tool", f"Using [bold]{tool_name}[/bold]...")
                elif kind == "on_tool_end":
                    tool_name = event.get("name", "")
                    if tool_name == "write_file":
                        completed_write_path = pending_write_path
                        pending_write_path = ""
                        if Path(completed_write_path).name == "plan.md":
                            plan_path = Path(completed_write_path)
                            if plan_path.exists():
                                self.state.mark_stage_completed(
                                    "plan",
                                    summary="Generated plan.md",
                                    artifact_ref=str(plan_path),
                                )
                                if plan_only:
                                    _set_plan_pending_approval(self.state.task_store)
                                    self.state.checkpoint(self.workspace)
                                    _notify_stage(
                                        "plan",
                                        "Plan generated; awaiting explicit approval before continuing.",
                                    )
                                    awaiting_plan_approval = True
                                    break

            # ── Post-pipeline validation ──────────────────────────────
            report_path = self.workspace / "final_report.md"
            review_path = self.workspace / "review_report.json"
            plan_path = self.workspace / "plan.md"
            plan_changed = (
                plan_path.exists()
                and (
                    plan_mtime_before is None
                    or plan_path.stat().st_mtime_ns != plan_mtime_before
                )
            )

            if plan_path.exists():
                self.state.mark_stage_completed(
                    "plan",
                    summary="Generated plan.md",
                    artifact_ref=str(plan_path),
                )
                if plan_only and (awaiting_plan_approval or plan_changed):
                    _set_plan_pending_approval(self.state.task_store)
            if report_path.exists():
                self.state.mark_stage_completed(
                    "write",
                    summary="Drafted final report",
                    artifact_ref=str(report_path),
                )
            if review_path.exists():
                self.state.mark_stage_completed(
                    "review",
                    summary="Produced review report",
                    artifact_ref=str(review_path),
                )

            # Final checkpoint
            self.state.checkpoint(self.workspace)

            warnings = []
            plan_state = _get_plan_state(self.state.task_store)
            plan_validation_snapshot = plan_state.validation
            plan_validation = (
                plan_validation_snapshot.to_result()
                if plan_validation_snapshot is not None
                else None
            )
            if plan_validation is not None and not plan_validation.valid:
                warnings.append(
                    "plan.md failed structural validation — review /plan before approval or downstream execution"
                )
            if not plan_path.exists() and not self.state.is_stage_done("plan"):
                warnings.append("plan.md not found — planner stage may have been skipped")
            if not report_path.exists() and not review_cap_reached and not awaiting_plan_approval:
                warnings.append("final_report.md not found — writing stage may have been skipped")

            if warnings:
                for w in warnings:
                    logger.warning("Pipeline validation: %s", w)
                    _notify_stage("warning", w)

            plan_payload = build_plan_result_payload(
                plan_state,
                awaiting_approval=awaiting_plan_approval,
            )
            manifest_path, completion_report_path, completion_payload, warnings = (
                _finalize_pipeline_workspace(
                    success=True,
                    warnings=warnings,
                )
            )

            return PipelineRunResult(
                success=True,
                report_path=str(report_path) if report_path.exists() else "",
                review_path=str(review_path) if review_path.exists() else "",
                notebook_path=self.notebook_path,
                workspace=str(self.workspace),
                manifest_path=manifest_path,
                completion_report_path=completion_report_path,
                intake={
                    "mode": intake.input_mode,
                    "title": intake.paper_title,
                    "geo_accessions": intake.geo_accessions,
                },
                completed_stages=list(self.state.completed_stages),
                review_iterations=self.state.review_iterations,
                review_cap_reached=review_cap_reached,
                plan=PlanRunResult.from_payload(plan_payload),
                completion=CompletionRunResult.from_mapping(
                    {"completion": completion_payload}
                ),
                warnings=list(warnings),
                final_output=final_output[:2000],
                error="",
            ).to_dict()

        except Exception as e:
            logger.error("Pipeline failed: %s", e, exc_info=True)
            self.state.error = str(e)
            if self.state.current_stage in self.STAGES and not self.state.is_stage_done(
                self.state.current_stage
            ):
                self.state.mark_stage_failed(
                    self.state.current_stage,
                    summary=str(e),
                )
            # Save checkpoint even on failure for resume
            try:
                self.state.checkpoint(self.workspace)
            except Exception:
                pass
            plan_payload = build_plan_result_payload(
                _get_plan_state(self.state.task_store),
                awaiting_approval=False,
            )
            report_path = self.workspace / "final_report.md"
            review_path = self.workspace / "review_report.json"
            manifest_path, completion_report_path, completion_payload, completion_warnings = (
                _finalize_pipeline_workspace(
                    success=False,
                    errors=[str(e)],
                )
            )
            return PipelineRunResult(
                success=False,
                report_path=str(report_path) if report_path.exists() else "",
                review_path=str(review_path) if review_path.exists() else "",
                notebook_path=self.notebook_path,
                workspace=str(self.workspace),
                manifest_path=manifest_path,
                completion_report_path=completion_report_path,
                intake=dict(intake_payload),
                completed_stages=list(self.state.completed_stages),
                plan=PlanRunResult.from_payload(plan_payload),
                completion=CompletionRunResult.from_mapping(
                    {"completion": completion_payload}
                ),
                warnings=completion_warnings,
                error=str(e),
            ).to_dict()
        finally:
            # Clean up notebook kernel
            from .tools import _nb_session
            if _nb_session is not None:
                try:
                    _nb_session.shutdown()
                except Exception:
                    pass

    def _build_initial_prompt(self, intake) -> str:
        """Build the initial prompt that kicks off the orchestrator.

        For Modes A/B, injects ``02_methodology.md`` content directly so the
        planner-agent receives untruncated methodology without needing
        a separate ``read_file`` call.  The coding-agent is NOT expected to
        read the methodology — it should follow ``plan.md`` instead.
        """
        from .intake import IntakeResult

        workspace_abs = str(self.workspace.resolve())

        parts = [
            "# New Research Request\n",
            "The user wants to conduct a multi-omics research project. "
            "Start the research pipeline workflow.\n",
            f"## Workspace\n",
            f"All output files MUST be saved under: `{workspace_abs}`\n",
            f"This includes: plan.md, todos.md, notebooks (.ipynb), "
            f"artifacts/, final_report.md, review_report.json.\n",
            f"When using shell commands, always use absolute paths with "
            f"this workspace prefix. When creating notebooks, use simple "
            f"filenames (the system resolves them to the workspace).\n",
        ]

        # Mode C: idea only
        if intake.input_mode == "C":
            parts.append(f"## User's Research Idea\n\n{intake.idea}\n")
            parts.append(
                "## Data (Mode C: idea only)\n"
                "No reference paper was provided. Start by delegating to the "
                "research-agent to search for relevant literature, datasets, "
                "and methods. Then proceed to the planner-agent.\n"
            )
        else:
            # Mode A / B — inject paper structure + methodology content
            parts.extend([
                "## Paper (Macro Agentic FS)\n",
                f"The reference paper has been 'unpacked' into a structured "
                f"directory at `{workspace_abs}/paper/`:\n",
                f"- `paper/01_abstract_conclusion.md` — "
                f"Abstract, introduction, conclusions (quick overview)\n",
                f"- `paper/02_methodology.md` — **MUST READ** "
                f"Complete, untruncated methods, algorithms, and parameters\n",
                f"- `paper/03_results_figs.md` — "
                f"Results and discussion sections\n",
                f"- `paper/04_fulltext.md` — "
                f"Full cleaned text (reference / fallback)\n",
            ])

            # ── Methodology: light hint + on-demand read ──────────────
            # Instead of embedding the full methodology (~2000 tokens) in
            # the initial prompt (which persists through ALL orchestrator
            # turns), we inject only a brief summary hint plus a mandatory
            # read_file instruction.  This keeps the prompt lean while
            # ensuring the planner still gets full methodology.
            #
            # Design rationale:
            #   - initial_prompt stays in orchestrator context for 50-100+
            #     LLM calls across all 7 stages.  Full methodology wastes
            #     tokens in execute/analyze/write/review stages.
            #   - Orchestrator reads the file once via read_file, passes
            #     it to planner's task body → only planner's sub-context
            #     carries the full text.
            #   - The brief hint serves as a safety net: even if the
            #     orchestrator skips read_file, the planner still has
            #     enough context to produce a reasonable plan.
            meth_path = self.workspace / "paper" / "02_methodology.md"
            if meth_path.exists():
                meth_content = meth_path.read_text(encoding="utf-8")
                # Extract a brief summary (first ~500 chars) as a hint
                hint = meth_content[:500].strip()
                if len(meth_content) > 500:
                    hint += "\n... [truncated — read full file for all parameters]"
                parts.append(
                    "## Paper Methodology (Summary Hint)\n"
                    "Below is a **brief excerpt** of the paper's computational "
                    "methods. The FULL untruncated methodology is in:\n"
                    f"`{workspace_abs}/paper/02_methodology.md`\n\n"
                    "```\n"
                    f"{hint}\n"
                    "```\n\n"
                    "**MANDATORY**: Before delegating to planner-agent, you MUST:\n"
                    f"1. Call `read_file(\"{workspace_abs}/paper/02_methodology.md\")`\n"
                    "2. Include the FULL content in the planner's task description\n"
                    "3. The planner needs exact parameters, QC thresholds, and "
                    "algorithm details to create an accurate plan.\n"
                )
            else:
                parts.append(
                    "## Paper Methodology\n"
                    "NOTE: `02_methodology.md` was not generated. Use `read_file` "
                    f"on `{workspace_abs}/paper/04_fulltext.md` for methods.\n"
                )

            parts.append(f"## User's Research Idea\n\n{intake.idea}\n")

            if intake.input_mode == "B":
                parts.append(
                    f"## Data (Mode B: user-provided)\n"
                    f"User provided h5ad file: {intake.h5ad_path}\n"
                )
                if intake.h5ad_metadata:
                    meta = intake.h5ad_metadata
                    parts.append(
                        f"- Cells: {meta.get('n_obs', 'N/A')}, "
                        f"Genes: {meta.get('n_vars', 'N/A')}\n"
                    )
                    if meta.get("has_spatial"):
                        parts.append("- Contains spatial coordinates\n")
            else:
                parts.append(
                    f"## Data (Mode A: from paper)\n"
                    f"GEO accessions found: {', '.join(intake.geo_accessions) or 'None'}\n"
                    f"Download datasets if accessions are available.\n"
                )

        # ── Delegation instructions (role separation) ─────────────
        parts.append(
            f"\n## Instructions\n"
            f"Follow the research pipeline workflow. Delegate to agents "
            f"based on the role separation below:\n\n"
            f"### Agent Delegation Rules\n"
            f"1. **planner-agent**: FIRST delegate here. Include the "
            f"'Paper Methodology' section above in the task body so the "
            f"planner can extract exact parameters and QC thresholds. "
            f"The planner produces `plan.md`.\n"
            f"2. **research-agent**: Delegate for literature search, "
            f"baseline comparison, and dataset discovery.\n"
            f"3. **coding-agent**: Delegate for experiment execution. "
            f"The coding-agent does NOT read the paper methodology — "
            f"it reads `plan.md` and follows the plan. Include the plan "
            f"content or key parameters in the task description.\n"
            f"4. **analysis-agent**: Delegate for interpreting results, "
            f"computing metrics, and generating plots.\n"
            f"5. **writing-agent**: Delegate for drafting the report.\n"
            f"6. **reviewer-agent**: Delegate for peer review.\n"
            f"\n"
            f"IMPORTANT: All generated files must go into `{workspace_abs}`.\n"
            f"Use this as the base directory for ALL read/write operations.\n"
        )

        return "\n".join(parts)
