"""Slash commands, after the globals they used to read were deleted.

The registry crossed from ``omicsclaw/surfaces/channels/commands/`` almost
unchanged; the handler bodies did not. Every one of them read something out
of the deleted ``omicsclaw.runtime.agent.state`` — a transcript store, a
data directory, a provider name — and each now reads the same fact off the
assembled :class:`~omicsclaw.entry.assembly.AgentApp`.

Three commands were removed rather than reconnected (``/forget``,
``/compact``, ``/plan``), and the test that matters most in this file is the
one asserting ``/help`` does not still advertise them: a help text is the
one place a stale list is read by exactly the person it misleads.
"""

from __future__ import annotations

import asyncio

from omicsclaw.context import CompactionState
from omicsclaw.entry.channel.base import Channel
from omicsclaw.entry.channel.commands import (
    SlashCommandContext,
    dispatch,
    registered_commands,
)
from omicsclaw.entry.channel.runtime import VALUE_REPLY_TARGET
from omicsclaw.entry.ingress import InboundMessage
from tests.entry.test_channel_ingress import (  # type: ignore[import-not-found]
    OWNER,
    Transport,
    binding_for,
    deployment,
)
from omicsclaw.entry.channel.runtime import ChannelRuntime

WAIT_S = 5.0

EXPECTED = (
    "/clear",
    "/compact",
    "/demo",
    "/examples",
    "/files",
    "/help",
    "/new",
    "/outputs",
    "/recent",
    "/skills",
    "/status",
    "/version",
)


def run(coro):
    return asyncio.run(asyncio.wait_for(coro, WAIT_S))


def context(app=None, *, text: str, session_id: str = "feishu:c1", workspace=""):
    return SlashCommandContext(
        chat_id="c1",
        user_id=OWNER,
        platform="feishu",
        user_text=text,
        workspace=str(workspace or (app.config.workspace if app else "")),
        app=app,
        session_id=session_id,
    )


def test_the_registered_set_is_exactly_what_survived_the_port():
    """Named, not counted. A count tells you something changed, not what."""
    assert registered_commands() == EXPECTED


def test_the_two_blocked_commands_are_absent():
    """``/forget`` touches the memory layer, which is not in this step.

    Half of a "complete reset" is worse than none: the person asked for
    their memory to be deleted and would be told it was. ``/compact`` was
    the third until plan 0035 gave it a lane-serialized implementation.
    """
    for name in ("/forget", "/plan"):
        assert name not in registered_commands()


def test_help_advertises_exactly_what_is_registered(tmp_path):
    """Generated from the registry, so it cannot drift from it."""
    reply = run(dispatch(context(text="/help")))

    assert reply is not None
    for name in registered_commands():
        assert f"- {name}" in reply
    for name in ("/forget", "/plan"):
        assert name not in reply


def test_anything_that_is_not_a_command_falls_through(tmp_path):
    """``None`` means "hand it to the agent", which is the common path."""
    assert run(dispatch(context(text="analyse this slide"))) is None
    assert run(dispatch(context(text="/nonesuch"))) is None


def test_commands_are_matched_case_insensitively(tmp_path):
    assert run(dispatch(context(text="  /HELP  "))) is not None


def test_skills_reports_the_index_this_deployment_loaded(tmp_path):
    """The same scan the system prompt was built from, not a second one."""

    async def scenario():
        app = deployment(tmp_path)[0]
        return await dispatch(context(app, text="/skills"))

    reply = run(scenario())

    assert reply == "No skills are loaded in this deployment."


def test_skills_renders_the_domain_summary_when_there_are_skills(tmp_path):
    """One scan, two readers: this and the prompt section must agree."""

    async def scenario():
        skills = tmp_path / "skills" / "spatial" / "spatial-de"
        skills.mkdir(parents=True)
        (skills / "SKILL.md").write_text(
            "---\nname: spatial-de\ndescription: Differential expression.\n---\n",
            encoding="utf-8",
        )
        app = deployment(tmp_path)[0]
        return app, await dispatch(context(app, text="/skills"))

    app, reply = run(scenario())

    assert len(app.skills) == 1
    assert reply == app.skills.domain_summary()
    assert "spatial-de" in reply


def test_status_reports_the_assembled_deployment(tmp_path):
    """What was actually wired, not what a module global once said."""

    async def scenario():
        app = deployment(tmp_path)[0]
        return app, await dispatch(context(app, text="/status"))

    app, reply = run(scenario())

    assert reply is not None
    assert "Uptime:" in reply
    assert f"Provider: {app.provider.name}" in reply
    assert f"Tools available: {len(app.tools_snapshot)}" in reply
    assert str(app.config.workspace) in reply


def test_status_without_a_deployment_says_so_rather_than_raising(tmp_path):
    """A command handler raising lands inside a vendor SDK's callback."""
    reply = run(dispatch(context(text="/status")))

    assert reply is not None
    assert "not bound to a deployment" in reply


def test_clear_empties_the_conversation_this_message_came_from(tmp_path):
    """And the carried summary with it.

    Keeping the compaction state over a cleared history would leave the
    next exchange summarising a conversation that no longer exists — and
    the summary is the half the model reads.
    """

    async def scenario():
        app, _spy = deployment(tmp_path)
        runtime = ChannelRuntime(app, [binding_for(Transport())])
        await runtime.start()
        result = await runtime.submit(
            InboundMessage(
                text="hello",
                session_id="feishu:c1",
                source_request_id="r1",
                sender=OWNER,
                surface="feishu",
                values={
                    VALUE_REPLY_TARGET: {"adapter": "feishu", "destination_id": "c1"}
                },
            )
        )
        assert result.handle is not None
        await result.handle.wait()
        session = app.sessions.session("feishu:c1")
        assert session is not None and session.history, "nothing to clear"
        # A summary the previous compaction left behind. Planted rather than
        # earned: one short exchange never triggers compaction, and without
        # it this test cannot tell a ``/clear`` that keeps the summary from
        # one that drops it — measured, that mutation survived.
        session.compaction = CompactionState(summary="they discussed a slide")
        reply = await dispatch(context(app, text="/clear"))
        await runtime.close(WAIT_S)
        return reply, session

    reply, session = run(scenario())

    assert reply == "Conversation history cleared."
    assert session.history == ()
    assert session.compaction.summary == ""


def test_clear_without_a_conversation_says_so(tmp_path):
    async def scenario():
        app = deployment(tmp_path)[0]
        return await dispatch(context(app, text="/clear", session_id=""))

    assert "not in one" in run(scenario())


def test_files_and_outputs_answer_rather_than_raise_on_an_empty_workspace(tmp_path):
    """Both were wrapped in bare ``except`` clauses; both now report.

    A missing directory is the ordinary state of a fresh deployment, not an
    error worth a traceback in a chat window.
    """

    async def scenario():
        app = deployment(tmp_path)[0]
        return (
            await dispatch(context(app, text="/files")),
            await dispatch(context(app, text="/outputs")),
            await dispatch(context(app, text="/recent")),
        )

    files, outputs, recent = run(scenario())

    assert "data" in files
    assert "output" in outputs
    assert recent == "No recent analyses found."


def test_files_lists_what_is_in_the_data_directory(tmp_path):
    async def scenario():
        data = tmp_path / "data"
        data.mkdir()
        (data / "visium.h5ad").write_bytes(b"x" * 2048)
        app = deployment(tmp_path)[0]
        return await dispatch(context(app, text="/files"))

    reply = run(scenario())

    assert "visium.h5ad" in reply
    assert "MB" in reply


def _module(root, name, *, status=None, report=None, modified=None):
    import json
    import os

    results = root / "results" / name
    (results / "provenance").mkdir(parents=True)
    if status is not None:
        (results / "provenance" / "manifest.json").write_text(json.dumps({"status": status}), encoding="utf-8")
    if report is not None:
        nn, slug = name.split("_", 1)
        (results / f"M{nn}_{slug}_REPORT.md").write_text(report, encoding="utf-8")
    if modified is not None:
        target = results / "provenance" / "manifest.json" if status is not None else results
        os.utime(target, (modified, modified))


def test_recent_lists_the_newest_modules_with_status_and_report_headline(tmp_path):
    _module(tmp_path, "01_qc", status="accepted", report="# QC of PBMC3k\nbody\n", modified=1_000)
    _module(tmp_path, "02_preprocess", status="replayed", report="intro\n# Preprocessing\n", modified=2_000)
    _module(tmp_path, "03_clustering", status="draft", modified=3_000)
    _module(tmp_path, "04_annotation", modified=4_000)
    (tmp_path / "results" / "_archive").mkdir()

    async def scenario():
        app = deployment(tmp_path)[0]
        return await dispatch(context(app, text="/recent"))

    reply = run(scenario())

    assert reply.startswith("Last 3 analyses:")
    assert reply.index("04_annotation") < reply.index("03_clustering") < reply.index("02_preprocess")
    assert "01_qc" not in reply and "_archive" not in reply
    assert "02_preprocess [REPLAYED]" in reply and "Preprocessing" in reply
    assert "03_clustering [DRAFT]" in reply and "No report yet" in reply


def test_recent_ignores_old_output_runs(tmp_path):
    async def scenario():
        run_dir = tmp_path / "output" / "run-1"
        run_dir.mkdir(parents=True)
        (run_dir / "report.md").write_text("# Spatial domains identified\n", encoding="utf-8")
        app = deployment(tmp_path)[0]
        return await dispatch(context(app, text="/recent"))

    assert run(scenario()) == "No recent analyses found."


def test_version_counts_the_deployment_rather_than_asserting_a_number(tmp_path):
    async def scenario():
        app = deployment(tmp_path)[0]
        return app, await dispatch(context(app, text="/version"))

    app, reply = run(scenario())

    assert f"Tools: {len(app.tools_snapshot)}" in reply
    assert f"Skills: {len(app.skills)}" in reply


# ---- the context every adapter assembles the same way ------------------


def test_the_shared_context_carries_the_session_the_two_stateful_commands_act_on(
    tmp_path,
):
    """``/clear`` and ``/compact`` act on a conversation, or on nothing.

    ``SlashCommandContext.session_id`` defaults to the empty string, which
    those two handlers read as "there is no conversation" and report as
    success. An adapter that assembled its own context and forgot the field
    would therefore answer ``/clear`` cheerfully, with the history intact —
    which is why the assembly is shared rather than copied per platform.
    """

    async def scenario():
        app, _spy = deployment(tmp_path)
        channel = _StubChannel()
        runtime = ChannelRuntime(app, [binding_for(Transport(), adapter="stub")])
        await runtime.start()
        channel.bind_control_runtime(runtime)
        ctx = channel.command_context("c1", OWNER, "/clear")
        await runtime.close(0.0)
        return app, ctx

    app, ctx = run(scenario())

    assert ctx.session_id == "stub:c1"
    assert ctx.platform == "stub"
    assert ctx.chat_id == "c1"
    assert ctx.user_id == OWNER
    assert ctx.app is app
    assert ctx.workspace == str(app.config.workspace)


def test_an_unbound_channel_still_assembles_a_context():
    """So the static commands answer before a runtime exists.

    A handler that needs the deployment says so in its reply; raising here
    instead would surface inside a provider callback, where nobody sees it.
    """
    ctx = _StubChannel().command_context("c1", None, "/help")

    assert ctx.app is None
    assert ctx.workspace == ""
    assert ctx.session_id == "stub:c1"


class _StubChannel(Channel):
    """A real ``Channel`` with no platform, for the base-class behaviour."""

    name = "stub"

    async def start(self) -> None:  # pragma: no cover - never started
        self._running = True

    async def stop(self) -> None:  # pragma: no cover - never started
        self._running = False
