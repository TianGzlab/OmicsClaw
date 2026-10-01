"""The frozen public surface of ``skills/_sdk`` (plan 0062 §3.10, case 18).

``_sdk`` is the read-only API that skill code — hand-written or produced by
a future self-improvement loop — may use, so what it exposes is a review
gate: adding or removing a public name means editing ``PUBLIC_SURFACE``.
Only names that skill or template code actually imports are frozen, plus
two machine-read contracts (``RESULT_SCHEMA``, ``DEPENDENCIES``). Checked
over non-test code in ``skills/**`` and ``templates/**``: every name taken
from an ``_sdk`` module is in that module's ``__all__`` and not private,
and every frozen name (contracts aside) has at least one user.
"""

from __future__ import annotations

import ast
import importlib

from tests.sdk._scan import REPO_ROOT, is_test_path, python_files, rel

PUBLIC_SURFACE: dict[str, set[str]] = {
    "skills._sdk": {"REPO_ROOT"},
    "skills._sdk.checksums": {"sha256_file"},
    "skills._sdk.report": {"generate_report_header", "generate_report_footer", "write_repro_requirements"},
    "skills._sdk.result": {"RESULT_SCHEMA", "write_result_json", "load_result_json", "mark_result_status", "write_owned_text"},
    "skills._sdk.runtime_env": {"ensure_runtime_cache_dirs"},
    "skills._sdk.user_guidance": {"emit_user_guidance", "emit_user_guidance_payload"},
    "skills._sdk.deps": {"DEPENDENCIES", "require", "get", "is_available", "install_hint", "validate_r_environment"},
    "skills._sdk.r_script_runner": {"R_SCRIPTS_DIR", "RScriptRunner", "RScriptError", "RScriptTimeoutError"},
    "skills._sdk.r_utils": {"read_r_result_csv"},
    "skills._sdk.r_dependency_manager": {"check_r_tier", "suggest_r_install"},
    "skills._sdk.external_env": {"EnvNotFoundError", "is_env_available", "run_anndata_op_in_env"},
    "skills._sdk.notebook": {"read_input", "write_output", "load_skill", "load_demo", "run_cli"},
    "skills._sdk.notebook.contract": {"LAYOUT", "MANIFEST_SCHEMA", "LEDGER_EVENTS", "ENVIRONMENT"},
}

CONTRACTS = {
    ("skills._sdk.result", "RESULT_SCHEMA"),
    ("skills._sdk.deps", "DEPENDENCIES"),
    ("skills._sdk.notebook.contract", "LAYOUT"),
    ("skills._sdk.notebook.contract", "MANIFEST_SCHEMA"),
    ("skills._sdk.notebook.contract", "LEDGER_EVENTS"),
    ("skills._sdk.notebook.contract", "ENVIRONMENT"),
}
"""Read by AST from outside, not imported by skills; exempt from the has-a-user rule."""

STEP_API = {
    ("skills._sdk.notebook", "read_input"),
    ("skills._sdk.notebook", "write_output"),
    ("skills._sdk.notebook", "load_skill"),
    ("skills._sdk.notebook", "load_demo"),
    ("skills._sdk.notebook", "run_cli"),
}
"""Called by the step files the agent writes in a project, outside this tree; exempt from the has-a-user rule."""

R_SCRIPTS = {
    "bulkrna_combat.R", "bulkrna_deseq2.R", "bulkrna_enrichment.R", "bulkrna_survival.R",
    "bulkrna_wgcna.R", "check_packages.R", "sc_cellchat.R", "sc_doubletfinder.R", "sc_gsea_r.R",
    "sc_gsva_r.R", "sc_mast_de.R", "sc_monocle3_r.R", "sc_nichenet.R", "sc_proportion_test_r.R",
    "sc_pseudobulk_deseq2.R", "sc_scdblfinder.R", "sc_scds.R", "sc_scmap_annotate.R",
    "sc_seurat_integrate.R", "sc_seurat_preprocess.R", "sc_singler_annotate.R",
    "sc_slingshot_pseudotime.R", "sc_soupx.R", "sp_card.R", "sp_numbat.R", "sp_rctd.R",
    "sp_sparkx.R", "sp_spotlight.R",
}


def _sdk_modules() -> set[str]:
    """``_sdk``, its top-level modules, and the step-code facade and contract of ``_sdk/notebook``."""
    base = REPO_ROOT / "skills" / "_sdk"
    top = {f"skills._sdk.{p.stem}" for p in base.glob("*.py") if p.stem != "__init__"}
    return {"skills._sdk", "skills._sdk.notebook", "skills._sdk.notebook.contract"} | top


def _uses() -> list[tuple[str, str, str]]:
    """(file, _sdk module, name) for every name skill or template code takes from ``_sdk``."""
    modules = _sdk_modules()
    uses: list[tuple[str, str, str]] = []
    for path in python_files("skills", "templates"):
        if is_test_path(path) or rel(path).startswith("skills/_sdk/"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        aliases: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module in modules:
                for alias in node.names:
                    child = f"{node.module}.{alias.name}"
                    if child in modules:
                        aliases[alias.asname or alias.name] = child
                    else:
                        uses.append((rel(path), node.module, alias.name))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in modules and alias.asname:
                        aliases[alias.asname] = alias.name
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in aliases:
                uses.append((rel(path), aliases[node.value.id], node.attr))
    return uses


def test_every_module_is_frozen():
    assert _sdk_modules() == set(PUBLIC_SURFACE)


def test_all_matches_the_frozen_surface():
    for module, names in PUBLIC_SURFACE.items():
        assert set(importlib.import_module(module).__all__) == names, module


def test_skill_code_takes_only_public_names():
    bad = sorted(
        f"{where}: {module}.{name}"
        for where, module, name in _uses()
        if name.startswith("_") or name not in PUBLIC_SURFACE[module]
    )
    assert bad == []


def test_every_frozen_name_has_a_user():
    used = {(module, name) for _where, module, name in _uses()}
    unused = sorted(
        f"{module}.{name}"
        for module, names in PUBLIC_SURFACE.items()
        for name in names
        if (module, name) not in used and (module, name) not in CONTRACTS | STEP_API
    )
    assert unused == []


def test_the_shared_r_scripts_are_frozen():
    assert {p.name for p in (REPO_ROOT / "skills" / "_sdk" / "r_scripts").glob("*.R")} == R_SCRIPTS
