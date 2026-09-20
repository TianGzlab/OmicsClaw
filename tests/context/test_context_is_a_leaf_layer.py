"""``omicsclaw/context/`` may import ``omicsclaw.schema`` and nothing else.

Plan 0030 §9-2 and decision Q2, and copied — as
``FRAMEWORK-REBUILD.md:296-300`` instructs steps 5 and 6 to do — from
the *repaired* guard in ``tests/tools/test_tools_is_a_leaf_layer.py``
rather than from the weaker one beside the engine. The differences
matter here for the same reasons they mattered there, and one of them
matters more: this layer is the one with a standing temptation to reach
for ``omicsclaw.provider``, because ``get_model_limits`` lives there and
a context window is exactly what a budget wants.

*A whitelist, not a blacklist.* Only ``omicsclaw.schema`` is permitted
inside the ``omicsclaw`` namespace. Naming what is forbidden would mean
predicting every package a future step adds; naming what is allowed does
not.

*Relative imports are resolved, not skipped.* ``from ..provider import
get_model_limits`` is a relative import that leaves the package, so the
level is resolved to an absolute module name before it is judged.

*Third parties are checked against the standard library*, via
:data:`sys.stdlib_module_names`. This layer must import on a machine
with no ``tiktoken`` and no vendor SDK, because that is the machine it
was written on and because an optional dependency that silently changes
a budget is not optional.

**And the fourth check is behavioural.** An ``ast`` walk that reads only
``Import`` and ``ImportFrom`` nodes cannot see a module named as a
string inside a function body. :func:`_dynamic_import_calls` refuses the
call forms at source level, and
:func:`test_running_the_layer_does_not_pull_in_a_single_runtime_module`
runs every real path this package has in a fresh process and inspects
:data:`sys.modules` **afterwards** — static checks inspect spelling,
only a behavioural probe inspects fact.
"""

from __future__ import annotations

import ast
import pathlib
import subprocess
import sys

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_CONTEXT_DIR = _REPO_ROOT / "omicsclaw" / "context"

_ALLOWED_INTERNAL = ("omicsclaw.schema", "omicsclaw.context")
"""``omicsclaw.context`` is on the list so the package may import itself.

Two entries, not three. ``omicsclaw.provider`` is deliberately absent
even though this layer's budget is built out of a model's context
window: the caller performs that lookup and passes an ``int``, which
costs one line at the call site and keeps this guard as strict as the
tool layer's.
"""

_TEMPTING_NEIGHBOURS = (
    "omicsclaw.runtime",
    "omicsclaw.engine",
    "omicsclaw.provider",
    "omicsclaw.providers",
    "omicsclaw.memory",
)
"""Named as well as covered by the rule, so a reader sees what it is for.

Copied unchanged from the tool layer's list, where every entry already
earns its place here. ``omicsclaw.runtime`` holds
``runtime/context/``, the 3,705-line assembly layer this package
replaces, and is the dangerous one: it is *also* called ``context``, so
borrowing a helper out of it would look entirely unremarkable in a diff.
``omicsclaw.provider`` is the second: ``get_model_limits`` and
``apply_cache_breakpoints`` both sit there and both look like things a
context layer should know about. It does not; its callers do.
"""


def _module_paths() -> list[pathlib.Path]:
    """Every module in the package, subpackages included.

    Globbed recursively rather than listed, so a new module inherits the
    rule the moment it is added instead of the moment someone remembers
    to add it here.
    """
    return sorted(_CONTEXT_DIR.rglob("*.py"))


def _package_of(path: pathlib.Path) -> str:
    """The dotted package a module lives in, for resolving relative imports."""
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
            # PEP 328: level 1 is the current package, each further level
            # ascends one. A level that ascends past the top is reported
            # as the empty string, which no whitelist entry matches.
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
"""Every way of naming a module at runtime, and **the whitelist is empty**.

Not "these are forbidden targets" but "this layer has no business
importing anything dynamically at all". A whitelist of permitted dynamic
targets would be unenforceable — the argument is an expression, and
``importlib.import_module("omicsclaw." + suffix)`` defeats any check
that reads it — so the call itself is what is refused. Nothing here
needs an exception: the one import this package might plausibly want to
defer is ``tiktoken``, and decision Q3 rules that it must never reach
for it at all.
"""


def _called_name(node: ast.Call) -> str:
    """The trailing identifier of whatever is being called, or ``""``.

    Attribute and bare-name forms collapse to the same answer on
    purpose: ``importlib.import_module(...)`` and the
    ``import_module(...)`` left behind by ``from importlib import
    import_module`` are one crossing written two ways.
    """
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _dynamic_import_calls(path: pathlib.Path) -> list[str]:
    """``name:lineno`` for every runtime-import call in ``path``."""
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
    assert _module_paths(), f"no modules found under {_CONTEXT_DIR}"


@pytest.mark.parametrize("path", _module_paths(), ids=lambda p: p.name)
def test_a_context_module_imports_only_schema_from_omicsclaw(path: pathlib.Path):
    offenders = [
        name
        for name in _imported_modules(path)
        if name.split(".")[0] == "omicsclaw" and not _is_allowed(name)
    ]

    assert not offenders, (
        f"{path.name} imports {offenders} — inside the omicsclaw namespace "
        "the context layer may import omicsclaw.schema and nothing else"
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
def test_a_context_module_imports_nothing_at_runtime(path: pathlib.Path):
    """The hole the two tests above share, closed at source level.

    Both of them read ``Import`` and ``ImportFrom`` nodes, so both are
    blind to a module named as a *string* and fetched inside a function
    body — which is exactly the shape a deferred ``tiktoken`` import
    would take.
    """
    offenders = _dynamic_import_calls(path)

    assert not offenders, (
        f"{path.name} imports at runtime via {offenders} — this layer has no "
        "dynamic imports, and a module named as a string is a module the "
        "import rules above cannot see"
    )


@pytest.mark.parametrize("path", _module_paths(), ids=lambda p: p.name)
def test_a_context_module_imports_only_the_standard_library(path: pathlib.Path):
    """Checked against :data:`sys.stdlib_module_names`, not a blacklist."""
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
    """The property the source rule is a proxy for, checked directly.

    ``omicsclaw.version`` is the permitted straggler: the top-level
    ``__init__`` imports it for ``__version__``.
    """
    source = (
        "import sys, omicsclaw.context as context;"
        "assert context.ContextBudget is not None;"
        "print(sorted(m for m in sys.modules if m.startswith('omicsclaw')"
        " and not m.startswith('omicsclaw.context')"
        " and not m.startswith('omicsclaw.schema') and m != 'omicsclaw'))"
    )
    result = _probe(source)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "['omicsclaw.version']", (
        f"importing the context layer dragged in {result.stdout.strip()}"
    )


def test_the_standard_library_context_modules_are_still_the_standard_ones():
    """``omicsclaw.context`` must not shadow ``contextlib`` or ``contextvars``.

    Python 3 has no implicit relative imports (PEP 328), so it cannot —
    but the claim is cheap to check and the consequence of being wrong
    would be spectacular and remote from its cause. ``omicsclaw/tools/``
    also has a ``context`` module, and the two coexist for the same
    reason: fully qualified names differ, so ``sys.modules`` holds two
    separate keys.
    """
    source = (
        "import contextlib, contextvars, sysconfig;"
        "import omicsclaw.context, omicsclaw.tools.context;"
        "stdlib = sysconfig.get_paths()['stdlib'];"
        "assert contextlib.__file__.startswith(stdlib), contextlib.__file__;"
        "assert contextvars.__file__.startswith(stdlib), contextvars.__file__;"
        "assert omicsclaw.context is not omicsclaw.tools.context;"
        "print('ok')"
    )
    result = _probe(source)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


_BEHAVIOUR_PROBE = '''
import asyncio
import sys

from omicsclaw.schema import Message, Role, ToolCall, ToolDefinition
from omicsclaw.context import (
    ContextBudget,
    PromptAssembler,
    Section,
    assemble,
    compact,
    estimate_tool_tokens,
    measure,
    repair_tool_pairs,
    static,
)


class Canned:
    async def summarize(self, prompt, *, system):
        return (
            "## Anchors\\n\\n### User Intent\\nship the thing\\n\\n"
            "## Summary\\nit was discussed at length"
        )


class Broken:
    async def summarize(self, prompt, *, system):
        raise RuntimeError("no summarizer today")


TOOLS = [
    ToolDefinition("read_file", "read a file", {"type": "object"}),
    ToolDefinition("spatial_de", "差异表达分析", {"type": "object"}),
]


def conversation():
    prompt = (
        PromptAssembler()
        .with_section(Section("persona", "", static("你是 OmicsClaw。")))
        .with_section(Section("project", "## Project", static("x" * 200)))
        .with_section(Section("empty", "## Gone", static("")))
        .render()
    )
    assert len(prompt.sections) == 2, prompt.section_stats
    history = []
    for index in range(24):
        history.append(Message.user(f"question {index} " + "q" * 300))
        history.append(
            Message.assistant(
                "thinking",
                tool_calls=(ToolCall(id=f"c{index}", name="read_file"),),
            )
        )
        history.append(
            Message.tool(tool_call_id=f"c{index}", content="r" * 300)
        )
    return assemble(prompt, history, "再跑一次")


async def main():
    messages = conversation()
    budget = ContextBudget(
        context_tokens=6_400,
        reserve_output_tokens=1_000,
        reserve_tool_tokens=estimate_tool_tokens(TOOLS),
    )
    report = measure(messages, TOOLS, budget)
    assert report.pressure is not None, report

    good, record, state = await compact(
        messages, budget, summarizer=Canned(), pinned=1
    )
    assert record.summarized > 0, record
    assert state.summary, state

    bad, bad_record, _ = await compact(
        messages, budget, summarizer=Broken(), pinned=1, state=state
    )
    assert bad_record.degraded, bad_record

    tiny = ContextBudget(
        context_tokens=1_200, reserve_output_tokens=100, reserve_tool_tokens=100
    )
    forced, forced_record, _ = await compact(
        messages, tiny, summarizer=Canned(), pinned=1
    )
    assert forced_record.pressure.value == "emergency", forced_record

    repaired = repair_tool_pairs(
        [
            Message.assistant(tool_calls=(ToolCall(id="orphan", name="bash"),)),
            Message.tool(tool_call_id="unknown", content="stale"),
        ]
    )
    assert len(repaired) == 2, repaired
    assert repaired[1].role is Role.TOOL, repaired


asyncio.run(main())
print(sorted(m for m in sys.modules if m.startswith("omicsclaw.runtime")))
'''
"""Every execution path this layer has, run for real in a fresh process.

The assertions inside are not the product — they are there so a probe
that silently stopped doing anything fails loudly instead of printing an
empty leak list. The product is the line after ``asyncio.run``: what
:data:`sys.modules` holds **once the layer has run**, which is the only
question a lazy ``import_module`` in a function body answers honestly.

The paths, chosen to cover each way into the package: a multi-section
render including one section that disappears; :func:`assemble`;
:func:`measure` over real tool definitions; a compaction that summarizes
successfully; one whose summarizer raises, taking the degradation path;
one forced into the emergency tier, which must reach the truncation code
rather than the summarizer; and :func:`repair_tool_pairs` in both of its
directions at once. The list has to grow when a public function does.
"""


def test_running_the_layer_does_not_pull_in_a_single_runtime_module():
    """Plan 0030 §9-2, checked by behaviour rather than by syntax.

    The AST rules above are a proxy, and every proxy has a spelling it
    does not cover. This one has none: whatever a module did to reach
    ``omicsclaw/runtime/context/`` — a dotted import, a string, an
    ``__import__`` built out of concatenation — the module it reached is
    in :data:`sys.modules` when the run finishes.
    """
    result = _probe(_BEHAVIOUR_PROBE)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]", (
        f"running the context layer loaded {result.stdout.strip()} — "
        "omicsclaw.runtime holds the assembly layer this one replaces"
    )


@pytest.mark.parametrize("path", _module_paths(), ids=lambda p: p.name)
def test_every_context_module_imports_with_no_tokenizer_installed(
    path: pathlib.Path,
):
    """Keeps its meaning on a machine where ``tiktoken`` *is* installed.

    Decision Q3-2: a local budget must not change because an optional
    package happens to be present. Blocking the imports outright is the
    strongest form of that — a module that reached for one would not
    load at all.
    """
    relative = path.relative_to(_REPO_ROOT).with_suffix("")
    parts = [p for p in relative.parts if p != "__init__"]
    source = (
        "import sys;"
        "sys.meta_path.insert(0, type('Blocker', (), {"
        "  'find_spec': staticmethod(lambda name, *a, **k: ("
        "      (_ for _ in ()).throw(ImportError('blocked: ' + name))"
        "      if name.split('.')[0] in ('tiktoken', 'openai', 'anthropic')"
        "      else None))"
        "})());"
        f"import {'.'.join(parts)};"
        "print('ok')"
    )
    result = _probe(source)

    assert result.returncode == 0, (
        f"{path.name} could not be imported without a tokenizer:\n{result.stderr}"
    )
    assert result.stdout.strip() == "ok"


def test_the_public_surface_is_exactly_what_plan_0030_delivered():
    """``__init__`` is an interface, so widening it should be deliberate.

    Widened once, by plan 0035: the offload vocabulary, ``MemoryExtractor``,
    ``ProgressiveCompactor`` / ``should_write_back`` and the tier ordering
    (``PRESSURE_ORDER`` / ``at_least``) moved down from the entry layer.

    Six modules' worth of names, and the shape of the list is the
    argument: every Protocol on it (``TokenCounter``, ``Summarizer``)
    and every callable type behind it (``SectionSource``) is a seam
    through which knowledge this package is not allowed to hold gets in.
    Deliberately absent are the two private helpers a caller might reach
    for — ``_emergency_survivors`` and ``_schema_text`` — because a
    package surface is not the place to look for internals.
    """
    import omicsclaw.context as context

    assert context.__all__ == [
        "Anchors",
        "AssembledPrompt",
        "BudgetReport",
        "COMPACTION_MARKER",
        "CompactionPlan",
        "CompactionRecord",
        "CompactionState",
        "ContextBudget",
        "DEFAULT_MIN_TAIL",
        "FIRST_TEMPLATE",
        "INCREMENTAL_TEMPLATE",
        "MAX_REFERENCES",
        "MISSING_TOOL_RESULT",
        "MemoryExtractor",
        "OFFLOAD_MARKER",
        "OFFLOAD_RULE",
        "OffloadEntry",
        "OffloadOutcome",
        "OffloadStore",
        "Offloader",
        "PRESSURE_ORDER",
        "Pressure",
        "ProgressiveCompactor",
        "PromptAssembler",
        "REFERENCES_HEADING",
        "RenderedSection",
        "SUMMARY_SYSTEM_PROMPT",
        "Section",
        "SectionSource",
        "Summarizer",
        "TokenCounter",
        "apply_compaction",
        "assemble",
        "at_least",
        "build_compaction_message",
        "build_summary_prompt",
        "collect_references",
        "compact",
        "emergency_fit",
        "estimate_message_tokens",
        "estimate_messages_tokens",
        "estimate_text_tokens",
        "estimate_tool_tokens",
        "fit_to_budget",
        "format_token_count",
        "is_offloaded",
        "is_summary_message",
        "measure",
        "offload_key",
        "offload_messages",
        "parse_anchors_and_summary",
        "parse_placeholder",
        "parse_references",
        "plan_compaction",
        "render_for_summary",
        "render_placeholder",
        "render_references",
        "repair_tool_pairs",
        "should_write_back",
        "split_head_tail",
        "static",
        "text_from_file",
    ]
    assert all(hasattr(context, name) for name in context.__all__)
    assert context.__all__ == sorted(context.__all__), "keep the list sorted"
