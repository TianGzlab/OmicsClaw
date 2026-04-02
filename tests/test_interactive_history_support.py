from omicsclaw.interactive._history_support import (
    build_skill_run_history_messages,
    build_skill_run_result_text,
)


def test_build_skill_run_result_text_success_includes_output_dir():
    text = build_skill_run_result_text(
        "spatial-preprocessing",
        {
            "success": True,
            "output_dir": "/tmp/run-output",
        },
    )

    assert text == (
        "Skill 'spatial-preprocessing' completed successfully. "
        "Output: /tmp/run-output"
    )


def test_build_skill_run_result_text_failure_truncates_stderr():
    stderr = "x" * 250

    text = build_skill_run_result_text(
        "spatial-preprocessing",
        {
            "success": False,
            "stderr": stderr,
        },
    )

    assert text == f"Skill 'spatial-preprocessing' failed: {'x' * 200}"


def test_build_skill_run_history_messages_builds_user_and_assistant_entries():
    messages = build_skill_run_history_messages(
        "spatial-preprocessing --demo",
        skill="spatial-preprocessing",
        result={
            "success": True,
            "output_dir": "/tmp/run-output",
        },
    )

    assert messages == [
        {
            "role": "user",
            "content": "[Ran skill] spatial-preprocessing --demo",
        },
        {
            "role": "assistant",
            "content": (
                "Skill 'spatial-preprocessing' completed successfully. "
                "Output: /tmp/run-output"
            ),
        },
    ]
