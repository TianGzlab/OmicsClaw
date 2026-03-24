"""Quick validation of Phase 2 pipeline changes."""
import sys
sys.path.insert(0, "/home/zhouwg/data1/project/OmicsClaw")

from omicsclaw.agents.pipeline import PipelineState, _generate_todos
from omicsclaw.agents.intake import IntakeResult
from pathlib import Path
import tempfile
import json

# Test 1: PipelineState basic operations
print("Test 1: PipelineState operations...")
state = PipelineState()
state.record_stage("intake", "test")
assert state.is_stage_done("intake")
assert not state.is_stage_done("plan")
assert not state.should_stop_review()
state.review_iterations = 3
assert state.should_stop_review()
print("  PASS")

# Test 2: checkpoint + load_checkpoint
print("Test 2: Checkpoint save/load...")
with tempfile.TemporaryDirectory() as td:
    ws = Path(td)
    state2 = PipelineState()
    state2.record_stage("intake", "paper.md")
    state2.record_stage("plan", "plan created")
    state2.review_iterations = 1
    state2.checkpoint(ws)

    loaded = PipelineState.load_checkpoint(ws)
    assert loaded is not None
    assert loaded.completed_stages == ["intake", "plan"]
    assert loaded.review_iterations == 1
    assert loaded.is_stage_done("intake")
    assert loaded.is_stage_done("plan")
    assert not loaded.is_stage_done("execute")
print("  PASS")

# Test 3: _generate_todos
print("Test 3: Auto-generated todos.md...")
with tempfile.TemporaryDirectory() as td:
    ws = Path(td)
    _generate_todos(ws, "A", True)
    todos = ws / "todos.md"
    assert todos.exists()
    content = todos.read_text()
    assert "Plan" in content
    assert "Review" in content
print("  PASS")

# Test 4: IntakeResult.from_workspace (Mode A)
print("Test 4: IntakeResult.from_workspace Mode A...")
with tempfile.TemporaryDirectory() as td:
    ws = Path(td)
    paper_dir = ws / "paper"
    paper_dir.mkdir()
    (paper_dir / "01_abstract_conclusion.md").write_text(
        "# My Paper Title\nAbstract content..."
    )
    (paper_dir / "02_methodology.md").write_text("Methods section...")
    result = IntakeResult.from_workspace(str(ws), idea="test idea")
    assert result.input_mode == "A", f"Expected A, got {result.input_mode}"
    assert result.paper_title == "My Paper Title", f"Got title: {result.paper_title}"
    assert "methodology" in result.paper_md_path.lower()
print("  PASS")

# Test 5: IntakeResult.from_workspace (Mode C)
print("Test 5: IntakeResult.from_workspace Mode C...")
with tempfile.TemporaryDirectory() as td:
    result2 = IntakeResult.from_workspace(str(td), idea="pure idea")
    assert result2.input_mode == "C"
    assert result2.paper_title == ""
print("  PASS")

# Test 6: load_checkpoint with corrupted file
print("Test 6: Corrupted checkpoint handling...")
with tempfile.TemporaryDirectory() as td:
    ws = Path(td)
    (ws / ".pipeline_checkpoint.json").write_text("not valid json!")
    loaded = PipelineState.load_checkpoint(ws)
    assert loaded is None
print("  PASS")

# Test 7: load_checkpoint with no file  
print("Test 7: Missing checkpoint handling...")
with tempfile.TemporaryDirectory() as td:
    loaded = PipelineState.load_checkpoint(Path(td))
    assert loaded is None
print("  PASS")

print("\nAll Phase 2 tests passed!")
