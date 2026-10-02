"""``omicsclaw.entry`` may import every layer; none may import it.

Plan 0031 Q2. The five packages before this one each carry a leaf test
that names what they are allowed to reach for. This package is the one
place allowed to reach for all five, so its rule runs the other way and
is made of two halves:

*Nothing below imports upwards.* A cycle between the composition root and
a layer it composes is how "the engine knows about sessions" starts, and
it starts as one convenience import that looks local.

*Driving this layer loads none of the packages it replaces.* The four
forbidden ``omicsclaw`` names — ``runtime``, ``control``, ``providers``
(plural), ``skill`` — are not absent by accident. Each holds
a working implementation of something this rebuild is redoing, so each is
the import a tired person reaches for. ``surfaces`` joins them from the
other direction: the three surfaces import ``entry``, and an import back
would make the dependency arrow meaningless in both directions.

**The second half is behavioural, in a subprocess, after the code has
run.** Plan 0028's handover records what a source-level check is worth on
its own: one lazy ``importlib.import_module`` inside a function body left
286 tests green while the boundary it was the sole enforcer of was
already crossed. An AST walk checks spellings; only :data:`sys.modules`
after a real run checks facts.
"""

from __future__ import annotations

import ast
import pathlib
import subprocess
import sys

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_ENTRY_DIR = _REPO_ROOT / "omicsclaw" / "entry"
_LOWER_LAYERS = (
    "schema",
    "provider",
    "engine",
    "tools",
    "context",
    "skills",
    "mcp",
    "memory",
    "sandbox",
    "skillenv",
)

_REPLACED_PACKAGES = (
    "omicsclaw.runtime",
    "omicsclaw.control",
    "omicsclaw.providers",
    "omicsclaw.skill",
    "omicsclaw.surfaces",
)
"""Everything this rebuild is replacing, named rather than inferred.

``omicsclaw.providers`` is the plural one and the trap: the layer this
step composes is ``omicsclaw.provider``, singular, so a check written as
a prefix match on ``omicsclaw.provider`` would pass while the legacy
package was loaded. ``omicsclaw.skill`` is the same trap in the other
direction — see :data:`_SUPERSEDED`.
"""

_SUPERSEDED = ("omicsclaw.skills", "omicsclaw.memory")
"""Forbidden by plan 0031, permitted by plan 0032. Named, not deleted.

Plan 0031 §12-1 is an explicit owner ruling — "skill 暂时预留着" — and its
acceptance §9-17 says the subprocess probe must confirm ``omicsclaw.skill*``
is absent from :data:`sys.modules`. That covered ``omicsclaw.skills`` by
its glob, and the entry given to task A listed it.

``omicsclaw/skills/`` (plural) is nonetheless a **rebuild** package, not a
replaced one: the legacy package was ``omicsclaw/skill/`` (singular, now
deleted), and the plural one arrived with ``docs/plans/0032-skill-loader.md``
after task A was written. Its lane wired ``use_skill`` and a skills section
into ``assembly.py`` and ``config.py``, which is a scope decision only the
owner can settle. This constant is where that tension is recorded rather
than resolved: if §12-1 still stands, move this name back into
:data:`_REPLACED_PACKAGES` above and the probe turns red again on the
import at ``omicsclaw/entry/assembly.py``.

``omicsclaw.memory`` followed the same path: the legacy graph memory was
deleted and the name now holds the rebuild's step-7 persistence layer
(plan 0033), which ``omicsclaw/entry/compaction.py`` composes for offloaded
tool results and the compaction log (plan 0035).
"""

_OPTIONAL_DEPENDENCIES = (
    "fastapi",
    "textual",
    "prompt_toolkit",
    "openai",
    "anthropic",
)
"""None of these is installed alongside every deployment.

Each surface imports what it needs **inside a factory function, in
plainly visible syntax** — not through ``importlib``, which is the form
the handover singles out as the one no check can see. Importing
``omicsclaw.entry`` must therefore cost none of them.
"""


def _module_paths(package: pathlib.Path) -> list[pathlib.Path]:
    return sorted(package.rglob("*.py"))


def _package_of(path: pathlib.Path) -> list[str]:
    return list(path.relative_to(_REPO_ROOT).with_suffix("").parts[:-1])


def _imported_modules(path: pathlib.Path) -> list[str]:
    """Absolute module names imported by *path*, relative ones resolved.

    Relative imports are resolved rather than skipped, for the reason
    ``tests/tools/test_tools_is_a_leaf_layer.py`` gives: ``from ..entry
    import x`` is a relative import that *leaves* the package, and a
    check that skips every non-zero level cannot see it.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    package = _package_of(path)
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


def _probe(source: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", source],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
    )


# ---- half one: nothing below imports upwards -------------------------


@pytest.mark.parametrize("layer", _LOWER_LAYERS)
def test_no_lower_layer_mentions_the_entry_package(layer: str):
    package = _REPO_ROOT / "omicsclaw" / layer
    offenders = [
        f"{layer}/{path.name}"
        for path in _module_paths(package)
        for name in _imported_modules(path)
        if name == "omicsclaw.entry" or name.startswith("omicsclaw.entry.")
    ]

    assert not offenders, (
        f"{offenders} import omicsclaw.entry — the composition root "
        "composes these layers and none of them may know it exists"
    )


@pytest.mark.parametrize("layer", _LOWER_LAYERS)
def test_importing_a_lower_layer_does_not_load_the_entry_package(layer: str):
    """The same property after import rather than in the syntax."""
    source = (
        f"import sys, omicsclaw.{layer};"
        "print('omicsclaw.entry' in sys.modules)"
    )
    result = _probe(source)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False"


# ---- half two: driving this layer loads nothing it replaced ----------


_BEHAVIOUR_PROBE = '''
import sys
import tempfile
from pathlib import Path

from omicsclaw.context import assemble, measure
from omicsclaw.entry import (
    InboundMessage,
    SenderPolicy,
    build_app,
    resolve_app_config,
)
from omicsclaw.entry.assembly import (
    build_budget,
    build_prompt,
    build_registry,
    build_summarizer,
    default_sections,
)
from omicsclaw.provider import provider_from_env
from omicsclaw.tools.builtin.bash import ENGINE_TIMEOUT_MARGIN

with tempfile.TemporaryDirectory() as root:
    (Path(root) / "OMICSCLAW.md").write_text("I am OmicsClaw", encoding="utf-8")

    config = resolve_app_config(
        argv=["--workspace", root, "--model", "deepseek-chat"],
        env={"OMICSCLAW_MAX_TURNS": "3"},
    )
    assert config.max_turns == 3
    assert config.bash_timeout() == config.tool_timeout_s - ENGINE_TIMEOUT_MARGIN

    registry = build_registry(config)
    snapshot = registry.available_tools()
    names = {tool.name for tool in snapshot}
    assert {"read_file", "write_file", "edit_file", "bash"} <= names, names

    budget = build_budget(config.model, snapshot)
    rendered = build_prompt(default_sections(config)).render()
    assert "I am OmicsClaw" in rendered.system_prompt
    assert "Safety rules" in rendered.system_prompt

    conversation = assemble(rendered, (), "analyse this slide")
    report = measure(conversation, snapshot, budget)
    assert report.budget.usable_tokens > 0

    summarizer = build_summarizer(
        provider_from_env(config.provider, config.model), config
    )
    assert summarizer is not None

    policy = SenderPolicy(allowed_senders=frozenset({"owner"}), bot_identity="bot")
    inbound = InboundMessage(
        text="hi", session_id="s1", source_request_id="r1", sender="owner"
    )
    assert policy.admits(inbound) is True

    app = build_app(config)
    assert app.engine is not None
    assert app.registry is not None

FORBIDDEN = __FORBIDDEN__
leaked = sorted(
    name
    for name in sys.modules
    if any(name == f or name.startswith(f + ".") for f in FORBIDDEN)
)
print(leaked)
'''
"""Everything task A owns, run for real, then the question asked once.

The assertions inside are scaffolding, not the product: they are there so
that a probe which quietly stopped doing anything fails loudly instead of
printing an empty leak list. The product is the line after the ``with``
block — what :data:`sys.modules` holds **once the layer has run**, which
is the only form of the question a lazy import answers honestly.
"""


def test_driving_the_entry_layer_loads_nothing_it_replaced():
    forbidden = _REPLACED_PACKAGES + _OPTIONAL_DEPENDENCIES
    source = _BEHAVIOUR_PROBE.replace("__FORBIDDEN__", repr(forbidden))
    result = _probe(source)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]", (
        f"driving omicsclaw.entry loaded {result.stdout.strip()}"
    )


def test_importing_the_package_costs_no_optional_dependency():
    """Trap 13, and acceptance §9-4.

    ``fastapi`` and ``textual`` are not installed on this machine and
    neither vendor SDK is, so an import-time dependency on any of them
    would not be a slow start-up here — it would be an
    :exc:`ImportError` for every user of the package.
    """
    source = (
        "import sys, omicsclaw.entry;"
        f"print(sorted(m for m in sys.modules if m in {_OPTIONAL_DEPENDENCIES!r}))"
    )
    result = _probe(source)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"


@pytest.mark.parametrize(
    "path",
    _module_paths(_ENTRY_DIR),
    ids=lambda p: p.name,
)
def test_every_entry_module_imports_with_no_vendor_sdk_installed(
    path: pathlib.Path,
):
    """Keeps its meaning on a machine where the SDKs *are* installed.

    Blocking the imports at :data:`sys.meta_path` rather than trusting
    that they are absent is what makes this test say the same thing in
    CI, in a developer's full environment and here.
    """
    relative = path.relative_to(_REPO_ROOT).with_suffix("")
    parts = [part for part in relative.parts if part != "__init__"]
    source = (
        "import sys;"
        "sys.meta_path.insert(0, type('Blocker', (), {"
        "  'find_spec': staticmethod(lambda name, *a, **k: ("
        "      (_ for _ in ()).throw(ImportError('blocked: ' + name))"
        "      if name.split('.')[0] in ('openai', 'anthropic', 'fastapi',"
        "                                'textual') else None))"
        "})());"
        f"import {'.'.join(parts)};"
        "print('ok')"
    )
    result = _probe(source)

    assert result.returncode == 0, (
        f"{path.name} could not be imported without the optional "
        f"dependencies:\n{result.stderr}"
    )
    assert result.stdout.strip() == "ok"


def test_the_entry_package_has_modules_to_check():
    """A rule that passes vacuously over an empty directory is not a rule."""
    assert _module_paths(_ENTRY_DIR)


def test_no_entry_module_names_a_replaced_package():
    """The source-level half of the behaviour probe, for the surfaces.

    The subprocess probe above only covers what task A's own code path
    touches. This one covers every file in the package, which is what
    catches the predictable mistake when the three surface subpackages
    are ported in: moving a file and moving its imports with it. Plan
    0031 §9-18 names it outright.
    """
    offenders = [
        f"{module.name}:{name}"
        for module in _module_paths(_ENTRY_DIR)
        for name in _imported_modules(module)
        if any(
            name == package or name.startswith(f"{package}.")
            for package in _REPLACED_PACKAGES
        )
    ]

    assert not offenders, f"{offenders} — plan 0031 §9-18"
