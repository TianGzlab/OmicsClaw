from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from bot.core import (
    _build_bot_query_engine_callbacks,
    execute_create_omics_skill,
    execute_custom_analysis_execute,
)
from omicsclaw.core.skill_scaffolder import SkillScaffoldResult
from omicsclaw.knowledge.retriever import _push_runtime_notice, clear_runtime_notices
from omicsclaw.runtime.policy import TOOL_POLICY_REQUIRE_APPROVAL, ToolPolicyDecision
from omicsclaw.runtime.tool_orchestration import (
    EXECUTION_STATUS_POLICY_BLOCKED,
    ToolExecutionRequest,
    ToolExecutionResult,
)
from omicsclaw.runtime.tool_spec import APPROVAL_MODE_ASK, ToolSpec


@pytest.mark.asyncio
async def test_execute_create_omics_skill_includes_gate_summary(monkeypatch):
    monkeypatch.setattr(
        "omicsclaw.core.skill_scaffolder.create_skill_scaffold",
        lambda **_kwargs: SkillScaffoldResult(
            skill_name="demo-skill",
            domain="spatial",
            skill_dir="/tmp/demo-skill",
            script_path="/tmp/demo-skill/demo_skill.py",
            skill_md_path="/tmp/demo-skill/SKILL.md",
            spec_path="/tmp/demo-skill/scaffold_spec.json",
            manifest_path="/tmp/demo-skill/manifest.json",
            completion_report_path="/tmp/demo-skill/completion_report.json",
            completion={
                "status": "complete",
                "completed": True,
                "missing_required_artifacts": [],
                "warnings": [],
                "errors": [],
            },
            created_files=["/tmp/demo-skill/SKILL.md"],
            registry_refreshed=True,
        ),
    )

    message = await execute_create_omics_skill(
        {"request": "Create a demo skill.", "domain": "spatial"}
    )

    assert "Created OmicsClaw skill scaffold." in message
    assert "Gate:" in message
    assert "Status: complete" in message
    assert "Completed: True" in message


class _FakeCapabilityDecision:
    def to_dict(self) -> dict[str, object]:
        return {"chosen_skill": "", "coverage": "no_skill"}


@pytest.mark.asyncio
async def test_execute_custom_analysis_execute_includes_gate_summary(monkeypatch):
    monkeypatch.setattr(
        "omicsclaw.core.capability_resolver.resolve_capability",
        lambda *_args, **_kwargs: _FakeCapabilityDecision(),
    )
    monkeypatch.setattr(
        "omicsclaw.execution.run_autonomous_analysis",
        lambda **_kwargs: {
            "ok": True,
            "output_dir": "/tmp/analysis",
            "notebook_path": "/tmp/analysis/reproducibility/analysis_notebook.ipynb",
            "summary_path": "/tmp/analysis/result_summary.md",
            "manifest_path": "/tmp/analysis/manifest.json",
            "completion_report_path": "/tmp/analysis/completion_report.json",
            "output_preview": "preview",
            "completion": {
                "status": "complete",
                "completed": True,
                "missing_required_artifacts": [],
                "warnings": ["review notebook before promotion"],
                "errors": [],
            },
        },
    )

    message = await execute_custom_analysis_execute(
        {
            "goal": "Run a one-off analysis.",
            "analysis_plan": "1. Load data\n2. Summarize results",
            "python_code": "print('ok')",
        }
    )

    assert "Custom analysis completed." in message
    assert "Gate:" in message
    assert "Status: complete" in message
    assert "Completed: True" in message
    assert "Warnings:" in message
    assert "- review notebook before promotion" in message


@pytest.mark.asyncio
async def test_consult_knowledge_ui_callback_receives_refresh_notice():
    clear_runtime_notices()
    _push_runtime_notice("Knowledge base updated; index refreshed automatically (12 file(s)).")

    observed: list[tuple[str, str]] = []
    callbacks = _build_bot_query_engine_callbacks(
        chat_id="chat-1",
        progress_fn=None,
        progress_update_fn=None,
        on_tool_call=None,
        on_tool_result=lambda tool_name, result: observed.append((tool_name, result)),
        on_stream_content=None,
        on_stream_reasoning=None,
        request_tool_approval=None,
        logger_obj=logging.getLogger("test.bot.callbacks"),
        audit_fn=lambda *_args, **_kwargs: None,
        deep_learning_methods=set(),
        usage_accumulator=None,
    )

    request = ToolExecutionRequest(
        call_id="call-knowledge",
        name="consult_knowledge",
        arguments={"query": "marker genes"},
        spec=ToolSpec(
            name="consult_knowledge",
            description="knowledge lookup",
            parameters={"type": "object", "properties": {}},
            read_only=True,
            concurrency_safe=True,
        ),
        executor=lambda _args: "ignored",
    )
    result = ToolExecutionResult(
        request=request,
        output='Knowledge base results for: "marker genes"\n',
        success=True,
    )

    await callbacks.after_tool(
        result,
        SimpleNamespace(content='Knowledge base results for: "marker genes"\n'),
        {},
    )

    assert observed == [
        (
            "consult_knowledge",
            'Knowledge base updated; index refreshed automatically (12 file(s)).\n'
            'Knowledge base results for: "marker genes"\n',
        )
    ]


@pytest.mark.asyncio
async def test_policy_blocked_tool_audits_and_emits_result():
    observed_results: list[tuple[str, str]] = []
    audit_events: list[tuple[str, dict[str, object]]] = []

    def audit_fn(event_name, **payload):
        audit_events.append((event_name, payload))

    callbacks = _build_bot_query_engine_callbacks(
        chat_id="chat-2",
        progress_fn=None,
        progress_update_fn=None,
        on_tool_call=None,
        on_tool_result=lambda tool_name, result: observed_results.append((tool_name, result)),
        on_stream_content=None,
        on_stream_reasoning=None,
        request_tool_approval=None,
        logger_obj=logging.getLogger("test.bot.policy"),
        audit_fn=audit_fn,
        deep_learning_methods=set(),
        usage_accumulator=None,
    )

    request = ToolExecutionRequest(
        call_id="call-writer",
        name="write_file",
        arguments={"filename": "demo.txt"},
        spec=ToolSpec(
            name="write_file",
            description="write file",
            parameters={"type": "object", "properties": {}},
            approval_mode=APPROVAL_MODE_ASK,
            writes_workspace=True,
        ),
        executor=lambda _args: "ignored",
        policy_decision=ToolPolicyDecision(
            action=TOOL_POLICY_REQUIRE_APPROVAL,
            reason="`write_file` requires explicit approval because it writes workspace files.",
            risk_level="high",
            approval_mode=APPROVAL_MODE_ASK,
            writes_workspace=True,
            writes_config=False,
            touches_network=False,
            allowed_in_background=True,
            policy_tags=("workspace",),
            surface="cli",
            trusted=False,
            hint="Ask the user to confirm this action, then retry the request.",
        ),
    )
    result = ToolExecutionResult(
        request=request,
        output="[tool policy blocked]\nreason: approval required",
        success=False,
        status=EXECUTION_STATUS_POLICY_BLOCKED,
        policy_decision=request.policy_decision,
    )

    await callbacks.after_tool(
        result,
        SimpleNamespace(content="[tool policy blocked]\nreason: approval required"),
        {},
    )

    assert observed_results == [
        ("write_file", "[tool policy blocked]\nreason: approval required")
    ]
    assert any(event == "tool_policy_blocked" for event, _payload in audit_events)


@pytest.mark.asyncio
async def test_after_tool_emits_timeout_metadata_when_callback_accepts_it():
    observed_results: list[tuple[str, str, dict[str, object]]] = []

    callbacks = _build_bot_query_engine_callbacks(
        chat_id="chat-3",
        progress_fn=None,
        progress_update_fn=None,
        on_tool_call=None,
        on_tool_result=(
            lambda tool_name, result, metadata: observed_results.append(
                (tool_name, result, metadata)
            )
        ),
        on_stream_content=None,
        on_stream_reasoning=None,
        request_tool_approval=None,
        logger_obj=logging.getLogger("test.bot.timeout"),
        audit_fn=lambda *_args, **_kwargs: None,
        deep_learning_methods=set(),
        usage_accumulator=None,
    )

    request = ToolExecutionRequest(
        call_id="call-timeout",
        name="notebook_add_execute",
        arguments={"source": "sleep(999)"},
        spec=ToolSpec(
            name="notebook_add_execute",
            description="execute notebook cell",
            parameters={"type": "object", "properties": {}},
            read_only=False,
        ),
        executor=lambda _args: "ignored",
    )

    class ToolTimeoutError(Exception):
        def __init__(self, timeout: int):
            super().__init__(f"Timed out after {timeout}s")
            self.timeout = timeout

    result = ToolExecutionResult(
        request=request,
        output="Cell execution timed out after 91s",
        success=False,
        error=ToolTimeoutError(91),
    )

    await callbacks.after_tool(
        result,
        SimpleNamespace(content="Cell execution timed out after 91s"),
        {},
    )

    assert observed_results == [
        (
            "notebook_add_execute",
            "Cell execution timed out after 91s",
            {
                "status": "completed",
                "success": False,
                "is_error": True,
                "error_type": "ToolTimeoutError",
                "timed_out": True,
                "elapsed_seconds": 91,
            },
        )
    ]
