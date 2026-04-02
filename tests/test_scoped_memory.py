from datetime import datetime, timedelta, timezone

from omicsclaw.memory.scoped_memory import (
    prune_scoped_memories,
    resolve_scoped_memory_root,
    write_scoped_memory,
)
from omicsclaw.memory.scoped_memory_index import (
    load_scoped_memory_record,
    scan_scoped_memory_headers,
)
from omicsclaw.memory.scoped_memory_select import load_scoped_memory_context


def test_scoped_memory_write_and_index_roundtrip(tmp_path):
    record = write_scoped_memory(
        body="Prefer mitochondrial cutoff 20% for PBMC QC before trying Harmony.",
        scope="project",
        title="PBMC QC defaults",
        owner="tester",
        domain="singlecell",
        keywords=("pbmc", "qc"),
        dataset_refs=("data/pbmc.h5ad",),
        workspace_dir=str(tmp_path),
    )

    assert record.path.exists()

    root = resolve_scoped_memory_root(workspace_dir=str(tmp_path))
    loaded = load_scoped_memory_record(record.path, root=root)
    headers = scan_scoped_memory_headers(root)

    assert loaded is not None
    assert loaded.title == "PBMC QC defaults"
    assert loaded.freshness == "evolving"
    assert loaded.domain == "singlecell"
    assert loaded.dataset_refs == ("data/pbmc.h5ad",)
    assert [header.title for header in headers] == ["PBMC QC defaults"]


def test_scoped_memory_context_selects_relevant_entries(tmp_path):
    write_scoped_memory(
        body="For PBMC single-cell QC, start with mito cutoff 20% and avoid Harmony before BBKNN.",
        scope="project",
        title="PBMC QC defaults",
        owner="tester",
        domain="singlecell",
        keywords=("pbmc", "qc", "bbknn"),
        workspace_dir=str(tmp_path),
    )
    write_scoped_memory(
        body="For this Visium dataset, trust tissue_positions_list.csv over inferred spot coordinates.",
        scope="dataset",
        title="Visium coordinate note",
        owner="tester",
        domain="spatial",
        keywords=("visium", "coordinate"),
        workspace_dir=str(tmp_path),
    )

    recall = load_scoped_memory_context(
        query="Need PBMC QC defaults before running BBKNN",
        domain="singlecell",
        workspace=str(tmp_path),
        preferred_scope="project",
    )

    assert recall.selected
    assert recall.selected[0].title == "PBMC QC defaults"
    assert "scope=project" in recall.to_context_text()
    assert "freshness=evolving" in recall.to_context_text()


def test_scoped_memory_prune_detects_duplicates_and_stale_records(tmp_path):
    now = datetime(2026, 4, 2, tzinfo=timezone.utc)
    latest = write_scoped_memory(
        body="Use BBKNN before Harmony for this project.",
        scope="workflow_hint",
        title="Integration order",
        owner="tester",
        freshness="volatile",
        workspace_dir=str(tmp_path),
        now=now,
    )
    duplicate_older = write_scoped_memory(
        body="Use BBKNN before Harmony for this project.",
        scope="workflow_hint",
        title="Integration order",
        owner="tester",
        freshness="volatile",
        workspace_dir=str(tmp_path),
        now=now - timedelta(days=10),
    )
    stale_unique = write_scoped_memory(
        body="Temporary troubleshooting note for an old dataset.",
        scope="dataset",
        title="Old troubleshooting note",
        owner="tester",
        freshness="volatile",
        workspace_dir=str(tmp_path),
        now=now - timedelta(days=60),
    )

    preview = prune_scoped_memories(
        workspace_dir=str(tmp_path),
        apply_changes=False,
        now=now,
    )

    assert len(preview.candidates) == 2
    assert {candidate.record.memory_id for candidate in preview.candidates} == {
        duplicate_older.memory_id,
        stale_unique.memory_id,
    }
    assert latest.path.exists()
    assert duplicate_older.path.exists()
    assert stale_unique.path.exists()

    applied = prune_scoped_memories(
        workspace_dir=str(tmp_path),
        apply_changes=True,
        now=now,
    )

    assert applied.deleted_count == 2
    assert latest.path.exists()
    assert not duplicate_older.path.exists()
    assert not stale_unique.path.exists()
