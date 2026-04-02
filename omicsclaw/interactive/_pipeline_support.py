"""Shared helpers for research pipeline commands in interactive surfaces."""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from omicsclaw.agents.pipeline import PIPELINE_STAGE_IDS, PipelineState
from omicsclaw.agents.pipeline_result import PipelineRunResult, normalize_pipeline_result
from omicsclaw.agents.plan_state import (
    PLAN_STATUS_APPROVED,
    PLAN_STATUS_PENDING_APPROVAL,
    load_plan_state_from_metadata,
    save_plan_state_to_metadata,
)
from omicsclaw.agents.plan_validation import (
    PlanValidationResult,
    resolve_plan_validation_result,
)
from omicsclaw.interactive._history_support import (
    build_research_history_messages as _build_research_history_messages,
)
from omicsclaw.runtime.events import EVENT_PLAN_APPROVED, EVENT_TASK_COMPLETED
from omicsclaw.runtime.hook_payloads import PlanHookPayload
from omicsclaw.runtime.hooks import (
    HOOK_MODE_NOTICE,
    LifecycleHookRuntime,
    build_default_lifecycle_hook_runtime,
    format_hook_notice_block,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_hook_runtime(
    omicsclaw_dir: str = "",
    hook_runtime: LifecycleHookRuntime | None = None,
) -> LifecycleHookRuntime | None:
    if hook_runtime is not None:
        return hook_runtime
    if not str(omicsclaw_dir or "").strip():
        return None
    return build_default_lifecycle_hook_runtime(omicsclaw_dir)


@dataclass(slots=True)
class ResearchCommandArgs:
    pdf_path: str | None = None
    idea: str = ""
    h5ad_path: str | None = None
    output_dir: str | None = None
    resume: bool = False
    from_stage: str | None = None
    skip_stages: list[str] = field(default_factory=list)
    plan_only: bool = False


@dataclass(slots=True)
class ApprovePlanArgs:
    workspace: str | None = None
    notes: str = ""
    approver: str = "user"


@dataclass(slots=True)
class PipelineWorkspaceSnapshot:
    workspace: Path
    state: PipelineState | None
    plan_path: Path
    todos_path: Path
    report_path: Path
    review_path: Path

    def plan_validation(self) -> PlanValidationResult:
        return resolve_plan_validation_result(
            self.plan_path,
            self.cached_plan_validation,
        )

    @property
    def exists(self) -> bool:
        return self.workspace.exists()

    @property
    def task_store(self):
        if self.state is None:
            return None
        return self.state.task_store

    @property
    def cached_plan_validation(self):
        plan_state = self.plan_state
        if plan_state is None:
            return None
        return plan_state.validation

    @property
    def plan_state(self):
        task_store = self.task_store
        if task_store is None:
            return None
        return load_plan_state_from_metadata(task_store.metadata)

    @property
    def has_pipeline_state(self) -> bool:
        return self.state is not None and self.task_store is not None

    @property
    def current_stage(self) -> str:
        if self.state is None:
            return ""
        return self.state.current_stage

    @property
    def plan_status(self) -> str:
        plan_state = self.plan_state
        if plan_state is None:
            return ""
        return plan_state.status

    @property
    def plan_approved_at(self) -> str:
        plan_state = self.plan_state
        if plan_state is None:
            return ""
        return plan_state.approved_at

    @property
    def plan_approved_by(self) -> str:
        plan_state = self.plan_state
        if plan_state is None:
            return ""
        return plan_state.approved_by

    @property
    def plan_approval_notes(self) -> str:
        plan_state = self.plan_state
        if plan_state is None:
            return ""
        return plan_state.approval_notes


@dataclass(slots=True)
class PlanDisplayView:
    status: str = ""
    awaiting_approval: bool = False
    approved_at: str = ""
    approved_by: str = ""
    approval_notes: str = ""
    validation_available: bool = False
    validation_valid: bool = False
    validation_errors: list[str] = field(default_factory=list)
    validation_warnings: list[str] = field(default_factory=list)
    validation_stage_count: int = 0
    next_action: str = ""


@dataclass(slots=True)
class PipelineDisplayView:
    workspace: str
    workspace_exists: bool = True
    has_pipeline_state: bool = True
    mode: str = "?"
    paper_flag: str = "?"
    current_stage: str = ""
    completed_stages: list[str] = field(default_factory=list)
    review_iterations: int = 0
    plan: PlanDisplayView = field(default_factory=PlanDisplayView)
    report_path: str = ""
    review_path: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PipelineCommandView:
    output_text: str
    active_workspace: str = ""
    persist_session: bool = False


def _paper_flag_from_mode(mode: str) -> str:
    if mode in {"A", "B"}:
        return "yes"
    if mode == "C":
        return "no"
    return "?"


def _next_plan_action(status: str, *, awaiting_approval: bool = False) -> str:
    if awaiting_approval or status == PLAN_STATUS_PENDING_APPROVAL:
        return "review plan.md, then run /approve-plan"
    return ""


def build_resume_task_command(
    workspace: str | Path,
    *,
    stage: str = "research",
) -> str:
    resolved = Path(workspace).expanduser().resolve()
    return f"/resume-task {stage} --output {resolved}"


def build_resume_research_command(
    workspace: str | Path,
    *,
    idea: str = "",
) -> str:
    resolved = Path(workspace).expanduser().resolve()
    command = f"/research --resume --output {resolved}"
    if idea:
        command += f" --idea {shlex.quote(idea)}"
    return command


def build_pipeline_display_from_snapshot(
    snapshot: PipelineWorkspaceSnapshot,
) -> PipelineDisplayView:
    if not snapshot.exists:
        return PipelineDisplayView(
            workspace=str(snapshot.workspace),
            workspace_exists=False,
            has_pipeline_state=False,
        )

    if not snapshot.has_pipeline_state:
        return PipelineDisplayView(
            workspace=str(snapshot.workspace),
            workspace_exists=True,
            has_pipeline_state=False,
        )

    task_store = snapshot.task_store
    assert task_store is not None
    validation = snapshot.plan_validation() if snapshot.plan_path.exists() else None
    mode = str(task_store.metadata.get("mode", "?")).strip() or "?"
    plan = PlanDisplayView(
        status=snapshot.plan_status,
        approved_at=snapshot.plan_approved_at,
        approved_by=snapshot.plan_approved_by,
        approval_notes=snapshot.plan_approval_notes,
        validation_available=validation is not None,
        validation_valid=validation.valid if validation is not None else False,
        validation_errors=list(validation.errors) if validation is not None else [],
        validation_warnings=list(validation.warnings) if validation is not None else [],
        validation_stage_count=validation.stage_count if validation is not None else 0,
        next_action=_next_plan_action(snapshot.plan_status),
    )
    return PipelineDisplayView(
        workspace=str(snapshot.workspace),
        workspace_exists=True,
        has_pipeline_state=True,
        mode=mode,
        paper_flag="yes"
        if task_store.metadata.get("has_pdf") is True
        else "no"
        if task_store.metadata.get("has_pdf") is False
        else _paper_flag_from_mode(mode),
        current_stage=snapshot.current_stage,
        completed_stages=list(snapshot.state.completed_stages if snapshot.state else []),
        review_iterations=snapshot.state.review_iterations if snapshot.state else 0,
        plan=plan,
        report_path=str(snapshot.report_path) if snapshot.report_path.exists() else "",
        review_path=str(snapshot.review_path) if snapshot.review_path.exists() else "",
    )


def build_pipeline_display_from_result(
    result: PipelineRunResult | dict[str, object],
) -> PipelineDisplayView:
    run_result = (
        result
        if isinstance(result, PipelineRunResult)
        else normalize_pipeline_result(result)
    )
    mode = str(run_result.intake.get("mode", "?")).strip() or "?"
    current_stage = ""
    if run_result.completed_stages:
        current_stage = run_result.completed_stages[-1]
    if run_result.plan.awaiting_approval:
        current_stage = "plan"
    plan = PlanDisplayView(
        status=run_result.plan.status,
        awaiting_approval=run_result.plan.awaiting_approval,
        approved_at=run_result.plan.approved_at,
        approved_by=run_result.plan.approved_by,
        approval_notes=run_result.plan.approval_notes,
        validation_available=run_result.plan.validation.available,
        validation_valid=run_result.plan.validation.valid,
        validation_errors=list(run_result.plan.validation.errors),
        validation_warnings=list(run_result.plan.validation.warnings),
        validation_stage_count=run_result.plan.validation.stage_count,
        next_action=_next_plan_action(
            run_result.plan.status,
            awaiting_approval=run_result.plan.awaiting_approval,
        ),
    )
    return PipelineDisplayView(
        workspace=run_result.workspace,
        workspace_exists=bool(run_result.workspace),
        has_pipeline_state=True,
        mode=mode,
        paper_flag=_paper_flag_from_mode(mode),
        current_stage=current_stage,
        completed_stages=list(run_result.completed_stages),
        review_iterations=run_result.review_iterations,
        plan=plan,
        report_path=run_result.report_path,
        review_path=run_result.review_path,
        warnings=list(run_result.warnings),
    )


def format_research_start_summary(
    command_args: ResearchCommandArgs,
    workspace: str | Path,
    snapshot: PipelineWorkspaceSnapshot,
    *,
    mode: str,
) -> str:
    workspace_path = str(Path(workspace).expanduser().resolve())
    lines: list[str] = []
    if command_args.resume:
        lines.append("[bold cyan]🔄 Resuming Research Pipeline from checkpoint[/bold cyan]")
    elif command_args.from_stage:
        lines.append(
            f"[bold cyan]↻ Continuing Research Pipeline from stage '{command_args.from_stage}'[/bold cyan]"
        )
    elif command_args.plan_only:
        lines.append("[bold cyan]📝 Starting Research Pipeline in Plan-Only Mode[/bold cyan]")
    else:
        lines.append(f"[bold cyan]🔬 Starting Research Pipeline (Mode {mode})[/bold cyan]")

    lines.append(f"  [dim]Workspace:[/dim] {workspace_path}")
    if command_args.pdf_path:
        lines.append(f"  [dim]PDF:[/dim]      {command_args.pdf_path}")
    if command_args.idea:
        lines.append(f"  [dim]Idea:[/dim]     {command_args.idea}")
    if command_args.h5ad_path:
        lines.append(f"  [dim]Data:[/dim]     {command_args.h5ad_path}")
    if command_args.skip_stages:
        lines.append(f"  [dim]Skip:[/dim]     {', '.join(command_args.skip_stages)}")
    if command_args.plan_only:
        lines.append("  [dim]Gate:[/dim]     stop after plan.md and wait for approval")

    if snapshot.has_pipeline_state:
        view = build_pipeline_display_from_snapshot(snapshot)
        completed = ", ".join(view.completed_stages) or "none"
        lines.append(f"  [dim]Completed:[/dim] {completed}")
        lines.append(f"  [dim]Current:[/dim]   {view.current_stage or 'none'}")
        lines.append(f"  [dim]Reviews:[/dim]   {view.review_iterations}")
        if view.plan.status:
            lines.append(f"  [dim]Plan:[/dim]      {view.plan.status}")
    elif command_args.resume or command_args.from_stage:
        lines.append(
            "  [yellow]⚠ No structured pipeline state found in the workspace.[/yellow]"
        )

    if mode == "C" and not (command_args.resume or command_args.from_stage):
        lines.append(
            "  [dim]Mode:[/dim]     Idea only — research-agent will find literature & data"
        )
    return "\n".join(lines)


def format_research_result_summary(
    result: PipelineRunResult | dict[str, object],
    *,
    workspace_fallback: str | Path,
    idea: str = "",
) -> str:
    run_result = (
        result if isinstance(result, PipelineRunResult) else normalize_pipeline_result(result)
    )
    view = build_pipeline_display_from_result(run_result)
    workspace = view.workspace or str(Path(workspace_fallback).expanduser().resolve())

    lines: list[str] = []
    if run_result.success and view.plan.awaiting_approval:
        lines.append("[bold yellow]⏸ Plan generated and awaiting approval[/bold yellow]")
        lines.append(f"  [dim]Workspace:[/dim]  {workspace}")
        if view.plan.status:
            lines.append(f"  [dim]Plan Status:[/dim] {view.plan.status}")
        lines.append(
            f"  [dim]Plan Validation:[/dim] {'passed' if view.plan.validation_valid else 'failed'}"
        )
        for error in view.plan.validation_errors:
            lines.append(f"  [red]✗ {error}[/red]")
        for warning in view.plan.validation_warnings:
            lines.append(f"  [yellow]⚠ {warning}[/yellow]")
        lines.append("  [dim]Next:[/dim]      /plan")
        lines.append("  [dim]Approve:[/dim]   /approve-plan")
        lines.append(
            f"  [dim]Continue:[/dim]  {build_resume_task_command(workspace)}"
        )
        return "\n".join(lines)

    if run_result.success:
        if run_result.completion.completed:
            lines.append("[bold green]✓ Research pipeline completed![/bold green]")
        else:
            lines.append(
                "[bold yellow]⚠ Research pipeline finished with an incomplete completion gate[/bold yellow]"
            )
        lines.append(f"  [dim]Workspace:[/dim]  {workspace}")
        if run_result.report_path:
            lines.append(f"  [dim]Report:[/dim]     {run_result.report_path}")
        if run_result.review_path:
            lines.append(f"  [dim]Review:[/dim]     {run_result.review_path}")
        if run_result.manifest_path:
            lines.append(f"  [dim]Manifest:[/dim]   {run_result.manifest_path}")
        if run_result.completion_report_path:
            lines.append(
                f"  [dim]Completion:[/dim] {run_result.completion_report_path}"
            )
        if run_result.completion.status:
            lines.append(
                f"  [dim]Gate Status:[/dim] {run_result.completion.status}"
            )
        if view.completed_stages:
            lines.append(f"  [dim]Stages:[/dim]     {' → '.join(view.completed_stages)}")
        if view.review_iterations > 0:
            lines.append(f"  [dim]Reviews:[/dim]    {view.review_iterations}")
        if run_result.review_cap_reached:
            lines.append(
                f"  [yellow]⚠ Review iteration cap reached ({view.review_iterations})[/yellow]"
            )
        for missing in run_result.completion.missing_required_artifacts:
            lines.append(f"  [yellow]⚠ Missing artifact: {missing}[/yellow]")
        for warning in run_result.completion.warnings:
            if warning not in view.warnings:
                lines.append(f"  [yellow]⚠ {warning}[/yellow]")
        for warning in view.warnings:
            lines.append(f"  [yellow]⚠ {warning}[/yellow]")
        return "\n".join(lines)

    lines.append(f"[red]✗ Research pipeline failed: {run_result.error or 'unknown'}[/red]")
    if view.completed_stages:
        lines.append(
            f"  [dim]Completed stages before failure:[/dim] {', '.join(view.completed_stages)}"
        )
    lines.append(
        f"  [dim]To resume:[/dim] {build_resume_research_command(workspace, idea=idea)}"
    )
    return "\n".join(lines)


def build_research_history_entries(
    command_args: ResearchCommandArgs,
    result: PipelineRunResult | dict[str, object],
    *,
    mode: str,
    workspace_fallback: str | Path,
) -> list[dict[str, str]]:
    return _build_research_history_messages(
        mode=mode,
        idea=command_args.idea,
        pdf_path=command_args.pdf_path,
        h5ad_path=command_args.h5ad_path,
        resume=command_args.resume,
        from_stage=command_args.from_stage,
        skip_stages=command_args.skip_stages,
        plan_only=command_args.plan_only,
        workspace_fallback=workspace_fallback,
        result=result,
    )


def build_research_history_messages(
    command_args: ResearchCommandArgs,
    result: PipelineRunResult | dict[str, object],
    *,
    mode: str,
    workspace_fallback: str | Path,
) -> list[dict[str, str]]:
    """Backward-compatible wrapper around the shared history formatter."""
    return build_research_history_entries(
        command_args,
        result,
        mode=mode,
        workspace_fallback=workspace_fallback,
    )


def build_approve_plan_command_view(
    arg: str,
    *,
    workspace_fallback: str | Path,
    omicsclaw_dir: str = "",
    hook_runtime: LifecycleHookRuntime | None = None,
) -> PipelineCommandView:
    command_args = parse_approve_plan_command(arg)
    workspace = resolve_pipeline_workspace(
        command_args.workspace,
        workspace_fallback,
    )
    runtime = _build_hook_runtime(omicsclaw_dir, hook_runtime)
    snapshot = approve_pipeline_plan(
        workspace,
        approver=command_args.approver,
        notes=command_args.notes,
        hook_runtime=runtime,
    )
    output_text = (
        f"Plan approved for: {snapshot.workspace}\n"
        f"{format_pipeline_tasks(snapshot)}\n"
        f"Continue with: {build_resume_task_command(snapshot.workspace)}"
    )
    if runtime is not None:
        notice_block = format_hook_notice_block(
            runtime.consume_pending_messages(
                mode=HOOK_MODE_NOTICE,
                event_names=(EVENT_PLAN_APPROVED, EVENT_TASK_COMPLETED),
            )
        )
        if notice_block:
            output_text = f"{output_text}\n\n{notice_block}"
    return PipelineCommandView(
        output_text=output_text,
        active_workspace=str(snapshot.workspace),
        persist_session=True,
    )


def _parse_skip_value(raw_value: str) -> list[str]:
    values = [item.strip() for item in raw_value.split(",")]
    return [value for value in values if value]


def _validate_stage(stage: str, *, flag_name: str) -> str:
    if stage not in PIPELINE_STAGE_IDS:
        raise ValueError(
            f"Invalid {flag_name} '{stage}'. Must be one of: "
            + ", ".join(PIPELINE_STAGE_IDS)
        )
    return stage


def _parse_research_tokens(tokens: list[str]) -> ResearchCommandArgs:
    args = ResearchCommandArgs()
    idx = 0

    if tokens and not tokens[0].startswith("--"):
        args.pdf_path = tokens[0]
        idx = 1

    while idx < len(tokens):
        token = tokens[idx]
        if token == "--idea":
            if idx + 1 >= len(tokens):
                raise ValueError("--idea requires a value")
            args.idea = tokens[idx + 1]
            idx += 2
        elif token == "--h5ad":
            if idx + 1 >= len(tokens):
                raise ValueError("--h5ad requires a value")
            args.h5ad_path = tokens[idx + 1]
            idx += 2
        elif token in {"--output", "--workspace"}:
            if idx + 1 >= len(tokens):
                raise ValueError(f"{token} requires a value")
            args.output_dir = tokens[idx + 1]
            idx += 2
        elif token == "--resume":
            args.resume = True
            idx += 1
        elif token == "--plan-only":
            args.plan_only = True
            idx += 1
        elif token == "--from-stage":
            if idx + 1 >= len(tokens):
                raise ValueError("--from-stage requires a stage name")
            args.from_stage = _validate_stage(
                tokens[idx + 1],
                flag_name="--from-stage",
            )
            idx += 2
        elif token == "--skip":
            if idx + 1 >= len(tokens):
                raise ValueError("--skip requires a comma-separated stage list")
            for stage in _parse_skip_value(tokens[idx + 1]):
                args.skip_stages.append(
                    _validate_stage(stage, flag_name="--skip")
                )
            idx += 2
        else:
            raise ValueError(f"Unknown argument: {token}")

    return args


def parse_research_command(arg: str) -> ResearchCommandArgs:
    tokens = shlex.split(arg.strip()) if arg.strip() else []
    return _parse_research_tokens(tokens)


def parse_resume_task_command(arg: str) -> ResearchCommandArgs:
    tokens = shlex.split(arg.strip()) if arg.strip() else []
    if not tokens:
        raise ValueError(
            "Usage: /resume-task <stage> [workspace.pdf] [--output <dir>] "
            "[--idea \"...\"] [--h5ad <file>] [--skip stage1,stage2]"
        )

    stage = _validate_stage(tokens[0], flag_name="stage")
    args = _parse_research_tokens(tokens[1:])
    args.from_stage = stage
    return args


def parse_approve_plan_command(arg: str) -> ApprovePlanArgs:
    tokens = shlex.split(arg.strip()) if arg.strip() else []
    args = ApprovePlanArgs()
    idx = 0

    if tokens and not tokens[0].startswith("--"):
        args.workspace = tokens[0]
        idx = 1

    while idx < len(tokens):
        token = tokens[idx]
        if token == "--notes":
            if idx + 1 >= len(tokens):
                raise ValueError("--notes requires a value")
            args.notes = tokens[idx + 1]
            idx += 2
        elif token == "--by":
            if idx + 1 >= len(tokens):
                raise ValueError("--by requires a value")
            args.approver = tokens[idx + 1]
            idx += 2
        else:
            raise ValueError(f"Unknown argument: {token}")

    return args


def looks_like_pipeline_workspace(path: str | Path) -> bool:
    workspace = Path(path).expanduser().resolve()
    if not workspace.exists():
        return False
    return any(
        (workspace / candidate).exists()
        for candidate in (
            ".pipeline_tasks.json",
            ".pipeline_checkpoint.json",
            "todos.md",
            "plan.md",
            "final_report.md",
            "review_report.json",
        )
    )


def resolve_research_workspace(
    output_dir: str | None,
    session_workspace: str | None,
) -> Path:
    if output_dir:
        return Path(output_dir).expanduser().resolve()

    base = Path(session_workspace or ".").expanduser().resolve()
    if looks_like_pipeline_workspace(base):
        return base
    return (base / "research_workspace").resolve()


def resolve_pipeline_workspace(
    explicit_workspace: str | None,
    session_workspace: str | None,
) -> Path:
    if explicit_workspace:
        return Path(explicit_workspace).expanduser().resolve()

    base = Path(session_workspace or ".").expanduser().resolve()
    if looks_like_pipeline_workspace(base):
        return base

    nested = (base / "research_workspace").resolve()
    if looks_like_pipeline_workspace(nested):
        return nested
    return base


def load_pipeline_workspace_snapshot(workspace: str | Path) -> PipelineWorkspaceSnapshot:
    resolved = Path(workspace).expanduser().resolve()
    return PipelineWorkspaceSnapshot(
        workspace=resolved,
        state=PipelineState.load_checkpoint(resolved),
        plan_path=resolved / "plan.md",
        todos_path=resolved / "todos.md",
        report_path=resolved / "final_report.md",
        review_path=resolved / "review_report.json",
    )


def approve_pipeline_plan(
    workspace: str | Path,
    *,
    approver: str = "user",
    notes: str = "",
    hook_runtime: LifecycleHookRuntime | None = None,
) -> PipelineWorkspaceSnapshot:
    snapshot = load_pipeline_workspace_snapshot(workspace)
    if not snapshot.exists:
        raise ValueError(f"Workspace does not exist: {snapshot.workspace}")
    if snapshot.state is None:
        raise ValueError(
            f"No structured pipeline state found in workspace: {snapshot.workspace}"
        )
    if not snapshot.plan_path.exists():
        raise ValueError(f"No plan.md found in workspace: {snapshot.workspace}")

    validation = snapshot.plan_validation()
    if not validation.valid:
        joined = "\n".join(f"- {error}" for error in validation.errors)
        raise ValueError(f"Plan validation failed:\n{joined}")

    state = snapshot.state
    if hook_runtime is not None:
        state.task_store.attach_lifecycle_runtime(
            hook_runtime,
            context={
                "workspace": str(snapshot.workspace),
                "plan_kind": "research_pipeline",
                "source": "research_pipeline",
            },
        )
    if not state.is_stage_done("plan"):
        state.mark_stage_completed(
            "plan",
            summary=f"Plan approved by {approver}",
            artifact_ref=str(snapshot.plan_path),
        )
    else:
        plan_task = state.task_store.require("plan")
        if str(snapshot.plan_path) not in plan_task.artifact_refs:
            plan_task.artifact_refs.append(str(snapshot.plan_path))

    plan_state = snapshot.plan_state or load_plan_state_from_metadata(
        state.task_store.metadata
    )
    plan_state.mark_approved(
        approved_at=_utc_now_iso(),
        approved_by=approver,
        approval_notes=notes,
    )
    save_plan_state_to_metadata(state.task_store.metadata, plan_state)
    if hook_runtime is not None:
        hook_runtime.emit(
            EVENT_PLAN_APPROVED,
            PlanHookPayload(
                request=str(state.task_store.metadata.get("idea", "")).strip(),
                plan_kind="research_pipeline",
                status=plan_state.status,
                task_count=len(state.task_store.tasks),
                workspace=str(snapshot.workspace),
                source="research_pipeline",
            ),
            context={
                "workspace": str(snapshot.workspace),
                "source": "research_pipeline",
            },
        )

    state.checkpoint(snapshot.workspace)
    return load_pipeline_workspace_snapshot(snapshot.workspace)


def format_pipeline_tasks(snapshot: PipelineWorkspaceSnapshot) -> str:
    view = build_pipeline_display_from_snapshot(snapshot)
    lines = [f"Pipeline workspace: {snapshot.workspace}"]

    if not view.workspace_exists:
        lines.append("Workspace does not exist.")
        return "\n".join(lines)

    if not view.has_pipeline_state:
        lines.append("No structured pipeline state found in this workspace.")
        return "\n".join(lines)

    task_store = snapshot.task_store
    assert task_store is not None

    lines.append(f"Mode: {view.mode} | Paper: {view.paper_flag}")
    lines.append(f"Current stage: {view.current_stage or 'none'}")
    lines.append(f"Review iterations: {view.review_iterations}")
    if view.plan.status:
        approval_line = f"Plan approval: {view.plan.status}"
        if view.plan.approved_by:
            approval_line += f" by {view.plan.approved_by}"
        if view.plan.approved_at:
            approval_line += f" at {view.plan.approved_at}"
        lines.append(approval_line)
        if view.plan.next_action:
            lines.append(f"Next action: {view.plan.next_action}")
    if view.plan.approval_notes:
        lines.append(f"Plan notes: {view.plan.approval_notes}")
    if view.plan.validation_available:
        lines.append(
            f"Plan validation: {'passed' if view.plan.validation_valid else 'failed'} "
            f"(stages: {view.plan.validation_stage_count})"
        )
        if view.plan.validation_errors:
            lines.append("Plan errors:")
            for error in view.plan.validation_errors:
                lines.append(f"  - {error}")
        if view.plan.validation_warnings:
            lines.append("Plan warnings:")
            for warning in view.plan.validation_warnings:
                lines.append(f"  - {warning}")
    lines.append(
        "Completed: " + (", ".join(view.completed_stages) if view.completed_stages else "none")
    )
    lines.append("")

    markers = {
        "pending": "[ ]",
        "in_progress": "[-]",
        "completed": "[x]",
        "skipped": "[x]",
        "failed": "[!]",
        "blocked": "[!]",
    }
    for task in task_store.tasks:
        lines.append(
            f"{markers.get(task.status, '[ ]')} {task.title} — {task.description}"
        )
        summary = str(task.metadata.get("summary", "")).strip()
        if summary:
            lines.append(f"    summary: {summary}")
        if task.artifact_refs:
            lines.append(f"    artifacts: {', '.join(task.artifact_refs)}")

    return "\n".join(lines)


def build_pipeline_tasks_command_view(
    workspace_arg: str | None,
    *,
    workspace_fallback: str | Path,
) -> PipelineCommandView:
    workspace = resolve_pipeline_workspace(workspace_arg, workspace_fallback)
    snapshot = load_pipeline_workspace_snapshot(workspace)
    return PipelineCommandView(
        output_text=format_pipeline_tasks(snapshot),
        active_workspace=str(snapshot.workspace) if snapshot.has_pipeline_state else "",
    )


def format_plan_preview(
    snapshot: PipelineWorkspaceSnapshot,
    *,
    max_lines: int = 80,
) -> str:
    view = build_pipeline_display_from_snapshot(snapshot)
    lines = [f"Pipeline workspace: {snapshot.workspace}"]

    if not view.workspace_exists:
        lines.append("Workspace does not exist.")
        return "\n".join(lines)

    if not snapshot.plan_path.exists():
        lines.append("No plan.md found in this workspace.")
        return "\n".join(lines)

    content_lines = snapshot.plan_path.read_text(encoding="utf-8").splitlines()
    preview = content_lines[:max_lines]
    lines.append(f"Plan file: {snapshot.plan_path}")
    if view.plan.status:
        approval_line = f"Plan approval: {view.plan.status}"
        if view.plan.approved_by:
            approval_line += f" by {view.plan.approved_by}"
        lines.append(approval_line)
        if view.plan.next_action:
            lines.append("Next action: /approve-plan")
    if view.plan.approval_notes:
        lines.append(f"Plan notes: {view.plan.approval_notes}")
    lines.append(
        f"Plan validation: {'passed' if view.plan.validation_valid else 'failed'} "
        f"(stages: {view.plan.validation_stage_count})"
    )
    if view.plan.validation_errors:
        lines.append("Validation errors:")
        for error in view.plan.validation_errors:
            lines.append(f"- {error}")
    if view.plan.validation_warnings:
        lines.append("Validation warnings:")
        for warning in view.plan.validation_warnings:
            lines.append(f"- {warning}")
    lines.append("")
    lines.append("# Plan")
    lines.append("")
    lines.extend(preview)
    if len(content_lines) > max_lines:
        lines.append("")
        lines.append(f"... truncated ({len(content_lines) - max_lines} more lines)")
    return "\n".join(lines)


def build_plan_preview_command_view(
    workspace_arg: str | None,
    *,
    workspace_fallback: str | Path,
) -> PipelineCommandView:
    workspace = resolve_pipeline_workspace(workspace_arg, workspace_fallback)
    snapshot = load_pipeline_workspace_snapshot(workspace)
    return PipelineCommandView(
        output_text=format_plan_preview(snapshot),
        active_workspace=str(snapshot.workspace) if snapshot.has_pipeline_state else "",
    )
