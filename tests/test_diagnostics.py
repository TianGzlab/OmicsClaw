from __future__ import annotations

import json
import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from omicsclaw import diagnostics
from omicsclaw.diagnostics import (
    DIAGNOSTIC_STATUS_OK,
    DIAGNOSTIC_STATUS_WARN,
    DiagnosticCheck,
)


ROOT = Path(__file__).resolve().parent.parent


class _FakeRegistry:
    def __init__(self, names: list[str]):
        self._names = names

    def iter_primary_skills(self, domain=None):
        return [(name, {"alias": name, "domain": domain or "test"}) for name in self._names]


def _load_omicsclaw_script():
    spec = importlib.util.spec_from_file_location("omicsclaw_main_doctor_test", ROOT / "omicsclaw.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_collect_skill_catalog_check_warns_on_registry_catalog_drift(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "catalog.json").write_text(
        json.dumps(
            {
                "skill_count": 3,
                "skills": [
                    {"name": "alpha"},
                    {"name": "beta"},
                    {"name": "literature"},
                ],
            }
        ),
        encoding="utf-8",
    )

    check = diagnostics._collect_skill_catalog_check(
        str(tmp_path),
        registry_obj=_FakeRegistry(["alpha", "beta"]),
    )

    assert check.name == "Skill Catalog"
    assert check.status == DIAGNOSTIC_STATUS_WARN
    assert "registry=2" in check.summary
    assert "catalog=3" in check.summary
    assert any("extra_in_catalog: literature" in detail for detail in check.details)


def test_collect_skill_catalog_check_ok_when_registry_and_catalog_match(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "catalog.json").write_text(
        json.dumps(
            {
                "skill_count": 2,
                "skills": [
                    {"name": "alpha"},
                    {"name": "beta"},
                ],
            }
        ),
        encoding="utf-8",
    )

    check = diagnostics._collect_skill_catalog_check(
        str(tmp_path),
        registry_obj=_FakeRegistry(["alpha", "beta"]),
    )

    assert check.status == DIAGNOSTIC_STATUS_OK
    assert "2 skills" in check.summary


def test_collect_graphify_check_warns_when_slice_index_lacks_root_entrypoint(tmp_path):
    slice_dir = tmp_path / "graphify-out" / "omicsclaw-slices"
    slice_dir.mkdir(parents=True)
    (slice_dir / "INDEX.md").write_text("# Slice Index\n", encoding="utf-8")

    check = diagnostics._collect_graphify_check(str(tmp_path))

    assert check.name == "Graphify Map"
    assert check.status == DIAGNOSTIC_STATUS_WARN
    assert "slice" in check.summary.lower()
    assert any("omicsclaw-slices/INDEX.md" in detail for detail in check.details)
    assert any("GRAPH_REPORT.md" in detail for detail in check.details)


def test_collect_graphify_check_warns_when_cache_has_no_navigable_report(tmp_path):
    ast_dir = tmp_path / "graphify-out" / "cache" / "ast"
    ast_dir.mkdir(parents=True)
    (ast_dir / "example.json").write_text("{}", encoding="utf-8")

    check = diagnostics._collect_graphify_check(str(tmp_path))

    assert check.status == DIAGNOSTIC_STATUS_WARN
    assert "no navigable" in check.summary.lower()
    assert any("ast_cache_files=1" in detail for detail in check.details)


def test_build_doctor_report_flags_invalid_installed_extensions(tmp_path, monkeypatch):
    (tmp_path / "skills" / "user" / "bad-ext").mkdir(parents=True)

    monkeypatch.setattr(
        diagnostics,
        "_collect_python_checks",
        lambda: (
            DiagnosticCheck("Python", DIAGNOSTIC_STATUS_OK, "ok"),
            DiagnosticCheck("Core Packages", DIAGNOSTIC_STATUS_OK, "ok"),
            DiagnosticCheck("Optional Packages", DIAGNOSTIC_STATUS_OK, "ok"),
        ),
    )
    monkeypatch.setattr(
        diagnostics,
        "_collect_r_check",
        lambda: DiagnosticCheck("R Runtime", DIAGNOSTIC_STATUS_OK, "ok"),
    )
    monkeypatch.setattr(
        diagnostics,
        "_collect_provider_check",
        lambda: DiagnosticCheck("Provider Config", DIAGNOSTIC_STATUS_OK, "ok"),
    )
    monkeypatch.setattr(
        diagnostics,
        "_collect_session_db_check",
        lambda: DiagnosticCheck("Session DB", DIAGNOSTIC_STATUS_OK, "ok"),
    )
    monkeypatch.setattr(
        diagnostics,
        "_collect_knowledge_check",
        lambda: DiagnosticCheck("Knowledge Index", DIAGNOSTIC_STATUS_OK, "ok"),
    )
    monkeypatch.setattr(
        diagnostics,
        "_collect_memory_check",
        lambda: DiagnosticCheck("Graph Memory", DIAGNOSTIC_STATUS_OK, "ok"),
    )
    monkeypatch.setattr(
        diagnostics,
        "_collect_mcp_check",
        lambda: DiagnosticCheck("MCP Config", DIAGNOSTIC_STATUS_OK, "ok"),
    )

    report = diagnostics.build_doctor_report(
        omicsclaw_dir=str(tmp_path),
        workspace_dir=str(tmp_path),
        output_dir=str(tmp_path / "output"),
    )

    extensions_check = next(check for check in report.checks if check.name == "Extensions")
    assert extensions_check.status == DIAGNOSTIC_STATUS_WARN
    assert "1 installed" in extensions_check.summary
    assert "bad-ext" in extensions_check.details[0]


def test_collect_memory_check_warns_when_db_not_yet_created(tmp_path, monkeypatch):
    db_dir = tmp_path / "memdb"
    db_dir.mkdir()
    monkeypatch.setenv(
        "OMICSCLAW_MEMORY_DB_URL",
        f"sqlite+aiosqlite:///{db_dir / 'memory.db'}",
    )

    check = diagnostics._collect_memory_check()

    assert check.name == "Graph Memory"
    assert check.status == DIAGNOSTIC_STATUS_WARN
    assert "not yet initialized" in check.summary


def test_collect_memory_check_info_for_postgres_backend(monkeypatch):
    monkeypatch.setenv(
        "OMICSCLAW_MEMORY_DB_URL",
        "postgresql+asyncpg://user:pw@example.com:5432/memdb",
    )

    check = diagnostics._collect_memory_check()

    assert check.status == diagnostics.DIAGNOSTIC_STATUS_INFO
    assert "non-SQLite" in check.summary


def test_collect_memory_check_redacts_password_in_postgres_url(monkeypatch):
    monkeypatch.setenv(
        "OMICSCLAW_MEMORY_DB_URL",
        "postgresql+asyncpg://alice:s3cret@example.com:5432/memdb",
    )

    check = diagnostics._collect_memory_check()

    detail_text = "\n".join(check.details)
    assert "s3cret" not in detail_text
    assert "alice:***@example.com" in detail_text


def _build_memory_sqlite(
    db_path: Path,
    *,
    applied_versions: list[str] | None = None,
    shared_paths: list[tuple[str, str]] | None = None,
) -> None:
    """Create a minimal SQLite DB that mirrors the memory subsystem schema.

    Only the tables the doctor probes are created — enough to drive
    schema-version, table-presence, and shared-namespace checks without
    pulling in the full SQLAlchemy stack. ``shared_paths`` seeds
    ``(domain, path)`` rows into the ``__shared__`` namespace.
    """
    import sqlite3 as _sqlite3

    connection = _sqlite3.connect(db_path)
    try:
        connection.executescript(
            """
            CREATE TABLE nodes (uuid TEXT PRIMARY KEY);
            CREATE TABLE memories (id INTEGER PRIMARY KEY);
            CREATE TABLE edges (id INTEGER PRIMARY KEY);
            CREATE TABLE paths (
                namespace TEXT NOT NULL,
                domain TEXT NOT NULL,
                path TEXT NOT NULL,
                PRIMARY KEY (namespace, domain, path)
            );
            CREATE TABLE _schema_version (
                version TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL
            );
            """
        )
        for v in applied_versions or []:
            connection.execute(
                "INSERT INTO _schema_version (version, applied_at) VALUES (?, ?)",
                (v, "2026-01-01T00:00:00+00:00"),
            )
        for domain, path in shared_paths or []:
            connection.execute(
                "INSERT INTO paths (namespace, domain, path) VALUES (?, ?, ?)",
                ("__shared__", domain, path),
            )
        connection.commit()
    finally:
        connection.close()


def test_collect_memory_check_reports_schema_version_when_initialized(tmp_path, monkeypatch):
    db_path = tmp_path / "memory.db"
    _build_memory_sqlite(db_path, applied_versions=["001", "002"])
    monkeypatch.setenv(
        "OMICSCLAW_MEMORY_DB_URL", f"sqlite+aiosqlite:///{db_path}"
    )

    check = diagnostics._collect_memory_check()

    assert check.status == DIAGNOSTIC_STATUS_OK
    assert "schema=002" in check.summary
    assert "migrations=2" in check.summary
    detail_text = "\n".join(check.details)
    assert "schema_version=002" in detail_text
    assert "migrations_applied=2" in detail_text


def test_collect_memory_check_reports_shared_and_kh_counts(tmp_path, monkeypatch):
    db_path = tmp_path / "memory.db"
    _build_memory_sqlite(
        db_path,
        applied_versions=["001"],
        shared_paths=[
            ("core", "kh"),
            ("core", "kh/data-analysis-best-practices"),
            ("core", "kh/de-padj-guardrails"),
            ("analysis", "sc-preprocessing"),
        ],
    )
    monkeypatch.setenv(
        "OMICSCLAW_MEMORY_DB_URL", f"sqlite+aiosqlite:///{db_path}"
    )

    check = diagnostics._collect_memory_check()

    assert check.status == DIAGNOSTIC_STATUS_OK
    assert "shared=4" in check.summary
    assert "kh_seeds=2" in check.summary
    detail_text = "\n".join(check.details)
    assert "shared_paths=4" in detail_text
    assert "kh_seed_paths=2" in detail_text


def test_collect_memory_check_warns_when_shared_lacks_kh_seeds(tmp_path, monkeypatch):
    db_path = tmp_path / "memory.db"
    _build_memory_sqlite(
        db_path,
        applied_versions=["001"],
        shared_paths=[("analysis", "sc-preprocessing")],
    )
    monkeypatch.setenv(
        "OMICSCLAW_MEMORY_DB_URL", f"sqlite+aiosqlite:///{db_path}"
    )

    check = diagnostics._collect_memory_check()

    assert check.status == DIAGNOSTIC_STATUS_WARN
    assert "no KH bootstrap seeds" in check.summary


def test_collect_memory_check_ok_for_empty_initialized_store(tmp_path, monkeypatch):
    db_path = tmp_path / "memory.db"
    _build_memory_sqlite(db_path, applied_versions=["001"])
    monkeypatch.setenv(
        "OMICSCLAW_MEMORY_DB_URL", f"sqlite+aiosqlite:///{db_path}"
    )

    check = diagnostics._collect_memory_check()

    assert check.status == DIAGNOSTIC_STATUS_OK
    assert "shared=0" in check.summary
    assert "kh_seeds=0" in check.summary


def test_collect_memory_check_warns_when_required_tables_missing(tmp_path, monkeypatch):
    import sqlite3 as _sqlite3

    db_path = tmp_path / "memory.db"
    connection = _sqlite3.connect(db_path)
    try:
        connection.execute("CREATE TABLE _schema_version (version TEXT, applied_at TEXT)")
        connection.commit()
    finally:
        connection.close()
    monkeypatch.setenv(
        "OMICSCLAW_MEMORY_DB_URL", f"sqlite+aiosqlite:///{db_path}"
    )

    check = diagnostics._collect_memory_check()

    assert check.status == DIAGNOSTIC_STATUS_WARN
    assert "missing required tables" in check.summary
    detail_text = "\n".join(check.details)
    for table in ("nodes", "memories", "edges", "paths"):
        assert table in detail_text


def test_build_context_report_surfaces_plan_layer_and_budget_warning(tmp_path, monkeypatch):
    monkeypatch.setenv("OMICSCLAW_CONTEXT_WARNING_TOKENS", "1")
    monkeypatch.setattr(diagnostics, "_resolve_context_budget_defaults", lambda: (2, None))
    monkeypatch.setattr(diagnostics, "should_attach_capability_context", lambda text: False)

    report = diagnostics.build_context_report(
        surface="interactive",
        messages=[
            {"role": "user", "content": "first request"},
            {"role": "assistant", "content": "first reply"},
            {"role": "user", "content": "second request"},
            {"role": "assistant", "content": "second reply"},
        ],
        session_metadata={"title": "demo"},
        workspace_dir=str(tmp_path),
        pipeline_workspace=str(tmp_path / "pipeline"),
        plan_context="## Active Plan Mode\n\n- Status: approved",
        query="Continue the current analysis",
        omicsclaw_dir="",
    )

    assert report.plan_context_present is True
    assert report.omitted_message_count > 0
    assert any(layer.name == "plan_context" for layer in report.layers)
    assert any("warning threshold" in warning for warning in report.warnings)


def test_build_usage_report_prefers_explicit_session_usage(monkeypatch):
    monkeypatch.setattr(
        diagnostics,
        "_resolve_usage_snapshot",
        lambda: {
            "model": "gpt-test",
            "provider": "openai",
            "input_price_per_1m": 1.0,
            "output_price_per_1m": 2.0,
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "api_calls": 1,
        },
    )

    report = diagnostics.build_usage_report(
        session_usage={
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "api_calls": 3,
        },
        session_seconds=65,
    )

    assert report.prompt_tokens == 100
    assert report.completion_tokens == 50
    assert report.total_tokens == 150
    assert report.api_calls == 3
    assert report.estimated_cost_usd == pytest.approx(0.0002)
    assert "Session time: 0h 1m 5s" in diagnostics.render_usage_report(report)


def test_main_doctor_command_dispatches_and_uses_exit_code(monkeypatch, capsys):
    oc = _load_omicsclaw_script()
    fake_diagnostics = ModuleType("omicsclaw.diagnostics")
    captured: dict[str, object] = {}

    def fake_build_doctor_report(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(failure_count=0)

    fake_diagnostics.build_doctor_report = fake_build_doctor_report
    fake_diagnostics.render_doctor_report = lambda report, markup=False: f"doctor markup={markup}"

    monkeypatch.setitem(sys.modules, "omicsclaw.diagnostics", fake_diagnostics)
    monkeypatch.setattr(sys, "argv", ["omicsclaw.py", "doctor", "--workspace", str(ROOT)])

    with pytest.raises(SystemExit) as excinfo:
        oc.main()

    assert excinfo.value.code == 0
    assert captured["omicsclaw_dir"] == str(oc.OMICSCLAW_DIR)
    assert captured["workspace_dir"] == str(ROOT.resolve())
    assert captured["output_dir"] == str(oc.DEFAULT_OUTPUT_ROOT)
    assert "doctor markup=False" in capsys.readouterr().out
