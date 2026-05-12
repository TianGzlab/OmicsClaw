import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from omicsclaw.core.registry import registry


def test_registry_import_does_not_require_package_file():
    """App-server startup must not crash if omicsclaw is a namespace package."""
    code = """
import importlib
import omicsclaw

omicsclaw.__file__ = None
registry = importlib.import_module("omicsclaw.core.registry")
assert registry.OMICSCLAW_DIR.name == "OmicsClaw"
assert registry.SKILLS_DIR.name == "skills"
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr

def test_registry_loaded():
    registry.load_all()
    assert "spatial-preprocessing" in registry.skills
    assert "spatial-preprocess" in registry.skills
    assert registry.skills["spatial-preprocessing"]["alias"] == "spatial-preprocess"
    assert "spatial-orchestrator" not in registry.skills
    assert "orchestrator" in registry.skills
    assert registry.skills["orchestrator"]["domain"] == "orchestrator"
    assert Path(registry.skills["orchestrator"]["script"]).name == "omics_orchestrator.py"
    assert "sc-qc" in registry.skills  # verify singlecell subdomain nesting
    assert "spatial-microenvironment-subset" in registry.skills
    assert "spatial-raw-processing" in registry.skills
    assert "st_pipeline" in [
        keyword.lower()
        for keyword in registry.skills["spatial-raw-processing"].get("trigger_keywords", [])
    ]
    assert "spatial" in registry.domains
    assert registry.domains["singlecell"]["skill_count"] == len(
        registry.iter_primary_skills(domain="singlecell")
    )
    for skill in [
        "sc-standardize-input",
        "sc-qc",
        "sc-preprocessing",
        "sc-filter",
        "sc-ambient-removal",
        "sc-doublet-detection",
        "sc-cell-annotation",
        "sc-pseudotime",
        "sc-velocity",
        "sc-batch-integration",
        "sc-de",
        "sc-markers",
        "sc-grn",
        "sc-cell-communication",
    ]:
        assert skill in registry.skills
    assert registry.domains["spatial"]["skill_count"] == len(
        registry.iter_primary_skills(domain="spatial")
    )
    assert len(registry.skills) > 0
    assert len(registry.domains) > 0


def test_registry_loads_top_level_literature_skill():
    registry.load_all()

    assert "literature" in registry.skills
    assert "omics-skill-builder" in registry.skills
    assert registry.skills["literature"]["alias"] == "literature"
    assert registry.skills["literature"]["domain"] == "literature"
    assert Path(registry.skills["literature"]["script"]).name == "literature_parse.py"
    assert ("literature", registry.skills["literature"]) in registry.iter_primary_skills()
    assert registry.domains["literature"]["skill_count"] == 1
    assert len(registry.iter_primary_skills()) == 89


def test_skill_runner_sees_registry_invalidate_after_load():
    """``registry.invalidate()`` must affect subsequent reads by the runner.

    Pre-fix ``omicsclaw.core.skill_runner`` cached ``SKILLS = registry.skills``
    at module-import time, so calls to ``registry.invalidate()`` /
    ``registry.reload()`` left the runner pointing at a stale dict and
    operators saw "skill not found" errors that did not match the live
    filesystem.
    """
    from omicsclaw.core import skill_runner

    registry.load_all()
    assert "spatial-preprocess" in registry.skills, "preconditions failed"

    try:
        registry.invalidate()
        # After invalidate the live dict is empty and the runner must see it.
        from omicsclaw.core.registry import ensure_registry_loaded as _ensure

        # Re-bind the live view the runner reads from; the runner accesses
        # ``ensure_registry_loaded().skills`` per call, not a frozen snapshot.
        assert _ensure is not None
        assert len(registry.skills) == 0
        # ``resolve_skill_alias`` reads ``registry.skills`` lazily and will
        # repopulate via ``ensure_registry_loaded`` — i.e. it must NOT raise
        # KeyError because of a stale module-level snapshot.
        resolved = skill_runner.resolve_skill_alias("spatial-preprocess")
        assert resolved == "spatial-preprocess"
        assert "spatial-preprocess" in registry.skills, (
            "ensure_registry_loaded() should have repopulated the live registry"
        )
    finally:
        registry.load_all()


def test_registry_reload_clears_stale_entries_for_runner():
    """``registry.reload()`` must let the runner pick up filesystem changes
    rather than continuing to return entries from a stale dict snapshot.
    """
    from omicsclaw.core import skill_runner
    from omicsclaw.core.registry import ensure_registry_loaded

    registry.load_all()
    assert "spatial-preprocess" in registry.skills

    # Simulate the SKILL.md / parameters.yaml edit lifecycle: inject a fake
    # entry, then call reload() and verify that both the registry AND the
    # runner observe the rebuilt dict (i.e. the fake entry is gone).
    registry.skills["__stale_only__"] = {
        "alias": "__stale_only__",
        "domain": "demo",
        "script": Path("/does/not/exist"),
        "demo_args": [],
        "description": "synthetic stale entry",
        "trigger_keywords": [],
        "allowed_extra_flags": set(),
        "legacy_aliases": [],
        "saves_h5ad": False,
        "requires_preprocessed": False,
        "param_hints": {},
    }
    try:
        # Before reload, the entry is observable.
        assert "__stale_only__" in registry.skills

        registry.reload()

        # After reload, both the registry and the runner's live read must
        # show the rebuilt state, NOT the stale snapshot.
        assert "__stale_only__" not in registry.skills
        assert "__stale_only__" not in ensure_registry_loaded().skills
        # And the runner's resolver does not fall through to the stale dict.
        assert skill_runner.resolve_skill_alias("__stale_only__") == "__stale_only__"
        assert "spatial-preprocess" in registry.skills, "real skills came back"
    finally:
        registry.skills.pop("__stale_only__", None)
        registry.load_all()
