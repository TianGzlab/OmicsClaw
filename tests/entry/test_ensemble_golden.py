"""The ``ensemble`` switch changes the tool table and nothing else.

The ablation baseline of the end-to-end benchmark is a deployment with
``ensemble=false``. For that comparison to measure the tools rather than a
prompt edit, the off deployment must be byte-identical to the deployment
that existed before ``run_skill`` was written, and the on deployment must
differ from it only by one tool definition inserted between
``memory_write`` and ``task``.

The golden files were written from the tree **before** the ensemble code
existed (``OMICSCLAW_WRITE_GOLDEN=1`` regenerates them; do that only for a
deliberate prompt or tool change, never to make this test pass). The
workspace path, the date and the platform line are normalised because they
belong to the machine running the test, not to the deployment.
"""

from __future__ import annotations

import json
import os
import platform
import sys
from datetime import date
from pathlib import Path

import pytest

from omicsclaw.entry import assembly
from omicsclaw.entry.config import AppConfig
from omicsclaw.provider import Completion
from omicsclaw.schema import Message, Role

GOLDEN = Path(__file__).resolve().parent / "golden"
PROMPT_FILE = GOLDEN / "ensemble_off_prompt.txt"
TOOLS_FILE = GOLDEN / "ensemble_off_tools.json"
FAKE_SKILLS = Path(__file__).resolve().parents[1] / "ensemble" / "fake_skills"


class _Offline:
    """A provider that is never called."""

    @property
    def name(self) -> str:
        return "offline"

    async def generate(self, messages, tools=None):
        return Completion(message=Message(role=Role.ASSISTANT, content=""))

    def generate_stream(self, messages, tools=None):
        raise NotImplementedError

    def bind(self, **overrides):
        return self


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setattr(assembly, "provider_from_env", lambda provider, model: _Offline())


def golden_config(workspace: Path, **overrides: object) -> AppConfig:
    """The fixed deployment the golden files describe."""
    return AppConfig(workspace=workspace, skills_dir=FAKE_SKILLS, **overrides)


def normalised_prompt(app, workspace: Path) -> str:
    text = app.prompt.render().system_prompt
    text = text.replace(str(workspace), "<workspace>")
    text = text.replace(date.today().isoformat(), "<today>")
    return text.replace(f"{platform.system()} ({sys.platform})", "<platform>")


def serialised_tools(definitions) -> list[dict]:
    return [
        {
            "name": definition.name,
            "description": definition.description,
            "input_schema": definition.input_schema,
        }
        for definition in definitions
    ]


def dump_tools(tools: list[dict]) -> str:
    return json.dumps(tools, indent=1, ensure_ascii=False) + "\n"


def _build(config: AppConfig, **kwargs):
    app = assembly.build_app(config, **kwargs)
    return app


def test_writing_the_golden_files(tmp_path, offline):
    """Regenerates the fixtures when asked to, and is a no-op otherwise."""
    if os.environ.get("OMICSCLAW_WRITE_GOLDEN") != "1":
        pytest.skip("set OMICSCLAW_WRITE_GOLDEN=1 to regenerate the golden files")
    app = _build(golden_config(tmp_path))
    try:
        GOLDEN.mkdir(exist_ok=True)
        PROMPT_FILE.write_text(normalised_prompt(app, tmp_path), encoding="utf-8")
        TOOLS_FILE.write_text(
            dump_tools(serialised_tools(app.registry.available_tools())),
            encoding="utf-8",
        )
    finally:
        if app.memory is not None:
            app.memory.close()


# ---- the assertions -----------------------------------------------------------------


def _runner(config: AppConfig):
    from omicsclaw.ensemble.resources import GpuDetection
    from omicsclaw.entry.ensemble import build_ensemble
    from omicsclaw.entry.sandbox import SandboxBinding

    skills = assembly.build_skill_index(config)
    runner = build_ensemble(config, skills, SandboxBinding(), gpus=GpuDetection((), "none"))
    assert runner is not None
    return runner


def _close(app) -> None:
    if app.memory is not None:
        app.memory.close()


def test_ensemble_off_is_byte_identical_to_the_golden_deployment(tmp_path, offline):
    app = _build(golden_config(tmp_path, ensemble=False))
    try:
        assert normalised_prompt(app, tmp_path) == PROMPT_FILE.read_text(encoding="utf-8")
        assert dump_tools(serialised_tools(app.registry.available_tools())) == TOOLS_FILE.read_text(
            encoding="utf-8"
        )
        assert app.ensemble is None
    finally:
        _close(app)


ENSEMBLE_TOOLS = {
    "all": ["run_skill", "inspect_trials", "select_result", "optimize_params"],
    "free": ["run_skill", "inspect_trials", "select_result"],
    "tuning": ["optimize_params"],
}
ALL_FILE = GOLDEN / "ensemble_tools_all.json"


def _ensemble_block(app):
    tools = serialised_tools(app.registry.available_tools())
    names = [tool["name"] for tool in tools]
    first = names.index("memory_write") + 1
    last = names.index("task")
    return tools, names[first:last], tools[:first] + tools[last:], tools[first:last]


@pytest.mark.parametrize("mode", ["all", "free", "tuning"])
@pytest.mark.parametrize("tissue", [True, False])
@pytest.mark.parametrize("budget", ["", "leiden:60,louvain:60,spagcn:12,graphst:12,cellcharter:12"])
@pytest.mark.parametrize("images", [False])
def test_every_ablation_switch_keeps_the_prompt_and_the_other_tools(tmp_path, offline, mode, tissue, budget, images):
    """The arms of the benchmark differ only in which ensemble tools exist.

    Whatever the tool mode, tissue switch or run budget, the system prompt is
    the golden one byte for byte and the tools outside the ensemble block are
    the golden list; within a mode, the descriptions do not depend on the
    other switches. (``ensemble_tuning_images=true`` refuses start-up and is
    covered in the config tests.)"""
    config = golden_config(
        tmp_path, ensemble=True, ensemble_tools=mode, ensemble_tuning_tissue=tissue,
        ensemble_run_budget=budget, ensemble_tuning_images=images,
    )
    app = _build(config, ensemble=_runner(config))
    try:
        assert normalised_prompt(app, tmp_path) == PROMPT_FILE.read_text(encoding="utf-8")
        _, block_names, outside, block = _ensemble_block(app)
        assert block_names == ENSEMBLE_TOOLS[mode]
        assert dump_tools(outside) == TOOLS_FILE.read_text(encoding="utf-8")
        reference = json.loads(ALL_FILE.read_text(encoding="utf-8"))
        by_name = {tool["name"]: tool for tool in reference}
        for tool in block:
            assert tool == by_name[tool["name"]], tool["name"]
    finally:
        _close(app)


def test_the_all_mode_golden_tools(tmp_path, offline):
    """Regenerated with OMICSCLAW_WRITE_GOLDEN=1 only for a deliberate tool change."""
    config = golden_config(tmp_path, ensemble=True)
    app = _build(config, ensemble=_runner(config))
    try:
        _, _, _, block = _ensemble_block(app)
        text = dump_tools(block).replace(str(tmp_path), "<workspace>")
        if os.environ.get("OMICSCLAW_WRITE_GOLDEN") == "1":
            ALL_FILE.write_text(text, encoding="utf-8")
        assert text == ALL_FILE.read_text(encoding="utf-8")
    finally:
        _close(app)


def test_ensemble_on_inserts_its_tools_between_memory_write_and_task(tmp_path, offline):
    config = golden_config(tmp_path, ensemble=True)
    app = _build(config, ensemble=_runner(config))
    try:
        assert normalised_prompt(app, tmp_path) == PROMPT_FILE.read_text(encoding="utf-8")
        _, names, outside, _ = _ensemble_block(app)
        assert names == ENSEMBLE_TOOLS["all"]
        assert dump_tools(outside) == TOOLS_FILE.read_text(encoding="utf-8")
        assert app.ensemble is not None
    finally:
        _close(app)


class _FakeMCP:
    """Stands in for a started MCP manager with one tool."""

    def tools(self):
        from omicsclaw.tools.function_tool import FunctionTool

        return (FunctionTool("mcp__demo__echo", "echo", lambda text="": text),)

    async def aclose(self):
        return None


def test_run_skill_comes_before_every_mcp_tool(tmp_path, offline):
    config = golden_config(tmp_path, ensemble=True)
    app = _build(config, ensemble=_runner(config), mcp=_FakeMCP())
    try:
        names = [d.name for d in app.registry.available_tools()]
        assert names[-7:] == [
            "memory_write", "run_skill", "inspect_trials", "select_result", "optimize_params",
            "mcp__demo__echo", "task",
        ]
    finally:
        _close(app)
