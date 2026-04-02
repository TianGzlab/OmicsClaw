from omicsclaw.interactive._skill_run_support import (
    build_skill_run_exception_result,
    build_skill_run_execution_view,
    parse_skill_run_command,
)


def test_parse_skill_run_command_extracts_supported_flags():
    command = parse_skill_run_command(
        'spatial-preprocessing --demo --input data.h5ad --output ./workspace --method scanpy'
    )

    assert command is not None
    assert command.skill == "spatial-preprocessing"
    assert command.demo is True
    assert command.input_path == "data.h5ad"
    assert command.output_dir == "./workspace"
    assert command.method == "scanpy"
    assert command.extra_args == ["--method", "scanpy"]


def test_parse_skill_run_command_accepts_inline_equals_flags():
    command = parse_skill_run_command(
        "spatial-preprocessing --input=data.h5ad --output=./workspace --method=spagcn"
    )

    assert command is not None
    assert command.input_path == "data.h5ad"
    assert command.output_dir == "./workspace"
    assert command.method == "spagcn"


def test_parse_skill_run_command_rejects_missing_flag_value():
    assert parse_skill_run_command("spatial-preprocessing --method") is None


def test_build_skill_run_execution_view_success_builds_shared_summary_and_history():
    execution = build_skill_run_execution_view(
        "spatial-preprocessing --demo",
        skill="spatial-preprocessing",
        result={
            "success": True,
            "duration_seconds": 4.2,
            "output_dir": "/tmp/output",
            "method": "scanpy",
            "readme_path": "/tmp/output/README.md",
            "notebook_path": "/tmp/output/run.ipynb",
            "stdout": "analysis complete",
        },
    )

    assert execution.success is True
    assert execution.system_summary_lines == [
        "✓ Skill 'spatial-preprocessing' completed in 4.2s",
        "  Output: /tmp/output",
        "  Method: scanpy",
        "  Guide: /tmp/output/README.md",
        "  Notebook: /tmp/output/run.ipynb",
    ]
    assert execution.system_message == "\n".join(execution.system_summary_lines)
    assert execution.stdout == "analysis complete"
    assert execution.history_messages[0]["content"] == "[Ran skill] spatial-preprocessing --demo"
    assert execution.history_messages[1]["content"] == (
        "Skill 'spatial-preprocessing' completed successfully. Output: /tmp/output"
    )


def test_build_skill_run_execution_view_exception_uses_warning_summary():
    execution = build_skill_run_execution_view(
        "spatial-preprocessing --demo",
        skill="spatial-preprocessing",
        result=build_skill_run_exception_result(RuntimeError("tool bootstrap failed")),
    )

    assert execution.success is False
    assert execution.system_summary_lines == [
        "⚠ Error running skill 'spatial-preprocessing': tool bootstrap failed"
    ]
    assert execution.history_messages[1]["content"] == (
        "Skill 'spatial-preprocessing' failed: tool bootstrap failed"
    )
