"""Shared generic plan mode support for interactive CLI/TUI sessions."""

from __future__ import annotations

import shlex
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from omicsclaw.agents.plan_state import (
    PLAN_STATUS_APPROVED,
    PLAN_STATUS_PENDING_APPROVAL,
)
from omicsclaw.runtime.events import (
    EVENT_PLAN_APPROVED,
    EVENT_PLAN_CREATED,
    EVENT_TASK_STARTED,
)
from omicsclaw.runtime.hook_payloads import PlanHookPayload
from omicsclaw.runtime.hooks import (
    HOOK_MODE_NOTICE,
    LifecycleHookRuntime,
    build_default_lifecycle_hook_runtime,
    format_hook_notice_block,
)
from omicsclaw.runtime.task_store import (
    DONE_TASK_STATUSES,
    TASK_STATUS_IN_PROGRESS,
    TASK_STATUS_PENDING,
    TaskRecord,
    TaskStore,
)

INTERACTIVE_PLAN_METADATA_KEY = "interactive_plan"

PLAN_KIND_GENERIC_ANALYSIS = "generic_analysis"
PLAN_KIND_SKILL_CREATION = "skill_creation"
PLAN_KIND_CUSTOM_ANALYSIS = "custom_analysis"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _empty_task_store() -> TaskStore:
    return TaskStore(kind="interactive_plan")


@dataclass(slots=True)
class InteractivePlanSnapshot:
    request: str = ""
    plan_kind: str = PLAN_KIND_GENERIC_ANALYSIS
    status: str = PLAN_STATUS_PENDING_APPROVAL
    approved_at: str = ""
    approved_by: str = ""
    approval_notes: str = ""
    active_task_id: str = ""
    created_at: str = field(default_factory=_utc_now_iso)
    updated_at: str = field(default_factory=_utc_now_iso)
    task_store: TaskStore = field(default_factory=_empty_task_store)

    def is_empty(self) -> bool:
        return not self.request.strip() and not self.task_store.tasks

    def touch(self) -> None:
        self.updated_at = _utc_now_iso()

    def active_task(self) -> TaskRecord | None:
        if self.active_task_id:
            task = self.task_store.get(self.active_task_id)
            if task is not None:
                return task

        task = self.task_store.active_task()
        if task is not None:
            return task

        for candidate in self.task_store.tasks:
            if candidate.status not in DONE_TASK_STATUSES:
                return candidate
        return self.task_store.tasks[0] if self.task_store.tasks else None

    def sync(self) -> None:
        self.task_store.kind = "interactive_plan"
        self.task_store.metadata.setdefault("request", self.request)
        self.task_store.metadata["request"] = self.request
        self.task_store.metadata["plan_kind"] = self.plan_kind
        self.task_store.metadata["status"] = self.status
        self.task_store.metadata["active_task_id"] = self.active_task_id
        active = self.active_task()
        self.active_task_id = active.id if active is not None else ""
        self.task_store.metadata["active_task_id"] = self.active_task_id

    def mark_approved(
        self,
        *,
        approved_by: str = "user",
        approval_notes: str = "",
    ) -> None:
        self.status = PLAN_STATUS_APPROVED
        self.approved_at = _utc_now_iso()
        self.approved_by = approved_by
        self.approval_notes = approval_notes
        active = self.active_task()
        if active is not None and active.status == TASK_STATUS_PENDING:
            self.task_store.set_task_status(
                active.id,
                TASK_STATUS_IN_PROGRESS,
                owner="assistant",
            )
        self.touch()
        self.sync()

    def select_task(self, task_id: str) -> TaskRecord:
        target = self.task_store.require(task_id)
        self.active_task_id = task_id
        if self.status == PLAN_STATUS_APPROVED and target.status not in DONE_TASK_STATUSES:
            for task in self.task_store.tasks:
                if task.id != task_id and task.status == TASK_STATUS_IN_PROGRESS:
                    self.task_store.set_task_status(
                        task.id,
                        TASK_STATUS_PENDING,
                        owner=task.owner or "assistant",
                    )
            self.task_store.set_task_status(
                target.id,
                TASK_STATUS_IN_PROGRESS,
                owner=target.owner or "assistant",
            )
        self.touch()
        self.sync()
        return target

    def to_dict(self) -> dict[str, Any]:
        self.sync()
        return {
            "request": self.request,
            "plan_kind": self.plan_kind,
            "status": self.status,
            "approved_at": self.approved_at,
            "approved_by": self.approved_by,
            "approval_notes": self.approval_notes,
            "active_task_id": self.active_task_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "task_store": self.task_store.to_dict(),
        }

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, Any] | None,
    ) -> "InteractivePlanSnapshot | None":
        if not isinstance(data, Mapping):
            return None

        task_store_data = data.get("task_store")
        if isinstance(task_store_data, Mapping):
            task_store = TaskStore.from_dict(dict(task_store_data))
        else:
            task_store = _empty_task_store()

        snapshot = cls(
            request=str(data.get("request", "")).strip(),
            plan_kind=str(data.get("plan_kind", PLAN_KIND_GENERIC_ANALYSIS)).strip()
            or PLAN_KIND_GENERIC_ANALYSIS,
            status=str(data.get("status", PLAN_STATUS_PENDING_APPROVAL)).strip()
            or PLAN_STATUS_PENDING_APPROVAL,
            approved_at=str(data.get("approved_at", "")).strip(),
            approved_by=str(data.get("approved_by", "")).strip(),
            approval_notes=str(data.get("approval_notes", "")).strip(),
            active_task_id=str(data.get("active_task_id", "")).strip(),
            created_at=str(data.get("created_at", _utc_now_iso())).strip() or _utc_now_iso(),
            updated_at=str(data.get("updated_at", _utc_now_iso())).strip() or _utc_now_iso(),
            task_store=task_store,
        )
        snapshot.sync()
        if snapshot.is_empty():
            return None
        return snapshot


@dataclass(slots=True)
class InteractivePlanCommandView:
    output_text: str
    success: bool = True
    persist_session: bool = False
    session_metadata: dict[str, Any] = field(default_factory=dict)
    replace_session_metadata: bool = False
    suggested_prompt: str = ""
    execution_prompt: str = ""


@dataclass(slots=True)
class GenericApprovePlanArgs:
    notes: str = ""
    approver: str = "user"


@dataclass(slots=True)
class AutoPlanSeedResult:
    created: bool = False
    snapshot: InteractivePlanSnapshot | None = None
    session_metadata: dict[str, Any] = field(default_factory=dict)
    notice_text: str = ""


def classify_interactive_plan_kind(request: str) -> str:
    lowered = str(request or "").lower()
    if any(
        marker in lowered
        for marker in (
            "create skill",
            "add skill",
            "new skill",
            "scaffold skill",
            "build skill",
            "封装成skill",
            "创建skill",
            "创建 skill",
            "新增skill",
            "新增 skill",
        )
    ):
        return PLAN_KIND_SKILL_CREATION
    if any(
        marker in lowered
        for marker in (
            "custom analysis",
            "custom script",
            "custom pipeline",
            "write python",
            "write r",
            "自定义分析",
            "自定义脚本",
            "写脚本",
            "写代码分析",
        )
    ):
        return PLAN_KIND_CUSTOM_ANALYSIS
    return PLAN_KIND_GENERIC_ANALYSIS


def should_auto_enter_plan_mode(request: str) -> bool:
    lowered = str(request or "").strip().lower()
    if not lowered:
        return False

    strong_markers = (
        "create skill",
        "add skill",
        "new skill",
        "build skill",
        "scaffold skill",
        "step by step",
        "step-by-step",
        "multi-step",
        "workflow",
        "pipeline",
        "from start to finish",
        "end to end",
        "integrate and refactor",
        "完整流程",
        "一步步",
        "逐步",
        "多步骤",
        "多步",
        "工作流",
        "流水线",
        "封装成skill",
        "创建 skill",
        "创建skill",
        "新增 skill",
        "新增skill",
        "从头到尾",
        "完整实现",
    )
    if any(marker in lowered for marker in strong_markers):
        return True

    sequencing_markers = (
        " then ",
        " after that ",
        " finally ",
        " and then ",
        "同时",
        "然后",
        "接着",
        "最后",
        "并且",
        "再",
    )
    analysis_markers = (
        "analy",
        "validate",
        "summar",
        "optimiz",
        "implement",
        "refactor",
        "analysis",
        "run ",
        "处理",
        "分析",
        "验证",
        "总结",
        "优化",
        "实现",
        "重构",
    )
    sequence_hits = sum(1 for marker in sequencing_markers if marker in lowered)
    if sequence_hits >= 2 and any(marker in lowered for marker in analysis_markers):
        return True

    if len(lowered) >= 180 and any(marker in lowered for marker in analysis_markers):
        return True
    return False


def _build_generic_analysis_tasks() -> list[TaskRecord]:
    return [
        TaskRecord(
            id="define-objective",
            title="Define objective",
            description="Clarify scientific goal, target outputs, and acceptance criteria.",
            owner="assistant",
        ),
        TaskRecord(
            id="inspect-inputs",
            title="Inspect inputs and prerequisites",
            description="Verify datasets, paths, metadata, and runtime prerequisites before analysis.",
            owner="assistant",
            dependencies=["define-objective"],
        ),
        TaskRecord(
            id="resolve-method",
            title="Resolve method and skill path",
            description="Choose the best OmicsClaw skill or custom method, with key parameters and fallback path.",
            owner="assistant",
            dependencies=["inspect-inputs"],
        ),
        TaskRecord(
            id="execute-analysis",
            title="Execute analysis",
            description="Run the selected analysis workflow and collect generated artifacts.",
            owner="assistant",
            dependencies=["resolve-method"],
        ),
        TaskRecord(
            id="validate-outputs",
            title="Validate outputs",
            description="Check QC, result integrity, and whether outputs satisfy the requested objective.",
            owner="assistant",
            dependencies=["execute-analysis"],
        ),
        TaskRecord(
            id="summarize-next-steps",
            title="Summarize results and next steps",
            description="Report conclusions, artifact locations, caveats, and recommended follow-up actions.",
            owner="assistant",
            dependencies=["validate-outputs"],
        ),
    ]


def _build_skill_creation_tasks() -> list[TaskRecord]:
    return [
        TaskRecord(
            id="scope-skill-contract",
            title="Scope skill contract",
            description="Define the skill boundary, CLI contract, inputs, outputs, and validation requirements.",
            owner="assistant",
        ),
        TaskRecord(
            id="inspect-existing-patterns",
            title="Inspect existing patterns",
            description="Review nearby skills, shared libs, and repo conventions before implementation.",
            owner="assistant",
            dependencies=["scope-skill-contract"],
        ),
        TaskRecord(
            id="scaffold-implementation",
            title="Scaffold implementation",
            description="Create or refactor the skill structure so it matches OmicsClaw architecture cleanly.",
            owner="assistant",
            dependencies=["inspect-existing-patterns"],
        ),
        TaskRecord(
            id="validate-tests-artifacts",
            title="Validate tests and artifacts",
            description="Run targeted tests and verify generated reports or outputs are correct.",
            owner="assistant",
            dependencies=["scaffold-implementation"],
        ),
        TaskRecord(
            id="finalize-installation",
            title="Finalize and install",
            description="Finalize docs or registration steps and confirm the skill is ready to use.",
            owner="assistant",
            dependencies=["validate-tests-artifacts"],
        ),
    ]


def _build_custom_analysis_tasks() -> list[TaskRecord]:
    return [
        TaskRecord(
            id="scope-problem",
            title="Scope problem",
            description="Clarify the biological question, exact deliverable, and data constraints.",
            owner="assistant",
        ),
        TaskRecord(
            id="inspect-inputs",
            title="Inspect inputs",
            description="Inspect provided files, schemas, and assumptions needed for custom analysis.",
            owner="assistant",
            dependencies=["scope-problem"],
        ),
        TaskRecord(
            id="gather-method-context",
            title="Gather method context",
            description="Determine suitable methods, parameters, and scientific constraints before coding.",
            owner="assistant",
            dependencies=["inspect-inputs"],
        ),
        TaskRecord(
            id="implement-custom-analysis",
            title="Implement custom analysis",
            description="Implement and run the custom analysis path in a controlled, reproducible way.",
            owner="assistant",
            dependencies=["gather-method-context"],
        ),
        TaskRecord(
            id="validate-results",
            title="Validate results",
            description="Check result correctness, failure modes, and whether assumptions held.",
            owner="assistant",
            dependencies=["implement-custom-analysis"],
        ),
        TaskRecord(
            id="decide-promote-vs-summarize",
            title="Decide promote vs summarize",
            description="Decide whether to promote the work into a reusable skill or keep it as a one-off analysis summary.",
            owner="assistant",
            dependencies=["validate-results"],
        ),
    ]


def build_interactive_plan(
    request: str,
    *,
    workspace_dir: str = "",
) -> InteractivePlanSnapshot:
    normalized_request = str(request or "").strip()
    plan_kind = classify_interactive_plan_kind(normalized_request)
    if plan_kind == PLAN_KIND_SKILL_CREATION:
        tasks = _build_skill_creation_tasks()
    elif plan_kind == PLAN_KIND_CUSTOM_ANALYSIS:
        tasks = _build_custom_analysis_tasks()
    else:
        tasks = _build_generic_analysis_tasks()

    store = TaskStore(
        kind="interactive_plan",
        metadata={
            "request": normalized_request,
            "plan_kind": plan_kind,
            "workspace": workspace_dir,
        },
        tasks=tasks,
    )
    snapshot = InteractivePlanSnapshot(
        request=normalized_request,
        plan_kind=plan_kind,
        status=PLAN_STATUS_PENDING_APPROVAL,
        active_task_id=tasks[0].id if tasks else "",
        task_store=store,
    )
    snapshot.sync()
    return snapshot


def load_interactive_plan_from_metadata(
    metadata: Mapping[str, Any] | None,
) -> InteractivePlanSnapshot | None:
    if not isinstance(metadata, Mapping):
        return None
    return InteractivePlanSnapshot.from_dict(
        metadata.get(INTERACTIVE_PLAN_METADATA_KEY)
    )


def save_interactive_plan_to_metadata(
    metadata: dict[str, Any],
    snapshot: InteractivePlanSnapshot | None,
) -> None:
    metadata.pop(INTERACTIVE_PLAN_METADATA_KEY, None)
    if snapshot is None or snapshot.is_empty():
        return
    metadata[INTERACTIVE_PLAN_METADATA_KEY] = snapshot.to_dict()


def normalize_interactive_plan_metadata(
    metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    normalized = dict(metadata or {})
    snapshot = load_interactive_plan_from_metadata(normalized)
    save_interactive_plan_to_metadata(normalized, snapshot)
    return normalized


def _latest_user_message_text(messages: list[dict[str, Any]] | None) -> str:
    for message in reversed(list(messages or [])):
        if message.get("role") != "user":
            continue
        content = message.get("content", "")
        if isinstance(content, list):
            text = " ".join(
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            ).strip()
        else:
            text = str(content or "").strip()
        if text:
            return text
    return ""


def _task_marker(status: str) -> str:
    return {
        "pending": "[ ]",
        "in_progress": "[-]",
        "completed": "[x]",
        "skipped": "[x]",
        "blocked": "[!]",
        "failed": "[!]",
    }.get(status, "[ ]")


def _format_task_rows(snapshot: InteractivePlanSnapshot) -> list[str]:
    rows: list[str] = []
    for index, task in enumerate(snapshot.task_store.tasks, start=1):
        active_suffix = "  <- active" if task.id == snapshot.active_task_id else ""
        rows.append(
            f"{index}. {_task_marker(task.status)} {task.id} — {task.title}{active_suffix}"
        )
        rows.append(f"   {task.description}")
        if task.dependencies:
            rows.append(f"   depends on: {', '.join(task.dependencies)}")
        summary = str(task.metadata.get("summary", "")).strip()
        if summary:
            rows.append(f"   summary: {summary}")
        if task.artifact_refs:
            rows.append(f"   artifacts: {', '.join(task.artifact_refs)}")
    return rows


def format_interactive_plan(snapshot: InteractivePlanSnapshot) -> str:
    active_task = snapshot.active_task()
    lines = [
        f"Interactive plan mode: {snapshot.plan_kind}",
        f"Status: {snapshot.status}",
        f"Request: {snapshot.request}",
    ]
    if active_task is not None:
        lines.append(
            f"Active task: {active_task.id} ({active_task.status}) — {active_task.title}"
        )
    if snapshot.approved_by:
        approval = f"Approved by: {snapshot.approved_by}"
        if snapshot.approved_at:
            approval += f" at {snapshot.approved_at}"
        lines.append(approval)
    if snapshot.approval_notes:
        lines.append(f"Approval notes: {snapshot.approval_notes}")
    lines.append("")
    lines.append("Planned tasks:")
    lines.extend(_format_task_rows(snapshot))
    lines.append("")
    if snapshot.status == PLAN_STATUS_PENDING_APPROVAL:
        lines.append("Next action: /approve-plan")
    elif active_task is not None:
        lines.append(f"Continue with: /resume-task {active_task.id}")
    return "\n".join(lines)


def format_interactive_tasks(snapshot: InteractivePlanSnapshot) -> str:
    active_task = snapshot.active_task()
    lines = [
        f"Interactive task store: {snapshot.plan_kind}",
        f"Plan status: {snapshot.status}",
    ]
    if active_task is not None:
        lines.append(
            f"Current focus: {active_task.id} ({active_task.status}) — {active_task.title}"
        )
    lines.append("")
    lines.extend(_format_task_rows(snapshot))
    return "\n".join(lines)


def render_interactive_plan_context(snapshot: InteractivePlanSnapshot) -> str:
    snapshot.sync()
    active_task = snapshot.active_task()
    lines = [
        "## Active Plan Mode",
        "",
        f"- Plan kind: {snapshot.plan_kind}",
        f"- Status: {snapshot.status}",
        f"- User request: {snapshot.request}",
    ]
    if snapshot.status == PLAN_STATUS_PENDING_APPROVAL:
        lines.append(
            "- Execution gate: The structured session plan is not approved yet. Stay in planning mode, refine the approach if needed, and wait for explicit approval before doing multi-step implementation or analysis execution."
        )
    else:
        lines.append(
            "- Execution rule: Follow the approved plan, preserve completed task state, and prioritize the active task unless the user explicitly changes direction."
        )
    if active_task is not None:
        lines.append(
            f"- Active task: {active_task.id} ({active_task.status}) — {active_task.title}"
        )
    if snapshot.approval_notes:
        lines.append(f"- Approval notes: {snapshot.approval_notes}")
    lines.append("- Task store:")
    for task in snapshot.task_store.tasks:
        lines.append(f"  - {_task_marker(task.status)} {task.id}: {task.title}")
    return "\n".join(lines).strip()


def build_interactive_plan_context_from_metadata(
    metadata: Mapping[str, Any] | None,
) -> str:
    snapshot = load_interactive_plan_from_metadata(metadata)
    if snapshot is None:
        return ""
    return render_interactive_plan_context(snapshot)


def build_interactive_plan_summary_lines(
    metadata: Mapping[str, Any] | None,
) -> list[str]:
    snapshot = load_interactive_plan_from_metadata(metadata)
    if snapshot is None:
        return []
    active_task = snapshot.active_task()
    lines = [f"Interactive Plan: {snapshot.status} · {snapshot.plan_kind}"]
    if active_task is not None:
        lines.append(
            f"Interactive Task: {active_task.id} ({active_task.status})"
        )
    return lines


def _replace_plan_metadata(
    session_metadata: Mapping[str, Any] | None,
    snapshot: InteractivePlanSnapshot | None,
) -> dict[str, Any]:
    metadata = normalize_interactive_plan_metadata(dict(session_metadata or {}))
    save_interactive_plan_to_metadata(metadata, snapshot)
    return metadata


def _build_hook_runtime(
    omicsclaw_dir: str = "",
    hook_runtime: LifecycleHookRuntime | None = None,
) -> LifecycleHookRuntime | None:
    if hook_runtime is not None:
        return hook_runtime
    if not str(omicsclaw_dir or "").strip():
        return None
    return build_default_lifecycle_hook_runtime(omicsclaw_dir)


def _attach_snapshot_hook_runtime(
    snapshot: InteractivePlanSnapshot,
    *,
    runtime: LifecycleHookRuntime | None,
    workspace_dir: str = "",
) -> None:
    if runtime is None:
        return
    snapshot.task_store.attach_lifecycle_runtime(
        runtime,
        context={
            "workspace": workspace_dir
            or str(snapshot.task_store.metadata.get("workspace", "")).strip(),
            "plan_kind": snapshot.plan_kind,
            "source": "interactive_plan",
        },
    )


def _append_hook_notices(
    output_text: str,
    runtime: LifecycleHookRuntime | None,
    *,
    event_names: tuple[str, ...] | list[str],
) -> str:
    if runtime is None:
        return output_text
    notices = runtime.consume_pending_messages(
        mode=HOOK_MODE_NOTICE,
        event_names=tuple(event_names),
    )
    notice_block = format_hook_notice_block(notices)
    if not notice_block:
        return output_text
    return f"{output_text}\n\n{notice_block}".strip()


def maybe_seed_interactive_plan(
    request: str,
    *,
    session_metadata: Mapping[str, Any] | None,
    workspace_dir: str = "",
    omicsclaw_dir: str = "",
    hook_runtime: LifecycleHookRuntime | None = None,
) -> AutoPlanSeedResult:
    existing = load_interactive_plan_from_metadata(session_metadata)
    if existing is not None:
        return AutoPlanSeedResult(
            created=False,
            snapshot=existing,
            session_metadata=normalize_interactive_plan_metadata(session_metadata),
        )
    if not should_auto_enter_plan_mode(request):
        return AutoPlanSeedResult(
            created=False,
            session_metadata=normalize_interactive_plan_metadata(session_metadata),
        )

    snapshot = build_interactive_plan(request, workspace_dir=workspace_dir)
    runtime = _build_hook_runtime(omicsclaw_dir, hook_runtime)
    _attach_snapshot_hook_runtime(snapshot, runtime=runtime, workspace_dir=workspace_dir)
    if runtime is not None:
        runtime.emit(
            EVENT_PLAN_CREATED,
            PlanHookPayload(
                request=snapshot.request,
                plan_kind=snapshot.plan_kind,
                status=snapshot.status,
                task_count=len(snapshot.task_store.tasks),
                workspace=workspace_dir,
                source="interactive_plan",
            ),
            context={
                "workspace": workspace_dir,
                "source": "interactive_plan",
            },
        )
    notice_text = (
        "Entered structured plan mode for this multi-step request. "
        "Review with /plan and approve with /approve-plan before execution."
    )
    notice_text = _append_hook_notices(
        notice_text,
        runtime,
        event_names=(EVENT_PLAN_CREATED,),
    )
    return AutoPlanSeedResult(
        created=True,
        snapshot=snapshot,
        session_metadata=_replace_plan_metadata(session_metadata, snapshot),
        notice_text=notice_text,
    )


def parse_generic_approve_plan_command(arg: str) -> GenericApprovePlanArgs:
    tokens = shlex.split(arg.strip()) if arg.strip() else []
    args = GenericApprovePlanArgs()
    note_tokens: list[str] = []
    idx = 0
    while idx < len(tokens):
        token = tokens[idx]
        if token == "--notes":
            if idx + 1 >= len(tokens):
                raise ValueError("--notes requires a value")
            note_tokens.append(tokens[idx + 1])
            idx += 2
        elif token == "--by":
            if idx + 1 >= len(tokens):
                raise ValueError("--by requires a value")
            args.approver = tokens[idx + 1]
            idx += 2
        else:
            note_tokens.append(token)
            idx += 1
    args.notes = " ".join(note_tokens).strip()
    return args


def _resolve_task_selector(
    snapshot: InteractivePlanSnapshot,
    selector: str,
) -> TaskRecord | None:
    normalized = selector.strip()
    if not normalized:
        return None
    if normalized.isdigit():
        index = int(normalized) - 1
        if 0 <= index < len(snapshot.task_store.tasks):
            return snapshot.task_store.tasks[index]
        return None
    task = snapshot.task_store.get(normalized)
    if task is not None:
        return task
    lowered = normalized.lower()
    for candidate in snapshot.task_store.tasks:
        if candidate.title.lower() == lowered:
            return candidate
    return None


def _unfinished_dependency_descriptors(
    snapshot: InteractivePlanSnapshot,
    task: TaskRecord,
) -> list[str]:
    unresolved: list[str] = []
    for dependency_id in task.dependencies:
        dependency = snapshot.task_store.get(dependency_id)
        if dependency is None:
            unresolved.append(dependency_id)
            continue
        if dependency.status in DONE_TASK_STATUSES:
            continue
        unresolved.append(f"{dependency.id} ({dependency.status})")
    return unresolved


def _build_task_suggested_prompt(
    snapshot: InteractivePlanSnapshot,
    task: TaskRecord,
) -> str:
    dependency_warning = _unfinished_dependency_descriptors(snapshot, task)
    prompt = (
        f"Continue with the approved plan and work on task '{task.id}' ({task.title}). "
        f"{task.description}"
    )
    if dependency_warning:
        prompt += (
            " Some dependencies are still incomplete: "
            + ", ".join(dependency_warning)
            + ". If that blocks progress, explain exactly what is missing and the minimal next step."
        )
    else:
        prompt += (
            " Use the existing artifacts and conversation context, and report concrete findings or blockers."
        )
    return prompt


def _build_task_execution_prompt(
    snapshot: InteractivePlanSnapshot,
    task: TaskRecord,
) -> str:
    dependency_warning = _unfinished_dependency_descriptors(snapshot, task)
    lines = [
        "Continue the approved interactive plan by working on the selected task.",
        f"Original user request: {snapshot.request}",
        f"Plan kind: {snapshot.plan_kind}",
        f"Selected task: {task.id} — {task.title}",
        f"Task description: {task.description}",
    ]
    if task.dependencies:
        lines.append(
            "Declared dependencies: " + ", ".join(task.dependencies)
        )
    if dependency_warning:
        lines.append(
            "Unfinished dependencies: " + ", ".join(dependency_warning)
        )
    lines.extend(
        [
            "Execution requirements:",
            "- Focus on this task first and keep the work aligned with the approved plan.",
            "- Reuse the current conversation context and any artifacts already produced.",
            "- If the task is blocked by missing prerequisites or outputs, say exactly what is missing instead of claiming completion.",
            "- When you finish, summarize what you validated or executed, any exact artifact paths, and the most appropriate next task.",
        ]
    )
    return "\n".join(lines)


def _build_task_followup_lines(
    snapshot: InteractivePlanSnapshot,
    task: TaskRecord,
) -> list[str]:
    lines: list[str] = []
    dependency_warning = _unfinished_dependency_descriptors(snapshot, task)
    if dependency_warning:
        lines.append(
            "Dependency warning: "
            + ", ".join(dependency_warning)
            + " is not completed yet. This command only changes focus; it does not mark dependencies complete."
        )
        lines.append("")
    lines.append("Suggested next prompt:")
    lines.append(_build_task_suggested_prompt(snapshot, task))
    lines.append("")
    lines.append("Start immediately: /do-current-task")
    return lines


def build_plan_command_view(
    arg: str,
    *,
    session_metadata: Mapping[str, Any] | None,
    messages: list[dict[str, Any]] | None,
    workspace_dir: str = "",
    omicsclaw_dir: str = "",
    hook_runtime: LifecycleHookRuntime | None = None,
) -> InteractivePlanCommandView:
    existing = load_interactive_plan_from_metadata(session_metadata)
    request = str(arg or "").strip()
    created = False

    if request:
        snapshot = build_interactive_plan(request, workspace_dir=workspace_dir)
        created = True
    elif existing is not None:
        snapshot = existing
    else:
        inferred_request = _latest_user_message_text(messages)
        if not inferred_request:
            return InteractivePlanCommandView(
                output_text="No interactive plan exists yet. Run /plan <request> after describing the work you want to do.",
                success=False,
            )
        snapshot = build_interactive_plan(
            inferred_request,
            workspace_dir=workspace_dir,
        )
        created = True

    output_text = format_interactive_plan(snapshot)
    if created:
        runtime = _build_hook_runtime(omicsclaw_dir, hook_runtime)
        _attach_snapshot_hook_runtime(snapshot, runtime=runtime, workspace_dir=workspace_dir)
        if runtime is not None:
            runtime.emit(
                EVENT_PLAN_CREATED,
                PlanHookPayload(
                    request=snapshot.request,
                    plan_kind=snapshot.plan_kind,
                    status=snapshot.status,
                    task_count=len(snapshot.task_store.tasks),
                    workspace=workspace_dir,
                    source="interactive_plan",
                ),
                context={
                    "workspace": workspace_dir,
                    "source": "interactive_plan",
                },
            )
        output_text = (
            "Interactive plan created for this session.\n"
            f"{output_text}"
        )
        output_text = _append_hook_notices(
            output_text,
            runtime,
            event_names=(EVENT_PLAN_CREATED,),
        )
    return InteractivePlanCommandView(
        output_text=output_text,
        persist_session=created,
        session_metadata=_replace_plan_metadata(session_metadata, snapshot),
        replace_session_metadata=created,
    )


def build_tasks_command_view(
    *,
    session_metadata: Mapping[str, Any] | None,
) -> InteractivePlanCommandView:
    snapshot = load_interactive_plan_from_metadata(session_metadata)
    if snapshot is None:
        return InteractivePlanCommandView(
            output_text="No interactive plan exists yet. Run /plan <request> to create one.",
            success=False,
        )
    return InteractivePlanCommandView(output_text=format_interactive_tasks(snapshot))


def build_approve_plan_command_view(
    arg: str,
    *,
    session_metadata: Mapping[str, Any] | None,
    omicsclaw_dir: str = "",
    hook_runtime: LifecycleHookRuntime | None = None,
) -> InteractivePlanCommandView:
    snapshot = load_interactive_plan_from_metadata(session_metadata)
    if snapshot is None:
        return InteractivePlanCommandView(
            output_text="No interactive plan exists yet. Run /plan <request> before approving.",
            success=False,
        )

    try:
        args = parse_generic_approve_plan_command(arg)
    except ValueError as exc:
        return InteractivePlanCommandView(output_text=str(exc), success=False)

    runtime = _build_hook_runtime(omicsclaw_dir, hook_runtime)
    _attach_snapshot_hook_runtime(
        snapshot,
        runtime=runtime,
        workspace_dir=str(snapshot.task_store.metadata.get("workspace", "")).strip(),
    )
    snapshot.mark_approved(
        approved_by=args.approver,
        approval_notes=args.notes,
    )
    if runtime is not None:
        runtime.emit(
            EVENT_PLAN_APPROVED,
            PlanHookPayload(
                request=snapshot.request,
                plan_kind=snapshot.plan_kind,
                status=snapshot.status,
                task_count=len(snapshot.task_store.tasks),
                workspace=str(snapshot.task_store.metadata.get("workspace", "")).strip(),
                source="interactive_plan",
            ),
            context={
                "workspace": str(snapshot.task_store.metadata.get("workspace", "")).strip(),
                "source": "interactive_plan",
            },
        )
    active_task = snapshot.active_task()
    lines = [
        "Interactive plan approved for this session.",
        format_interactive_tasks(snapshot),
    ]
    if active_task is not None:
        lines.append("")
        lines.append(f"Continue with: /resume-task {active_task.id}")
        lines.append("Start immediately: /do-current-task")
    output_text = _append_hook_notices(
        "\n".join(lines),
        runtime,
        event_names=(EVENT_TASK_STARTED, EVENT_PLAN_APPROVED),
    )
    return InteractivePlanCommandView(
        output_text=output_text,
        persist_session=True,
        session_metadata=_replace_plan_metadata(session_metadata, snapshot),
        replace_session_metadata=True,
    )


def build_resume_task_command_view(
    arg: str,
    *,
    session_metadata: Mapping[str, Any] | None,
    omicsclaw_dir: str = "",
    hook_runtime: LifecycleHookRuntime | None = None,
) -> InteractivePlanCommandView:
    snapshot = load_interactive_plan_from_metadata(session_metadata)
    if snapshot is None:
        return InteractivePlanCommandView(
            output_text="No interactive plan exists yet. Run /plan <request> first.",
            success=False,
        )
    if snapshot.status != PLAN_STATUS_APPROVED:
        return InteractivePlanCommandView(
            output_text="The interactive plan is still pending approval. Run /approve-plan before resuming a task.",
            success=False,
        )

    selector = str(arg or "").strip()
    if not selector:
        return InteractivePlanCommandView(
            output_text="Usage: /resume-task <task-id|index>",
            success=False,
        )

    task = _resolve_task_selector(snapshot, selector)
    if task is None:
        available = ", ".join(record.id for record in snapshot.task_store.tasks)
        return InteractivePlanCommandView(
            output_text=f"Unknown task '{selector}'. Available tasks: {available}",
            success=False,
        )
    if task.status in DONE_TASK_STATUSES:
        return InteractivePlanCommandView(
            output_text=f"Task '{task.id}' is already completed. Choose a pending task instead.",
            success=False,
        )

    runtime = _build_hook_runtime(omicsclaw_dir, hook_runtime)
    _attach_snapshot_hook_runtime(
        snapshot,
        runtime=runtime,
        workspace_dir=str(snapshot.task_store.metadata.get("workspace", "")).strip(),
    )
    selected = snapshot.select_task(task.id)
    output_text = _append_hook_notices(
        "\n".join(
            [
                f"Interactive task resumed: {selected.id} — {selected.title}",
                format_interactive_tasks(snapshot),
                "",
                *_build_task_followup_lines(snapshot, selected),
            ]
        ),
        runtime,
        event_names=(EVENT_TASK_STARTED,),
    )
    return InteractivePlanCommandView(
        output_text=output_text,
        persist_session=True,
        session_metadata=_replace_plan_metadata(session_metadata, snapshot),
        replace_session_metadata=True,
        suggested_prompt=_build_task_suggested_prompt(snapshot, selected),
        execution_prompt=_build_task_execution_prompt(snapshot, selected),
    )


def build_do_current_task_command_view(
    arg: str,
    *,
    session_metadata: Mapping[str, Any] | None,
    omicsclaw_dir: str = "",
    hook_runtime: LifecycleHookRuntime | None = None,
) -> InteractivePlanCommandView:
    snapshot = load_interactive_plan_from_metadata(session_metadata)
    if snapshot is None:
        return InteractivePlanCommandView(
            output_text="No interactive plan exists yet. Run /plan <request> first.",
            success=False,
        )
    if snapshot.status != PLAN_STATUS_APPROVED:
        return InteractivePlanCommandView(
            output_text="The interactive plan is still pending approval. Run /approve-plan before executing the current task.",
            success=False,
        )

    selector = str(arg or "").strip()
    if selector:
        task = _resolve_task_selector(snapshot, selector)
        if task is None:
            available = ", ".join(record.id for record in snapshot.task_store.tasks)
            return InteractivePlanCommandView(
                output_text=f"Unknown task '{selector}'. Available tasks: {available}",
                success=False,
            )
    else:
        task = snapshot.active_task()
        if task is not None and task.status in DONE_TASK_STATUSES:
            task = next(
                (
                    candidate
                    for candidate in snapshot.task_store.tasks
                    if candidate.status not in DONE_TASK_STATUSES
                ),
                None,
            )

    if task is None:
        return InteractivePlanCommandView(
            output_text="No unfinished interactive task remains. Review /tasks or create a new /plan.",
            success=False,
        )
    if task.status in DONE_TASK_STATUSES:
        return InteractivePlanCommandView(
            output_text=f"Task '{task.id}' is already completed. Choose a pending task instead.",
            success=False,
        )

    runtime = _build_hook_runtime(omicsclaw_dir, hook_runtime)
    _attach_snapshot_hook_runtime(
        snapshot,
        runtime=runtime,
        workspace_dir=str(snapshot.task_store.metadata.get("workspace", "")).strip(),
    )
    selected = snapshot.select_task(task.id)
    output_lines = [
        f"Executing interactive task: {selected.id} — {selected.title}",
        "Dispatching the approved task to the assistant with the structured plan context.",
    ]
    dependency_warning = _unfinished_dependency_descriptors(snapshot, selected)
    if dependency_warning:
        output_lines.append(
            "Dependency warning: "
            + ", ".join(dependency_warning)
            + " is still incomplete, so the assistant should verify blockers instead of assuming the task is already satisfiable."
        )

    output_text = _append_hook_notices(
        "\n".join(output_lines),
        runtime,
        event_names=(EVENT_TASK_STARTED,),
    )
    return InteractivePlanCommandView(
        output_text=output_text,
        persist_session=True,
        session_metadata=_replace_plan_metadata(session_metadata, snapshot),
        replace_session_metadata=True,
        suggested_prompt=_build_task_suggested_prompt(snapshot, selected),
        execution_prompt=_build_task_execution_prompt(snapshot, selected),
    )


__all__ = [
    "INTERACTIVE_PLAN_METADATA_KEY",
    "InteractivePlanCommandView",
    "InteractivePlanSnapshot",
    "AutoPlanSeedResult",
    "PLAN_KIND_CUSTOM_ANALYSIS",
    "PLAN_KIND_GENERIC_ANALYSIS",
    "PLAN_KIND_SKILL_CREATION",
    "build_approve_plan_command_view",
    "build_do_current_task_command_view",
    "build_interactive_plan",
    "build_interactive_plan_context_from_metadata",
    "build_interactive_plan_summary_lines",
    "build_plan_command_view",
    "build_resume_task_command_view",
    "build_tasks_command_view",
    "classify_interactive_plan_kind",
    "format_interactive_plan",
    "format_interactive_tasks",
    "load_interactive_plan_from_metadata",
    "maybe_seed_interactive_plan",
    "normalize_interactive_plan_metadata",
    "parse_generic_approve_plan_command",
    "render_interactive_plan_context",
    "save_interactive_plan_to_metadata",
    "should_auto_enter_plan_mode",
]
