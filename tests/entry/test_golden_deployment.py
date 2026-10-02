"""The system prompt and the tool table of one fixed deployment, byte for byte.

The golden files describe the deployment :func:`golden_config` builds: a
workspace with one fixture skill and every other setting at its default.
A change to the assembled prompt or to any tool definition shows up here as
a diff. Regenerate the files with ``OMICSCLAW_WRITE_GOLDEN=1`` only for a
deliberate prompt or tool change, never to make this test pass. The
workspace path, the date and the platform line are normalised because they
belong to the machine running the test, not to the deployment.

Other tests import :func:`golden_config`, the serialisers and the offline
provider from here, so a deployment they build can be compared with the same
files.
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
PROMPT_FILE = GOLDEN / "deployment_prompt.txt"
TOOLS_FILE = GOLDEN / "deployment_tools.json"
FAKE_SKILLS = Path(__file__).resolve().parent / "fake_skills"


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


def _close(app) -> None:
    if app.memory is not None:
        app.memory.close()


def test_writing_the_golden_files(tmp_path, offline):
    """Regenerates the fixtures when asked to, and is a no-op otherwise."""
    if os.environ.get("OMICSCLAW_WRITE_GOLDEN") != "1":
        pytest.skip("set OMICSCLAW_WRITE_GOLDEN=1 to regenerate the golden files")
    app = assembly.build_app(golden_config(tmp_path))
    try:
        GOLDEN.mkdir(exist_ok=True)
        PROMPT_FILE.write_text(normalised_prompt(app, tmp_path), encoding="utf-8")
        TOOLS_FILE.write_text(
            dump_tools(serialised_tools(app.registry.available_tools())),
            encoding="utf-8",
        )
    finally:
        _close(app)


def test_the_deployment_is_byte_identical_to_the_golden_files(tmp_path, offline):
    app = assembly.build_app(golden_config(tmp_path))
    try:
        assert normalised_prompt(app, tmp_path) == PROMPT_FILE.read_text(encoding="utf-8")
        assert dump_tools(serialised_tools(app.registry.available_tools())) == TOOLS_FILE.read_text(
            encoding="utf-8"
        )
    finally:
        _close(app)
