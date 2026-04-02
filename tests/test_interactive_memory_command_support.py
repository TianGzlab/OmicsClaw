from omicsclaw.interactive._memory_command_support import (
    build_memory_command_view,
    resolve_active_scoped_memory_scope,
)
from omicsclaw.memory.scoped_memory import write_scoped_memory


def test_build_memory_command_view_sets_active_scope_in_session_metadata():
    view = build_memory_command_view(
        "scope project",
        session_metadata={"title": "Demo"},
        workspace_dir="/tmp/workspace",
    )

    assert view.success is True
    assert view.replace_session_metadata is True
    assert view.session_metadata["title"] == "Demo"
    assert resolve_active_scoped_memory_scope(view.session_metadata) == "project"


def test_build_memory_command_view_adds_and_lists_memories(tmp_path):
    scope_view = build_memory_command_view(
        "scope dataset",
        session_metadata={},
        workspace_dir=str(tmp_path),
    )
    add_view = build_memory_command_view(
        'add "Visium coordinate note :: Prefer tissue_positions_list.csv for spot coordinates."',
        session_metadata=scope_view.session_metadata,
        workspace_dir=str(tmp_path),
    )
    list_view = build_memory_command_view(
        "list",
        session_metadata=scope_view.session_metadata,
        workspace_dir=str(tmp_path),
    )

    assert add_view.success is True
    assert "Scoped memory saved: Visium coordinate note" in add_view.output_text
    assert "Active scope: dataset" in list_view.output_text
    assert "[dataset] Visium coordinate note" in list_view.output_text


def test_build_memory_command_view_previews_and_applies_prune(tmp_path):
    write_scoped_memory(
        body="Use BBKNN before Harmony for this project.",
        scope="workflow_hint",
        title="Integration order",
        workspace_dir=str(tmp_path),
    )
    write_scoped_memory(
        body="Use BBKNN before Harmony for this project.",
        scope="workflow_hint",
        title="Integration order",
        workspace_dir=str(tmp_path),
    )

    preview = build_memory_command_view(
        "prune workflow_hint",
        session_metadata={},
        workspace_dir=str(tmp_path),
    )
    applied = build_memory_command_view(
        "prune workflow_hint --apply",
        session_metadata={},
        workspace_dir=str(tmp_path),
    )

    assert "Scoped memory prune preview" in preview.output_text
    assert "duplicate of" in preview.output_text
    assert "Pruned 1 scoped memories." in applied.output_text
