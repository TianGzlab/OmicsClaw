from omicsclaw.runtime.task_store import (
    TASK_STATUS_COMPLETED,
    TASK_STATUS_IN_PROGRESS,
    TaskRecord,
    TaskStore,
)


def test_task_store_roundtrip_and_markdown_projection(tmp_path):
    store = TaskStore(
        kind="research_pipeline",
        metadata={"mode": "A", "has_pdf": True},
    )
    store.add_task(
        TaskRecord(
            id="plan",
            title="Plan",
            description="Generate experiment plan",
        )
    )
    store.add_task(
        TaskRecord(
            id="write",
            title="Write",
            description="Draft final report",
        )
    )

    store.set_task_status(
        "plan",
        TASK_STATUS_IN_PROGRESS,
        summary="Drafting experimental plan",
        artifact_ref="plan.md",
    )
    store.set_task_status(
        "write",
        TASK_STATUS_COMPLETED,
        summary="Drafted report",
        artifact_ref="final_report.md",
    )

    path = tmp_path / "tasks.json"
    store.save(path)
    loaded = TaskStore.load(path)

    assert loaded is not None
    assert loaded.require("plan").status == TASK_STATUS_IN_PROGRESS
    assert loaded.require("write").status == TASK_STATUS_COMPLETED
    assert loaded.completed_task_ids() == ["write"]

    markdown = loaded.render_markdown(title="# Pipeline Tasks")
    assert "# Pipeline Tasks" in markdown
    assert "mode: A" in markdown
    assert "Drafting experimental plan" in markdown
    assert "final_report.md" in markdown
