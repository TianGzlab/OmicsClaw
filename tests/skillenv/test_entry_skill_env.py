"""How a deployment wires the environment check (plan 0061 cases 6b and 12, §4.10).

``skill_env`` is ``off``, ``probe`` (the default) or ``install``; the last is
covered by ``test_install_wiring.py``. Neither ``off`` nor ``probe`` changes the system prompt
or the tool definitions — the note rides on ``use_skill``'s *result* — so the
golden files of the fixed deployment (``tests/entry/golden/deployment_*``)
describe both. ``off`` leaves ``use_skill``'s output
byte-identical; read-only mode gets no note, because ``bash`` is refused
there anyway. An unreadable registry only degrades the note in ``probe``
mode.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

import pytest

from omicsclaw.entry import assembly
from omicsclaw.entry.config import AppConfig, AppConfigError, SkillEnvMode, resolve_app_config
from omicsclaw.entry.sandbox import SandboxBinding
from omicsclaw.entry.skill_env import build_skill_env, log_skill_env
from omicsclaw.permission import PermissionMode
from omicsclaw.skillenv.probe import LocalProbeRunner, SandboxProbeRunner
from omicsclaw.tools.builtin.bash import CommandOutcome
from tests.entry.test_golden_deployment import (
    PROMPT_FILE,
    TOOLS_FILE,
    dump_tools,
    golden_config,
    normalised_prompt,
    serialised_tools,
)

from .conftest import FIXTURE_SKILLS, FIXTURES


@pytest.fixture
def offline(monkeypatch):
    from tests.entry.test_golden_deployment import _Offline

    monkeypatch.setattr(assembly, "provider_from_env", lambda provider, model: _Offline())


def _close(app) -> None:
    if app.memory is not None:
        app.memory.close()


# ---- configuration --------------------------------------------------------------------------


def test_the_default_is_probe(tmp_path):
    assert AppConfig(workspace=tmp_path).skill_env is SkillEnvMode.PROBE


@pytest.mark.parametrize("raw", ["off", "probe", "PROBE"])
def test_known_values_parse(raw, tmp_path):
    config = resolve_app_config(["--skill-env", raw], {}, workspace=tmp_path)
    assert config.skill_env.value == raw.lower()
    from_env = resolve_app_config([], {"OMICSCLAW_SKILL_ENV": raw}, workspace=tmp_path)
    assert from_env.skill_env == config.skill_env


@pytest.mark.parametrize("raw", ["on", ""])
def test_other_values_are_refused(raw, tmp_path):
    with pytest.raises(AppConfigError, match="not a skill_env mode"):
        resolve_app_config(["--skill-env", raw], {}, workspace=tmp_path)


def test_install_is_accepted_and_starts(tmp_path, offline):
    """Plan 0061 P2 lifted the P1 refusal; no package-source setting is needed (version 7.2, Q26 void)."""
    config = resolve_app_config(["--skill-env", "install", "--skills-dir", str(FIXTURE_SKILLS),
                                 "--skill-env-dir", str(tmp_path / "envs")],
                                {}, workspace=tmp_path)
    assert config.skill_env is SkillEnvMode.INSTALL
    app = assembly.build_app(config)
    try:
        assert "install_skill_deps" in [d.name for d in app.registry.available_tools()]
    finally:
        _close(app)


# ---- the prompt and the tool table do not move ----------------------------------------------


@pytest.mark.parametrize("mode", [SkillEnvMode.OFF, SkillEnvMode.PROBE])
def test_prompt_and_tools_equal_the_golden_deployment(tmp_path, offline, mode):
    app = assembly.build_app(golden_config(tmp_path, skill_env=mode))
    try:
        assert normalised_prompt(app, tmp_path) == PROMPT_FILE.read_text(encoding="utf-8")
        assert dump_tools(serialised_tools(app.registry.available_tools())) == TOOLS_FILE.read_text(
            encoding="utf-8"
        )
    finally:
        _close(app)


def _use_skill(app) -> str:
    """Call the mounted ``use_skill`` directly, below the permission gate's approval flow."""
    return asyncio.run(app.registry.get("use_skill").execute(json.dumps({"skill_name": "demo-skill"})))


def _config(tmp_path: Path, **overrides) -> AppConfig:
    return AppConfig(workspace=tmp_path, skills_dir=FIXTURE_SKILLS, **overrides)


def test_off_leaves_use_skill_byte_identical(tmp_path, offline):
    app = assembly.build_app(_config(tmp_path, skill_env=SkillEnvMode.OFF))
    try:
        out = _use_skill(app).replace(str(FIXTURE_SKILLS.resolve()), "<root>")
        assert out == (FIXTURES / "golden" / "use_skill_off.txt").read_text(encoding="utf-8")
        assert app.skill_env is None
    finally:
        _close(app)


def test_probe_appends_the_note_end_to_end(tmp_path, offline):
    app = assembly.build_app(_config(tmp_path))
    try:
        out = _use_skill(app)
        plain = (FIXTURES / "golden" / "use_skill_off.txt").read_text(encoding="utf-8")
        assert out.replace(str(FIXTURE_SKILLS.resolve()), "<root>").startswith(plain)
        note = out.split("Skill directory:", 1)[1]
        assert "Environment check (the `python` bash runs here:" in note
        assert "oc-missing-pkg (import oc_missing_pkg)" in note
        assert "or the conda env `omicsclaw_banksy`" in note
        assert "R package, not checked here" in note
    finally:
        _close(app)


def test_read_only_gets_no_note(tmp_path, offline):
    app = assembly.build_app(_config(tmp_path, permission_mode=PermissionMode.READ_ONLY))
    try:
        out = _use_skill(app).replace(str(FIXTURE_SKILLS.resolve()), "<root>")
        assert out == (FIXTURES / "golden" / "use_skill_off.txt").read_text(encoding="utf-8")
    finally:
        _close(app)


def test_skills_index_off_builds_nothing(tmp_path):
    from omicsclaw.entry.config import SkillsIndex

    config = _config(tmp_path, skills_index=SkillsIndex.OFF)
    assert build_skill_env(config, assembly.build_skill_index(config), SandboxBinding()) is None


# ---- where the probe runs --------------------------------------------------------------------


class _FakeEnvironment:
    def __init__(self, output: str):
        self.output = output
        self.calls: list[str] = []

    async def run_bash(self, command, cwd, timeout):
        self.calls.append(command)
        return CommandOutcome(output=self.output, exit_code=0)


def _probe_json(executable: str, missing=()) -> str:
    return json.dumps({"executable": executable, "version": "3.11.15", "prefix": "/p", "base_prefix": "/p",
                       "user_site_enabled": False, "missing": list(missing), "from_user_site": [], "versions": {}})


def test_local_and_sandbox_bindings_pick_their_runner(tmp_path):
    config = _config(tmp_path)
    skills = assembly.build_skill_index(config)
    assert isinstance(build_skill_env(config, skills, SandboxBinding()).runner, LocalProbeRunner)
    environment = _FakeEnvironment(_probe_json("/usr/bin/python3"))
    boxed = build_skill_env(config, skills, SandboxBinding(environment=environment))
    assert isinstance(boxed.runner, SandboxProbeRunner)
    skill = skills.get("demo-skill")
    note = asyncio.run(boxed.annotate(skill, skills.get_full_content("demo-skill")))
    assert environment.calls and "the `python` bash runs in the sandbox: /usr/bin/python3" in note


# ---- an unreadable registry (case 6b) ---------------------------------------------------------


def test_an_unreadable_registry_degrades_the_note_in_probe_mode(tmp_path, caplog):
    root = tmp_path / "skills"
    target = root / "demo" / "demo-skill"
    target.mkdir(parents=True)
    (target / "SKILL.md").write_text((FIXTURE_SKILLS / "demo" / "demo-skill" / "SKILL.md").read_text())
    config = AppConfig(workspace=tmp_path, skills_dir=root)
    skills = assembly.build_skill_index(config)
    with caplog.at_level(logging.WARNING, logger="omicsclaw.entry.skill_env"):
        binding = build_skill_env(config, skills, SandboxBinding())
    assert binding is not None and binding.registry_error
    assert any("dependency registry unreadable" in r.getMessage() for r in caplog.records)
    note = asyncio.run(binding.annotate(skills.get("demo-skill"), skills.get_full_content("demo-skill")))
    lines = note.splitlines()
    assert lines[1].startswith("dependency registry unreadable: ")
    assert "not an OmicsClaw skills tree" in lines[1]
    assert "Missing" in note


def test_an_unreadable_registry_is_kept_when_the_probe_fails(tmp_path):
    class _Failing:
        location = "local"

        async def run(self, command, *, cwd, timeout, env=None):
            return 1, "python: command not found"

    root = tmp_path / "skills"
    target = root / "demo" / "demo-skill"
    target.mkdir(parents=True)
    (target / "SKILL.md").write_text((FIXTURE_SKILLS / "demo" / "demo-skill" / "SKILL.md").read_text())
    config = AppConfig(workspace=tmp_path, skills_dir=root)
    skills = assembly.build_skill_index(config)
    binding = build_skill_env(config, skills, SandboxBinding())
    binding = type(binding)(**{**{f: getattr(binding, f) for f in binding.__dataclass_fields__},
                               "runner": _Failing()})
    import omicsclaw.entry.skill_env as module

    note = asyncio.run(module._annotator(binding)(skills.get("demo-skill"), skills.get_full_content("demo-skill")))
    lines = note.splitlines()
    assert lines[1].startswith("dependency registry unreadable: ")
    assert lines[2].startswith("Environment check unavailable: the probe exited with status 1")


# ---- the start-up line and the interpreter warning -------------------------------------------


def test_the_startup_line_names_mode_location_and_python(tmp_path, caplog):
    config = _config(tmp_path)
    binding = build_skill_env(config, assembly.build_skill_index(config), SandboxBinding())
    with caplog.at_level(logging.INFO, logger="omicsclaw.entry.skill_env"):
        asyncio.run(log_skill_env(binding, config))
    messages = [r.getMessage() for r in caplog.records]
    assert any(m.startswith("skill_env=probe location=local python=/") for m in messages)


def test_a_different_bash_python_is_warned_about(tmp_path, caplog):
    config = _config(tmp_path)
    environment = _FakeEnvironment(_probe_json("/elsewhere/bin/python"))
    skills = assembly.build_skill_index(config)
    binding = build_skill_env(config, skills, SandboxBinding())
    binding = type(binding)(**{**{f: getattr(binding, f) for f in binding.__dataclass_fields__},
                               "runner": SandboxProbeRunner(environment), "location": "local"})
    with caplog.at_level(logging.INFO, logger="omicsclaw.entry.skill_env"):
        asyncio.run(log_skill_env(binding, config))
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any("/elsewhere/bin/python" in w and sys.executable in w for w in warnings)


def test_matching_interpreters_are_not_warned_about(tmp_path, caplog):
    config = _config(tmp_path)
    environment = _FakeEnvironment(_probe_json(sys.executable))
    skills = assembly.build_skill_index(config)
    binding = build_skill_env(config, skills, SandboxBinding())
    binding = type(binding)(**{**{f: getattr(binding, f) for f in binding.__dataclass_fields__},
                               "runner": SandboxProbeRunner(environment), "location": "local"})
    with caplog.at_level(logging.INFO, logger="omicsclaw.entry.skill_env"):
        asyncio.run(log_skill_env(binding, config))
    assert not [r for r in caplog.records if r.levelno == logging.WARNING]
