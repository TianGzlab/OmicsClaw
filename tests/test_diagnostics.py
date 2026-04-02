from __future__ import annotations

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


def _load_omicsclaw_script():
    spec = importlib.util.spec_from_file_location("omicsclaw_main_doctor_test", ROOT / "omicsclaw.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
