from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .events import EVENT_TASK_COMPLETED, EVENT_TASK_STARTED
from .hook_payloads import TaskHookPayload

TASK_STATUS_PENDING = "pending"
TASK_STATUS_IN_PROGRESS = "in_progress"
TASK_STATUS_COMPLETED = "completed"
TASK_STATUS_SKIPPED = "skipped"
TASK_STATUS_BLOCKED = "blocked"
TASK_STATUS_FAILED = "failed"

DONE_TASK_STATUSES = {TASK_STATUS_COMPLETED, TASK_STATUS_SKIPPED}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class TaskRecord:
    id: str
    title: str
    description: str = ""
    status: str = TASK_STATUS_PENDING
    owner: str = ""
    dependencies: list[str] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_utc_now_iso)
    updated_at: str = field(default_factory=_utc_now_iso)
    started_at: str = ""
    completed_at: str = ""

    def touch(self) -> None:
        self.updated_at = _utc_now_iso()

    def set_status(
        self,
        status: str,
        *,
        summary: str = "",
        artifact_ref: str = "",
        owner: str = "",
    ) -> None:
        self.status = status
        if owner:
            self.owner = owner
        if summary:
            self.metadata["summary"] = summary
        if artifact_ref and artifact_ref not in self.artifact_refs:
            self.artifact_refs.append(artifact_ref)
        now = _utc_now_iso()
        if status == TASK_STATUS_IN_PROGRESS and not self.started_at:
            self.started_at = now
        if status in DONE_TASK_STATUSES | {TASK_STATUS_FAILED}:
            self.completed_at = now
            if not self.started_at:
                self.started_at = now
        self.updated_at = now

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskRecord":
        return cls(
            id=data["id"],
            title=data["title"],
            description=data.get("description", ""),
            status=data.get("status", TASK_STATUS_PENDING),
            owner=data.get("owner", ""),
            dependencies=list(data.get("dependencies", [])),
            artifact_refs=list(data.get("artifact_refs", [])),
            metadata=dict(data.get("metadata", {})),
            created_at=data.get("created_at", _utc_now_iso()),
            updated_at=data.get("updated_at", _utc_now_iso()),
            started_at=data.get("started_at", ""),
            completed_at=data.get("completed_at", ""),
        )


@dataclass(slots=True)
class TaskStore:
    kind: str = "generic"
    tasks: list[TaskRecord] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    lifecycle_runtime: Any = field(default=None, repr=False)
    lifecycle_context: dict[str, Any] = field(default_factory=dict, repr=False)

    def attach_lifecycle_runtime(
        self,
        runtime: Any,
        *,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.lifecycle_runtime = runtime
        self.lifecycle_context = dict(context or {})

    def task_ids(self) -> list[str]:
        return [task.id for task in self.tasks]

    def get(self, task_id: str) -> TaskRecord | None:
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None

    def require(self, task_id: str) -> TaskRecord:
        task = self.get(task_id)
        if task is None:
            raise KeyError(f"Unknown task id: {task_id}")
        return task

    def add_task(self, task: TaskRecord) -> None:
        if self.get(task.id) is not None:
            raise ValueError(f"Duplicate task id: {task.id}")
        self.tasks.append(task)

    def ensure_task(self, task_id: str, **kwargs) -> TaskRecord:
        task = self.get(task_id)
        if task is None:
            task = TaskRecord(id=task_id, title=kwargs.pop("title", task_id), **kwargs)
            self.tasks.append(task)
        return task

    def set_task_status(
        self,
        task_id: str,
        status: str,
        *,
        summary: str = "",
        artifact_ref: str = "",
        owner: str = "",
    ) -> TaskRecord:
        task = self.require(task_id)
        previous_status = task.status
        task.set_status(
            status,
            summary=summary,
            artifact_ref=artifact_ref,
            owner=owner,
        )
        self._emit_task_lifecycle_event(task, previous_status=previous_status)
        return task

    def is_done(self, task_id: str) -> bool:
        return self.require(task_id).status in DONE_TASK_STATUSES

    def completed_task_ids(self) -> list[str]:
        return [task.id for task in self.tasks if task.status in DONE_TASK_STATUSES]

    def active_task(self) -> TaskRecord | None:
        for task in self.tasks:
            if task.status == TASK_STATUS_IN_PROGRESS:
                return task
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "metadata": dict(self.metadata),
            "tasks": [task.to_dict() for task in self.tasks],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskStore":
        return cls(
            kind=data.get("kind", "generic"),
            metadata=dict(data.get("metadata", {})),
            tasks=[TaskRecord.from_dict(item) for item in data.get("tasks", [])],
        )

    def save(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path) -> "TaskStore | None":
        path = Path(path)
        if not path.exists():
            return None
        try:
            return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, TypeError, KeyError, ValueError):
            return None

    def render_markdown(self, *, title: str = "# Tasks") -> str:
        lines = [title, ""]
        for meta_key in ("mode", "has_pdf"):
            if meta_key in self.metadata:
                lines.append(f"{meta_key}: {self.metadata[meta_key]}")
        if lines[-1] != "":
            lines.append("")

        for task in self.tasks:
            checkbox = {
                TASK_STATUS_PENDING: "[ ]",
                TASK_STATUS_IN_PROGRESS: "[-]",
                TASK_STATUS_COMPLETED: "[x]",
                TASK_STATUS_SKIPPED: "[x]",
                TASK_STATUS_BLOCKED: "[!]",
                TASK_STATUS_FAILED: "[!]",
            }.get(task.status, "[ ]")
            status_note = ""
            if task.status == TASK_STATUS_SKIPPED:
                status_note = " (skipped)"
            elif task.status == TASK_STATUS_IN_PROGRESS:
                status_note = " (in progress)"
            elif task.status == TASK_STATUS_FAILED:
                status_note = " (failed)"
            lines.append(f"- {checkbox} **{task.title}** — {task.description}{status_note}")
            summary = str(task.metadata.get("summary", "")).strip()
            if summary:
                lines.append(f"  summary: {summary}")
            if task.artifact_refs:
                lines.append(f"  artifacts: {', '.join(task.artifact_refs)}")

        lines.extend(["", "---", "*Auto-generated from structured task store.*"])
        return "\n".join(lines)

    def _emit_task_lifecycle_event(
        self,
        task: TaskRecord,
        *,
        previous_status: str,
    ) -> None:
        runtime = self.lifecycle_runtime
        if runtime is None or previous_status == task.status:
            return

        if task.status == TASK_STATUS_IN_PROGRESS:
            event_name = EVENT_TASK_STARTED
        elif task.status in DONE_TASK_STATUSES | {TASK_STATUS_FAILED}:
            event_name = EVENT_TASK_COMPLETED
        else:
            return

        payload = TaskHookPayload(
            task_id=task.id,
            title=task.title,
            status=task.status,
            owner=task.owner,
            summary=str(task.metadata.get("summary", "")).strip(),
            workspace=str(
                self.lifecycle_context.get("workspace")
                or self.metadata.get("workspace")
                or ""
            ).strip(),
            plan_kind=str(
                self.lifecycle_context.get("plan_kind")
                or self.metadata.get("plan_kind")
                or ""
            ).strip(),
            source=str(self.lifecycle_context.get("source") or self.kind).strip(),
            artifact_refs=tuple(task.artifact_refs),
            previous_status=previous_status,
        )
        runtime.emit(
            event_name,
            payload,
            context={
                "workspace": payload.workspace,
                "source": payload.source or self.kind,
            },
        )
