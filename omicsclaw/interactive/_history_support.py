"""Shared conversation-history formatters for interactive command execution."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from omicsclaw.agents.pipeline_result import (
    PipelineRunResult,
    normalize_pipeline_result,
)


def build_research_history_messages(
    *,
    mode: str,
    idea: str = "",
    pdf_path: str | None = None,
    h5ad_path: str | None = None,
    resume: bool = False,
    from_stage: str | None = None,
    skip_stages: list[str] | None = None,
    plan_only: bool = False,
    workspace_fallback: str | Path,
    result: PipelineRunResult | dict[str, object],
) -> list[dict[str, str]]:
    run_result = (
        result if isinstance(result, PipelineRunResult) else normalize_pipeline_result(result)
    )
    workspace = run_result.workspace or str(Path(workspace_fallback).expanduser().resolve())

    user_parts = [f"[Research pipeline Mode {mode}]"]
    if idea:
        user_parts.append(f"Idea: {idea}")
    if pdf_path:
        user_parts.append(f"PDF: {pdf_path}")
    if h5ad_path:
        user_parts.append(f"H5AD: {h5ad_path}")
    if resume:
        user_parts.append("resume: true")
    if from_stage:
        user_parts.append(f"from_stage: {from_stage}")
    if skip_stages:
        user_parts.append(f"skip: {','.join(skip_stages)}")
    if plan_only:
        user_parts.append("plan_only: true")
    user_parts.append(f"workspace: {workspace}")

    status_text = (
        "awaiting approval"
        if run_result.plan.awaiting_approval
        else "completed"
        if run_result.success and run_result.completion.completed
        else "incomplete"
        if run_result.success
        else "failed"
    )
    assistant_parts = [f"Research pipeline {status_text}.", f"Workspace: {workspace}"]
    if run_result.plan.status:
        assistant_parts.append(f"Plan status: {run_result.plan.status}")
    if run_result.completion.status:
        assistant_parts.append(f"Completion status: {run_result.completion.status}")
    if run_result.report_path:
        assistant_parts.append(f"Report: {run_result.report_path}")
    if run_result.review_path:
        assistant_parts.append(f"Review: {run_result.review_path}")
    if run_result.error:
        assistant_parts.append(f"Error: {run_result.error}")

    return [
        {
            "role": "user",
            "content": " ".join(user_parts),
        },
        {
            "role": "assistant",
            "content": " ".join(assistant_parts),
        },
    ]


def build_skill_run_result_text(
    skill: str,
    result: dict[str, Any],
) -> str:
    if result.get("success"):
        return (
            f"Skill '{skill}' completed successfully. "
            f"Output: {result.get('output_dir', '?')}"
        )
    error_text = str(result.get("stderr", "unknown error"))
    return f"Skill '{skill}' failed: {error_text[:200]}"


def build_skill_run_history_messages(
    command: str,
    *,
    skill: str,
    result: dict[str, Any],
) -> list[dict[str, str]]:
    return [
        {
            "role": "user",
            "content": f"[Ran skill] {command}",
        },
        {
            "role": "assistant",
            "content": build_skill_run_result_text(skill, result),
        },
    ]
