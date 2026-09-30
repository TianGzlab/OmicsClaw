"""``omicsclaw.launch`` imports ``omicsclaw.entry``; the arrow ends there.

Plan 0037 judgements 1 and 2, and acceptance §8-1 / §8-2. Four
properties, each written so that breaking it turns a **named** test red:

1. This package is the only reader of ``sys.argv`` and of the process
   environment, and within it only :mod:`omicsclaw.launch` itself names
   either —— every function below takes them as arguments.
2. ``omicsclaw/entry/**`` does not import this package, in the syntax
   and in :data:`sys.modules` after the code has run.
3. This shell names **no deployment flag**. The forbidden set is derived
   from ``config.py`` rather than copied, which is the strengthening
   plan 0037 asks for over ``test_cli_main.py``'s hand-written
   ``SURFACE_FLAGS``: a flag added to ``AppConfig`` tomorrow is covered
   without anybody remembering to add it here.
4. Driving this shell loads none of the packages the rebuild replaces
   —— ``omicsclaw.surfaces`` above all, because plan 0037 §7's whole
   argument is that the new shell owes the old CLI nothing.

The behavioural halves run in a subprocess. Plan 0028's handover
records what a source-level check is worth on its own: one lazy
``importlib.import_module`` inside a function body left 286 tests green
while the boundary it was the sole enforcer of was already crossed.
"""

from __future__ import annotations

import ast
import pathlib
import subprocess
import sys

import pytest

from omicsclaw.entry.config import _BY_FLAG
from tests._env_probe import offending_sources

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_LAUNCH_DIR = _REPO_ROOT / "omicsclaw" / "launch"
_ENTRY_DIR = _REPO_ROOT / "omicsclaw" / "entry"

_REPLACED_PACKAGES = (
    "omicsclaw.runtime",
    "omicsclaw.control",
    "omicsclaw.providers",
    "omicsclaw.skill",
    "omicsclaw.surfaces",
)
"""Mirrors ``tests/entry/test_entry_is_the_top_layer.py``, one layer up.

``omicsclaw.providers`` is the plural one and the trap: the layer this
shell reaches is ``omicsclaw.provider``, singular, so a prefix match on
``omicsclaw.provider`` would pass while the legacy package was loaded.
"""

_OPTIONAL_DEPENDENCIES = (
    "fastapi",
    "uvicorn",
    "textual",
    "prompt_toolkit",
    "openai",
    "anthropic",
    "telegram",
    "lark_oapi",
)
"""None of these is installed alongside every deployment.

The shell imports all three surfaces at module scope —— that is what
makes the command table a table —— so if any surface paid for its
optional dependency at import time, *every* deployment would pay for
all of them.

Two tests below use this list and they are not equally strong.
:func:`test_importing_the_shell_costs_no_optional_dependency` and
:func:`test_driving_the_shell_loads_nothing_it_replaced` check all eight
by asking what is in :data:`sys.modules`, which works because none of
the eight is installed here.
:func:`test_every_launch_module_imports_with_no_vendor_sdk_installed`
*blocks* imports at :data:`sys.meta_path` so that it keeps its meaning
where they are installed —— and it blocks five, not eight:
``prompt_toolkit`` is installed and is a hard dependency of the CLI
surface, and ``telegram`` / ``lark_oapi`` are imported inside adapter
methods that this package never calls. Five is the honest number and
saying "the optional dependencies" was not.
"""


def _sources(package: pathlib.Path) -> list[pathlib.Path]:
    return sorted(package.rglob("*.py"))


def _probe(source: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", source],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
        timeout=180,
    )


def test_there_are_launch_modules_to_check():
    """A rule that passes vacuously over an empty directory is not a rule."""
    assert len(_sources(_LAUNCH_DIR)) >= 4


# ---- 1. the two globals are read in one file, at two defaults ---------


def test_only_the_shell_itself_names_the_two_globals():
    """Plan 0037 §5.4's probe, in its stricter half.

    ``_grammar.py``, ``_surfaces.py`` and ``__main__.py`` take the
    command line and the environment as arguments. The day one of them
    reaches for a global instead, the injection point stops being the
    production path and becomes decoration again.

    The spellings come from :mod:`tests._env_probe`, shared with the
    same rule one layer down —— see that module for why they are not
    three.
    """
    offenders = offending_sources(_LAUNCH_DIR, exempt=("__init__.py",))

    assert not offenders, f"{offenders} — only launch/__init__.py may"


def _global_reads(source: str) -> list[str]:
    """``os.environ`` / ``os.getenv`` / ``sys.argv`` as *code*, not as prose.

    Counted through the syntax tree rather than with ``str.count``,
    which is the fix for what the first version of this test measured:
    it counted occurrences in the module docstring too, so explaining
    the rule in one more sentence broke it and adding one more read did
    not stand out. A docstring is not a parse point.
    """
    reads: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Attribute):
            continue
        base = node.value
        if not isinstance(base, ast.Name):
            continue
        name = f"{base.id}.{node.attr}"
        if name in ("os.environ", "os.getenv", "sys.argv"):
            reads.append(name)
    return reads


def test_the_shell_reads_each_global_exactly_once():
    """One read of each, in code, in the one file allowed to have them.

    A second read of either is a second parse point, which is what plan
    0031 Q8 exists to prevent and what nothing else in this repository
    would notice.
    """
    source = (_LAUNCH_DIR / "__init__.py").read_text(encoding="utf-8")

    assert sorted(_global_reads(source)) == ["os.environ", "sys.argv"]


def test_the_shell_hands_both_globals_down_explicitly():
    """The other half: they are *used*, not merely named.

    ``main`` resolving the defaults and then dropping them would satisfy
    the count above and break the program, so the call is checked too.
    """
    source = (_LAUNCH_DIR / "__init__.py").read_text(encoding="utf-8")

    assert "sys.argv[1:] if argv is None else argv" in source
    assert "environment: Mapping[str, str] = os.environ" in source
    assert "command.start(deployment, surface, environment)" in source


# ---- 2. the arrow points one way --------------------------------------


_DYNAMIC_IMPORTERS = ("import_module", "__import__")
"""Calls whose first string argument names a module.

``importlib.import_module("omicsclaw.launch")`` is an import that no
``ast.Import`` node describes, and it is the exact spelling plan 0028's
handover records getting past a source-level check for 286 tests.
Matched on the attribute name rather than on ``importlib.import_module``
so that ``from importlib import import_module`` is covered too.
"""


def _imported_modules(path: pathlib.Path) -> list[str]:
    """Absolute module names imported by *path*, however they are spelled.

    Three spellings, and the first version of this helper saw only one
    and a half of them:

    *Relative imports are resolved rather than skipped*, for the reason
    ``tests/tools/test_tools_is_a_leaf_layer.py`` gives: ``from ..launch
    import x`` is a relative import that *leaves* the package, and a
    check that skips every non-zero level cannot see it.

    *``from X import Y`` also names ``X.Y``.* Recording only
    ``node.module`` meant ``from omicsclaw import launch`` —— the
    spelling a reader reaches for first —— was recorded as importing
    ``omicsclaw``, which no layering rule forbids.

    *A module named by a string is still imported.* See
    :data:`_DYNAMIC_IMPORTERS`.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    package = list(path.relative_to(_REPO_ROOT).with_suffix("").parts[:-1])
    names: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if not node.level:
                base = node.module or ""
            else:
                climbed = len(package) - (node.level - 1)
                ascended = package[:climbed] if climbed > 0 else []
                base = ".".join([*ascended, node.module] if node.module else ascended)
            if base:
                names.append(base)
            names.extend(f"{base}.{alias.name}" if base else alias.name
                         for alias in node.names)
        elif isinstance(node, ast.Call):
            called = node.func
            attribute = getattr(called, "attr", None) or getattr(called, "id", None)
            if attribute not in _DYNAMIC_IMPORTERS or not node.args:
                continue
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                names.append(first.value)

    return names


def test_no_entry_module_imports_the_shell():
    """Plan 0037 §8-2, in the syntax.

    **Naming the shell is allowed; importing it is not.** Five
    docstrings under ``omicsclaw/entry/`` mention
    :mod:`omicsclaw.launch` —— ``config.py``, ``entry/__init__.py``,
    ``channel/__init__.py``, ``session.py`` and ``ingress.py`` —— and
    they should. §3-2's one-line summary says the entry layer "does not
    know the shell exists", but what it can be held to, and what this
    test checks, is the arrow: nothing here may *import* the shell. A
    module that refused to name its only caller would be worse
    documentation for no architectural gain.

    That is the opposite ruling from
    ``tests/entry/test_config.py::test_no_entry_module_reads_the_environment``,
    which scans prose too —— and the difference is not taste. There the
    prose was *false*: the package had stopped reading those globals, so
    a docstring saying otherwise was a defect. Here the prose is true.
    """
    offenders = [
        f"{path.relative_to(_ENTRY_DIR)}:{name}"
        for path in _sources(_ENTRY_DIR)
        for name in _imported_modules(path)
        if name == "omicsclaw.launch" or name.startswith("omicsclaw.launch.")
    ]

    assert not offenders, (
        f"{offenders} import omicsclaw.launch — the shell starts this "
        "layer and this layer may not know the shell exists"
    )


@pytest.mark.parametrize("surface", ["", ".cli", ".desktop", ".channel"])
def test_importing_the_entry_layer_does_not_load_the_shell(surface: str):
    """The same property after import rather than in the syntax."""
    result = _probe(
        f"import sys, omicsclaw.entry{surface};"
        "print('omicsclaw.launch' in sys.modules)"
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False"


_EVERY_ENTRY_MODULE = '''
import importlib
import pathlib
import sys

root = pathlib.Path("omicsclaw/entry")
skipped = []
for path in sorted(root.rglob("*.py")):
    parts = [p for p in path.with_suffix("").parts if p != "__init__"]
    try:
        importlib.import_module(".".join(parts))
    except ImportError as exc:
        skipped.append(exc.name)

print(sorted(set(skipped)))
print("omicsclaw.launch" in sys.modules)
'''
"""Import *every* module of the layer below, then ask the question once.

The four-target parametrisation above imports the package and its three
subpackages, which between them reach none of the channel adapters or
their delivery modules: files that the reverse-layering probe could never
have caught a lazy ``import omicsclaw.launch`` in. One subprocess covers
all of them; a subprocess per file would cost a minute and say the same
thing.
"""


def test_importing_every_entry_module_does_not_load_the_shell():
    result = _probe(_EVERY_ENTRY_MODULE)

    assert result.returncode == 0, result.stderr
    skipped, loaded = result.stdout.strip().splitlines()

    assert skipped == "[]", (
        f"{skipped} could not be imported, so those modules were not checked "
        "— an adapter that needs its SDK at module scope has to be listed "
        "here deliberately rather than skipped silently"
    )
    assert loaded == "False", "importing the entry layer loaded omicsclaw.launch"


def test_the_entry_layer_no_longer_ships_a_process():
    """Plan 0037 §6: ``python -m omicsclaw.entry.cli`` is not kept.

    Not as a file and not as an alias —— an alias would preserve exactly
    the entry point the redesign removes.
    """
    assert not (_ENTRY_DIR / "cli" / "__main__.py").exists()

    result = _probe("import runpy; runpy.run_module('omicsclaw.entry.cli')")

    assert result.returncode != 0
    assert "No module named omicsclaw.entry.cli.__main__" in result.stderr


def test_the_shell_imports_only_public_names_of_the_entry_layer():
    """Plan 0037 §5.1: ``_surfaces.py`` consumes the published surface.

    A private module of ``entry`` reached from here would make this
    shell part of that layer's implementation, which is the coupling the
    whole redesign is spending a package to avoid.
    """
    offenders = []
    for path in _sources(_LAUNCH_DIR):
        for name in _imported_modules(path):
            if not name.startswith("omicsclaw.entry"):
                continue
            private = [part for part in name.split(".") if part.startswith("_")]
            if private:
                offenders.append(f"{path.name}:{name}")

    assert not offenders, f"{offenders} reach into omicsclaw.entry's privates"


# ---- 3. no deployment flag is named here ------------------------------


DEPLOYMENT_FLAGS = frozenset(_BY_FLAG)
"""Every flag ``resolve_app_config`` answers to, taken from ``config.py``.

Derived rather than transcribed. ``test_cli_main.py``'s predecessor
listed the *surface's* flags by hand, which caught a deployment flag
being reinterpreted only for the flags somebody had thought of; this
direction needs no maintenance and covers flags that do not exist yet.
"""

SHELL_FLAGS = frozenset(
    {
        "--",
        "-h",
        "--help",
        "--abandon-grace",
        "--hide-reasoning",
        "--channels",
        "--configure",
        "--health-port",
        "--host",
        "--list",
        "--port",
        "--prompt",
        "--prompt-file",
        "--session",
        "--show-reasoning",
        "--verbose",
    }
)
"""Every flag literal this package may branch on: the three surfaces', and the cut.

A deployment flag appearing here would mean plan 0031 Q8 has two parse
points again —— ``--model`` read once by ``resolve_app_config`` into
``AppConfig`` and once more by a shell that thinks it knows better.
Nothing else in the repository would notice that, which is why it is
asserted rather than assumed.
"""


def _flag_literals(source: str) -> frozenset[str]:
    """Flag-shaped string literals; docstrings and usage text excluded.

    Prose is not a parse: the module docstrings show ``--workspace`` in
    examples and the three ``*_USAGE`` blocks name deployment flags in
    sentences, and a check that could not tell those from a comparison
    would force the documentation to be written badly. Bare string
    statements are docstrings by construction; the usage blocks are
    excluded by name.

    Only the **first whitespace-separated token** of a literal counts,
    because a refusal message such as ``"--channels is required"`` is
    one flag and a sentence, not a flag called "--channels is required".
    """
    tree = ast.parse(source)
    documentation = {
        id(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id.endswith("USAGE")
            for target in node.targets
        ):
            documentation.add(id(node.value))

    found: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in documentation
        ):
            head = node.value.strip().split(" ")[0] if node.value.strip() else ""
            if head == "--" or _looks_like_a_flag(head):
                found.add(head)
    return frozenset(found)


def _looks_like_a_flag(token: str) -> bool:
    body = token[2:] if token.startswith("--") else token[1:]
    if not token.startswith("-") or not body:
        return False
    return body[0].isalpha() and all(c.isalnum() or c == "-" for c in body)


def test_the_flags_the_shell_acts_on_are_exactly_these():
    found: set[str] = set()
    for path in _sources(_LAUNCH_DIR):
        found |= _flag_literals(path.read_text(encoding="utf-8"))

    assert found == SHELL_FLAGS


def test_the_shell_names_no_deployment_flag():
    """The derived half, which needs no maintenance."""
    assert DEPLOYMENT_FLAGS, "config.py published no flags — check the import"

    offenders = []
    for path in _sources(_LAUNCH_DIR):
        overlap = _flag_literals(path.read_text(encoding="utf-8")) & DEPLOYMENT_FLAGS
        offenders.extend(f"{path.name}:{flag}" for flag in sorted(overlap))

    assert not offenders, (
        f"{offenders} — resolve_app_config already reads these; a second "
        "reading is plan 0031 Q8's two parse points"
    )


def test_the_surface_flags_and_the_deployment_flags_do_not_overlap():
    """The rule has to be falsifiable, so the two sets must be comparable.

    If ``SHELL_FLAGS`` and ``DEPLOYMENT_FLAGS`` were disjoint by
    construction —— different spellings, say —— the test above would be
    unable to fail. They are not: both families use the same ``--word``
    spelling and ``config.py`` publishes over thirty of them.
    """
    assert len(DEPLOYMENT_FLAGS) > 10
    assert not SHELL_FLAGS & DEPLOYMENT_FLAGS


# ---- 4. the shell owes the legacy CLI nothing -------------------------


def test_the_shell_names_no_replaced_package():
    offenders = [
        f"{path.name}:{name}"
        for path in _sources(_LAUNCH_DIR)
        for name in _imported_modules(path)
        if any(
            name == package or name.startswith(f"{package}.")
            for package in _REPLACED_PACKAGES
        )
    ]

    assert not offenders, f"{offenders} — plan 0037 §7"


_BEHAVIOUR_PROBE = '''
import contextlib
import io
import sys

from omicsclaw.launch import main

quiet = io.StringIO()
with contextlib.redirect_stdout(quiet), contextlib.redirect_stderr(quiet):
    assert main(["channel", "--", "--list"], {}) == 0
    assert main(["cli", "--", "--help"], {}) == 0
    assert main(["desktop", "--", "--help"], {}) == 0
    assert main(["nonesuch"], {}) == 2
assert "TelegramChannel" in quiet.getvalue()

FORBIDDEN = __FORBIDDEN__
leaked = sorted(
    name
    for name in sys.modules
    if any(name == f or name.startswith(f + ".") for f in FORBIDDEN)
)
print(leaked)
'''
"""Every command dispatched for real, then the question asked once.

The assertions inside are scaffolding, not the product: they are there
so that a probe which quietly stopped doing anything fails loudly
instead of printing an empty leak list. The product is the line after
them —— what :data:`sys.modules` holds **once the shell has run**, which
is the only form of the question a lazy import answers honestly.
"""


def test_driving_the_shell_loads_nothing_it_replaced():
    forbidden = _REPLACED_PACKAGES + _OPTIONAL_DEPENDENCIES
    source = _BEHAVIOUR_PROBE.replace("__FORBIDDEN__", repr(forbidden))
    result = _probe(source)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]", (
        f"driving omicsclaw.launch loaded {result.stdout.strip()}"
    )


def test_importing_the_shell_costs_no_optional_dependency():
    """Trap 13, for the package that imports all three surfaces.

    ``prompt_toolkit`` **is** installed here, so a module-scope import
    would not fail —— it would simply be paid by everybody, including
    the desktop server and the channel runner, and no other test in this
    repository would notice.
    """
    result = _probe(
        "import sys, omicsclaw.launch;"
        f"print(sorted(m for m in sys.modules if m in {_OPTIONAL_DEPENDENCIES!r}))"
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"


@pytest.mark.parametrize(
    "path", _sources(_LAUNCH_DIR), ids=lambda p: p.name
)
def test_every_launch_module_imports_with_no_vendor_sdk_installed(
    path: pathlib.Path,
):
    """Keeps its meaning on a machine where the SDKs *are* installed.

    Blocking the imports at :data:`sys.meta_path` rather than trusting
    that they are absent is what makes this test say the same thing in
    CI, in a developer's full environment and here.
    """
    relative = path.relative_to(_REPO_ROOT).with_suffix("")
    parts = [part for part in relative.parts if part != "__init__"]
    if parts[-1] == "__main__":
        pytest.skip("importing a __main__ module runs it")
    result = _probe(
        "import sys;"
        "sys.meta_path.insert(0, type('Blocker', (), {"
        "  'find_spec': staticmethod(lambda name, *a, **k: ("
        "      (_ for _ in ()).throw(ImportError('blocked: ' + name))"
        "      if name.split('.')[0] in ('openai', 'anthropic', 'fastapi',"
        "                                'uvicorn', 'textual') else None))"
        "})());"
        f"import {'.'.join(parts)};"
        "print('ok')"
    )

    assert result.returncode == 0, (
        f"{path.name} could not be imported without the optional "
        f"dependencies:\n{result.stderr}"
    )
    assert result.stdout.strip() == "ok"


# ---- the desktop surface's honest failure -----------------------------


_WITHOUT_A_WEB_SERVER = """
import runpy
import sys

sys.modules["fastapi"] = None
sys.modules["uvicorn"] = None
sys.argv = ["omicsclaw.launch", *sys.argv[1:]]
runpy.run_module("omicsclaw.launch", run_name="__main__", alter_sys=True)
"""
"""Run ``python -m omicsclaw.launch`` with ``fastapi`` and ``uvicorn``
unimportable: a ``None`` entry in :data:`sys.modules` makes ``import``
raise :exc:`ImportError` whether or not the interpreter has them."""


def test_the_desktop_command_names_its_missing_dependency_and_stops(tmp_path):
    """The branch a user without the web server hits, as a real process.

    The command must name the remedy and return the shell's refusal code
    rather than a traceback. The two packages are made unimportable in
    the child, so the test takes this branch in every interpreter: where
    they are installed, the unguarded command would start serving on
    ``127.0.0.1:8765`` and this test would wait out its timeout instead.
    ``--workspace`` points at a temporary directory so that nothing, even
    on a regression that got further, is written into the checkout.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            _WITHOUT_A_WEB_SERVER,
            "desktop",
            "--workspace",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
        timeout=60,
    )

    assert result.returncode == 2, result.stderr
    assert "uvicorn and fastapi" in result.stderr
    assert "conda" in result.stderr
    assert "pip install" not in result.stderr
    assert "Traceback" not in result.stderr


def test_the_desktop_command_checks_the_dependency_before_assembling(monkeypatch):
    """"Before assembling" is an ordering claim, so ordering is what is asserted.

    An earlier version of this test asserted only the exit code, the
    message and an elapsed-time bound —— and a mutant that moved the
    check *after* :func:`~omicsclaw.entry.open_app` survived all three,
    because assembling an app takes about 0.2 s here and produces no
    output. A bound loose enough not to flake is loose enough not to
    test anything. Recording the call order does test it.

    This one runs in-process and with doubles, deliberately: the
    property is "which of these two runs first", which no observable of
    the real process distinguishes. The real-process half is the test
    above.
    """
    from omicsclaw.launch import _surfaces

    calls: list[str] = []

    def refuse() -> object:
        calls.append("dependency")
        raise _surfaces.MissingSurfaceDependency("no uvicorn (test double)")

    async def assembled(_config: object) -> object:
        calls.append("open_app")
        raise AssertionError("the agent was assembled before the check")

    monkeypatch.setattr(_surfaces, "_asgi_server_module", refuse)
    monkeypatch.setattr(_surfaces, "open_app", assembled)

    from omicsclaw.launch import main

    assert main(["desktop"], {}) == 2
    assert calls == ["dependency"]
