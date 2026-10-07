"""A delegated review reaches acceptance without a model copying its text."""

import asyncio
import json

import pytest

from omicsclaw.entry import AppConfig, build_app
from omicsclaw.schema import Message, ToolCall
from tests.entry.test_turn_runner import Scripted
from tests.sdk.notebook.conftest import InProcessRunner, Project
from tests.sdk.notebook.test_acceptance import _replayed, _report


def test_desktop_review_requires_a_click_for_each_turn(tmp_path):
    from omicsclaw.entry.desktop.server import open_chat_stream
    from omicsclaw.entry.session import attach_sessions
    from omicsclaw.provider import Completion
    from omicsclaw.schema import Role

    project = Project(tmp_path, InProcessRunner())
    module = _replayed(project)
    _report(project, module)

    class WantsReview(Scripted):
        reviews = 0

        async def generate(self, messages, tools=None):
            if any("You review one analysis module" in m.content for m in messages):
                self.reviews += 1
                return Completion(message=Message.assistant("VERDICT: APPROVE\nOK"))
            if messages[-1].role == Role.USER:
                return Completion(message=Message(
                    role=Role.ASSISTANT,
                    tool_calls=(ToolCall(id="review", name="task", arguments=json.dumps({
                        "subagent_type": "module-reviewer", "review_module": module,
                        "prompt": f"Review module {module}.",
                    })),),
                ))
            return Completion(message=Message.assistant("Finished."))

    async def drive():
        provider = WantsReview()
        app = build_app(AppConfig(workspace=tmp_path, memory=False), provider=provider)
        app = attach_sessions(app)
        try:
            for index, requested in enumerate((False, True, False), 1):
                document = {
                    "ingress_schema_version": 3, "session_id": "review-click",
                    "source_request_id": f"{index:032x}", "content": "Check this result.",
                }
                if requested:
                    document["module_review_requested"] = True
                stream = await open_chat_stream(app, document)
                frames = [frame async for frame in stream.body]
                assert any('"done"' in frame for frame in frames)
                assert provider.reviews == (0 if index == 1 else 1)
                if not requested:
                    assert any("Independent review" in frame for frame in frames)
        finally:
            await app.aclose()

    asyncio.run(asyncio.wait_for(drive(), 10))


@pytest.mark.parametrize("value", [None, 1, "true", {}, []])
def test_desktop_review_flag_must_be_boolean(value):
    from omicsclaw.entry.desktop.turn_submission import (
        DesktopIngressError, decode_chat_stream_request,
    )

    with pytest.raises(DesktopIngressError, match="invalid_module_review_requested"):
        decode_chat_stream_request({
            "ingress_schema_version": 3, "source_request_id": "1" * 32,
            "content": "Review", "module_review_requested": value,
        })


@pytest.mark.parametrize("edited", [None, "review", "report", "receipt", "replay", "archive", "malformed", "receipt_escape"])
def test_task_archives_the_exact_review_and_accept_uses_it(tmp_path, edited):
    project = Project(tmp_path, InProcessRunner())
    module = _replayed(project)
    _report(project, module)
    raw = "VERDICT: APPROVE\n\n检查通过：A–B，α/β。\n"

    async def drive():
        app = build_app(AppConfig(workspace=tmp_path, memory=False),
                        provider=Scripted(Message.assistant(raw)))
        try:
            return await app.registry.execute(ToolCall(id="review", name="task", arguments=json.dumps({
                "subagent_type": "module-reviewer", "review_module": module,
                "prompt": f"Review analysis/{module}.",
            })))
        finally:
            await app.aclose()

    result = asyncio.run(drive())
    assert not result.is_error, result.output
    saved = list((tmp_path / "results" / module / "reviews").glob("task-review-*.md"))
    assert len(saved) == 1
    assert saved[0].read_bytes() == raw.encode("utf-8")
    relative = saved[0].relative_to(tmp_path).as_posix()
    assert relative in result.output
    if edited == "review":
        saved[0].write_text(raw.replace("–", "-"), encoding="utf-8")
        assert project.accept(f"analysis/{module}", review=relative) == 4, project.text
        assert "review text changed" in project.text
    elif edited == "report":
        _report(project, module, "# Changed conclusion\n\n" + (tmp_path / "results" / module / "M01_m_REPORT.md").read_text())
        assert project.accept(f"analysis/{module}", review=relative) == 4, project.text
        assert "reviewed files changed" in project.text
    elif edited == "receipt":
        saved[0].with_suffix(".json").unlink()
        assert project.accept(f"analysis/{module}", review=relative) == 4, project.text
        assert "receipt is missing or invalid" in project.text
    elif edited == "replay":
        manifest = tmp_path / "results" / module / "provenance" / "manifest.json"
        state = json.loads(manifest.read_text())
        state["replay"]["new_interpreter_reason"] = "different replay"
        manifest.write_text(json.dumps(state))
        assert project.accept(f"analysis/{module}", review=relative) == 4, project.text
        assert "different replay" in project.text
    elif edited == "archive":
        assert project.replay(f"analysis/{module}") == 0, project.text
        archived = list(saved[0].parent.glob(f"archive/*/{saved[0].name}"))
        assert len(archived) == 1
        assert archived[0].with_suffix(".json").is_file()
        assert project.accept(f"analysis/{module}", review=str(archived[0])) == 4
    elif edited == "malformed":
        sidecar = saved[0].with_suffix(".json")
        record = json.loads(sidecar.read_text())
        record["files"] = list(record["files"])
        sidecar.write_text(json.dumps(record))
        assert project.accept(f"analysis/{module}", review=relative) == 4, project.text
    elif edited == "receipt_escape":
        sidecar = saved[0].with_suffix(".json")
        outside = tmp_path / "receipt-copy.json"
        sidecar.rename(outside)
        sidecar.symlink_to(outside)
        assert project.accept(f"analysis/{module}", review=relative) == 4, project.text
    else:
        assert project.accept(f"analysis/{module}", review=relative) == 0, project.text


@pytest.mark.parametrize("case", ["revise", "malformed", "changed", "outside", "missing_module"])
def test_task_cannot_supply_an_acceptance_review_for_invalid_inputs(tmp_path, case):
    project = Project(tmp_path, InProcessRunner())
    module = _replayed(project)
    report = _report(project, module)
    text = "VERDICT: REVISE\nCheck table 1.\n" if case == "revise" else "VERDICT: APPROVE\nok\n"
    if case == "malformed":
        text = "I approve this module."
    selected = "../escape" if case == "outside" else module

    class Reviewer(Scripted):
        async def generate(self, messages, tools=None):
            if case == "changed":
                report.write_text(report.read_text() + "\nA new conclusion.\n")
            return await super().generate(messages, tools)

    async def drive():
        app = build_app(AppConfig(workspace=tmp_path, memory=False), provider=Reviewer(Message.assistant(text)))
        payload = {"subagent_type": "module-reviewer", "review_module": selected, "prompt": "Review module 01_m."}
        if case == "missing_module":
            payload["review_module"] = "02_absent"
        try:
            return await app.registry.execute(ToolCall(id="review", name="task", arguments=json.dumps(payload)))
        finally:
            await app.aclose()

    result = asyncio.run(drive())
    saved = list((tmp_path / "results" / module / "reviews").glob("task-review-*.md"))
    if case == "revise":
        assert not result.is_error, result.output
        assert len(saved) == 1
        assert saved[0].read_text() == text
        assert project.accept(f"analysis/{module}", review=str(saved[0])) == 4
    else:
        assert result.is_error, result.output
        assert not saved
