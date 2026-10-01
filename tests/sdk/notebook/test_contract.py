"""Contracts the step runner shares with the framework and the skill loader."""

from __future__ import annotations

import ast
from pathlib import Path

from omicsclaw.skills import load_skills
from skills._sdk.notebook import _skills, contract

REPO = Path(__file__).resolve().parents[3]
CONTRACT = REPO / "skills" / "_sdk" / "notebook" / "contract.py"


def literals(path: Path) -> dict:
    """Every top-level literal assignment in *path*, read with ``ast.literal_eval``."""
    values = {}
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name.isupper():
                values[name] = ast.literal_eval(node.value)
    return values


def test_the_contract_is_readable_without_importing_it():
    values = literals(CONTRACT)
    assert set(values) == set(contract.__all__)
    for name in contract.__all__:
        assert values[name] == getattr(contract, name)


def test_every_indexed_skill_directory_is_named_after_the_skill():
    """``load_skill`` finds skills by directory name; the loader indexes them by frontmatter name."""
    index = load_skills(REPO / "skills")
    mismatched = sorted(f"{s.directory.name} != {s.name}" for s in index.skills if s.directory.name != s.name)
    assert mismatched == []
    for skill in index.skills:
        assert _skills.skill_dir(skill.name, REPO / "skills") == skill.directory.resolve()


def test_every_event_carries_the_common_fields_and_its_own():
    from skills._sdk.notebook import _ledger

    for event, fields in contract.LEDGER_EVENTS.items():
        assert len(fields) == len(set(fields)), event
        assert not {"v", "event", "at"} & set(fields), event
    assert _ledger.VERSION == 1


def test_the_framework_reads_the_layout_the_runner_writes():
    """``omicsclaw/entry/project.py`` spells the layout as literals; they must equal the runner's."""
    from omicsclaw.entry import project

    assert project.MODULE_DIR_PATTERN == contract.LAYOUT["module_dir"]
    assert project.MANIFEST_FILE == contract.LAYOUT["manifest"]
    assert project.REPORT_FILE == contract.LAYOUT["report"]
    assert project.RESULTS_DIR + "/" == contract.LAYOUT["archive_dir"].split("_archive")[0]
    assert project.MANIFEST_STATUS_KEY in contract.MANIFEST_SCHEMA["required"]
    assert set(contract.MANIFEST_SCHEMA["status_values"]) == {"draft", "replayed", "reviewed", "accepted"}
    assert REPO.joinpath("skills", *project.STEP_RUNNER).is_file()


def _runner_commands_and_flags() -> tuple[set[str], set[str]]:
    import argparse

    from skills._sdk.notebook import run

    parser = run.build_parser()
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    flags = {
        option
        for subparser in sub.choices.values()
        for action in subparser._actions
        for option in action.option_strings
    }
    return set(sub.choices), flags


def test_every_runner_command_the_contract_names_exists():
    import re

    text = (REPO / "OMICSCLAW.md").read_text(encoding="utf-8")
    section = text[text.index("## Projects, modules and steps"):text.index("## Skills")]
    table = section[section.index("### Running steps"):section.index("### Finishing a module")]
    named = {re.match(r"\| `(\w+)", line).group(1) for line in table.splitlines() if line.startswith("| `")}
    runner_text = section[section.index("### Running steps"):]
    flags = set(re.findall(r"(--[a-z][a-z-]*)", runner_text))
    commands, known_flags = _runner_commands_and_flags()
    assert named, "the contract's command table is empty"
    assert named <= commands, named - commands
    assert flags <= known_flags, flags - known_flags
