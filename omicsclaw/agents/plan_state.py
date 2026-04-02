"""Structured lifecycle state for research pipeline plan.md files."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from omicsclaw.agents.plan_validation import (
    PLAN_VALIDATION_METADATA_KEY,
    PlanValidationResult,
    PlanValidationSnapshot,
    load_plan_validation_snapshot,
    resolve_plan_validation_snapshot,
)

PLAN_STATE_METADATA_KEY = "plan_state"
PLAN_STATUS_PENDING_APPROVAL = "pending_approval"
PLAN_STATUS_APPROVED = "approved"

_LEGACY_PLAN_METADATA_KEYS = (
    "plan_status",
    "plan_approved_at",
    "plan_approved_by",
    "plan_approval_notes",
    PLAN_VALIDATION_METADATA_KEY,
)


@dataclass(slots=True)
class PlanStateSnapshot:
    status: str = ""
    approved_at: str = ""
    approved_by: str = ""
    approval_notes: str = ""
    validation: PlanValidationSnapshot | None = None

    def is_empty(self) -> bool:
        return not any(
            (
                self.status,
                self.approved_at,
                self.approved_by,
                self.approval_notes,
            )
        ) and self.validation is None

    def mark_pending_approval(self) -> None:
        self.status = PLAN_STATUS_PENDING_APPROVAL
        self.approved_at = ""
        self.approved_by = ""
        self.approval_notes = ""

    def mark_approved(
        self,
        *,
        approved_at: str,
        approved_by: str = "user",
        approval_notes: str = "",
    ) -> None:
        self.status = PLAN_STATUS_APPROVED
        self.approved_at = approved_at
        self.approved_by = approved_by
        self.approval_notes = approval_notes

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "status": self.status,
            "approved_at": self.approved_at,
            "approved_by": self.approved_by,
            "approval_notes": self.approval_notes,
        }
        if self.validation is not None:
            data["validation"] = self.validation.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "PlanStateSnapshot | None":
        if not isinstance(data, Mapping):
            return None
        return cls(
            status=str(data.get("status", "")).strip(),
            approved_at=str(data.get("approved_at", "")).strip(),
            approved_by=str(data.get("approved_by", "")).strip(),
            approval_notes=str(data.get("approval_notes", "")).strip(),
            validation=load_plan_validation_snapshot(data.get("validation")),
        )


def load_plan_state_from_metadata(metadata: Mapping[str, Any]) -> PlanStateSnapshot:
    state = PlanStateSnapshot.from_dict(metadata.get(PLAN_STATE_METADATA_KEY))
    if state is not None:
        return state
    return PlanStateSnapshot(
        status=str(metadata.get("plan_status", "")).strip(),
        approved_at=str(metadata.get("plan_approved_at", "")).strip(),
        approved_by=str(metadata.get("plan_approved_by", "")).strip(),
        approval_notes=str(metadata.get("plan_approval_notes", "")).strip(),
        validation=load_plan_validation_snapshot(
            metadata.get(PLAN_VALIDATION_METADATA_KEY)
        ),
    )


def save_plan_state_to_metadata(
    metadata: dict[str, Any],
    plan_state: PlanStateSnapshot | None,
) -> None:
    metadata.pop(PLAN_STATE_METADATA_KEY, None)
    for key in _LEGACY_PLAN_METADATA_KEYS:
        metadata.pop(key, None)
    if plan_state is None or plan_state.is_empty():
        return
    metadata[PLAN_STATE_METADATA_KEY] = plan_state.to_dict()


def sync_plan_state_metadata(
    metadata: dict[str, Any],
    workspace: str | Path,
) -> PlanStateSnapshot:
    plan_state = load_plan_state_from_metadata(metadata)
    plan_path = Path(workspace).expanduser().resolve() / "plan.md"
    plan_state.validation = resolve_plan_validation_snapshot(
        plan_path,
        plan_state.validation,
    )
    save_plan_state_to_metadata(metadata, plan_state)
    return plan_state


def build_plan_result_payload(
    plan_state: PlanStateSnapshot | None,
    *,
    awaiting_approval: bool = False,
) -> dict[str, Any]:
    validation_result: PlanValidationResult | None = None
    if plan_state is not None and plan_state.validation is not None:
        validation_result = plan_state.validation.to_result()

    return {
        "status": plan_state.status if plan_state is not None else "",
        "awaiting_approval": awaiting_approval,
        "approved_at": plan_state.approved_at if plan_state is not None else "",
        "approved_by": plan_state.approved_by if plan_state is not None else "",
        "approval_notes": plan_state.approval_notes if plan_state is not None else "",
        "validation": {
            "available": validation_result is not None,
            "valid": validation_result.valid if validation_result is not None else False,
            "errors": validation_result.errors if validation_result is not None else [],
            "warnings": validation_result.warnings if validation_result is not None else [],
            "detected_sections": (
                validation_result.detected_sections
                if validation_result is not None
                else []
            ),
            "stage_count": validation_result.stage_count if validation_result is not None else 0,
        },
    }
