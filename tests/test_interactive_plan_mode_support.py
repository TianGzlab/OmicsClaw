from omicsclaw.agents.plan_state import (
    PLAN_STATUS_APPROVED,
    PLAN_STATUS_PENDING_APPROVAL,
)
from omicsclaw.runtime.events import (
    EVENT_PLAN_APPROVED,
    EVENT_PLAN_CREATED,
    EVENT_TASK_STARTED,
)
from omicsclaw.runtime.hooks import LifecycleHookRuntime, LifecycleHookSpec
from omicsclaw.interactive._plan_mode_support import (
    PLAN_KIND_GENERIC_ANALYSIS,
    PLAN_KIND_SKILL_CREATION,
    build_approve_plan_command_view,
    build_do_current_task_command_view,
    build_interactive_plan_context_from_metadata,
    build_plan_command_view,
    build_resume_task_command_view,
    load_interactive_plan_from_metadata,
    maybe_seed_interactive_plan,
    should_auto_enter_plan_mode,
)


def test_build_plan_command_view_infers_latest_user_request_and_persists_plan():
    view = build_plan_command_view(
        "",
        session_metadata={},
        messages=[
            {"role": "assistant", "content": "How can I help?"},
            {"role": "user", "content": "Analyze sample.h5ad and choose the right workflow."},
        ],
        workspace_dir="/tmp/workspace",
    )

    assert view.success is True
    assert view.persist_session is True
    assert view.replace_session_metadata is True
    snapshot = load_interactive_plan_from_metadata(view.session_metadata)
    assert snapshot is not None
    assert snapshot.request == "Analyze sample.h5ad and choose the right workflow."
    assert snapshot.plan_kind == PLAN_KIND_GENERIC_ANALYSIS
    assert snapshot.status == PLAN_STATUS_PENDING_APPROVAL
    assert snapshot.active_task_id == "define-objective"
    assert "Interactive plan created for this session." in view.output_text


def test_build_approve_and_resume_task_views_advance_generic_plan_state():
    create_view = build_plan_command_view(
        "Create a new skill for metabolomics QC",
        session_metadata={},
        messages=[],
        workspace_dir="/tmp/workspace",
    )
    created = load_interactive_plan_from_metadata(create_view.session_metadata)
    assert created is not None
    assert created.plan_kind == PLAN_KIND_SKILL_CREATION

    approve_view = build_approve_plan_command_view(
        '--notes "ship it" --by reviewer',
        session_metadata=create_view.session_metadata,
    )
    approved = load_interactive_plan_from_metadata(approve_view.session_metadata)
    assert approved is not None
    assert approved.status == PLAN_STATUS_APPROVED
    assert approved.approved_by == "reviewer"
    assert approved.approval_notes == "ship it"
    assert approved.active_task_id == "scope-skill-contract"
    assert approved.task_store.require("scope-skill-contract").status == "in_progress"

    resume_view = build_resume_task_command_view(
        "3",
        session_metadata=approve_view.session_metadata,
    )
    resumed = load_interactive_plan_from_metadata(resume_view.session_metadata)
    assert resumed is not None
    assert resumed.active_task_id == "scaffold-implementation"
    assert resumed.task_store.require("scaffold-implementation").status == "in_progress"
    assert resumed.task_store.require("scope-skill-contract").status == "pending"
    assert "Interactive task resumed: scaffold-implementation" in resume_view.output_text
    assert "Suggested next prompt:" in resume_view.output_text
    assert "Start immediately: /do-current-task" in resume_view.output_text
    assert "Continue with the approved plan and work on task 'scaffold-implementation'" in resume_view.suggested_prompt


def test_resume_late_task_warns_about_unfinished_dependencies_and_do_current_task_builds_execution_prompt():
    create_view = build_plan_command_view(
        "Analyze sample.h5ad step by step",
        session_metadata={},
        messages=[],
        workspace_dir="/tmp/workspace",
    )
    approve_view = build_approve_plan_command_view(
        "",
        session_metadata=create_view.session_metadata,
    )

    resume_view = build_resume_task_command_view(
        "validate-outputs",
        session_metadata=approve_view.session_metadata,
    )

    assert "Dependency warning:" in resume_view.output_text
    assert "execute-analysis (pending)" in resume_view.output_text
    assert "Start immediately: /do-current-task" in resume_view.output_text

    execute_view = build_do_current_task_command_view(
        "",
        session_metadata=resume_view.session_metadata,
    )

    assert execute_view.success is True
    assert execute_view.persist_session is True
    assert execute_view.output_text.startswith("Executing interactive task: validate-outputs")
    assert "Dependency warning:" in execute_view.output_text
    assert "Selected task: validate-outputs — Validate outputs" in execute_view.execution_prompt
    assert "Unfinished dependencies: execute-analysis (pending)" in execute_view.execution_prompt
    assert "Continue with the approved plan and work on task 'validate-outputs'" in execute_view.suggested_prompt


def test_build_interactive_plan_context_from_metadata_carries_execution_gate():
    view = build_plan_command_view(
        "Analyze a custom dataset and validate the output",
        session_metadata={},
        messages=[],
        workspace_dir="/tmp/workspace",
    )

    context = build_interactive_plan_context_from_metadata(view.session_metadata)

    assert "## Active Plan Mode" in context
    assert "Status: pending_approval" in context
    assert "Execution gate:" in context
    assert "define-objective" in context


def test_should_auto_enter_plan_mode_is_conservative_but_catches_multi_step_requests():
    assert should_auto_enter_plan_mode("介绍你自己") is False
    assert should_auto_enter_plan_mode("Create a new skill and validate it step by step") is True
    assert should_auto_enter_plan_mode("请一步步完成这个多步骤分析并最终总结结果") is True


def test_maybe_seed_interactive_plan_creates_pending_plan_for_complex_request():
    seed = maybe_seed_interactive_plan(
        "Please create a new skill, validate tests, and finalize installation step by step.",
        session_metadata={},
        workspace_dir="/tmp/workspace",
    )

    assert seed.created is True
    assert "Entered structured plan mode" in seed.notice_text
    snapshot = load_interactive_plan_from_metadata(seed.session_metadata)
    assert snapshot is not None
    assert snapshot.status == PLAN_STATUS_PENDING_APPROVAL
    assert snapshot.plan_kind == PLAN_KIND_SKILL_CREATION


def test_plan_mode_views_surface_hook_notices():
    hook_runtime = LifecycleHookRuntime(
        [
            LifecycleHookSpec(
                name="plan-created",
                event=EVENT_PLAN_CREATED,
                message="Plan created for {plan_kind}.",
            ),
            LifecycleHookSpec(
                name="plan-approved",
                event=EVENT_PLAN_APPROVED,
                message="Plan approved for {plan_kind}.",
            ),
            LifecycleHookSpec(
                name="task-started",
                event=EVENT_TASK_STARTED,
                message="Active task is now {task_id}.",
            ),
        ]
    )

    create_view = build_plan_command_view(
        "Analyze sample.h5ad step by step",
        session_metadata={},
        messages=[],
        workspace_dir="/tmp/workspace",
        hook_runtime=hook_runtime,
    )
    approve_view = build_approve_plan_command_view(
        "",
        session_metadata=create_view.session_metadata,
        hook_runtime=hook_runtime,
    )

    assert "Hook notice: Plan created for generic_analysis." in create_view.output_text
    assert "Hook notice: Plan approved for generic_analysis." in approve_view.output_text
    assert "Hook notice: Active task is now define-objective." in approve_view.output_text
