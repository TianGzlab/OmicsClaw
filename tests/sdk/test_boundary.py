"""Guards for the code boundary between ``skills/**`` and ``omicsclaw/**``.

Plan 0062 §3.8. Skills and the framework meet only through file contracts
(``SKILL.md``, ``tuning.yaml``, the result.json schema in ``skills/_sdk``);
the mechanical helpers every skill needs live in ``skills/_sdk/``. These
tests pin that down statically, with known-item tables that must match the
violations *exactly* — a violation that appears or disappears both turn the
test red, so the tables cannot rot silently.

Rules and the plan's names for them:

* B1 — nothing imports ``omicsclaw.core``; ``omicsclaw/core/`` and
  ``omicsclaw/r_scripts/`` hold no code.
* B2 — every ``omicsclaw.*`` / ``skills.*`` module a skill imports exists.
* B3 — skill code does not import ``omicsclaw`` at all.
* B4 — the framework does not import ``skills.*``.
* B5 — ``skills/_sdk`` imports nothing above itself.
* B6 — a domain ``_lib`` imports only its own ``_lib`` and ``skills._sdk``.
* B7 — no ``SKILL.md`` under ``skills/_sdk`` (the loader would index it).
* B8 — skill code carries no framework control-plane credential names.
* B9 — no string constant in skill code spells an ``omicsclaw.*`` module.
* B10 — every domain ``_lib`` module imports with ``omicsclaw`` made unimportable.

``skills/**/tests/`` are outside B3 (plan 0062 Q5); B1 still covers them.
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys

from tests.sdk._scan import (
    REPO_ROOT,
    imports_of,
    is_test_path,
    missing_targets,
    python_files,
    rel,
    targets,
    within,
)

SDK = REPO_ROOT / "skills" / "_sdk"

B2_KNOWN = {
    # 0058: the consensus-interpret helper still reaches the deleted providers package.
    ("skills/spatial/consensus-interpret/_llm.py", "omicsclaw.providers.chat_completion"),
}

B3_KNOWN = {
    # 0058 replaces the four consensus shells and the interpreter helper.
    ("skills/singlecell/scrna/sc-consensus-clustering/sc_consensus_clustering.py", "omicsclaw.runtime.consensus.run"),
    ("skills/singlecell/scrna/sc-consensus-integration/sc_consensus_integration.py", "omicsclaw.runtime.consensus.run"),
    ("skills/singlecell/scrna/sc-consensus-pseudotime/sc_consensus_pseudotime.py", "omicsclaw.runtime.consensus.run"),
    ("skills/spatial/consensus-domains/consensus_domains.py", "omicsclaw.runtime.consensus.run"),
    ("skills/spatial/consensus-interpret/_llm.py", "omicsclaw.providers.chat_completion"),
}

B4_KNOWN: set[str] = set()


def _skill_code():
    return [p for p in python_files("skills", "templates/skill") if not is_test_path(p)]


def test_core_is_gone():
    """B1, directory half: no code is left where ``core`` and the R scripts used to be."""
    leftovers = []
    for old in ("omicsclaw/core", "omicsclaw/r_scripts"):
        base = REPO_ROOT / old
        if base.exists():
            leftovers += [
                rel(p) for p in base.rglob("*")
                if p.is_file() and "__pycache__" not in p.parts and p.suffix in {".py", ".R"}
            ]
    assert leftovers == []
    assert (SDK / "__init__.py").is_file()
    assert len(sorted((SDK / "r_scripts").glob("*.R"))) == 28


def test_nothing_imports_omicsclaw_core():
    """B1: including string imports, skill tests, framework tests and the template."""
    offenders = sorted(
        f"{ref.path}:{ref.lineno} {ref.module}"
        for p in python_files("skills", "omicsclaw", "tests", "templates")
        for ref in imports_of(p)
        if any(within(t, "omicsclaw.core") for t in targets(ref))
    )
    assert offenders == []


def test_imported_modules_exist_on_disk():
    """B2: a skill never imports a module that is not there."""
    violations = set()
    for p in _skill_code():
        for ref in imports_of(p):
            if within(ref.module, "omicsclaw") or within(ref.module, "skills"):
                for name in missing_targets(ref):
                    violations.add((ref.path, name))
    assert violations == B2_KNOWN


def test_sdk_imports_nothing_above_it():
    """B5: ``skills/_sdk`` depends on the standard library, third parties and itself."""
    offenders = sorted(
        f"{ref.path}:{ref.lineno} {t}"
        for p in python_files("skills/_sdk")
        for ref in imports_of(p)
        for t in targets(ref)
        if within(t, "omicsclaw") or (within(t, "skills") and not within(t, "skills._sdk"))
    )
    assert offenders == []


def test_no_skill_md_under_sdk():
    """B7: the skill loader indexes any ``SKILL.md``; ``_sdk`` is not a skill."""
    assert sorted(SDK.rglob("SKILL.md")) == []


def test_skill_code_carries_no_control_credentials():
    """B8: credential scrubbing belongs to the framework's launch boundary."""
    needles = ("OMICSCLAW_REMOTE_AUTH_TOKEN", "SKILL_EVOLUTION", "scrub_internal_control_credentials")
    offenders = sorted(
        f"{rel(p)}: {n}"
        for p in (REPO_ROOT / "skills").rglob("*")
        if p.is_file() and p.suffix in {".py", ".R", ".sh", ".md", ".yaml", ".yml"}
        and "__pycache__" not in p.parts
        for n in needles
        if n in p.read_text(encoding="utf-8", errors="replace")
    )
    assert offenders == []


def test_no_omicsclaw_module_strings():
    """B9: a module path hidden in a string is an import the AST scan cannot see."""
    offenders = sorted(
        f"{rel(p)}:{node.lineno} {node.value}"
        for p in python_files("skills")
        if not is_test_path(p)
        for node in ast.walk(ast.parse(p.read_text(encoding="utf-8")))
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and re.fullmatch(r"omicsclaw(\.\w+)+", node.value)
    )
    assert offenders == []


def test_framework_imports_no_skills():
    """B4: the framework reaches skills through files, never through imports."""
    offenders = {
        ref.path
        for p in python_files("omicsclaw")
        for ref in imports_of(p)
        if any(within(t, "skills") for t in targets(ref))
    }
    assert offenders == B4_KNOWN


def test_skill_code_imports_no_omicsclaw():
    """B3: skills meet the framework only through files."""
    violations = {
        (ref.path, t)
        for p in _skill_code()
        for ref in imports_of(p)
        for t in targets(ref)
        if within(t, "omicsclaw")
    }
    assert violations == B3_KNOWN


def _lib_files():
    return [
        p for p in python_files("skills")
        if len(p.relative_to(REPO_ROOT).parts) > 3 and p.relative_to(REPO_ROOT).parts[2] == "_lib"
    ]


def test_domain_lib_imports_only_itself_and_sdk():
    """B6: a domain's shared code depends on its own domain and ``_sdk`` only."""
    offenders = []
    for p in _lib_files():
        domain = p.relative_to(REPO_ROOT).parts[1]
        own = f"skills.{domain}._lib"
        for ref in imports_of(p):
            for t in targets(ref):
                if within(t, "omicsclaw") or (
                    within(t, "skills") and not within(t, own) and not within(t, "skills._sdk")
                ):
                    offenders.append(f"{ref.path}:{ref.lineno} {t}")
    assert sorted(offenders) == []


def test_lib_modules_import_without_omicsclaw():
    """B10: import every domain ``_lib`` module in a child where ``omicsclaw`` cannot load.

    A failure whose traceback mentions ``omicsclaw`` is a violation. A module
    that cannot load because a third-party package is missing is listed as
    skipped — neither passed nor a violation.
    """
    modules = sorted(
        ".".join(p.relative_to(REPO_ROOT).with_suffix("").parts).removesuffix(".__init__")
        for p in _lib_files()
    )
    code = (
        "import importlib, json, sys, traceback\n"
        "sys.modules['omicsclaw'] = None\n"
        "out = {}\n"
        "for m in json.loads(sys.argv[1]):\n"
        "    try:\n"
        "        importlib.import_module(m)\n"
        "        out[m] = 'ok'\n"
        "    except BaseException as e:\n"
        "        tb = traceback.format_exc()\n"
        "        chain, x = [], e\n"
        "        while x is not None:\n"
        "            chain.append(str(x) + ' ' + str(getattr(x, 'name', '') or ''))\n"
        "            x = x.__cause__ or x.__context__\n"
        "        if any('omicsclaw' in c for c in chain):\n"
        "            out[m] = 'violation: ' + tb[-800:]\n"
        "        elif isinstance(e, ModuleNotFoundError):\n"
        "            out[m] = 'skipped: ' + str(e.name)\n"
        "        else:\n"
        "            out[m] = 'error: ' + tb[-800:]\n"
        "print('B10=' + json.dumps(out))\n"
    )
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT), "PYTHONDONTWRITEBYTECODE": "1"}
    proc = subprocess.run(
        [sys.executable, "-B", "-c", code, json.dumps(modules)],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=900,
    )
    line = next((l for l in proc.stdout.splitlines() if l.startswith("B10=")), None)
    assert line is not None, proc.stderr[-3000:]
    result = json.loads(line[4:])
    skipped = sorted(m for m, v in result.items() if v.startswith("skipped"))
    if skipped:
        print("B10 skipped for missing third-party packages:", {m: result[m] for m in skipped})
    violations = {m: v for m, v in result.items() if v.startswith("violation")}
    assert violations == {}
