"""Repository-wide pytest collection policy.

Skill demo tests launch scientific workflows and validate their native output
artifacts.  They are integration tests, even when an individual assertion is
small, so keep them out of the deterministic fast suite by assigning the
``demo`` marker during collection.
"""

from __future__ import annotations

from pathlib import Path

import pytest


_REPOSITORY_ROOT = Path(__file__).resolve().parent
_SKILLS_ROOT = _REPOSITORY_ROOT / "skills"


def _is_skill_demo_test(item: pytest.Item) -> bool:
    """Return whether *item* is a Skill-local demo integration test."""

    try:
        item_path = Path(str(item.path)).resolve()
        item_path.relative_to(_SKILLS_ROOT)
    except (AttributeError, ValueError):
        return False

    test_name = str(getattr(item, "originalname", None) or item.name).lower()
    fixture_names = {str(name).lower() for name in getattr(item, "fixturenames", ())}
    return "demo" in test_name or any(
        name == "demo_output" or name.endswith("_demo_output") for name in fixture_names
    )


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Classify Skill demo executions before pytest applies ``-m`` filters."""

    for item in items:
        if _is_skill_demo_test(item):
            item.add_marker(pytest.mark.demo)
