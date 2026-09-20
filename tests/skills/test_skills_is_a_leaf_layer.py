"""``omicsclaw/skills/`` may import ``omicsclaw.schema`` and ``omicsclaw.tools``.

Copied from the repaired guard beside the tool layer, with one entry that
matters more here than anywhere else: ``omicsclaw.skill`` — **singular** —
is the legacy skill system, forty modules of registry, orchestration and
governance. It differs from this package by one letter, so an import of
it would look entirely unremarkable in a diff, and the whitelist prefix
check has to distinguish the two rather than treating one as a prefix of
the other.

*A whitelist, not a blacklist.* Naming what is forbidden means predicting
every package a future step adds; naming what is allowed does not.

*Relative imports are resolved, not skipped.* ``from ..skill import x``
leaves the package, so the level is resolved to an absolute name before
it is judged.

*Third parties are checked against the standard library.* This layer
parses YAML without PyYAML on purpose: an optional dependency that
silently changes how a skill header is read is not optional.

**And the last check is behavioural.** An ``ast`` walk cannot see a
module named as a string inside a function body, so
:func:`test_running_the_layer_does_not_pull_in_the_legacy_skill_system`
runs every real path this package has in a fresh process and inspects
:data:`sys.modules` afterwards.
"""

from __future__ import annotations

import ast
import pathlib
import subprocess
import sys

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SKILLS_DIR = _REPO_ROOT / "omicsclaw" / "skills"

_ALLOWED_INTERNAL = ("omicsclaw.schema", "omicsclaw.tools", "omicsclaw.skills")
"""``omicsclaw.tools`` is allowed because ``use_skill`` declares its own
:class:`~omicsclaw.tools.base.ToolPolicy` and is built as a
:class:`~omicsclaw.tools.function_tool.FunctionTool`; leaving the policy
to default would put an approval prompt in front of every skill load."""

_TEMPTING_NEIGHBOURS = (
    "omicsclaw.skill",
    "omicsclaw.context",
    "omicsclaw.runtime",
    "omicsclaw.engine",
    "omicsclaw.provider",
    "omicsclaw.providers",
    "omicsclaw.memory",
)
"""Named as well as covered by the rule, so a reader sees what it is for.

``omicsclaw.skill`` is the legacy skill system and the dangerous one.
``omicsclaw.context`` is the second: this package renders text for a
prompt section, so importing ``Section`` to return one looks helpful and
would make two leaf layers depend on each other instead of on the
composition root that joins them.
"""


def _module_paths() -> list[pathlib.Path]:
    """Every module in the package, so a new one inherits the rule at once."""
    return sorted(_SKILLS_DIR.rglob("*.py"))


def _package_of(path: pathlib.Path) -> str:
    parts = path.relative_to(_REPO_ROOT).with_suffix("").parts
    return ".".join(parts[:-1])


def _imported_modules(path: pathlib.Path) -> list[str]:
    """Absolute module names imported by ``path``, relative ones resolved."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    package = _package_of(path).split(".")
    names: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if not node.level:
                if node.module:
                    names.append(node.module)
                continue
            climbed = len(package) - (node.level - 1)
            base = package[:climbed] if climbed > 0 else []
            names.append(".".join([*base, node.module] if node.module else base))

    return names


_DYNAMIC_IMPORT_CALLS = frozenset(
    {
        "__import__",
        "import_module",
        "reload",
        "spec_from_file_location",
        "module_from_spec",
        "exec_module",
        "load_module",
    }
)
"""Every way of naming a module at runtime, and the whitelist is empty.

A whitelist of permitted dynamic targets would be unenforceable — the
argument is an expression — so the call itself is what is refused.
"""


def _called_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _dynamic_import_calls(path: pathlib.Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        f"{_called_name(node)}:{node.lineno}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _called_name(node) in _DYNAMIC_IMPORT_CALLS
    ]


def _is_allowed(name: str) -> bool:
    return any(name == p or name.startswith(f"{p}.") for p in _ALLOWED_INTERNAL)


def test_the_package_has_modules_to_check():
    """A rule that vacuously passes over an empty directory is not a rule."""
    assert _module_paths(), f"no modules found under {_SKILLS_DIR}"


def test_the_whitelist_tells_the_two_skill_packages_apart():
    """The guard itself, checked: one letter is the whole distinction."""
    assert _is_allowed("omicsclaw.skills.loader")
    assert not _is_allowed("omicsclaw.skill")
    assert not _is_allowed("omicsclaw.skill.registry")


@pytest.mark.parametrize("path", _module_paths(), ids=lambda p: p.name)
def test_a_skills_module_imports_only_schema_and_tools(path: pathlib.Path):
    offenders = [
        name
        for name in _imported_modules(path)
        if name.split(".")[0] == "omicsclaw" and not _is_allowed(name)
    ]

    assert not offenders, (
        f"{path.name} imports {offenders} — inside the omicsclaw namespace "
        "the skill loader may import omicsclaw.schema and omicsclaw.tools"
    )


@pytest.mark.parametrize("forbidden", _TEMPTING_NEIGHBOURS)
def test_the_named_neighbours_appear_nowhere_in_the_package(forbidden: str):
    offenders = [
        path.name
        for path in _module_paths()
        if any(
            name == forbidden or name.startswith(f"{forbidden}.")
            for name in _imported_modules(path)
        )
    ]

    assert not offenders, f"{offenders} import {forbidden}"


@pytest.mark.parametrize("path", _module_paths(), ids=lambda p: p.name)
def test_a_skills_module_imports_nothing_at_runtime(path: pathlib.Path):
    offenders = _dynamic_import_calls(path)

    assert not offenders, (
        f"{path.name} imports at runtime via {offenders} — a module named as "
        "a string is a module the import rules above cannot see"
    )


@pytest.mark.parametrize("path", _module_paths(), ids=lambda p: p.name)
def test_a_skills_module_imports_only_the_standard_library(path: pathlib.Path):
    offenders = [
        name
        for name in _imported_modules(path)
        if name.split(".")[0] not in sys.stdlib_module_names
        and name.split(".")[0] != "omicsclaw"
    ]

    assert not offenders, f"{path.name} imports non-stdlib {offenders}"


def _probe(source: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", source],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
    )


def test_importing_the_package_drags_in_no_unrelated_omicsclaw_module():
    source = (
        "import sys, omicsclaw.skills as skills;"
        "assert skills.load_skills is not None;"
        "print(sorted(m for m in sys.modules if m.startswith('omicsclaw')"
        " and not m.startswith('omicsclaw.skills')"
        " and not m.startswith('omicsclaw.schema')"
        " and not m.startswith('omicsclaw.tools') and m != 'omicsclaw'))"
    )
    result = _probe(source)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "['omicsclaw.version']", (
        f"importing the skill loader dragged in {result.stdout.strip()}"
    )


def test_the_package_is_not_the_repository_s_skills_data_directory():
    """``skills/`` at the repository root is content, not a Python package."""
    source = (
        "import omicsclaw.skills, pathlib;"
        "here = pathlib.Path(omicsclaw.skills.__file__).resolve().parent;"
        "assert here.name == 'skills' and here.parent.name == 'omicsclaw', here;"
        "print('ok')"
    )
    result = _probe(source)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


def test_the_package_imports_with_no_yaml_installed():
    """The subset parser must not quietly start depending on PyYAML."""
    source = (
        "import sys;"
        "sys.meta_path.insert(0, type('Blocker', (), {"
        "  'find_spec': staticmethod(lambda name, *a, **k: ("
        "      (_ for _ in ()).throw(ImportError('blocked: ' + name))"
        "      if name.split('.')[0] in ('yaml', 'tiktoken', 'openai', 'anthropic')"
        "      else None))"
        "})());"
        "import omicsclaw.skills;"
        "print('ok')"
    )
    result = _probe(source)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


_BEHAVIOUR_PROBE = '''
import asyncio
import json
import pathlib
import sys
import tempfile

from omicsclaw.skills import (
    SkillIndex,
    SkillNotFound,
    load_skills,
    parse_frontmatter,
    use_skill_tool,
)
from omicsclaw.tools import ToolRegistry
from omicsclaw.schema import ToolCall


def tree(root):
    for domain, name in (("spatial", "spatial-de"), ("singlecell", "sc-de")):
        directory = root / domain / name
        directory.mkdir(parents=True)
        (directory / "SKILL.md").write_text(
            "---\\nname: " + name + "\\ndescription: 分析差异表达。\\n"
            "  Skip when 数据是别的。\\ntags:\\n- omics\\n---\\n\\n# "
            + name
            + "\\n",
            encoding="utf-8",
        )
    (root / "broken").mkdir()
    (root / "broken" / "SKILL.md").write_text("no header", encoding="utf-8")


async def main():
    with tempfile.TemporaryDirectory() as raw:
        root = pathlib.Path(raw)
        tree(root)

        assert load_skills(root / "absent").is_empty
        index = load_skills(root)
        assert index.names() == ("sc-de", "spatial-de"), index.names()
        assert len(index.skipped) == 1, index.skipped
        assert "Skip when" in index.summary()
        assert "singlecell" in index.domain_summary()
        assert "use_skill" in index.prompt_body()
        assert index.prompt_body(compact=True)
        assert SkillIndex().prompt_body() == ""
        assert index.by_domain()[0][0] == "singlecell"
        assert "# sc-de" in index.get_full_content("sc-de")
        try:
            index.get_full_content("sc-dee")
        except SkillNotFound as exc:
            assert "sc-de" in str(exc)
        else:
            raise AssertionError("an unknown skill loaded")

        assert parse_frontmatter("no header").body == "no header"

        registry = ToolRegistry()
        registry.register(use_skill_tool(index))
        result = await registry.execute(
            ToolCall(id="1", name="use_skill", arguments=json.dumps(
                {"skill_name": "spatial-de"}))
        )
        assert not result.is_error, result.output
        assert "Skill directory" in result.output


asyncio.run(main())
print(sorted(
    m for m in sys.modules
    if m.startswith("omicsclaw.skill.")
    or m == "omicsclaw.skill"
    or m.startswith("omicsclaw.runtime")
    or m.startswith("omicsclaw.context")
))
'''
"""Every execution path this layer has, run for real in a fresh process.

The assertions inside are there so a probe that silently stopped doing
anything fails loudly instead of printing an empty leak list. The product
is the line after ``asyncio.run``: what :data:`sys.modules` holds once
the layer has run, which is the only question a lazy import in a function
body answers honestly. The list has to grow when a public function does.
"""


def test_running_the_layer_does_not_pull_in_the_legacy_skill_system():
    result = _probe(_BEHAVIOUR_PROBE)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]", (
        f"running the skill loader loaded {result.stdout.strip()}"
    )


def test_the_public_surface_is_deliberate():
    """``__init__`` is an interface, so widening it should be a decision."""
    import omicsclaw.skills as skills

    assert skills.__all__ == [
        "Frontmatter",
        "SKILL_FILENAME",
        "Skill",
        "SkillIndex",
        "SkillLoadError",
        "SkillNotFound",
        "SkipReason",
        "SkippedSkill",
        "USE_SKILL_SCHEMA",
        "USE_SKILL_TOOL_NAME",
        "load_skills",
        "parse_frontmatter",
        "use_skill_tool",
    ]
    assert all(hasattr(skills, name) for name in skills.__all__)
    assert skills.__all__ == sorted(skills.__all__), "keep the list sorted"
