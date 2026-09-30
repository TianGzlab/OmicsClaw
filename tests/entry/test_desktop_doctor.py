"""``GET /env/doctor``'s payload and the effective model, without HTTP."""

from __future__ import annotations

import dataclasses
import os
import pathlib
from types import SimpleNamespace

import pytest

from omicsclaw.entry.desktop.doctor import DOCTOR_CHECKS, doctor_report, effective_model
from omicsclaw.entry.desktop.server import health_payload
from omicsclaw.entry.session import attach_sessions
from omicsclaw.provider.config import resolve_config
from tests.entry.test_turn_runner import Scripted, make_app  # type: ignore[import-not-found]


def app_for(tmp_path: pathlib.Path, **overrides):
    return attach_sessions(
        make_app(tmp_path, Scripted(), tools=(), **overrides), abandon_grace_s=None
    )


def configured(tmp_path: pathlib.Path, **fields):
    """An app whose configuration names *fields*; the provider is still the
    scripted one, since only the configuration is read here."""
    app = app_for(tmp_path)
    return dataclasses.replace(app, config=dataclasses.replace(app.config, **fields))


def checks(report: dict) -> dict[str, dict]:
    return {check["name"]: check for check in report["checks"]}


def test_every_check_is_reported_in_order_with_counts_that_agree(tmp_path):
    report = doctor_report(app_for(tmp_path))

    assert [check["name"] for check in report["checks"]] == list(DOCTOR_CHECKS)
    statuses = [check["status"] for check in report["checks"]]
    assert report["failure_count"] == statuses.count("fail")
    assert report["warning_count"] == statuses.count("warn")
    expected = (
        "fail" if "fail" in statuses else "warn" if "warn" in statuses else "ok"
    )
    assert report["overall_status"] == expected
    assert report["generated_at"].endswith("Z")
    assert report["workspace_dir"] == report["omicsclaw_dir"] == str(tmp_path)


def test_no_skills_is_a_warning_that_names_the_remedy(tmp_path):
    """The M2/M3 launch mistake: a workspace with no ``skills/`` beside it."""
    skills = checks(doctor_report(app_for(tmp_path)))["skills"]
    assert skills["status"] == "warn"
    assert "OMICSCLAW_SKILLS_DIR" in skills["summary"]


def test_skills_and_skipped_skills_are_read_off_the_index(tmp_path):
    app = app_for(tmp_path)
    index = SimpleNamespace(
        skills=("a", "b"),
        skipped=(SimpleNamespace(path=pathlib.Path("x/SKILL.md"), reason="no_frontmatter", detail=""),),
        root=pathlib.Path("/skills"),
    )
    report = checks(doctor_report(dataclasses.replace(app, skills=index)))
    assert (report["skills"]["status"], report["skills"]["summary"]) == ("ok", "2 skills indexed.")
    assert report["skipped_skills"]["status"] == "warn"
    assert report["skipped_skills"]["details"] == ["x/SKILL.md: no_frontmatter"]


def test_a_failed_mcp_server_is_a_warning_and_a_connected_one_is_not(tmp_path):
    def status(name: str, state: str, error: str = ""):
        return SimpleNamespace(name=name, state=SimpleNamespace(value=state), tools=(), error=error)

    app = app_for(tmp_path)
    manager = SimpleNamespace(
        statuses=lambda: (status("good", "connected"), status("bad", "failed", "refused " * 100))
    )
    mcp = checks(doctor_report(dataclasses.replace(app, mcp=manager)))["mcp"]
    assert mcp["status"] == "warn"
    assert mcp["details"][0] == "good: connected, 0 tool(s)"
    assert mcp["details"][1].startswith("bad: failed (refused")
    assert len(mcp["details"][1]) <= 300

    none = checks(doctor_report(dataclasses.replace(app, mcp=None)))["mcp"]
    assert none["status"] == "info"


def test_deliberately_off_is_information_not_a_warning(tmp_path):
    app = dataclasses.replace(app_for(tmp_path), sandbox=None, memory=None)
    report = checks(doctor_report(app))
    assert report["sandbox"]["status"] == "info"
    assert report["memory"]["status"] == "info"
    assert report["permission"]["status"] == "ok"
    assert report["permission"]["summary"] == "Permission mode default."


def test_a_degraded_sandbox_is_a_warning(tmp_path):
    binding = SimpleNamespace(active=False, degraded=True, unavailable="docker is not running")
    report = checks(doctor_report(dataclasses.replace(app_for(tmp_path), sandbox=binding)))
    assert report["sandbox"]["status"] == "warn"
    assert report["sandbox"]["details"] == ["docker is not running"]


@pytest.mark.skipif(os.geteuid() == 0, reason="root can write anywhere")
def test_an_unwritable_workspace_is_a_failure(tmp_path):
    app = app_for(tmp_path)
    tmp_path.chmod(0o500)
    try:
        report = doctor_report(app)
    finally:
        tmp_path.chmod(0o700)
    assert checks(report)["workspace"]["status"] == "fail"
    assert report["overall_status"] == "fail"


def test_a_missing_workspace_is_a_failure(tmp_path):
    app = app_for(tmp_path)
    moved = dataclasses.replace(app, config=dataclasses.replace(app.config, workspace=tmp_path / "gone"))
    assert checks(doctor_report(moved))["workspace"]["status"] == "fail"


def test_the_effective_model_is_the_resolved_one_not_the_configured_one(tmp_path, monkeypatch):
    """A deployment that names only its provider runs the preset's model;
    ``/health`` and the doctor report that model, not ``""``."""
    for name in ("OMICSCLAW_MODEL", "LLM_MODEL", "SPATIALCLAW_MODEL", "DEEPSEEK_MODEL"):
        monkeypatch.delenv(name, raising=False)
    app = configured(tmp_path, provider="deepseek")
    expected = resolve_config("deepseek", "").model

    assert app.config.model == ""
    assert expected
    assert effective_model(app) == expected
    assert health_payload(app)["model"] == expected
    assert expected in checks(doctor_report(app))["provider"]["summary"]


def test_a_named_model_is_reported_as_the_provider_layer_normalises_it(tmp_path):
    """``deepseek-reasoner`` is a retired alias the provider layer rewrites;
    what is reported is what is called."""
    app = configured(tmp_path, provider="deepseek", model="deepseek-reasoner")
    assert effective_model(app) == resolve_config("deepseek", "deepseek-reasoner").model
