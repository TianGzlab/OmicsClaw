"""The free-orchestration arm's system prompt is pinned, and equals the one the development runs saw.

A3 measures an agent with no product contract: its front matter is one empty
file, not whatever contract a deployment would read. The development runs
rendered their prompt in fresh workspaces with no front-matter files, before
the repository gained a contract file of its own; that render is kept as
``golden/a3_dev_prompt.txt`` (workspace, repository path, date and platform
normalised). The pinned prompt must equal it byte for byte, and over the golden
skill set equal the golden prompt; the unpinned prompt must now differ, which
is what shows the pin is doing something.
"""

from __future__ import annotations

import dataclasses
import platform
import sys
from datetime import date
from pathlib import Path

import pytest

from omicsclaw.entry import assembly
from tests.entry.test_ensemble_golden import PROMPT_FILE, _Offline

REPO = Path(__file__).resolve().parents[3]
FAKE_SKILLS = REPO / "tests" / "ensemble" / "fake_skills"
DEV_PROMPT = Path(__file__).resolve().parent / "golden" / "a3_dev_prompt.txt"
sys.path.insert(0, str(REPO / "docs" / "plans" / "0057-validation"))


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setattr(assembly, "provider_from_env", lambda provider, model: _Offline())


def _render(config) -> str:
    app = assembly.build_app(config)
    try:
        return app.prompt.render().system_prompt
    finally:
        if app.memory is not None:
            app.memory.close()


def _normalised(text: str, workspace: Path) -> str:
    text = text.replace(str(workspace), "<workspace>").replace(str(REPO), "<repo>")
    text = text.replace(date.today().isoformat(), "<today>")
    return text.replace(f"{platform.system()} ({sys.platform})", "<platform>")


def _pinned(tmp_path: Path, **kwargs):
    from run_arms import a3_config

    ws = (tmp_path / "ws").resolve()
    ws.mkdir()
    return a3_config(tmp_path.resolve(), ws, {"leiden": 60}, **kwargs), ws


def test_the_pin_is_one_empty_file_outside_the_workspace(tmp_path):
    config, ws = _pinned(tmp_path)
    (empty,) = config.system_prompt_files
    assert empty.read_text() == "" and ws not in empty.parents


def test_the_pinned_prompt_is_the_development_prompt(tmp_path, offline):
    config, ws = _pinned(tmp_path)
    assert _normalised(_render(config), ws) == DEV_PROMPT.read_text(encoding="utf-8")


def test_over_the_golden_skills_the_pinned_prompt_is_the_golden_prompt(tmp_path, offline):
    config, ws = _pinned(tmp_path, skills_dir=FAKE_SKILLS)
    assert _normalised(_render(config), ws) == PROMPT_FILE.read_text(encoding="utf-8")


def test_without_the_pin_the_front_matter_differs(tmp_path, offline):
    config, ws = _pinned(tmp_path)
    unpinned = _normalised(_render(dataclasses.replace(config, system_prompt_files=())), ws)
    assert unpinned != DEV_PROMPT.read_text(encoding="utf-8")
    assert len(unpinned) > len(DEV_PROMPT.read_text(encoding="utf-8"))
