from __future__ import annotations

import asyncio
import importlib
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import threading
import time
import pytest


def _install_fake_skills(
    monkeypatch,
    skills: dict,
    domains: dict | None = None,
    *,
    skills_root: Path | None = None,
) -> None:
    """Atomically publish a deeply frozen fake Registry for one test.

    The runner no longer caches ``SKILLS`` / ``DOMAINS`` at module-import time
    (so that ``registry.reload()`` actually takes effect for downstream
    callers). Published Registry fields are now immutable, so fixtures assemble
    a private Registry, freeze it through ``snapshot()``, then swap the one
    state pointer exactly like a production reload. Monkeypatch restores that
    pointer directly at teardown without using the denied public setters.
    """
    from omicsclaw.skill.registry import SKILLS_DIR, OmicsRegistry, registry

    script_parents = [
        Path(info["script"]).expanduser().resolve().parent
        for info in skills.values()
        if info.get("script")
    ]
    resolved_skills_root = (
        skills_root.resolve()
        if skills_root is not None
        else (
            Path(os.path.commonpath([str(path) for path in script_parents])).parent
            if script_parents
            else SKILLS_DIR.resolve()
        )
    )
    fake = OmicsRegistry()
    fake.skills = skills
    fake.canonical_aliases = list(skills)
    fake.domains = domains if domains is not None else {"demo": {"name": "Demo"}}
    fake._loaded_dir = resolved_skills_root
    fake._loaded = True
    frozen_state = fake.snapshot()._state
    monkeypatch.setattr(registry, "_state", frozen_state)
    runner = importlib.import_module("omicsclaw.skill.runner")
    monkeypatch.setattr(runner, "ensure_registry_loaded", lambda: registry)


def test_skill_runner_module_exposes_run_skill_contract():
    module = importlib.import_module("omicsclaw.skill.runner")

    assert hasattr(module, "run_skill")
    signature = inspect.signature(module.run_skill)
    assert list(signature.parameters) == [
        "skill_name",
        "input_path",
        "input_paths",
        "output_dir",
        "demo",
        "session_path",
        "extra_args",
        "project_id",  # ADR 0035: project-scoped output
        "project_name",
        "stdout_callback",
        "stderr_callback",
        "cancel_event",
        "status_callback",  # adaptive-env provisioning progress sink
    ]


def test_run_skill_returns_skill_run_result_natively():
    """OMI-12 P1.6: ``run_skill`` returns the typed model — not a dict.

    The unknown-skill error path is the cheapest exit; pin the native
    return type here so a future "convenience dict-wrap" cannot silently
    regress the contract and reintroduce the dict↔model round-trip.
    """
    from omicsclaw.skill.result import SkillRunResult
    from omicsclaw.skill.runner import run_skill

    result = run_skill("__definitely_not_a_real_skill__", demo=True)
    assert isinstance(result, SkillRunResult)
    assert result.success is False
    assert "Unknown skill" in result.stderr

    # The legacy dict shape is still reachable for callers that need it.
    legacy = result.to_legacy_dict()
    assert isinstance(legacy, dict)
    assert legacy["success"] is False
    assert "Unknown skill" in legacy["stderr"]


def test_shared_runner_rejects_manifest_changed_after_registry_load_before_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from omicsclaw.skill.evolution import SkillHealthLedger
    from omicsclaw.skill.registry import OmicsRegistry

    skill_runner = importlib.import_module("omicsclaw.skill.runner")
    skills_root = tmp_path / "skills"
    skill_dir = skills_root / "spatial" / "runner-bound"
    skill_dir.mkdir(parents=True)
    script = skill_dir / "runner_bound.py"
    script.write_text("raise AssertionError('must not execute')\n", encoding="utf-8")
    manifest = skill_dir / "skill.yaml"

    def write_manifest(version: str) -> None:
        manifest.write_text(
            "\n".join(
                [
                    "schema_version: 2",
                    "id: runner-bound",
                    "name: runner-bound",
                    "domain: spatial",
                    f"version: {version}",
                    "summary:",
                    "  load_when: exercising frozen runner authority",
                    "runtime:",
                    "  entry: runner_bound.py",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    write_manifest("1.0.0")
    registry = OmicsRegistry()
    registry.load_all(skills_root)
    write_manifest("2.0.0")
    output_root = tmp_path / "must-not-exist"
    monkeypatch.setenv(
        "OMICSCLAW_SKILL_HEALTH_LEDGER",
        str(tmp_path / "health.jsonl"),
    )
    monkeypatch.setattr(skill_runner, "ensure_registry_loaded", lambda: registry)
    monkeypatch.setattr(
        skill_runner,
        "drive_subprocess",
        lambda *_args, **_kwargs: pytest.fail("runner must not spawn"),
    )

    result = skill_runner.run_skill(
        "runner-bound",
        demo=True,
        output_dir=str(output_root),
    )

    assert result.success is False
    assert "reload" in result.stderr
    assert not output_root.exists()
    assert result.audit_identity is not None
    assert result.audit_identity.skill_hash == "unknown"
    assert result.audit_identity.source_hash == "unknown"
    event = SkillHealthLedger(tmp_path / "health.jsonl").events()[-1]
    assert event.skill_hash == "unknown"
    assert event.source_hash == "unknown"


def test_shared_runner_keeps_loaded_legacy_skill_without_manifest_compatible(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from omicsclaw.skill.registry import OmicsRegistry

    skill_runner = importlib.import_module("omicsclaw.skill.runner")
    skills_root = tmp_path / "skills"
    skill_dir = skills_root / "spatial" / "legacy-bound"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: legacy-bound\ndescription: Legacy test skill\n---\n",
        encoding="utf-8",
    )
    (skill_dir / "parameters.yaml").write_text(
        "script: legacy_bound.py\n",
        encoding="utf-8",
    )
    (skill_dir / "legacy_bound.py").write_text("pass\n", encoding="utf-8")
    registry = OmicsRegistry()
    registry.load_all(skills_root)
    assert registry.snapshot().skill_manifest_revisions["legacy-bound"] == "unknown"
    calls: list[list[str]] = []

    def fake_drive(cmd, **_kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="legacy invoked")

    monkeypatch.setenv(
        "OMICSCLAW_SKILL_HEALTH_LEDGER",
        str(tmp_path / "legacy-health.jsonl"),
    )
    monkeypatch.setattr(skill_runner, "ensure_registry_loaded", lambda: registry)
    monkeypatch.setattr(skill_runner, "drive_subprocess", fake_drive)

    result = skill_runner.run_skill(
        "legacy-bound",
        demo=True,
        output_dir=str(tmp_path / "legacy-out"),
    )

    assert calls
    assert "reload" not in result.stderr


def test_unknown_skill_identifier_is_not_copied_into_health_ledger(
    tmp_path,
    monkeypatch,
):
    from omicsclaw.skill.evolution import SkillHealthLedger
    from omicsclaw.skill.runner import run_skill

    ledger_path = tmp_path / "unknown-skill-events.jsonl"
    monkeypatch.setenv("OMICSCLAW_SKILL_HEALTH_LEDGER", str(ledger_path))
    supplied = "/home/alice/patient_A.h5ad token=super-secret"

    result = run_skill(supplied, demo=True)
    serialized = ledger_path.read_text(encoding="utf-8")
    events = SkillHealthLedger(ledger_path).events()

    assert result.success is False
    assert len(events) == 1
    assert events[0].skill_id.startswith("unresolved-")
    assert "/home/alice" not in serialized
    assert "super-secret" not in serialized


def test_shared_runner_blocks_deprecated_skill_before_output_or_process(
    tmp_path,
    monkeypatch,
):
    skill_runner = importlib.import_module("omicsclaw.skill.runner")
    fake_script = tmp_path / "deprecated_skill.py"
    fake_script.write_text(
        "raise AssertionError('must not execute')\n", encoding="utf-8"
    )
    _install_fake_skills(
        monkeypatch,
        {
            "deprecated-skill": {
                "alias": "deprecated-skill",
                "script": fake_script,
                "domain": "demo",
                "demo_args": ["--demo"],
                "allowed_extra_flags": set(),
                "description": "Deprecated execution contract test",
                "input_contract": {},
                "output_contract": {},
                "lifecycle_status": "deprecated",
                "superseded_by": "replacement-skill",
            },
            "replacement-skill": {
                "alias": "replacement-skill",
                "script": fake_script,
                "domain": "demo",
                "demo_args": ["--demo"],
                "allowed_extra_flags": set(),
                "description": "Replacement execution contract test",
                "input_contract": {},
                "output_contract": {},
                "lifecycle_status": "stable",
                "validation_level": "demo-validated",
            },
        },
    )
    monkeypatch.setattr(
        skill_runner,
        "drive_subprocess",
        lambda *_args, **_kwargs: pytest.fail("deprecated skill must not spawn"),
    )

    result = skill_runner.run_skill(
        "deprecated-skill",
        demo=True,
        output_dir=str(tmp_path / "must-not-exist"),
    )

    assert result.success is False
    assert "deprecated" in result.stderr
    assert "replacement-skill" in result.stderr
    assert not (tmp_path / "must-not-exist").exists()


def test_zero_exit_with_invalid_declared_output_is_a_contract_failure(
    tmp_path,
    monkeypatch,
):
    """A successful process is not a successful Skill Run until its declared
    result envelope passes the shared execution-contract Module."""

    skill_runner = importlib.import_module("omicsclaw.skill.runner")
    fake_script = tmp_path / "contract_skill.py"
    fake_script.write_text("# subprocess is intercepted\n", encoding="utf-8")
    output_dir = tmp_path / "out"
    _install_fake_skills(
        monkeypatch,
        {
            "contract-skill": {
                "script": fake_script,
                "domain": "demo",
                "demo_args": ["--demo"],
                "allowed_extra_flags": set(),
                "description": "Execution contract test",
                "input_contract": {},
                "output_contract": {"files": ["result.json"]},
            }
        },
    )

    def _fake_process(cmd, *, out_dir, **_kwargs):
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "result.json").write_text(
            json.dumps({"summary": {}, "data": {}}),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(cmd, 0, "done", "")

    monkeypatch.setattr(skill_runner, "drive_subprocess", _fake_process)
    monkeypatch.setattr(
        skill_runner,
        "finalize_output_directory",
        lambda *_args, **_kwargs: pytest.fail(
            "successful output finalizer must not run after contract failure"
        ),
    )
    events = []
    evidence_kinds = []

    def _capture_event(result, **kwargs):
        events.append(result)
        evidence_kinds.append(kwargs.get("evidence_kind"))

    monkeypatch.setattr(
        skill_runner,
        "_record_skill_run_event",
        _capture_event,
    )

    result = skill_runner.run_skill(
        "contract-skill",
        demo=True,
        output_dir=str(output_dir),
    )

    assert result.success is False
    assert result.exit_code == 1
    assert result.error_kind == "contract_failure"
    assert result.output_dir == str(output_dir)
    assert "result_envelope_invalid" in result.stderr
    assert result.readme_path == ""
    assert result.replay_path == ""
    assert events == [result]
    assert evidence_kinds == ["demo"]


def test_claim_alias_anndata_never_records_earned_demo_success(
    tmp_path,
    monkeypatch,
):
    """A zero-exit demo with forged AnnData remains failed audit evidence."""

    from omicsclaw.common.output_claim import OUTPUT_CLAIM_FILENAME
    from omicsclaw.skill.evolution import SkillHealthLedger

    skill_runner = importlib.import_module("omicsclaw.skill.runner")
    fake_script = tmp_path / "anndata_contract_skill.py"
    fake_script.write_text("# subprocess is intercepted\n", encoding="utf-8")
    output_dir = tmp_path / "out"
    ledger_path = tmp_path / "audit" / "skill-runs.jsonl"
    monkeypatch.setenv("OMICSCLAW_SKILL_HEALTH_LEDGER", str(ledger_path))
    _install_fake_skills(
        monkeypatch,
        {
            "anndata-contract-skill": {
                "alias": "anndata-contract-skill",
                "version": "1.0.0",
                "script": fake_script,
                "domain": "demo",
                "demo_args": ["--demo"],
                "allowed_extra_flags": set(),
                "description": "AnnData execution contract test",
                "input_contract": {},
                "saves_h5ad": True,
                "output_contract": {
                    "files": ["result.json", "processed.h5ad"],
                    "anndata": {"saves_h5ad": True},
                },
            }
        },
    )

    def _fake_process(cmd, *, out_dir, **_kwargs):
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "result.json").write_text(
            json.dumps(
                {
                    "skill": "anndata-contract-skill",
                    "version": "1.0.0",
                    "completed_at": "2026-07-16T00:00:00+00:00",
                    "input_checksum": "",
                    "summary": {"method": "default"},
                    "data": {},
                }
            ),
            encoding="utf-8",
        )
        (out_dir / "processed.h5ad").hardlink_to(out_dir / OUTPUT_CLAIM_FILENAME)
        return subprocess.CompletedProcess(cmd, 0, "done", "")

    monkeypatch.setattr(skill_runner, "drive_subprocess", _fake_process)
    monkeypatch.setattr(
        skill_runner,
        "finalize_output_directory",
        lambda *_args, **_kwargs: pytest.fail(
            "successful output finalizer must not run after AnnData contract failure"
        ),
    )

    result = skill_runner.run_skill(
        "anndata-contract-skill",
        demo=True,
        output_dir=str(output_dir),
    )

    assert result.success is False
    assert result.error_kind == "contract_failure"
    assert "anndata_missing" in result.stderr
    [event] = SkillHealthLedger(ledger_path).events()
    assert event.outcome == "failed"
    assert event.evidence_kind == "demo"
    assert event.error_kind == "contract_failure"
    assert not (event.outcome == "succeeded" and event.evidence_kind == "demo")


def test_anndata_validator_strips_all_backend_roots_and_preserves_runtime_paths(
    tmp_path,
    monkeypatch,
    request,
):
    """AutoAgent's duplicate Backend roots must not shadow runtime AnnData."""

    skill_runner = importlib.import_module("omicsclaw.skill.runner")
    fake_script = tmp_path / "runtime_skill.py"
    fake_script.write_text("# subprocess is intercepted\n", encoding="utf-8")
    output_dir = tmp_path / "out"
    backend_root = tmp_path / "backend-root"
    backend_root.mkdir()
    backend_import_trace = tmp_path / "backend-anndata-import.json"
    runtime_import_trace = tmp_path / "runtime-anndata-import.json"
    runtime_modules = tmp_path / "runtime-modules"
    runtime_modules.mkdir()
    # Keep the hostile PYTHONPATH entry outside the fake Skill source tree so
    # execution-source hashing reaches the verifier sanitizer under test.
    pythonpath_loop = tmp_path.parent / f"{tmp_path.name}-pythonpath-loop"
    pythonpath_loop.symlink_to(pythonpath_loop)
    request.addfinalizer(lambda: pythonpath_loop.unlink(missing_ok=True))
    (backend_root / "anndata.py").write_text(
        textwrap.dedent(
            """\
            import json
            import os
            import sys
            from pathlib import Path

            Path(os.environ["BACKEND_ANNDATA_IMPORT_TRACE"]).write_text(
                json.dumps(sys.path),
                encoding="utf-8",
            )

            class _File:
                def close(self):
                    pass

            class _Backed:
                file = _File()

            def read_h5ad(path, backed=None):
                return _Backed()
            """
        ),
        encoding="utf-8",
    )
    (runtime_modules / "anndata.py").write_text(
        textwrap.dedent(
            """\
            import json
            import os
            import sys
            from pathlib import Path

            Path(os.environ["RUNTIME_ANNDATA_IMPORT_TRACE"]).write_text(
                json.dumps({
                    "sys_path": sys.path,
                    "marker": os.environ.get("RUNTIME_ENV_MARKER"),
                }),
                encoding="utf-8",
            )

            def read_h5ad(path, backed=None):
                raise ValueError("invalid runtime-owned AnnData")
            """
        ),
        encoding="utf-8",
    )
    _install_fake_skills(
        monkeypatch,
        {
            "runtime-skill": {
                "alias": "runtime-skill",
                "version": "1.0.0",
                "script": fake_script,
                "domain": "demo",
                "demo_args": ["--demo"],
                "allowed_extra_flags": set(),
                "description": "AnnData runtime isolation test",
                "input_contract": {},
                "saves_h5ad": True,
                "output_contract": {
                    "files": ["result.json", "processed.h5ad"],
                    "anndata": {"saves_h5ad": True},
                },
            }
        },
    )
    monkeypatch.setattr(skill_runner, "OMICSCLAW_DIR", backend_root)
    monkeypatch.chdir(backend_root)
    monkeypatch.setenv(
        "PYTHONPATH",
        os.pathsep.join(
            [
                str(backend_root),
                ".",
                str(pythonpath_loop),
                str(backend_root),
                "",
                str(runtime_modules),
            ]
        ),
    )
    monkeypatch.setenv("BACKEND_ANNDATA_IMPORT_TRACE", str(backend_import_trace))
    monkeypatch.setenv("RUNTIME_ANNDATA_IMPORT_TRACE", str(runtime_import_trace))
    monkeypatch.setenv("RUNTIME_ENV_MARKER", "preserved")

    def _fake_process(cmd, *, out_dir, **_kwargs):
        (out_dir / "result.json").write_text(
            json.dumps(
                {
                    "skill": "runtime-skill",
                    "version": "1.0.0",
                    "completed_at": "2026-07-17T00:00:00+00:00",
                    "input_checksum": "",
                    "summary": {"method": "default"},
                    "data": {},
                }
            ),
            encoding="utf-8",
        )
        (out_dir / "processed.h5ad").write_text(
            "not an AnnData container",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(cmd, 0, "done", "")

    monkeypatch.setattr(skill_runner, "drive_subprocess", _fake_process)

    result = skill_runner.run_skill(
        "runtime-skill",
        demo=True,
        output_dir=str(output_dir),
    )

    assert result.success is False
    assert result.error_kind == "contract_failure"
    assert "anndata_invalid" in result.stderr
    assert not backend_import_trace.exists()
    observed_runtime = json.loads(runtime_import_trace.read_text(encoding="utf-8"))
    assert observed_runtime["marker"] == "preserved"
    assert str(runtime_modules) in observed_runtime["sys_path"]
    assert str(backend_root) not in observed_runtime["sys_path"]


def test_anndata_validator_resolves_relative_pythonpath_from_skill_cwd(
    tmp_path,
    monkeypatch,
):
    """The verifier must import from the same relative-path graph as the Skill.

    ``python -P`` removes the implicit current directory, but an explicit
    relative ``PYTHONPATH`` entry is still interpreted against ``cwd``. The
    producer runs from the Skill directory, so validating from the Backend
    process cwd could otherwise load a different ``anndata`` implementation.
    """

    skill_runner = importlib.import_module("omicsclaw.skill.runner")
    backend_cwd = tmp_path / "backend-cwd"
    skill_dir = tmp_path / "skill-dir"
    backend_modules = backend_cwd / "mods"
    skill_modules = skill_dir / "mods"
    backend_modules.mkdir(parents=True)
    skill_modules.mkdir(parents=True)
    script = skill_dir / "runtime_skill.py"
    script.write_text("# subprocess is intercepted\n", encoding="utf-8")

    (backend_modules / "anndata.py").write_text(
        textwrap.dedent(
            """\
            class _File:
                def close(self):
                    pass

            class _Backed:
                file = _File()

            def read_h5ad(path, backed=None):
                return _Backed()
            """
        ),
        encoding="utf-8",
    )
    (skill_modules / "anndata.py").write_text(
        "def read_h5ad(path, backed=None):\n"
        "    raise ValueError('skill runtime rejects invalid container')\n",
        encoding="utf-8",
    )
    _install_fake_skills(
        monkeypatch,
        {
            "relative-runtime-skill": {
                "alias": "relative-runtime-skill",
                "version": "1.0.0",
                "script": script,
                "domain": "demo",
                "demo_args": ["--demo"],
                "allowed_extra_flags": set(),
                "description": "relative runtime authority test",
                "input_contract": {},
                "saves_h5ad": True,
                "output_contract": {
                    "files": ["result.json", "processed.h5ad"],
                    "anndata": {"saves_h5ad": True},
                },
            }
        },
    )
    monkeypatch.chdir(backend_cwd)
    monkeypatch.setenv("PYTHONPATH", "mods")
    observed_cwd: list[Path] = []

    def _fake_process(cmd, *, cwd, out_dir, **_kwargs):
        observed_cwd.append(Path(cwd))
        (out_dir / "result.json").write_text(
            json.dumps(
                {
                    "skill": "relative-runtime-skill",
                    "version": "1.0.0",
                    "completed_at": "2026-07-17T00:00:00+00:00",
                    "input_checksum": "",
                    "summary": {"method": "default"},
                    "data": {},
                }
            ),
            encoding="utf-8",
        )
        (out_dir / "processed.h5ad").write_text(
            "not an AnnData container",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(skill_runner, "drive_subprocess", _fake_process)

    result = skill_runner.run_skill(
        "relative-runtime-skill",
        demo=True,
        output_dir=str(tmp_path / "out"),
    )

    assert observed_cwd == [skill_dir]
    assert result.success is False
    assert result.error_kind == "contract_failure"
    assert "anndata_invalid" in result.stderr


def test_run_ledger_keeps_pre_spawn_manifest_and_execution_source_identity(
    tmp_path,
    monkeypatch,
):
    from omicsclaw.skill.evolution import (
        SkillHealthLedger,
        _sha256,
        compute_execution_source_hash,
    )

    skill_runner = importlib.import_module("omicsclaw.skill.runner")
    skills_root = tmp_path / "skills"
    domain_dir = skills_root / "singlecell"
    subdomain_dir = domain_dir / "scrna"
    skill_dir = subdomain_dir / "identity-skill"
    lib_dir = domain_dir / "_lib"
    subdomain_lib_dir = subdomain_dir / "_lib"
    skill_dir.mkdir(parents=True)
    lib_dir.mkdir(parents=True)
    subdomain_lib_dir.mkdir(parents=True)
    script = skill_dir / "entry.py"
    helper = skill_dir / "helper.py"
    shared = lib_dir / "shared.py"
    subdomain_shared = subdomain_lib_dir / "shared.py"
    manifest = skill_dir / "skill.yaml"
    script.write_text("print('before')\n", encoding="utf-8")
    helper.write_text("HELPER = 'before'\n", encoding="utf-8")
    shared.write_text("SHARED = 'before'\n", encoding="utf-8")
    subdomain_shared.write_text("SUBDOMAIN_SHARED = 'before'\n", encoding="utf-8")
    manifest.write_text("id: identity-skill\nversion: 1.0.0\n", encoding="utf-8")
    expected_manifest_hash = _sha256(manifest.read_bytes())
    expected_source_hash = compute_execution_source_hash(
        script,
        skills_root=skills_root,
    )
    ledger_path = tmp_path / "audit" / "skill-runs.jsonl"
    monkeypatch.setenv("OMICSCLAW_SKILL_HEALTH_LEDGER", str(ledger_path))
    _install_fake_skills(
        monkeypatch,
        {
            "identity-skill": {
                "script": script,
                "directory_name": "identity-skill",
                "version": "1.0.0",
                "domain": "singlecell",
                "demo_args": ["--demo"],
                "allowed_extra_flags": set(),
                "input_contract": {},
                "output_contract": {},
            }
        },
        skills_root=skills_root,
    )

    def _mutate_after_prepare(cmd, **_kwargs):
        manifest.write_text("id: identity-skill\nversion: 2.0.0\n", encoding="utf-8")
        script.write_text("print('after')\n", encoding="utf-8")
        helper.write_text("HELPER = 'after'\n", encoding="utf-8")
        shared.write_text("SHARED = 'after'\n", encoding="utf-8")
        subdomain_shared.write_text(
            "SUBDOMAIN_SHARED = 'after'\n",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(cmd, 1, "", "execution failed")

    monkeypatch.setattr(skill_runner, "drive_subprocess", _mutate_after_prepare)

    result = skill_runner.run_skill(
        "identity-skill",
        demo=True,
        output_dir=str(tmp_path / "out"),
    )

    assert result.success is False
    assert result.error_kind == "contract_validator_failed"
    assert result.stderr == (
        "Skill execution provenance changed while the subprocess was running."
    )
    assert "execution failed" not in result.stderr
    assert result.audit_identity is not None
    assert result.audit_identity.skill_hash == expected_manifest_hash
    assert result.audit_identity.source_hash == expected_source_hash
    [event] = SkillHealthLedger(ledger_path).events()
    assert event.skill_hash == expected_manifest_hash
    assert event.source_hash == expected_source_hash


def test_sync_driver_exception_records_the_pre_spawn_execution_identity(
    tmp_path,
    monkeypatch,
):
    from omicsclaw.skill.evolution import (
        SkillHealthLedger,
        _sha256,
        compute_execution_source_hash,
    )

    skill_runner = importlib.import_module("omicsclaw.skill.runner")
    skills_root = tmp_path / "skills"
    skill_dir = skills_root / "singlecell" / "driver-error"
    skill_dir.mkdir(parents=True)
    script = skill_dir / "entry.py"
    manifest = skill_dir / "skill.yaml"
    script.write_text("print('before')\n", encoding="utf-8")
    manifest.write_text("id: driver-error\nversion: 1.0.0\n", encoding="utf-8")
    expected_manifest_hash = _sha256(manifest.read_bytes())
    expected_source_hash = compute_execution_source_hash(
        script,
        skills_root=skills_root,
    )
    ledger_path = tmp_path / "audit" / "driver-error.jsonl"
    monkeypatch.setenv("OMICSCLAW_SKILL_HEALTH_LEDGER", str(ledger_path))
    _install_fake_skills(
        monkeypatch,
        {
            "driver-error": {
                "script": script,
                "version": "1.0.0",
                "domain": "singlecell",
                "demo_args": ["--demo"],
                "allowed_extra_flags": set(),
                "input_contract": {},
                "output_contract": {},
            }
        },
        skills_root=skills_root,
    )

    def _crash_after_prepare(*_args, **_kwargs):
        manifest.write_text("id: driver-error\nversion: 2.0.0\n", encoding="utf-8")
        script.write_text("print('after')\n", encoding="utf-8")
        raise RuntimeError("driver crashed with patient-secret")

    monkeypatch.setattr(skill_runner, "drive_subprocess", _crash_after_prepare)

    result = skill_runner.run_skill(
        "driver-error",
        demo=True,
        output_dir=str(tmp_path / "out"),
    )

    assert result.success is False
    assert result.error_kind == "contract_validator_failed"
    assert result.stderr == (
        "Skill execution provenance changed while the subprocess was running."
    )
    assert "patient-secret" not in result.stderr
    assert result.audit_identity is not None
    assert result.audit_identity.skill_id == "driver-error"
    assert result.audit_identity.skill_version == "1.0.0"
    assert result.audit_identity.skill_hash == expected_manifest_hash
    assert result.audit_identity.source_hash == expected_source_hash
    [event] = SkillHealthLedger(ledger_path).events()
    assert event.skill_hash == expected_manifest_hash
    assert event.source_hash == expected_source_hash
    assert event.evidence_kind == "demo"
    assert event.error_kind == "contract_validator_failed"


@pytest.mark.asyncio
async def test_async_driver_exception_records_the_pre_spawn_execution_identity(
    tmp_path,
    monkeypatch,
):
    from omicsclaw.skill.evolution import (
        SkillHealthLedger,
        _sha256,
        compute_execution_source_hash,
    )

    skill_runner = importlib.import_module("omicsclaw.skill.runner")
    skills_root = tmp_path / "skills"
    skill_dir = skills_root / "singlecell" / "async-driver-error"
    skill_dir.mkdir(parents=True)
    script = skill_dir / "entry.py"
    manifest = skill_dir / "skill.yaml"
    script.write_text("print('before')\n", encoding="utf-8")
    manifest.write_text(
        "id: async-driver-error\nversion: 1.0.0\n",
        encoding="utf-8",
    )
    expected_manifest_hash = _sha256(manifest.read_bytes())
    expected_source_hash = compute_execution_source_hash(
        script,
        skills_root=skills_root,
    )
    ledger_path = tmp_path / "audit" / "async-driver-error.jsonl"
    monkeypatch.setenv("OMICSCLAW_SKILL_HEALTH_LEDGER", str(ledger_path))
    _install_fake_skills(
        monkeypatch,
        {
            "async-driver-error": {
                "script": script,
                "version": "1.0.0",
                "domain": "singlecell",
                "demo_args": ["--demo"],
                "allowed_extra_flags": set(),
                "input_contract": {},
                "output_contract": {},
            }
        },
        skills_root=skills_root,
    )

    async def _crash_after_prepare(*_args, **_kwargs):
        manifest.write_text(
            "id: async-driver-error\nversion: 2.0.0\n",
            encoding="utf-8",
        )
        script.write_text("print('after')\n", encoding="utf-8")
        raise RuntimeError("async driver crashed with patient-secret")

    monkeypatch.setattr(skill_runner, "adrive_subprocess", _crash_after_prepare)

    result = await skill_runner.arun_skill(
        "async-driver-error",
        demo=True,
        output_dir=str(tmp_path / "out"),
    )

    assert result.success is False
    assert result.error_kind == "contract_validator_failed"
    assert result.stderr == (
        "Skill execution provenance changed while the subprocess was running."
    )
    assert "patient-secret" not in result.stderr
    assert result.audit_identity is not None
    assert result.audit_identity.skill_hash == expected_manifest_hash
    assert result.audit_identity.source_hash == expected_source_hash
    [event] = SkillHealthLedger(ledger_path).events()
    assert event.skill_hash == expected_manifest_hash
    assert event.source_hash == expected_source_hash
    assert event.evidence_kind == "demo"
    assert event.error_kind == "contract_validator_failed"


@pytest.mark.asyncio
async def test_arun_skill_accepts_one_internal_frozen_snapshot_without_recapture(
    tmp_path,
    monkeypatch,
):
    skill_runner = importlib.import_module("omicsclaw.skill.runner")
    from omicsclaw.skill.registry import registry

    skills_root = tmp_path / "skills"
    skill_dir = skills_root / "demo" / "frozen-async"
    skill_dir.mkdir(parents=True)
    script = skill_dir / "entry.py"
    script.write_text("print('ok')\n", encoding="utf-8")
    (skill_dir / "skill.yaml").write_text(
        "id: frozen-async\nversion: 1.0.0\n",
        encoding="utf-8",
    )
    _install_fake_skills(
        monkeypatch,
        {
            "frozen-async": {
                "alias": "frozen-async",
                "script": script,
                "directory_name": "frozen-async",
                "version": "1.0.0",
                "domain": "demo",
                "demo_args": ["--demo"],
                "allowed_extra_flags": set(),
                "input_contract": {},
                "output_contract": {},
            }
        },
        skills_root=skills_root,
    )
    snapshot = registry.snapshot()
    expected_revision = snapshot.skill_revision("frozen-async")
    monkeypatch.setattr(
        skill_runner,
        "ensure_registry_loaded",
        lambda: pytest.fail("internal snapshot seam must not recapture Registry"),
    )

    async def completed(cmd, **_kwargs):
        return subprocess.CompletedProcess(cmd, 1, "", "expected failure")

    monkeypatch.setattr(skill_runner, "adrive_subprocess", completed)

    result = await skill_runner.arun_skill(
        "frozen-async",
        demo=True,
        output_dir=str(tmp_path / "out"),
        _registry_snapshot=snapshot,
        _expected_skill_revision=expected_revision,
    )

    assert result.success is False
    assert result.audit_identity is not None
    assert result.audit_identity.skill_hash == expected_revision["manifest_hash"]
    assert result.audit_identity.source_hash == expected_revision["source_hash"]


def test_bound_sync_run_rejects_source_drift_before_output_or_runtime_resolution(
    tmp_path,
    monkeypatch,
):
    skill_runner = importlib.import_module("omicsclaw.skill.runner")
    from omicsclaw.skill.registry import registry

    skills_root = tmp_path / "skills"
    skill_dir = skills_root / "demo" / "bound-sync"
    skill_dir.mkdir(parents=True)
    script = skill_dir / "entry.py"
    script.write_text("print('v1')\n", encoding="utf-8")
    (skill_dir / "skill.yaml").write_text(
        "id: bound-sync\nversion: 1.0.0\n",
        encoding="utf-8",
    )
    _install_fake_skills(
        monkeypatch,
        {
            "bound-sync": {
                "alias": "bound-sync",
                "script": script,
                "directory_name": "bound-sync",
                "version": "1.0.0",
                "domain": "demo",
                "demo_args": ["--demo"],
                "allowed_extra_flags": set(),
                "input_contract": {},
                "output_contract": {},
            }
        },
        skills_root=skills_root,
    )
    snapshot = registry.snapshot()
    expected_revision = snapshot.skill_revision("bound-sync")
    script.write_text("print('v2')\n", encoding="utf-8")
    monkeypatch.setenv(
        "OMICSCLAW_SKILL_HEALTH_LEDGER",
        str(tmp_path / "events.jsonl"),
    )
    monkeypatch.setattr(
        skill_runner,
        "ensure_registry_loaded",
        lambda: pytest.fail("bound execution must not recapture Registry"),
    )
    runtime_or_spawn_calls: list[str] = []

    def forbidden_runtime(*_args, **_kwargs):
        runtime_or_spawn_calls.append("runtime")
        raise AssertionError("source drift reached runtime resolution")

    def forbidden_spawn(*_args, **_kwargs):
        runtime_or_spawn_calls.append("spawn")
        raise AssertionError("source drift reached subprocess execution")

    monkeypatch.setattr(skill_runner, "resolve_skill_runtime", forbidden_runtime)
    monkeypatch.setattr(skill_runner, "drive_subprocess", forbidden_spawn)
    output_dir = tmp_path / "out"

    result = skill_runner._run_skill_bound(
        "bound-sync",
        demo=True,
        output_dir=str(output_dir),
        _registry_snapshot=snapshot,
        _expected_skill_revision=expected_revision,
    )

    assert result.success is False
    assert result.error_kind == "contract_validator_failed"
    assert "bound authority" in result.stderr
    assert result.output_dir is None
    assert runtime_or_spawn_calls == []
    assert not output_dir.exists()


@pytest.mark.asyncio
async def test_async_cancellation_records_one_frozen_cancelled_event_then_reraises(
    tmp_path,
    monkeypatch,
):
    from omicsclaw.skill.evolution import SkillHealthLedger

    skill_runner = importlib.import_module("omicsclaw.skill.runner")
    skills_root = tmp_path / "skills"
    skill_dir = skills_root / "demo" / "cancel-async"
    skill_dir.mkdir(parents=True)
    script = skill_dir / "entry.py"
    script.write_text("print('running')\n", encoding="utf-8")
    (skill_dir / "skill.yaml").write_text(
        "id: cancel-async\nversion: 1.0.0\n",
        encoding="utf-8",
    )
    ledger_path = tmp_path / "cancel-events.jsonl"
    monkeypatch.setenv("OMICSCLAW_SKILL_HEALTH_LEDGER", str(ledger_path))
    _install_fake_skills(
        monkeypatch,
        {
            "cancel-async": {
                "alias": "cancel-async",
                "script": script,
                "directory_name": "cancel-async",
                "version": "1.0.0",
                "domain": "demo",
                "demo_args": ["--demo"],
                "allowed_extra_flags": set(),
                "input_contract": {},
                "output_contract": {},
            }
        },
        skills_root=skills_root,
    )

    async def cancelled(*_args, **_kwargs):
        raise asyncio.CancelledError

    monkeypatch.setattr(skill_runner, "adrive_subprocess", cancelled)

    with pytest.raises(asyncio.CancelledError):
        await skill_runner.arun_skill(
            "cancel-async",
            demo=True,
            output_dir=str(tmp_path / "out"),
        )

    [event] = SkillHealthLedger(ledger_path).events()
    assert event.skill_id == "cancel-async"
    assert event.outcome == "cancelled"
    assert event.error_kind == "cancelled"
    assert event.skill_hash.startswith("sha256:")
    assert event.source_hash.startswith("sha256:")


def test_output_contract_validator_exception_fails_closed_with_typed_error(
    tmp_path,
    monkeypatch,
):
    skill_runner = importlib.import_module("omicsclaw.skill.runner")
    fake_script = tmp_path / "validator_failure_skill.py"
    fake_script.write_text("# subprocess is intercepted\n", encoding="utf-8")
    output_dir = tmp_path / "out"
    _install_fake_skills(
        monkeypatch,
        {
            "validator-failure-skill": {
                "script": fake_script,
                "domain": "demo",
                "demo_args": ["--demo"],
                "allowed_extra_flags": set(),
                "description": "Validator failure test",
                "input_contract": {},
                "output_contract": {"files": ["result.json"]},
            }
        },
    )

    def _fake_process(cmd, *, out_dir, **_kwargs):
        out_dir.mkdir(parents=True, exist_ok=True)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(skill_runner, "drive_subprocess", _fake_process)
    monkeypatch.setattr(
        skill_runner,
        "verify_skill_run_outputs",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("secret")),
    )

    result = skill_runner.run_skill(
        "validator-failure-skill",
        demo=True,
        output_dir=str(output_dir),
    )

    assert result.success is False
    assert result.error_kind == "contract_validator_failed"
    assert result.audit_identity is not None
    assert "RuntimeError" in result.stderr
    assert "secret" not in result.stderr


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["sync", "async"])
async def test_output_finalizer_exception_is_one_typed_framework_failure(
    tmp_path,
    monkeypatch,
    mode,
):
    from omicsclaw.skill.evolution import SkillHealthLedger

    skill_runner = importlib.import_module("omicsclaw.skill.runner")
    skills_root = tmp_path / "skills"
    skill_dir = skills_root / "demo" / f"finalizer-{mode}"
    skill_dir.mkdir(parents=True)
    script = skill_dir / "entry.py"
    script.write_text("print('ok')\n", encoding="utf-8")
    (skill_dir / "skill.yaml").write_text(
        f"id: finalizer-{mode}\nversion: 1.0.0\n",
        encoding="utf-8",
    )
    ledger_path = tmp_path / f"finalizer-{mode}.jsonl"
    monkeypatch.setenv("OMICSCLAW_SKILL_HEALTH_LEDGER", str(ledger_path))
    _install_fake_skills(
        monkeypatch,
        {
            f"finalizer-{mode}": {
                "alias": f"finalizer-{mode}",
                "script": script,
                "directory_name": f"finalizer-{mode}",
                "version": "1.0.0",
                "domain": "demo",
                "demo_args": ["--demo"],
                "allowed_extra_flags": set(),
                "input_contract": {},
                "output_contract": {},
            }
        },
        skills_root=skills_root,
    )

    def completed(cmd, **_kwargs):
        return subprocess.CompletedProcess(cmd, 0, "", "")

    async def async_completed(cmd, **_kwargs):
        return subprocess.CompletedProcess(cmd, 0, "", "")

    if mode == "sync":
        monkeypatch.setattr(skill_runner, "drive_subprocess", completed)
    else:
        monkeypatch.setattr(skill_runner, "adrive_subprocess", async_completed)

    def finalizer_failure(*_args, **_kwargs):
        raise RuntimeError("secret-finalizer-detail")

    monkeypatch.setattr(
        skill_runner,
        "finalize_output_directory",
        finalizer_failure,
    )

    if mode == "sync":
        result = skill_runner.run_skill(
            f"finalizer-{mode}",
            demo=True,
            output_dir=str(tmp_path / f"out-{mode}"),
        )
    else:
        result = await skill_runner.arun_skill(
            f"finalizer-{mode}",
            demo=True,
            output_dir=str(tmp_path / f"out-{mode}"),
        )

    assert result.success is False
    assert result.error_kind == "contract_validator_failed"
    assert result.stderr == "Skill output finalization failed: RuntimeError."
    assert "secret-finalizer-detail" not in result.stderr
    assert result.audit_identity is not None
    [event] = SkillHealthLedger(ledger_path).events()
    assert event.error_kind == "contract_validator_failed"
    assert event.skill_hash == result.audit_identity.skill_hash
    assert event.source_hash == result.audit_identity.source_hash


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["sync", "async"])
async def test_project_completed_commit_is_terminal_provenance_boundary(
    tmp_path: Path,
    monkeypatch,
    mode: str,
) -> None:
    from omicsclaw.common import run_paths
    from omicsclaw.skill.evolution import (
        SkillHealthLedger,
        capture_skill_execution_identity,
    )

    skill_runner = importlib.import_module("omicsclaw.skill.runner")
    skills_root = tmp_path / "skills"
    skill_name = f"completed-boundary-{mode}"
    skill_dir = skills_root / "demo" / skill_name
    skill_dir.mkdir(parents=True)
    script = skill_dir / "entry.py"
    manifest = skill_dir / "skill.yaml"
    script.write_text("print('before')\n", encoding="utf-8")
    manifest.write_text(
        f"id: {skill_name}\nversion: 1.0.0\n",
        encoding="utf-8",
    )
    expected_manifest_hash, expected_source_hash = capture_skill_execution_identity(
        script,
        skills_root=skills_root,
        directory_name=skill_name,
    )
    output_root = tmp_path / "outputs"
    ledger_path = tmp_path / f"{skill_name}.jsonl"
    monkeypatch.setenv("OMICSCLAW_OUTPUT_DIR", str(output_root))
    monkeypatch.setenv("OMICSCLAW_SKILL_HEALTH_LEDGER", str(ledger_path))
    _install_fake_skills(
        monkeypatch,
        {
            skill_name: {
                "alias": skill_name,
                "script": script,
                "directory_name": skill_name,
                "version": "1.0.0",
                "domain": "demo",
                "demo_args": ["--demo"],
                "allowed_extra_flags": set(),
                "input_contract": {},
                "output_contract": {},
            }
        },
        skills_root=skills_root,
    )

    def completed(cmd, **_kwargs):
        return subprocess.CompletedProcess(cmd, 0, "", "")

    async def async_completed(cmd, **_kwargs):
        return subprocess.CompletedProcess(cmd, 0, "", "")

    if mode == "sync":
        monkeypatch.setattr(skill_runner, "drive_subprocess", completed)
    else:
        monkeypatch.setattr(skill_runner, "adrive_subprocess", async_completed)
    monkeypatch.setattr(
        skill_runner,
        "finalize_output_directory",
        lambda out_dir, **_kwargs: (Path(out_dir), None, "", "", None),
    )

    real_finalize_run = run_paths.finalize_run
    committed_run_dirs: list[Path] = []

    def mutate_during_completed_commit(run_dir, **kwargs):
        assert kwargs["status"] == "completed"
        script.write_text("print('after commit began')\n", encoding="utf-8")
        committed_run_dirs.append(Path(run_dir))
        return real_finalize_run(run_dir, **kwargs)

    monkeypatch.setattr(run_paths, "finalize_run", mutate_during_completed_commit)

    if mode == "sync":
        result = skill_runner.run_skill(
            skill_name,
            demo=True,
            project_id="project-completed-boundary",
            project_name="Completed Boundary",
        )
    else:
        result = await skill_runner.arun_skill(
            skill_name,
            demo=True,
            project_id="project-completed-boundary",
            project_name="Completed Boundary",
        )

    assert result.success is True
    assert len(committed_run_dirs) == 1
    rows = run_paths.read_index(committed_run_dirs[0].parent)
    assert [row["status"] for row in rows] == ["completed"]
    assert result.audit_identity is not None
    assert result.audit_identity.skill_hash == expected_manifest_hash
    assert result.audit_identity.source_hash == expected_source_hash
    [event] = SkillHealthLedger(ledger_path).events()
    assert event.outcome == "succeeded"
    assert event.skill_hash == expected_manifest_hash
    assert event.source_hash == expected_source_hash


@pytest.mark.parametrize(
    "metadata_kind",
    ["symlink", "hardlink", "missing-project-id"],
)
def test_explicit_skill_output_requires_authoritative_project_metadata(
    tmp_path: Path,
    monkeypatch,
    metadata_kind: str,
) -> None:
    """An unrelated explicit output parent cannot impersonate a Project."""
    from omicsclaw.common import run_paths

    skill_runner = importlib.import_module("omicsclaw.skill.runner")
    skills_root = tmp_path / "skills"
    skill_dir = skills_root / "demo" / "explicit-output-skill"
    skill_dir.mkdir(parents=True)
    fake_script = skill_dir / "explicit_output_skill.py"
    fake_script.write_text("# subprocess is intercepted\n", encoding="utf-8")
    explicit_parent = tmp_path / "explicit-parent"
    explicit_parent.mkdir()
    project_meta = explicit_parent / run_paths.PROJECT_META_FILENAME
    metadata_text = json.dumps(
        {"display_name": "Missing ID"}
        if metadata_kind == "missing-project-id"
        else {"project_id": "spoofed-project", "display_name": "Spoofed"}
    )
    victim = tmp_path / f"project-meta-victim-{metadata_kind}.json"
    if metadata_kind == "missing-project-id":
        project_meta.write_text(metadata_text, encoding="utf-8")
    elif metadata_kind == "symlink":
        victim.write_text(metadata_text, encoding="utf-8")
        project_meta.symlink_to(victim)
    else:
        victim.write_text(metadata_text, encoding="utf-8")
        project_meta.hardlink_to(victim)

    _install_fake_skills(
        monkeypatch,
        {
            "explicit-output-skill": {
                "alias": "explicit-output-skill",
                "script": fake_script,
                "domain": "demo",
                "demo_args": ["--demo"],
                "allowed_extra_flags": set(),
                "input_contract": {},
                "output_contract": {},
            }
        },
        skills_root=skills_root,
    )
    monkeypatch.setattr(
        skill_runner,
        "drive_subprocess",
        lambda cmd, **_kwargs: subprocess.CompletedProcess(cmd, 0, "", ""),
    )
    monkeypatch.setattr(
        skill_runner,
        "finalize_output_directory",
        lambda out_dir, **_kwargs: (Path(out_dir), None, "", "", None),
    )
    real_finalize_run = run_paths.finalize_run
    finalized: list[Path] = []

    def record_finalize(run_dir, **kwargs):
        finalized.append(Path(run_dir))
        return real_finalize_run(run_dir, **kwargs)

    monkeypatch.setattr(run_paths, "finalize_run", record_finalize)
    output_dir = explicit_parent / "run"

    result = skill_runner.run_skill(
        "explicit-output-skill",
        demo=True,
        output_dir=str(output_dir),
    )

    assert result.success is True
    assert finalized == []
    assert not (explicit_parent / run_paths.RUN_INDEX_FILENAME).exists()
    assert project_meta.read_text(encoding="utf-8") == metadata_text


@pytest.mark.asyncio
async def test_async_zero_exit_uses_the_same_output_contract_gate(
    tmp_path,
    monkeypatch,
):
    skill_runner = importlib.import_module("omicsclaw.skill.runner")
    fake_script = tmp_path / "async_contract_skill.py"
    fake_script.write_text("# subprocess is intercepted\n", encoding="utf-8")
    output_dir = tmp_path / "async-out"
    _install_fake_skills(
        monkeypatch,
        {
            "async-contract-skill": {
                "script": fake_script,
                "domain": "demo",
                "demo_args": ["--demo"],
                "allowed_extra_flags": set(),
                "description": "Async execution contract test",
                "input_contract": {},
                "output_contract": {"files": ["result.json"]},
            }
        },
    )

    async def _fake_process(cmd, *, out_dir, **_kwargs):
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "result.json").write_text("not-json", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(skill_runner, "adrive_subprocess", _fake_process)
    monkeypatch.setattr(
        skill_runner,
        "finalize_output_directory",
        lambda *_args, **_kwargs: pytest.fail(
            "successful output finalizer must not run after contract failure"
        ),
    )

    result = await skill_runner.arun_skill(
        "async-contract-skill",
        demo=True,
        output_dir=str(output_dir),
    )

    assert result.success is False
    assert result.exit_code == 1
    assert result.error_kind == "contract_failure"
    assert result.audit_identity is not None
    assert "result_json_invalid" in result.stderr


def test_root_omicsclaw_reexports_shared_run_skill():
    root = importlib.import_module("omicsclaw")
    runner = importlib.import_module("omicsclaw.skill.runner")

    assert root.run_skill is runner.run_skill


def test_explicit_skill_rejects_uninspectable_local_input_before_execution(
    tmp_path,
    monkeypatch,
):
    """RET-04b: named skills share the same fail-closed execution gate.

    A corrupt local ``.h5ad`` must be rejected before the runner creates its
    output directory or starts a subprocess.  This public runner contract is
    intentionally independent of the Analysis Router's auto-route preflight.
    """
    skill_runner = importlib.import_module("omicsclaw.skill.runner")

    fake_script = tmp_path / "must_not_run.py"
    fake_script.write_text("raise SystemExit('must not execute')\n", encoding="utf-8")
    corrupt_input = tmp_path / "corrupt.h5ad"
    corrupt_input.write_text("not an h5ad file\n", encoding="utf-8")
    output_dir = tmp_path / "out"

    _install_fake_skills(
        monkeypatch,
        {
            "guarded-skill": {
                "script": fake_script,
                "domain": "singlecell",
                "demo_args": ["--demo"],
                "allowed_extra_flags": set(),
                "description": "Explicit execution gate test skill",
                "input_contract": {
                    "modalities": ["scrna"],
                    "file_types": ["h5ad"],
                    "preconditions": {
                        "data_shape": {
                            "requires_preprocessed": True,
                            "obsm": ["X_pca"],
                        }
                    },
                },
            }
        },
    )

    subprocess_calls: list[list[str]] = []

    def _must_not_execute(cmd, **_kwargs):
        subprocess_calls.append(cmd)
        raise AssertionError("subprocess must not start after preflight failure")

    monkeypatch.setattr(skill_runner, "drive_subprocess", _must_not_execute)

    result = skill_runner.run_skill(
        "guarded-skill",
        input_path=str(corrupt_input),
        output_dir=str(output_dir),
    )

    assert result.success is False
    assert result.exit_code == -1
    assert "USER_GUIDANCE_JSON:" in result.stderr
    assert "precondition" in result.stderr.lower()
    assert "inspection" in result.stderr.lower()
    assert subprocess_calls == []
    assert not output_dir.exists()


def test_explicit_skill_gate_allows_a_verified_local_input(tmp_path, monkeypatch):
    import anndata as ad
    import numpy as np

    skill_runner = importlib.import_module("omicsclaw.skill.runner")
    fake_script = tmp_path / "verified.py"
    fake_script.write_text("raise SystemExit('driver is stubbed')\n", encoding="utf-8")
    input_path = tmp_path / "verified.h5ad"
    adata = ad.AnnData(np.ones((3, 2)))
    adata.obsm["X_pca"] = np.ones((3, 2))
    adata.uns["omicsclaw_input_contract"] = {
        "domain": "singlecell",
        "modality": "scrna",
        "preprocessed": True,
    }
    adata.write_h5ad(input_path)

    _install_fake_skills(
        monkeypatch,
        {
            "guarded-skill": {
                "script": fake_script,
                "domain": "singlecell",
                "demo_args": ["--demo"],
                "allowed_extra_flags": set(),
                "input_contract": {
                    "modalities": ["scrna"],
                    "file_types": ["h5ad"],
                    "preconditions": {
                        "data_shape": {
                            "requires_preprocessed": True,
                            "obsm": ["X_pca"],
                        }
                    },
                },
            }
        },
    )
    calls: list[list[str]] = []

    def _completed(cmd, **_kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(skill_runner, "drive_subprocess", _completed)

    result = skill_runner.run_skill(
        "guarded-skill",
        input_path=str(input_path),
        output_dir=str(tmp_path / "out"),
    )

    assert result.success is True, result.stderr
    assert result.audit_identity is not None
    assert len(calls) == 1


def test_explicit_gate_allows_external_h5ad_without_omicsclaw_modality_tag(
    tmp_path,
    monkeypatch,
):
    """Explicit selection supplies intent; unknown identity is not a conflict."""
    import anndata as ad
    import numpy as np

    skill_runner = importlib.import_module("omicsclaw.skill.runner")
    fake_script = tmp_path / "external.py"
    fake_script.write_text("raise SystemExit('driver is stubbed')\n", encoding="utf-8")
    input_path = tmp_path / "external.h5ad"
    adata = ad.AnnData(np.ones((3, 2)))
    adata.obsm["X_pca"] = np.ones((3, 2))
    adata.write_h5ad(input_path)
    _install_fake_skills(
        monkeypatch,
        {
            "guarded-skill": {
                "script": fake_script,
                "domain": "singlecell",
                "demo_args": ["--demo"],
                "allowed_extra_flags": set(),
                "input_contract": {
                    "modalities": ["scrna"],
                    "file_types": ["h5ad"],
                    "preconditions": {
                        "data_shape": {
                            "requires_preprocessed": True,
                            "obsm": ["X_pca"],
                        }
                    },
                },
            }
        },
    )
    calls: list[list[str]] = []

    def _completed(cmd, **_kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(skill_runner, "drive_subprocess", _completed)

    result = skill_runner.run_skill(
        "guarded-skill",
        input_path=str(input_path),
        output_dir=str(tmp_path / "external-out"),
    )

    assert result.success is True, result.stderr
    assert len(calls) == 1


def test_explicit_gate_still_rejects_an_observed_modality_conflict(
    tmp_path,
    monkeypatch,
):
    import anndata as ad
    import numpy as np

    skill_runner = importlib.import_module("omicsclaw.skill.runner")
    fake_script = tmp_path / "conflict.py"
    fake_script.write_text("raise SystemExit('must not execute')\n", encoding="utf-8")
    input_path = tmp_path / "genomics.h5ad"
    adata = ad.AnnData(np.ones((2, 2)))
    adata.uns["omicsclaw_input_contract"] = {"modality": "genomics"}
    adata.write_h5ad(input_path)
    _install_fake_skills(
        monkeypatch,
        {
            "scrna-skill": {
                "script": fake_script,
                "domain": "singlecell",
                "demo_args": ["--demo"],
                "allowed_extra_flags": set(),
                "input_contract": {
                    "modalities": ["scrna"],
                    "file_types": ["h5ad"],
                    "preconditions": {},
                },
            }
        },
    )
    calls: list[list[str]] = []

    def _must_not_execute(cmd, **_kwargs):
        calls.append(cmd)
        raise AssertionError("modality conflict must not reach subprocess")

    monkeypatch.setattr(skill_runner, "drive_subprocess", _must_not_execute)

    result = skill_runner.run_skill(
        "scrna-skill",
        input_path=str(input_path),
        output_dir=str(tmp_path / "conflict-out"),
    )

    assert result.success is False
    assert "modality 'genomics' is incompatible" in result.stderr
    assert calls == []


def test_explicit_gate_preserves_existing_directory_inputs(tmp_path, monkeypatch):
    skill_runner = importlib.import_module("omicsclaw.skill.runner")
    fake_script = tmp_path / "directory.py"
    fake_script.write_text("raise SystemExit('driver is stubbed')\n", encoding="utf-8")
    input_dir = tmp_path / "tenx_matrix.v1"
    input_dir.mkdir()
    (input_dir / "matrix.mtx").write_text("%%MatrixMarket\n", encoding="utf-8")
    _install_fake_skills(
        monkeypatch,
        {
            "standardize-skill": {
                "script": fake_script,
                "domain": "singlecell",
                "demo_args": ["--demo"],
                "allowed_extra_flags": set(),
                "input_contract": {
                    "modalities": ["scrna"],
                    "file_types": ["h5ad", "h5", "loom"],
                    "path_kinds": ["file", "directory"],
                    "preconditions": {},
                },
            }
        },
    )
    calls: list[list[str]] = []

    def _completed(cmd, **_kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(skill_runner, "drive_subprocess", _completed)

    result = skill_runner.run_skill(
        "standardize-skill",
        input_path=str(input_dir),
        output_dir=str(tmp_path / "directory-out"),
    )

    assert result.success is True, result.stderr
    assert len(calls) == 1


def test_explicit_gate_rejects_directory_for_a_file_only_skill(tmp_path, monkeypatch):
    skill_runner = importlib.import_module("omicsclaw.skill.runner")
    fake_script = tmp_path / "file_only.py"
    fake_script.write_text("raise SystemExit('must not execute')\n", encoding="utf-8")
    input_dir = tmp_path / "not_an_h5ad"
    input_dir.mkdir()
    _install_fake_skills(
        monkeypatch,
        {
            "file-only-skill": {
                "script": fake_script,
                "domain": "singlecell",
                "demo_args": ["--demo"],
                "allowed_extra_flags": set(),
                "input_contract": {
                    "modalities": ["scrna"],
                    "file_types": ["h5ad"],
                    "path_kinds": ["file"],
                    "preconditions": {},
                },
            }
        },
    )

    result = skill_runner.run_skill(
        "file-only-skill",
        input_path=str(input_dir),
        output_dir=str(tmp_path / "file-only-out"),
    )

    assert result.success is False
    assert "directory input is incompatible" in result.stderr


def test_explicit_gate_rejects_file_for_a_directory_only_skill(tmp_path, monkeypatch):
    skill_runner = importlib.import_module("omicsclaw.skill.runner")
    fake_script = tmp_path / "directory_only.py"
    fake_script.write_text("raise SystemExit('must not execute')\n", encoding="utf-8")
    input_file = tmp_path / "audit.json"
    input_file.write_text("{}\n", encoding="utf-8")
    _install_fake_skills(
        monkeypatch,
        {
            "directory-only-skill": {
                "script": fake_script,
                "domain": "spatial",
                "demo_args": ["--demo"],
                "allowed_extra_flags": set(),
                "input_contract": {
                    "modalities": [],
                    "file_types": ["json"],
                    "path_kinds": ["directory"],
                    "preconditions": {},
                },
            }
        },
    )

    result = skill_runner.run_skill(
        "directory-only-skill",
        input_path=str(input_file),
        output_dir=str(tmp_path / "directory-only-out"),
    )

    assert result.success is False
    assert "file input is incompatible" in result.stderr


@pytest.mark.parametrize(
    "freeform_input",
    [
        "plain raw text",
        "10.1038/s41586-024-00000-0",
        "https://example.org/paper",
    ],
)
def test_explicit_gate_rejects_freeform_for_a_file_only_skill(
    tmp_path,
    monkeypatch,
    freeform_input,
):
    skill_runner = importlib.import_module("omicsclaw.skill.runner")
    fake_script = tmp_path / "file_only.py"
    fake_script.write_text("raise SystemExit('must not execute')\n", encoding="utf-8")
    _install_fake_skills(
        monkeypatch,
        {
            "file-only-skill": {
                "script": fake_script,
                "domain": "singlecell",
                "demo_args": ["--demo"],
                "allowed_extra_flags": set(),
                "input_contract": {
                    "modalities": ["scrna"],
                    "file_types": ["h5ad"],
                    "path_kinds": ["file"],
                    "preconditions": {},
                },
            }
        },
    )

    result = skill_runner.run_skill(
        "file-only-skill",
        input_path=freeform_input,
        output_dir=str(tmp_path / "freeform-out"),
    )

    assert result.success is False
    assert "freeform input is incompatible" in result.stderr


def test_explicit_skill_gate_does_not_reclassify_demo_or_free_form_inputs(
    tmp_path,
    monkeypatch,
):
    skill_runner = importlib.import_module("omicsclaw.skill.runner")
    fake_script = tmp_path / "flexible.py"
    fake_script.write_text("raise SystemExit('driver is stubbed')\n", encoding="utf-8")
    _install_fake_skills(
        monkeypatch,
        {
            "flexible-skill": {
                "script": fake_script,
                "domain": "literature",
                "demo_args": ["--demo"],
                "allowed_extra_flags": set(),
                "input_contract": {
                    "modalities": [],
                    "file_types": ["pdf"],
                    "path_kinds": ["file", "freeform"],
                    "preconditions": {},
                },
            }
        },
    )
    calls: list[list[str]] = []

    def _completed(cmd, **_kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(skill_runner, "drive_subprocess", _completed)

    demo_result = skill_runner.run_skill(
        "flexible-skill",
        input_path=str(tmp_path / "corrupt.pdf"),
        output_dir=str(tmp_path / "demo-out"),
        demo=True,
    )
    doi_result = skill_runner.run_skill(
        "flexible-skill",
        input_path="10.1038/s41586-024-00000-0",
        output_dir=str(tmp_path / "doi-out"),
    )

    assert demo_result.success is True, demo_result.stderr
    assert doi_result.success is True, doi_result.stderr
    assert len(calls) == 2


def test_explicit_gate_preserves_matching_non_h5ad_inputs_until_they_are_inspectable(
    tmp_path,
    monkeypatch,
):
    """RET-04b must not invent missing structure for formats it cannot probe."""
    skill_runner = importlib.import_module("omicsclaw.skill.runner")
    fake_script = tmp_path / "csv_skill.py"
    fake_script.write_text("raise SystemExit('driver is stubbed')\n", encoding="utf-8")
    input_path = tmp_path / "proteins.csv"
    input_path.write_text("protein_id,intensity\nP1,1.0\n", encoding="utf-8")
    _install_fake_skills(
        monkeypatch,
        {
            "csv-skill": {
                "script": fake_script,
                "domain": "proteomics",
                "demo_args": ["--demo"],
                "allowed_extra_flags": set(),
                "input_contract": {
                    "modalities": ["proteomics"],
                    "file_types": ["csv"],
                    "preconditions": {
                        "data_shape": {
                            "obs": ["sample_id"],
                        }
                    },
                },
            }
        },
    )
    calls: list[list[str]] = []

    def _completed(cmd, **_kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(skill_runner, "drive_subprocess", _completed)

    result = skill_runner.run_skill(
        "csv-skill",
        input_path=str(input_path),
        output_dir=str(tmp_path / "csv-out"),
    )

    assert result.success is True, result.stderr
    assert len(calls) == 1


@pytest.mark.parametrize("filename", ["missing.csv", "missing.vcf"])
def test_explicit_gate_rejects_a_missing_non_h5ad_path(
    tmp_path,
    monkeypatch,
    filename,
):
    """File existence is observable even when content structure is not."""
    skill_runner = importlib.import_module("omicsclaw.skill.runner")
    fake_script = tmp_path / "csv_skill.py"
    fake_script.write_text("raise SystemExit('must not execute')\n", encoding="utf-8")
    missing_input = tmp_path / filename
    output_dir = tmp_path / "missing-out"
    _install_fake_skills(
        monkeypatch,
        {
            "csv-skill": {
                "script": fake_script,
                "domain": "proteomics",
                "demo_args": ["--demo"],
                "allowed_extra_flags": set(),
                "input_contract": {
                    "modalities": ["proteomics"],
                    "file_types": ["csv"],
                    "preconditions": {},
                },
            }
        },
    )
    calls: list[list[str]] = []

    def _must_not_execute(cmd, **_kwargs):
        calls.append(cmd)
        raise AssertionError("missing input must not reach subprocess")

    monkeypatch.setattr(skill_runner, "drive_subprocess", _must_not_execute)

    result = skill_runner.run_skill(
        "csv-skill",
        input_path=str(missing_input),
        output_dir=str(output_dir),
    )

    assert result.success is False
    assert "does not exist" in result.stderr
    assert calls == []
    assert not output_dir.exists()


def test_explicit_gate_returns_a_stable_result_for_an_invalid_session(
    tmp_path,
    monkeypatch,
):
    skill_runner = importlib.import_module("omicsclaw.skill.runner")
    fake_script = tmp_path / "session_skill.py"
    fake_script.write_text("raise SystemExit('must not execute')\n", encoding="utf-8")
    bad_session = tmp_path / "session.json"
    bad_session.write_text("{broken json", encoding="utf-8")
    output_dir = tmp_path / "session-out"
    _install_fake_skills(
        monkeypatch,
        {
            "session-skill": {
                "script": fake_script,
                "domain": "singlecell",
                "demo_args": ["--demo"],
                "allowed_extra_flags": set(),
                "input_contract": {
                    "modalities": ["scrna"],
                    "file_types": ["h5ad"],
                    "preconditions": {},
                },
            }
        },
    )

    result = skill_runner.run_skill(
        "session-skill",
        session_path=str(bad_session),
        output_dir=str(output_dir),
    )

    assert result.success is False
    assert result.exit_code == -1
    assert "USER_GUIDANCE_JSON:" in result.stderr
    assert "session input inspection failed" in result.stderr
    assert not output_dir.exists()


def test_explicit_runner_rejects_missing_input_before_creating_output(
    tmp_path,
    monkeypatch,
):
    skill_runner = importlib.import_module("omicsclaw.skill.runner")
    fake_script = tmp_path / "input_required.py"
    fake_script.write_text("raise SystemExit('must not execute')\n", encoding="utf-8")
    output_dir = tmp_path / "missing-input-out"
    _install_fake_skills(
        monkeypatch,
        {
            "input-required-skill": {
                "script": fake_script,
                "domain": "singlecell",
                "demo_args": ["--demo"],
                "allowed_extra_flags": set(),
                "input_contract": {
                    "modalities": ["scrna"],
                    "file_types": ["h5ad"],
                    "path_kinds": ["file"],
                    "preconditions": {},
                },
            }
        },
    )

    result = skill_runner.run_skill(
        "input-required-skill",
        output_dir=str(output_dir),
    )

    assert result.success is False
    assert "No --input, --demo, or --session provided." in result.stderr
    assert not output_dir.exists()


def test_runner_uses_one_registry_snapshot_across_selection_and_preflight(
    tmp_path,
    monkeypatch,
):
    """A concurrent publication cannot apply a new contract to an old script."""
    from omicsclaw.skill.registry import OmicsRegistry, registry

    skill_runner = importlib.import_module("omicsclaw.skill.runner")
    old_root = tmp_path / "old-skills"
    new_root = tmp_path / "new-skills"
    old_dir = old_root / "demo" / "snapshot-skill"
    new_dir = new_root / "demo" / "snapshot-skill"
    old_dir.mkdir(parents=True)
    new_dir.mkdir(parents=True)
    old_script = old_dir / "entry.py"
    new_script = new_dir / "entry.py"
    old_script.write_text("print('old')\n", encoding="utf-8")
    new_script.write_text("print('new')\n", encoding="utf-8")
    (old_dir / "skill.yaml").write_text("id: snapshot-skill\n", encoding="utf-8")
    (new_dir / "skill.yaml").write_text("id: snapshot-skill\n", encoding="utf-8")
    input_path = tmp_path / "observed.txt"
    input_path.write_text("observed\n", encoding="utf-8")
    output_dir = tmp_path / "must-not-run"

    common = {
        "alias": "snapshot-skill",
        "canonical_name": "snapshot-skill",
        "directory_name": "snapshot-skill",
        "domain": "demo",
        "demo_args": ["--demo"],
        "allowed_extra_flags": set(),
        "description": "snapshot test",
        "requires": [],
        "output_contract": {},
        "lifecycle_status": "mvp",
        "version": "1.0.0",
    }
    old_info = {
        **common,
        "script": old_script,
        "input_contract": {"path_kinds": ["file"], "file_types": ["csv"]},
    }
    new_info = {
        **common,
        "script": new_script,
        "input_contract": {"path_kinds": ["file"], "file_types": ["txt"]},
    }
    _install_fake_skills(
        monkeypatch,
        {"snapshot-skill": old_info},
        skills_root=old_root,
    )
    replacement = OmicsRegistry()
    replacement.skills = {"snapshot-skill": new_info}
    replacement.canonical_aliases = ["snapshot-skill"]
    replacement.domains = {"demo": {"name": "Demo"}}
    replacement._loaded = True
    replacement._loaded_dir = new_root.resolve()

    original_preflight = skill_runner.preflight_skill_execution

    def publish_before_preflight(*args, **kwargs):
        # Track the publication through monkeypatch so the process-global
        # Registry state is restored for tests that run after this one.
        monkeypatch.setattr(registry, "_state", replacement._state)
        return original_preflight(*args, **kwargs)

    monkeypatch.setattr(
        skill_runner,
        "preflight_skill_execution",
        publish_before_preflight,
    )
    spawned: list[list[str]] = []

    def observe_spawn(cmd, **_kwargs):
        spawned.append(cmd)
        raise AssertionError("the old contract must block this input")

    monkeypatch.setattr(skill_runner, "drive_subprocess", observe_spawn)

    result = skill_runner.run_skill(
        "snapshot-skill",
        input_path=str(input_path),
        output_dir=str(output_dir),
    )

    assert result.success is False
    assert "file type 'txt' is incompatible" in result.stderr
    assert spawned == []
    assert not output_dir.exists()


@pytest.mark.parametrize(
    "session_payload",
    [
        {},
        {"primary_data_path": ""},
        {"primary_data_path": "missing-relative-input"},
    ],
)
def test_explicit_gate_rejects_a_session_without_a_usable_local_input(
    tmp_path,
    monkeypatch,
    session_payload,
):
    skill_runner = importlib.import_module("omicsclaw.skill.runner")
    fake_script = tmp_path / "session_skill.py"
    fake_script.write_text("raise SystemExit('must not execute')\n", encoding="utf-8")
    session_path = tmp_path / "session.json"
    session_path.write_text(json.dumps(session_payload), encoding="utf-8")
    output_dir = tmp_path / "session-out"
    _install_fake_skills(
        monkeypatch,
        {
            "session-skill": {
                "script": fake_script,
                "domain": "singlecell",
                "demo_args": ["--demo"],
                "allowed_extra_flags": set(),
                "input_contract": {
                    "modalities": ["scrna"],
                    "file_types": ["h5ad"],
                    "path_kinds": ["file"],
                    "preconditions": {},
                },
            }
        },
    )

    result = skill_runner.run_skill(
        "session-skill",
        session_path=str(session_path),
        output_dir=str(output_dir),
    )

    assert result.success is False
    assert "USER_GUIDANCE_JSON:" in result.stderr
    assert "session" in result.stderr.lower()
    assert not output_dir.exists()


@pytest.mark.asyncio
async def test_async_explicit_skill_uses_the_same_precondition_gate(
    tmp_path, monkeypatch
):
    skill_runner = importlib.import_module("omicsclaw.skill.runner")
    fake_script = tmp_path / "must_not_run_async.py"
    fake_script.write_text("raise SystemExit('must not execute')\n", encoding="utf-8")
    corrupt_input = tmp_path / "corrupt.h5ad"
    corrupt_input.write_text("not an h5ad file\n", encoding="utf-8")
    output_dir = tmp_path / "async-out"
    _install_fake_skills(
        monkeypatch,
        {
            "guarded-skill": {
                "script": fake_script,
                "domain": "singlecell",
                "demo_args": ["--demo"],
                "allowed_extra_flags": set(),
                "input_contract": {
                    "modalities": ["scrna"],
                    "file_types": ["h5ad"],
                    "preconditions": {},
                },
            }
        },
    )
    calls: list[list[str]] = []

    async def _must_not_execute(cmd, **_kwargs):
        calls.append(cmd)
        raise AssertionError("async subprocess must not start")

    monkeypatch.setattr(skill_runner, "adrive_subprocess", _must_not_execute)

    result = await skill_runner.arun_skill(
        "guarded-skill",
        input_path=str(corrupt_input),
        output_dir=str(output_dir),
    )

    assert result.success is False
    assert "precondition" in result.stderr.lower()
    assert calls == []
    assert not output_dir.exists()


@pytest.mark.asyncio
async def test_async_skill_applies_only_governed_resource_environment(
    tmp_path,
    monkeypatch,
):
    skill_runner = importlib.import_module("omicsclaw.skill.runner")
    fake_script = tmp_path / "resource_skill.py"
    fake_script.write_text("# execution is intercepted\n", encoding="utf-8")
    output_dir = tmp_path / "resource-out"
    _install_fake_skills(
        monkeypatch,
        {
            "resource-skill": {
                "script": fake_script,
                "domain": "singlecell",
                "demo_args": ["--demo"],
                "allowed_extra_flags": set(),
                "input_contract": {},
            }
        },
    )
    observed_env: dict[str, str] = {}

    async def _capture_env(cmd, *, env, out_dir, **_kwargs):
        for key in (
            "CUDA_VISIBLE_DEVICES",
            "OMP_NUM_THREADS",
            "OPENBLAS_NUM_THREADS",
            "UNSAFE_SECRET",
            "OMICSCLAW_SKILL_EVOLUTION_TOKEN",
            "OMICSCLAW_SKILL_EVOLUTION_TOKEN_FD",
            "OMICSCLAW_REMOTE_AUTH_TOKEN",
        ):
            if key in env:
                observed_env[key] = env[key]
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "result.json").write_text(
            json.dumps({"status": "ok"}),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(skill_runner, "adrive_subprocess", _capture_env)
    monkeypatch.setenv("OMICSCLAW_SKILL_EVOLUTION_TOKEN", "must-not-reach-the-skill")
    monkeypatch.setenv("OMICSCLAW_SKILL_EVOLUTION_TOKEN_FD", "3")
    monkeypatch.setenv("OMICSCLAW_REMOTE_AUTH_TOKEN", "must-not-reach-the-skill")

    result = await skill_runner.arun_skill(
        "resource-skill",
        demo=True,
        output_dir=str(output_dir),
        resource_env={
            "CUDA_VISIBLE_DEVICES": "2",
            "OMP_NUM_THREADS": "3",
            "OPENBLAS_NUM_THREADS": "3",
            "MKL_NUM_THREADS": "3",
            "NUMEXPR_NUM_THREADS": "3",
            "UNSAFE_SECRET": "must-not-pass",
        },
    )

    assert result.success is True
    assert observed_env["CUDA_VISIBLE_DEVICES"] == "2"
    assert observed_env["OMP_NUM_THREADS"] == "3"
    assert observed_env["OPENBLAS_NUM_THREADS"] == "3"
    assert "UNSAFE_SECRET" not in observed_env
    assert "OMICSCLAW_SKILL_EVOLUTION_TOKEN" not in observed_env
    assert "OMICSCLAW_SKILL_EVOLUTION_TOKEN_FD" not in observed_env
    assert "OMICSCLAW_REMOTE_AUTH_TOKEN" not in observed_env


def test_resource_environment_precedes_adaptive_runtime_resolution(
    tmp_path,
    monkeypatch,
) -> None:
    from omicsclaw.skill.execution.env_resolver import SkillRuntime

    skill_runner = importlib.import_module("omicsclaw.skill.runner")
    fake_script = tmp_path / "resource_order_skill.py"
    fake_script.write_text("# execution is intercepted\n", encoding="utf-8")
    _install_fake_skills(
        monkeypatch,
        {
            "resource-order": {
                "script": fake_script,
                "domain": "singlecell",
                "demo_args": ["--demo"],
                "allowed_extra_flags": set(),
                "input_contract": {},
            }
        },
    )
    run_root = tmp_path / "run"
    run_root.mkdir()
    trusted_temp = run_root / ".tmp"
    trusted_temp.mkdir()
    observed: dict[str, str] = {}

    def resolve_runtime(*_args, **kwargs):
        observed.update(kwargs["base_env"])
        return SkillRuntime(python=kwargs["base_python"], source="base")

    monkeypatch.setattr(skill_runner, "resolve_skill_runtime", resolve_runtime)
    prepared = skill_runner._prepare_skill_run(
        "resource-order",
        input_path=None,
        input_paths=None,
        output_dir=str(run_root / "artifacts"),
        demo=True,
        session_path=None,
        extra_args=None,
        resource_env={
            "CUDA_VISIBLE_DEVICES": "3",
            "OMP_NUM_THREADS": "2",
            "OPENBLAS_NUM_THREADS": "2",
            "MKL_NUM_THREADS": "2",
            "NUMEXPR_NUM_THREADS": "2",
            "TMPDIR": str(trusted_temp),
        },
        trusted_resource_temp_dir=str(trusted_temp),
        log_banner=False,
    )

    assert not isinstance(prepared, skill_runner.SkillRunResult)
    assert observed["CUDA_VISIBLE_DEVICES"] == "3"
    assert observed["OMP_NUM_THREADS"] == "2"
    assert observed["TMPDIR"] == str(trusted_temp)


def test_canonical_prepare_can_disable_adaptive_provisioning(
    tmp_path,
    monkeypatch,
) -> None:
    skill_runner = importlib.import_module("omicsclaw.skill.runner")
    fake_script = tmp_path / "fixed_runtime_skill.py"
    fake_script.write_text("# execution is intercepted\n", encoding="utf-8")
    _install_fake_skills(
        monkeypatch,
        {
            "fixed-runtime": {
                "script": fake_script,
                "domain": "singlecell",
                "demo_args": ["--demo"],
                "allowed_extra_flags": set(),
                "input_contract": {},
                "requires": ["definitely-missing-package"],
            }
        },
    )

    def forbidden_resolver(*_args, **_kwargs):
        raise AssertionError("canonical tracer must not provision an environment")

    monkeypatch.setattr(skill_runner, "resolve_skill_runtime", forbidden_resolver)
    prepared = skill_runner._prepare_skill_run(
        "fixed-runtime",
        input_path=None,
        input_paths=None,
        output_dir=str(tmp_path / "fixed-output"),
        demo=True,
        session_path=None,
        extra_args=None,
        allow_adaptive_environment=False,
        log_banner=False,
    )
    assert not isinstance(prepared, skill_runner.SkillRunResult)
    assert prepared.runtime_source == "base"


@pytest.mark.asyncio
async def test_async_prepare_cancellation_waits_for_preparation_thread(
    tmp_path,
    monkeypatch,
) -> None:
    import threading

    skill_runner = importlib.import_module("omicsclaw.skill.runner")
    fake_script = tmp_path / "slow_prepare_skill.py"
    fake_script.write_text("# preparation is intercepted\n", encoding="utf-8")
    _install_fake_skills(
        monkeypatch,
        {
            "slow-prepare": {
                "script": fake_script,
                "domain": "singlecell",
                "demo_args": ["--demo"],
                "allowed_extra_flags": set(),
                "input_contract": {},
            }
        },
    )
    started = threading.Event()
    release = threading.Event()

    def slow_prepare(*_args, **_kwargs):
        started.set()
        release.wait(timeout=2)
        return skill_runner.SkillRunResult(
            skill="slow-prepare",
            success=False,
            exit_code=1,
        )

    monkeypatch.setattr(skill_runner, "_prepare_skill_run", slow_prepare)
    task = asyncio.create_task(
        skill_runner.arun_skill(
            "slow-prepare",
            demo=True,
            output_dir=str(tmp_path / "slow-output"),
        )
    )
    assert await asyncio.to_thread(started.wait, 1)
    task.cancel()
    await asyncio.sleep(0.05)
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task


def test_run_skill_streams_stdout_and_stderr_lines_via_callbacks(tmp_path, monkeypatch):
    """The runner must surface skill output line-by-line in real time so that
    long-running deep-learning skills produce visible logs to the bot/operator
    instead of staying silent until completion."""
    skill_runner = importlib.import_module("omicsclaw.skill.runner")

    fake_script = tmp_path / "fake_streamer.py"
    fake_script.write_text(
        textwrap.dedent("""\
        import argparse, json, sys, time
        from pathlib import Path

        ap = argparse.ArgumentParser()
        ap.add_argument("--demo", action="store_true")
        ap.add_argument("--output", required=True)
        args = ap.parse_args()

        for i in range(3):
            print(f"epoch {i}/3", flush=True)
            time.sleep(0.02)
        print("warning: synthetic stderr", file=sys.stderr, flush=True)
        print("done", flush=True)

        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        (out / "result.json").write_text(json.dumps({"summary": {"method": "fake"}}), encoding="utf-8")
    """),
        encoding="utf-8",
    )

    monkeypatch.setattr(skill_runner, "DEFAULT_OUTPUT_ROOT", tmp_path)
    _install_fake_skills(
        monkeypatch,
        {
            "fake-streamer": {
                "script": fake_script,
                "domain": "demo",
                "demo_args": ["--demo"],
                "allowed_extra_flags": set(),
                "description": "Streaming test skill",
            }
        },
    )

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    result = skill_runner.run_skill(
        "fake-streamer",
        demo=True,
        output_dir=str(tmp_path / "out"),
        stdout_callback=stdout_lines.append,
        stderr_callback=stderr_lines.append,
    )

    assert result.success is True, result.stderr
    assert stdout_lines == ["epoch 0/3", "epoch 1/3", "epoch 2/3", "done"]
    assert stderr_lines == ["warning: synthetic stderr"]
    # Aggregated stdout/stderr fields must still contain the same content.
    for line in stdout_lines:
        assert line in result.stdout
    assert "warning: synthetic stderr" in result.stderr


def test_run_skill_callback_exception_does_not_break_run(tmp_path, monkeypatch):
    """A buggy stdout/stderr callback must not abort the skill — the runner
    swallows callback errors so the underlying analysis still completes."""
    skill_runner = importlib.import_module("omicsclaw.skill.runner")

    fake_script = tmp_path / "fake_one_line.py"
    fake_script.write_text(
        textwrap.dedent("""\
        import argparse, json
        from pathlib import Path

        ap = argparse.ArgumentParser()
        ap.add_argument("--demo", action="store_true")
        ap.add_argument("--output", required=True)
        args = ap.parse_args()

        print("hello")
        Path(args.output).mkdir(parents=True, exist_ok=True)
        (Path(args.output) / "result.json").write_text(json.dumps({"summary": {}}), encoding="utf-8")
    """),
        encoding="utf-8",
    )

    monkeypatch.setattr(skill_runner, "DEFAULT_OUTPUT_ROOT", tmp_path)
    _install_fake_skills(
        monkeypatch,
        {
            "fake-one-line": {
                "script": fake_script,
                "domain": "demo",
                "demo_args": ["--demo"],
                "allowed_extra_flags": set(),
                "description": "One-line test skill",
            }
        },
    )

    def boom(_line: str) -> None:
        raise RuntimeError("callback exploded")

    result = skill_runner.run_skill(
        "fake-one-line",
        demo=True,
        output_dir=str(tmp_path / "out"),
        stdout_callback=boom,
    )
    assert result.success is True
    assert "hello" in result.stdout


def test_run_skill_cancel_event_kills_long_running_subprocess(tmp_path, monkeypatch):
    """Setting ``cancel_event`` while a skill is running must terminate the
    child subprocess (and its process group) and return promptly.

    Pre-fix the runner's ``popen.wait()`` would not wake up for asyncio
    cancellation, so jobs cancelled by the FastAPI router would leak
    children that kept consuming CPU/GPU until they finished naturally.
    """
    skill_runner = importlib.import_module("omicsclaw.skill.runner")

    fake_script = tmp_path / "fake_long.py"
    fake_script.write_text(
        textwrap.dedent("""\
        import argparse, time
        ap = argparse.ArgumentParser()
        ap.add_argument("--demo", action="store_true")
        ap.add_argument("--output", required=True)
        args = ap.parse_args()
        for i in range(60):
            print(f"working {i}", flush=True)
            time.sleep(0.5)
    """),
        encoding="utf-8",
    )

    monkeypatch.setattr(skill_runner, "DEFAULT_OUTPUT_ROOT", tmp_path)
    _install_fake_skills(
        monkeypatch,
        {
            "fake-long": {
                "script": fake_script,
                "domain": "demo",
                "demo_args": ["--demo"],
                "allowed_extra_flags": set(),
                "description": "Long-running test skill",
            }
        },
    )

    cancel_event = threading.Event()

    def _trigger_cancel_after_startup() -> None:
        # Wait for the child to actually start producing output before cancelling
        # so we exercise the real "kill while busy" path, not "kill before start".
        time.sleep(1.0)
        cancel_event.set()

    threading.Thread(target=_trigger_cancel_after_startup, daemon=True).start()

    started_at = time.time()
    result = skill_runner.run_skill(
        "fake-long",
        demo=True,
        output_dir=str(tmp_path / "long_out"),
        cancel_event=cancel_event,
    )
    elapsed = time.time() - started_at

    # Without cancellation the fake script would run for ~30s. Cancellation
    # must interrupt within a few seconds (1s pre-cancel + grace + cleanup).
    assert elapsed < 10, f"cancel did not interrupt; ran for {elapsed:.1f}s"
    assert result.success is False
    assert result.exit_code != 0
    assert result.audit_identity is not None


def test_run_skill_cancellation_with_partial_result_json_is_not_reported_as_success(
    tmp_path, monkeypatch
):
    """A skill that wrote ``result.json`` early then was SIGKILL'd via
    ``cancel_event`` must NOT be silently reclassified as success.

    Pre-fix, the runner mapped any ``returncode == -9`` to ``0`` whenever
    ``result.json`` existed (originally a workaround for the orphan reaper's
    SIGKILL race). After we wired ``cancel_event`` through SIGTERM/SIGKILL,
    ``-9`` also became the *normal* outcome of cancellation — so cancelled
    runs that happened to leave a partial ``result.json`` were silently
    reported as ``success=True``.
    """
    skill_runner = importlib.import_module("omicsclaw.skill.runner")

    fake_script = tmp_path / "fake_partial_then_sleep.py"
    fake_script.write_text(
        textwrap.dedent("""\
        import argparse, json, signal, time
        from pathlib import Path
        # Ignore SIGTERM so the runner has to escalate to SIGKILL (-9), which is
        # exactly the path that used to trip the "-9 + result.json → success"
        # heuristic.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        ap = argparse.ArgumentParser()
        ap.add_argument("--demo", action="store_true")
        ap.add_argument("--output", required=True)
        args = ap.parse_args()
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        (out / "result.json").write_text(
            json.dumps({"summary": {"method": "fake", "partial": True}}),
            encoding="utf-8",
        )
        print("partial-result-written", flush=True)
        for _ in range(60):
            time.sleep(0.5)
    """),
        encoding="utf-8",
    )

    monkeypatch.setattr(skill_runner, "DEFAULT_OUTPUT_ROOT", tmp_path)
    _install_fake_skills(
        monkeypatch,
        {
            "fake-partial": {
                "script": fake_script,
                "domain": "demo",
                "demo_args": ["--demo"],
                "allowed_extra_flags": set(),
                "description": "Partial-then-sleep test skill",
            }
        },
    )

    cancel_event = threading.Event()

    def _trigger_cancel_after_partial_write() -> None:
        # Give the child time to write result.json before cancelling.
        time.sleep(1.0)
        cancel_event.set()

    threading.Thread(target=_trigger_cancel_after_partial_write, daemon=True).start()

    result = skill_runner.run_skill(
        "fake-partial",
        demo=True,
        output_dir=str(tmp_path / "partial_out"),
        cancel_event=cancel_event,
    )

    # The partial result.json was on disk when SIGKILL fired, which used to
    # trip the -9 → 0 heuristic. Cancellation must override the heuristic.
    assert (
        result.success is False
    ), "cancelled run with partial result.json must NOT be reported as success"
    assert result.exit_code != 0
    assert result.audit_identity is not None


# ---------------------------------------------------------------------------
# Skill-subprocess interpreter + environment isolation ("missing deps"
# regression, first seen under an HTTP backend started in a lighter env).
#
# Two failure modes, both exercised at the ``_prepare_skill_run`` seam where
# the subprocess argv + env are actually built:
#   1. ``OMICSCLAW_RUN_PYTHON`` was ignored on the main run path (runner.py
#      hardcoded ``sys.executable``), so a backend running in a lighter
#      env could not redirect skills to the analysis env.
#   2. Skill subprocesses inherited ``~/.local`` user-site, letting a broken
#      package there shadow the analysis env's deps.
# ---------------------------------------------------------------------------


def _install_fake_demo_skill(monkeypatch, tmp_path):
    """Register a trivial demo skill and return the runner module."""
    skill_runner = importlib.import_module("omicsclaw.skill.runner")
    fake_script = tmp_path / "fake_prep.py"
    fake_script.write_text("print('noop')\n", encoding="utf-8")
    monkeypatch.setattr(skill_runner, "DEFAULT_OUTPUT_ROOT", tmp_path)
    _install_fake_skills(
        monkeypatch,
        {
            "fake-prep": {
                "script": fake_script,
                "domain": "demo",
                "demo_args": ["--demo"],
                "allowed_extra_flags": set(),
                "description": "Prep test skill",
            }
        },
    )
    return skill_runner


def _prepare(skill_runner, tmp_path):
    prepared = skill_runner._prepare_skill_run(
        "fake-prep",
        input_path=None,
        input_paths=None,
        output_dir=str(tmp_path / "out"),
        demo=True,
        session_path=None,
        extra_args=None,
        log_banner=False,
    )
    assert not isinstance(prepared, skill_runner.SkillRunResult), getattr(
        prepared, "stderr", prepared
    )
    return prepared


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["sync", "async"])
async def test_shared_runner_rejects_stale_explicit_output_before_spawn(
    tmp_path: Path,
    monkeypatch,
    mode: str,
) -> None:
    skill_runner = importlib.import_module("omicsclaw.skill.runner")
    spawned = tmp_path / f"spawned-{mode}"
    script = tmp_path / f"stale_guard_{mode}.py"
    script.write_text(
        textwrap.dedent(
            f"""\
            import argparse
            import sys
            from pathlib import Path

            parser = argparse.ArgumentParser()
            parser.add_argument("--demo", action="store_true")
            parser.add_argument("--output", required=True)
            parser.parse_args()
            Path({str(spawned)!r}).write_text("spawned", encoding="utf-8")
            print("CURRENT RUN CRASH", file=sys.stderr)
            raise SystemExit(7)
            """
        ),
        encoding="utf-8",
    )
    _install_fake_skills(
        monkeypatch,
        {
            "stale-guard": {
                "alias": "stale-guard",
                "script": script,
                "domain": "demo",
                "demo_args": ["--demo"],
                "allowed_extra_flags": set(),
                "input_contract": {},
                "output_contract": {},
                "lifecycle_status": "mvp",
            }
        },
    )
    output_dir = tmp_path / f"stale-out-{mode}"
    output_dir.mkdir()
    stale_result = output_dir / "result.json"
    stale_result.write_text('{"status":"ok"}\n', encoding="utf-8")

    if mode == "sync":
        result = skill_runner.run_skill(
            "stale-guard",
            demo=True,
            output_dir=str(output_dir),
        )
    else:
        result = await skill_runner.arun_skill(
            "stale-guard",
            demo=True,
            output_dir=str(output_dir),
        )

    assert result.success is False
    assert "fresh output directory" in result.stderr
    assert not spawned.exists()
    assert stale_result.read_text(encoding="utf-8") == '{"status":"ok"}\n'


def test_shared_runner_claims_empty_output_once(tmp_path: Path, monkeypatch) -> None:
    skill_runner = _install_fake_demo_skill(monkeypatch, tmp_path)
    first = _prepare(skill_runner, tmp_path)
    second = skill_runner._prepare_skill_run(
        "fake-prep",
        input_path=None,
        input_paths=None,
        output_dir=str(first.out_dir),
        demo=True,
        session_path=None,
        extra_args=None,
        log_banner=False,
    )

    assert isinstance(second, skill_runner.SkillRunResult)
    assert second.success is False
    assert "fresh output directory" in second.stderr


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["sync", "async"])
async def test_shared_runner_fails_closed_when_runtime_claim_binding_fails(
    tmp_path: Path,
    monkeypatch,
    mode: str,
) -> None:
    skill_runner = _install_fake_demo_skill(monkeypatch, tmp_path)
    spawn_attempts: list[list[str]] = []

    def refuse_binding(*_args, **_kwargs):
        raise skill_runner.OutputDirectoryClaimError(
            "injected claim audit binding failure"
        )

    def forbidden_spawn(cmd, **_kwargs):
        spawn_attempts.append(list(cmd))
        raise AssertionError("claim audit binding failure reached subprocess spawn")

    async def forbidden_async_spawn(cmd, **_kwargs):
        spawn_attempts.append(list(cmd))
        raise AssertionError("claim audit binding failure reached subprocess spawn")

    monkeypatch.setattr(
        skill_runner,
        "bind_output_claim_audit_identity",
        refuse_binding,
        raising=False,
    )
    monkeypatch.setattr(skill_runner, "drive_subprocess", forbidden_spawn)
    monkeypatch.setattr(skill_runner, "adrive_subprocess", forbidden_async_spawn)

    if mode == "sync":
        result = skill_runner.run_skill(
            "fake-prep",
            demo=True,
            output_dir=str(tmp_path / f"binding-failure-{mode}"),
        )
    else:
        result = await skill_runner.arun_skill(
            "fake-prep",
            demo=True,
            output_dir=str(tmp_path / f"binding-failure-{mode}"),
        )

    assert result.success is False
    assert result.error_kind == "contract_validator_failed"
    assert "claim audit binding failed" in result.stderr
    assert spawn_attempts == []


def test_shared_runner_binds_selected_runtime_and_frozen_hashes_before_spawn(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from omicsclaw.common.output_claim import OUTPUT_CLAIM_FILENAME

    skill_runner = _install_fake_demo_skill(monkeypatch, tmp_path)

    prepared = _prepare(skill_runner, tmp_path)

    payload = json.loads(
        (prepared.out_dir / OUTPUT_CLAIM_FILENAME).read_text(encoding="utf-8")
    )
    assert (
        payload["audit_identity"]
        == skill_runner._prepared_audit_identity(prepared).to_dict()
    )
    assert payload["runtime_source"] == prepared.runtime_source
    assert payload["audit_identity"]["source_hash"].startswith("sha256:")
    assert payload["audit_identity"]["environment_id"].startswith("env:")


def test_shared_runner_environment_id_comes_from_selected_runtime_and_env(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from omicsclaw.common.output_claim import OUTPUT_CLAIM_FILENAME
    from omicsclaw.skill.execution.env_resolver import SkillRuntime

    skill_runner = _install_fake_demo_skill(monkeypatch, tmp_path)
    selected_env = {"value": str(tmp_path / "runtime-env-a")}

    def selected_runtime(*_args, **_kwargs):
        return SkillRuntime(
            python=sys.executable,
            env_overlay={"VIRTUAL_ENV": selected_env["value"]},
            source="venv:test-runtime",
        )

    monkeypatch.setattr(skill_runner, "resolve_skill_runtime", selected_runtime)

    first = skill_runner._prepare_skill_run(
        "fake-prep",
        input_path=None,
        input_paths=None,
        output_dir=str(tmp_path / "runtime-a"),
        demo=True,
        session_path=None,
        extra_args=None,
        log_banner=False,
    )
    assert not isinstance(first, skill_runner.SkillRunResult)
    selected_env["value"] = str(tmp_path / "runtime-env-b")
    second = skill_runner._prepare_skill_run(
        "fake-prep",
        input_path=None,
        input_paths=None,
        output_dir=str(tmp_path / "runtime-b"),
        demo=True,
        session_path=None,
        extra_args=None,
        log_banner=False,
    )
    assert not isinstance(second, skill_runner.SkillRunResult)

    assert first.cmd[0] == sys.executable
    assert first.environment_id != second.environment_id
    first_claim = (first.out_dir / OUTPUT_CLAIM_FILENAME).read_text(encoding="utf-8")
    second_claim = (second.out_dir / OUTPUT_CLAIM_FILENAME).read_text(encoding="utf-8")
    assert str(tmp_path) not in first_claim
    assert str(tmp_path) not in second_claim
    assert "runtime-env-a" not in first_claim
    assert "runtime-env-b" not in second_claim


def test_shared_runner_environment_id_distinguishes_selected_executable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from omicsclaw.skill.execution.env_resolver import SkillRuntime

    skill_runner = _install_fake_demo_skill(monkeypatch, tmp_path)
    runtime_dir = tmp_path / ".cache" / "runtime-fixtures"
    runtime_dir.mkdir(parents=True)
    first_python = runtime_dir / "selected-python-a"
    second_python = runtime_dir / "selected-python-b"
    try:
        first_python.symlink_to(sys.executable)
        second_python.symlink_to(sys.executable)
    except OSError:
        pytest.skip("runtime does not permit executable symlink fixtures")
    selected = {"python": str(first_python)}

    def selected_runtime(*_args, **_kwargs):
        return SkillRuntime(
            python=selected["python"],
            source="base",
        )

    monkeypatch.setattr(skill_runner, "resolve_skill_runtime", selected_runtime)
    first = skill_runner._prepare_skill_run(
        "fake-prep",
        input_path=None,
        input_paths=None,
        output_dir=str(tmp_path / "selected-a"),
        demo=True,
        session_path=None,
        extra_args=None,
        log_banner=False,
    )
    assert not isinstance(first, skill_runner.SkillRunResult)
    selected["python"] = str(second_python)
    second = skill_runner._prepare_skill_run(
        "fake-prep",
        input_path=None,
        input_paths=None,
        output_dir=str(tmp_path / "selected-b"),
        demo=True,
        session_path=None,
        extra_args=None,
        log_banner=False,
    )
    assert not isinstance(second, skill_runner.SkillRunResult)

    assert first.environment_id != second.environment_id


def test_shared_runner_environment_id_uses_selected_runtime_dependency_versions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from omicsclaw.common.output_claim import OUTPUT_CLAIM_FILENAME
    from omicsclaw.skill.execution.env_resolver import SkillRuntime

    skill_runner = importlib.import_module("omicsclaw.skill.runner")
    fake_script = tmp_path / "dependency_probe_skill.py"
    fake_script.write_text("print('intercepted')\n", encoding="utf-8")
    _install_fake_skills(
        monkeypatch,
        {
            "dependency-probe": {
                "script": fake_script,
                "domain": "demo",
                "demo_args": ["--demo"],
                "allowed_extra_flags": set(),
                "description": "Runtime dependency evidence test",
                "requires": ["fake-dep>=1"],
            }
        },
    )
    monkeypatch.setattr(
        skill_runner,
        "resolve_skill_runtime",
        lambda *_args, **kwargs: SkillRuntime(
            python=kwargs["base_python"],
            source="base",
        ),
    )

    environments: list[Path] = []
    for name, version in (("a", "1.0+env.a"), ("b", "1.0+env.b")):
        environment = tmp_path / ".cache" / f"dependency-env-{name}"
        metadata = environment / f"fake_dep-{version}.dist-info"
        metadata.mkdir(parents=True)
        (metadata / "METADATA").write_text(
            f"Metadata-Version: 2.1\nName: fake-dep\nVersion: {version}\n",
            encoding="utf-8",
        )
        environments.append(environment)

    prepared_runs = []
    for index, environment in enumerate(environments):
        monkeypatch.setenv("PYTHONPATH", str(environment))
        prepared = skill_runner._prepare_skill_run(
            "dependency-probe",
            input_path=None,
            input_paths=None,
            output_dir=str(tmp_path / f"dependency-run-{index}"),
            demo=True,
            session_path=None,
            extra_args=None,
            log_banner=False,
        )
        assert not isinstance(prepared, skill_runner.SkillRunResult)
        prepared_runs.append(prepared)

    assert prepared_runs[0].environment_id != prepared_runs[1].environment_id
    for prepared in prepared_runs:
        claim = (prepared.out_dir / OUTPUT_CLAIM_FILENAME).read_text(encoding="utf-8")
        assert "1.0+env." not in claim
        assert str(tmp_path) not in claim


def test_shared_runner_runtime_probe_failure_does_not_spawn_skill(
    tmp_path: Path,
    monkeypatch,
) -> None:
    skill_runner = _install_fake_demo_skill(monkeypatch, tmp_path)
    malicious_imports = tmp_path / "probe-imports"
    malicious_imports.mkdir()
    (malicious_imports / "platform.py").write_text(
        "raise RuntimeError('probe must fail')\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PYTHONPATH", str(malicious_imports))
    spawn_attempts: list[list[str]] = []

    def forbidden_spawn(cmd, **_kwargs):
        spawn_attempts.append(list(cmd))
        raise AssertionError("failed runtime probe reached Skill spawn")

    monkeypatch.setattr(skill_runner, "drive_subprocess", forbidden_spawn)

    result = skill_runner.run_skill(
        "fake-prep",
        demo=True,
        output_dir=str(tmp_path / "probe-failure"),
    )

    assert result.success is False
    assert result.error_kind == "contract_validator_failed"
    assert "runtime evidence probe failed" in result.stderr
    assert spawn_attempts == []


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["sync", "async"])
async def test_shared_runner_rejects_unsupported_unified_method_before_spawn(
    tmp_path: Path,
    monkeypatch,
    mode: str,
) -> None:
    skill_runner = _install_fake_demo_skill(monkeypatch, tmp_path)
    output_dir = tmp_path / f"unsupported-method-{mode}"
    spawn_attempts: list[list[str]] = []

    def forbidden_spawn(cmd, **_kwargs):
        spawn_attempts.append(list(cmd))
        raise AssertionError("unsupported method request reached subprocess spawn")

    async def forbidden_async_spawn(cmd, **_kwargs):
        spawn_attempts.append(list(cmd))
        raise AssertionError("unsupported method request reached subprocess spawn")

    monkeypatch.setattr(skill_runner, "drive_subprocess", forbidden_spawn)
    monkeypatch.setattr(skill_runner, "adrive_subprocess", forbidden_async_spawn)

    if mode == "sync":
        result = skill_runner.run_skill(
            "fake-prep",
            demo=True,
            output_dir=str(output_dir),
            extra_args=["--method", "tsne"],
        )
    else:
        result = await skill_runner.arun_skill(
            "fake-prep",
            demo=True,
            output_dir=str(output_dir),
            extra_args=["--method=tsne"],
        )

    assert result.success is False
    assert result.method is None
    assert "does not expose the unified --method flag" in result.stderr
    assert spawn_attempts == []
    assert not output_dir.exists()


def test_prepare_skill_run_honours_omicsclaw_run_python(tmp_path, monkeypatch):
    """The skill-subprocess interpreter must follow ``OMICSCLAW_RUN_PYTHON``.

    Regression: ``runner.py`` used to hardcode ``PYTHON = sys.executable`` and
    pass it to ``build_skill_argv``, so the documented override silently did
    nothing — skills always ran under whatever interpreter launched the server
    (e.g. base anaconda3 instead of the activated analysis env).
    """
    skill_runner = _install_fake_demo_skill(monkeypatch, tmp_path)

    # A real probe-capable selected interpreter is required by the producer
    # evidence contract; keep the fixture outside the Skill source inventory.
    fake_py = tmp_path / ".cache" / "analysis_env" / "bin" / "python"
    fake_py.parent.mkdir(parents=True)
    try:
        fake_py.symlink_to(sys.executable)
    except OSError:
        pytest.skip("runtime does not permit selected-interpreter symlink fixture")
    monkeypatch.setenv("OMICSCLAW_RUN_PYTHON", str(fake_py))

    prepared = _prepare(skill_runner, tmp_path)
    assert prepared.cmd[0] == str(fake_py.resolve())


def test_prepare_skill_run_defaults_to_sys_executable_without_override(
    tmp_path, monkeypatch
):
    skill_runner = _install_fake_demo_skill(monkeypatch, tmp_path)
    monkeypatch.delenv("OMICSCLAW_RUN_PYTHON", raising=False)

    prepared = _prepare(skill_runner, tmp_path)
    assert prepared.cmd[0] == sys.executable


@pytest.mark.parametrize(
    ("runtime_language", "interpreter"),
    [("bash", "bash"), ("r", "Rscript")],
)
def test_prepare_non_python_runtime_skips_adaptive_python_probe(
    tmp_path: Path,
    monkeypatch,
    runtime_language: str,
    interpreter: str,
) -> None:
    skill_runner = importlib.import_module("omicsclaw.skill.runner")
    suffix = ".sh" if runtime_language == "bash" else ".R"
    entry = tmp_path / f"non_python{suffix}"
    entry.write_text("# runtime is intercepted\n", encoding="utf-8")
    _install_fake_skills(
        monkeypatch,
        {
            "non-python": {
                "script": entry,
                "runtime_language": runtime_language,
                "domain": "demo",
                "demo_args": ["--demo"],
                "allowed_extra_flags": set(),
                "input_contract": {},
                "output_contract": {},
            }
        },
    )
    probes: list[str] = []

    def forbidden_probe(*_args, **_kwargs):
        probes.append("called")
        raise AssertionError("non-Python runtime must not use adaptive Python")

    monkeypatch.setattr(skill_runner, "resolve_skill_runtime", forbidden_probe)

    prepared = skill_runner._prepare_skill_run(
        "non-python",
        input_path=None,
        input_paths=None,
        output_dir=str(tmp_path / "run-output"),
        demo=True,
        session_path=None,
        extra_args=None,
        log_banner=False,
    )

    assert not isinstance(prepared, skill_runner.SkillRunResult)
    assert prepared.cmd[:2] == [interpreter, str(entry)]
    assert prepared.runtime_source == f"base/{runtime_language}"
    assert probes == []


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["sync", "async"])
async def test_missing_declared_runtime_interpreter_is_actionable_dependency_failure(
    tmp_path: Path,
    monkeypatch,
    mode: str,
) -> None:
    skill_runner = importlib.import_module("omicsclaw.skill.runner")
    entry = tmp_path / "missing_runtime.sh"
    entry.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    _install_fake_skills(
        monkeypatch,
        {
            "missing-runtime": {
                "script": entry,
                "runtime_language": "bash",
                "domain": "demo",
                "demo_args": ["--demo"],
                "allowed_extra_flags": set(),
                "input_contract": {},
                "output_contract": {},
            }
        },
    )

    def missing(*_args, **_kwargs):
        raise FileNotFoundError(2, "No such file or directory", "bash")

    async def async_missing(*_args, **_kwargs):
        raise FileNotFoundError(2, "No such file or directory", "bash")

    if mode == "sync":
        monkeypatch.setattr(skill_runner, "drive_subprocess", missing)
        result = skill_runner.run_skill(
            "missing-runtime",
            demo=True,
            output_dir=str(tmp_path / "missing-output"),
        )
    else:
        monkeypatch.setattr(skill_runner, "adrive_subprocess", async_missing)
        result = await skill_runner.arun_skill(
            "missing-runtime",
            demo=True,
            output_dir=str(tmp_path / "missing-output"),
        )

    assert result.success is False
    assert result.error_kind == "missing_dependency"
    assert result.runtime_source == "base/bash"
    assert "bash" in result.stderr
    assert "PATH" in result.stderr


def test_prepare_skill_run_isolates_user_site_by_default(tmp_path, monkeypatch):
    """Skill subprocesses must not inherit ``~/.local`` user-site packages.

    Regression: a broken ABI-mismatched ``~/.local`` torch shadowed the
    analysis env's torch, so CellCharter failed to import even under the
    correct interpreter.
    """
    skill_runner = _install_fake_demo_skill(monkeypatch, tmp_path)
    monkeypatch.delenv("PYTHONNOUSERSITE", raising=False)

    prepared = _prepare(skill_runner, tmp_path)
    assert prepared.env["PYTHONNOUSERSITE"] == "1"


def test_prepare_skill_run_does_not_add_an_empty_pythonpath_element(
    tmp_path,
    monkeypatch,
):
    """An absent inherited PYTHONPATH must not grant current-directory imports."""

    skill_runner = _install_fake_demo_skill(monkeypatch, tmp_path)
    monkeypatch.delenv("PYTHONPATH", raising=False)

    prepared = _prepare(skill_runner, tmp_path)

    assert prepared.env["PYTHONPATH"].split(os.pathsep) == [
        str(skill_runner.OMICSCLAW_DIR)
    ]


def test_prepare_skill_run_respects_explicit_pythonnousersite_optout(
    tmp_path, monkeypatch
):
    skill_runner = _install_fake_demo_skill(monkeypatch, tmp_path)
    monkeypatch.setenv("PYTHONNOUSERSITE", "0")

    prepared = _prepare(skill_runner, tmp_path)
    assert prepared.env["PYTHONNOUSERSITE"] == "0"
