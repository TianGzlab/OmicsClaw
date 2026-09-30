"""Scanning a directory of agent files.

Plan 0046 §10. Three properties, and all three are about a deployment
whose agents directory is imperfect: an absent directory is the ordinary
case and not an error, one unusable file costs only itself, and a file
overrides the built-in it shares a name with — which is the loader's
contract with :func:`~omicsclaw.entry.subagent.build_subagent_registry`,
where the built-ins are registered first.
"""

from __future__ import annotations

import pathlib

from omicsclaw.subagent import SubAgentDefinition, SubAgentRegistry, load_agents


def _write(directory: pathlib.Path, name: str, body: str) -> pathlib.Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(body, encoding="utf-8")
    return path


def _agent(name: str, description: str = "Does a thing") -> str:
    return f"---\nname: {name}\ndescription: {description}\n---\nDo the thing.\n"


def test_a_directory_that_does_not_exist_is_not_an_error(tmp_path):
    """Most deployments never write one."""
    assert load_agents(tmp_path / "agents") == ()


def test_a_file_that_is_not_a_directory_is_not_an_error(tmp_path):
    path = tmp_path / "agents"
    path.write_text("not a directory", encoding="utf-8")

    assert load_agents(path) == ()


def test_an_empty_directory_loads_nothing(tmp_path):
    (tmp_path / "agents").mkdir()

    assert load_agents(tmp_path / "agents") == ()


def test_every_markdown_file_is_loaded_in_filename_order(tmp_path):
    agents = tmp_path / "agents"
    _write(agents, "surveyor.md", _agent("surveyor"))
    _write(agents, "reviewer.md", _agent("reviewer"))

    assert [d.name for d in load_agents(agents)] == ["reviewer", "surveyor"]


def test_a_file_that_is_not_markdown_is_ignored(tmp_path):
    agents = tmp_path / "agents"
    _write(agents, "reviewer.md", _agent("reviewer"))
    _write(agents, "notes.txt", _agent("notes"))

    assert [d.name for d in load_agents(agents)] == ["reviewer"]


def test_a_subdirectory_is_not_descended_into(tmp_path):
    agents = tmp_path / "agents"
    _write(agents, "reviewer.md", _agent("reviewer"))
    _write(agents / "nested", "surveyor.md", _agent("surveyor"))

    assert [d.name for d in load_agents(agents)] == ["reviewer"]


def test_one_bad_file_does_not_stop_the_scan(tmp_path):
    """The symptom is one missing entry in the enum, never a dead feature."""
    agents = tmp_path / "agents"
    _write(agents, "broken.md", "no header here\n")
    _write(agents, "reviewer.md", _agent("reviewer"))

    assert [d.name for d in load_agents(agents)] == ["reviewer"]


def test_a_bad_file_is_reported_to_the_sink(tmp_path):
    """This package cannot log, so the one way to see a typo is the sink."""
    agents = tmp_path / "agents"
    broken = _write(agents, "broken.md", "no header here\n")
    _write(agents, "reviewer.md", _agent("reviewer"))
    seen: list[tuple[pathlib.Path, str]] = []

    load_agents(agents, on_error=lambda path, error: seen.append((path, str(error))))

    assert [path for path, _ in seen] == [broken]
    assert "frontmatter" in seen[0][1]


def test_a_file_without_a_name_is_loaded_under_its_filename(tmp_path):
    agents = tmp_path / "agents"
    _write(agents, "Reviewer.md", "---\ndescription: Reviews\n---\nReview it.\n")

    assert [d.name for d in load_agents(agents)] == ["reviewer"]


def test_the_source_records_which_file_a_definition_came_from(tmp_path):
    agents = tmp_path / "agents"
    path = _write(agents, "reviewer.md", _agent("reviewer"))

    assert load_agents(agents)[0].source == str(path)


def test_a_file_overrides_a_builtin_of_the_same_name_in_place(tmp_path):
    """Registered after the built-ins, so the later registration wins.

    The position is the built-in's, so overriding one does not reorder
    the enum the model is shown.
    """
    agents = tmp_path / "agents"
    _write(agents, "general-purpose.md", _agent("general-purpose", "Mine instead"))
    registry = SubAgentRegistry(
        [
            SubAgentDefinition(
                name="general-purpose",
                description="The built-in one",
                system_prompt="Work.",
                source="builtin",
            ),
            SubAgentDefinition(
                name="reviewer", description="Reviews", system_prompt="Review."
            ),
        ]
    )

    for definition in load_agents(agents):
        registry.register(definition)

    assert registry.names() == ("general-purpose", "reviewer")
    assert registry.get("general-purpose").description == "Mine instead"
    assert registry.get("general-purpose").source.endswith("general-purpose.md")
