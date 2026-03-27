"""Tests that all skill scripts conform to the SkillProtocol conventions.

Uses AST-based validation (no heavy imports needed) to check that
every skill defines SKILL_NAME, SKILL_VERSION, and main().
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from omicsclaw.core.registry import OmicsRegistry, SKILLS_DIR
from omicsclaw.core.skill_protocol import validate_skill_module, ValidationResult


def _find_all_skill_scripts() -> list[Path]:
    """Discover all skill scripts via registry directory scanning."""
    reg = OmicsRegistry()
    scripts: list[Path] = []
    for domain_path in SKILLS_DIR.iterdir():
        if not domain_path.is_dir() or domain_path.name.startswith((".", "__")):
            continue
        for skill_path in reg._iter_skill_dirs(domain_path):
            script_name = f"{skill_path.name.replace('-', '_')}.py"
            script = skill_path / script_name
            if script.exists():
                scripts.append(script)
    return sorted(scripts)


_SKILL_SCRIPTS = _find_all_skill_scripts()


def test_skill_scripts_found():
    """Sanity check: we should find a reasonable number of skill scripts."""
    assert len(_SKILL_SCRIPTS) >= 20, f"Only found {len(_SKILL_SCRIPTS)} scripts"


def test_all_skills_have_skill_name():
    """Every skill script must define SKILL_NAME."""
    missing = []
    for script in _SKILL_SCRIPTS:
        result = validate_skill_module(script)
        if any("Missing SKILL_NAME" in e for e in result.errors):
            missing.append(script.stem)
    assert missing == [], f"Skills missing SKILL_NAME: {missing}"


def test_all_skills_have_skill_version():
    """Every skill script must define SKILL_VERSION."""
    missing = []
    for script in _SKILL_SCRIPTS:
        result = validate_skill_module(script)
        if any("Missing SKILL_VERSION" in e for e in result.errors):
            missing.append(script.stem)
    assert missing == [], f"Skills missing SKILL_VERSION: {missing}"


def test_all_skills_have_main():
    """Every skill script must define main()."""
    missing = []
    for script in _SKILL_SCRIPTS:
        result = validate_skill_module(script)
        if any("Missing main()" in e for e in result.errors):
            missing.append(script.stem)
    assert missing == [], f"Skills missing main(): {missing}"


def test_all_skills_pass_validation():
    """Every skill script must pass all required checks (no errors)."""
    failures = []
    for script in _SKILL_SCRIPTS:
        result = validate_skill_module(script)
        if not result.passed:
            failures.append(f"{script.stem}: {result.errors}")
    assert failures == [], f"Skills failing validation:\n" + "\n".join(str(f) for f in failures)
