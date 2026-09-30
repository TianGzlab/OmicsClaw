"""The Desktop return channels: ``/chat/permission``, ``/chat/abort``, ``/workspace``.

Everything here runs the route logic as plain ``async`` functions on the
same event loop as a live ``/chat/stream`` body, which is the only way to
test a decision that arrives *while* a stream is open: Starlette's
``TestClient`` buffers a streaming response to its end before returning,
so a test that POSTs through it while a stream waits for that POST can
never finish. ``test_desktop_http.py`` covers the HTTP shapes, plus one
interleaved run against a real uvicorn.

The app is the real composition root over a scripted backend and tools
that ask, sleep or report, so the approvals and cancellations below travel
through the real registry, turn kernel, engine and approval broker.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import pathlib
from types import SimpleNamespace
from typing import Any, Awaitable, Callable

import pytest

from omicsclaw.entry.desktop.interactions import (
    DENIED_REASON,
    DesktopInteractions,
    TurnUsage,
    abort_chat,
    answer_permission,
    change_permission_profile,
)
from omicsclaw.entry.desktop.server import (
    change_workspace,
    open_chat_stream,
    workspace_payload,
)
from omicsclaw.entry.desktop.turn_submission import DesktopIngressError
from omicsclaw.entry.events import TurnEvent, TurnEventType
from omicsclaw.entry.session import attach_sessions
from omicsclaw.entry.turn import TurnHandle
from omicsclaw.schema import Message, Role, ToolCall, ToolDefinition
from omicsclaw.tools import ApprovalMode, ApprovalRequest, ToolPolicy
from tests.entry.test_desktop_stream import Paused
from tests.entry.test_turn_runner import (  # type: ignore[import-not-found]
    Asking,
    Scripted,
    Sleeping,
    calling,
    make_app,
)

WAIT_S = 5.0
KEY = "a" * 32
OTHER_KEY = "b" * 32
DONE = Message(role=Role.ASSISTANT, content="done")


class Insistent(Asking):
    """A tool whose question no standing grant may answer.

    The permission gate marks every question about a
    ``DENY_UNLESS_TRUSTED`` tool ``ask_every_time``, as it does a
    dangerous command or an explicit ``ask`` rule; the policy is the way to
    get there that needs no rule file.
    """

    policy = ToolPolicy(
        approval_mode=ApprovalMode.DENY_UNLESS_TRUSTED, concurrency_safe=True
    )


class Shell:
    """A shell-shaped tool: its principal argument is ``command``, so the
    permission gate applies the dangerous-command patterns and the
    protected-file check to it, as it does to ``bash``. It never runs
    anything; it reports the command it was given."""

    policy = ToolPolicy(approval_mode=ApprovalMode.ASK)
    name = "shell"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="shell",
            description="Runs a command.",
            input_schema={
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        )

    async def execute(self, arguments: str) -> str:
        return "ran " + json.loads(arguments)["command"]


def shell(*commands: str) -> Message:
    """One assistant message calling :class:`Shell` once per command."""
    return Message(
        role=Role.ASSISTANT,
        tool_calls=tuple(
            ToolCall(id=f"c{index}", name="shell", arguments=json.dumps({"command": command}))
            for index, command in enumerate(commands)
        ),
    )


def document(**overrides: Any) -> dict:
    body = {
        "ingress_schema_version": 3,
        "content": "run it",
        "session_id": "s1",
        "source_request_id": KEY,
    }
    body.update(overrides)
    return body


def decode(frame: str) -> tuple[str, Any]:
    """A frame's type and data; its ``id:`` line, if any, is skipped."""
    lines = frame[:-2].split("\n")
    if lines[0].startswith("id: "):
        lines = lines[1:]
    (line,) = lines
    payload = json.loads(line[len("data: ") :])
    data = payload["data"]
    if payload["type"] in {
        "tool_use",
        "tool_result",
        "permission_request",
        "result",
        "status",
        "event_omitted",
    }:
        data = json.loads(data)
    return payload["type"], data


def served(tmp_path: pathlib.Path, provider, tools) -> Any:
    return attach_sessions(
        make_app(tmp_path, provider, tools=tools), abandon_grace_s=None
    )


Card = Callable[[dict], Awaitable[None]]


async def drive(
    app: Any,
    interactions: DesktopInteractions,
    body: dict,
    on_card: Card,
) -> list[tuple[str, Any]]:
    """Stream one request to its end, answering each card as it arrives.

    ``on_card`` runs between two frames of the same body, while the
    exchange is suspended on the question — the interleaving an HTTP client
    produces by POSTing ``/chat/permission`` with its stream still open.
    """
    stream = await open_chat_stream(
        app, body, keepalive_s=None, interactions=interactions
    )
    frames: list[tuple[str, Any]] = []
    async with stream.body as frames_iter:
        async for raw in frames_iter:
            kind, data = decode(raw)
            frames.append((kind, data))
            if kind == "permission_request":
                await on_card(data)
    return frames


def allow(scope: str = "once") -> Callable[..., Card]:
    def bind(app: Any, interactions: DesktopInteractions, answers: list) -> Card:
        async def on_card(card: dict) -> None:
            answers.append(
                await answer_permission(
                    app,
                    interactions,
                    {
                        "request_id": card["request_id"],
                        "decision": {"behavior": "allow", "scope": scope},
                    },
                )
            )

        return on_card

    return bind


def results(frames: list[tuple[str, Any]]) -> list[dict]:
    return [data for kind, data in frames if kind == "tool_result"]


def kinds(frames: list[tuple[str, Any]]) -> list[str]:
    return [kind for kind, _ in frames]


# ---- /chat/permission, interleaved with a live stream -------------------


def test_allow_once_runs_the_tool_and_the_stream_completes(tmp_path):
    """The P0 loop: card, answer, tool result, ``result``, ``done``."""
    app = served(tmp_path, Scripted(calling("ask"), DONE), [Asking("ask")])
    interactions = DesktopInteractions(app)
    answers: list[dict] = []

    frames = asyncio.run(
        asyncio.wait_for(
            drive(app, interactions, document(), allow()(app, interactions, answers)),
            WAIT_S,
        )
    )

    assert kinds(frames).count("permission_request") == 1
    card = next(data for kind, data in frames if kind == "permission_request")
    turn_id = card["turn_id"]
    assert card["request_id"] == f"{turn_id}#1"
    assert card["tool_name"] == "ask"
    assert card["ask_every_time"] is False
    assert answers == [
        {
            "ok": True,
            "request_id": card["request_id"],
            "behavior": "allow",
            "scope": "once",
            "session_id": "s1",
            "remembered_pattern": None,
        }
    ]
    assert [r["content"] for r in results(frames)] == ["ask ran"]
    assert kinds(frames)[-2:] == ["result", "done"]


def test_deny_tells_the_model_why_in_the_desktop_s_words(tmp_path):
    """No message ⇒ :data:`DENIED_REASON`; a message ⇒ that message."""
    for message, expected in (("", DENIED_REASON), ("not on this data", "not on this data")):
        app = served(tmp_path, Scripted(calling("ask"), DONE), [Asking("ask")])
        interactions = DesktopInteractions(app)
        answers: list[dict] = []

        async def on_card(card: dict) -> None:
            answers.append(
                await answer_permission(
                    app,
                    interactions,
                    {
                        "request_id": card["request_id"],
                        "decision": {"behavior": "deny", "message": message},
                    },
                )
            )

        frames = asyncio.run(
            asyncio.wait_for(drive(app, interactions, document(), on_card), WAIT_S)
        )

        assert answers[0]["behavior"] == "deny"
        assert answers[0]["scope"] == "once"
        (result,) = results(frames)
        assert result["is_error"] is True
        assert expected in result["content"]
        assert kinds(frames)[-2:] == ["result", "done"]


def test_allow_for_the_session_stops_asking_about_that_tool(tmp_path):
    """One card for two calls: the second is allowed by the grant.

    The grant is applied by the body that observes the second request, so
    the card never reaches the client.
    """
    app = served(
        tmp_path, Scripted(calling("ask"), calling("ask"), DONE), [Asking("ask")]
    )
    interactions = DesktopInteractions(app)
    answers: list[dict] = []

    frames = asyncio.run(
        asyncio.wait_for(
            drive(
                app, interactions, document(), allow("session")(app, interactions, answers)
            ),
            WAIT_S,
        )
    )

    assert kinds(frames).count("permission_request") == 1
    assert answers[0]["scope"] == "session"
    assert [r["content"] for r in results(frames)] == ["ask ran", "ask ran"]
    assert interactions.is_granted("s1", "ask")
    assert not interactions.is_granted("another-session", "ask")


def test_a_session_grant_never_answers_an_ask_every_time_request(tmp_path):
    """The CLI's ``s`` rule: a grant covers the tool's ordinary calls only."""
    app = served(
        tmp_path,
        Scripted(calling("rm"), calling("rm"), DONE),
        [Insistent("rm")],
    )
    interactions = DesktopInteractions(app)
    answers: list[dict] = []

    frames = asyncio.run(
        asyncio.wait_for(
            drive(
                app, interactions, document(), allow("session")(app, interactions, answers)
            ),
            WAIT_S,
        )
    )

    cards = [data for kind, data in frames if kind == "permission_request"]
    assert len(cards) == 2
    assert all(card["ask_every_time"] is True for card in cards)
    assert [r["content"] for r in results(frames)] == ["rm ran", "rm ran"]


def test_session_on_an_ask_every_time_card_allows_that_call_only(tmp_path):
    """The CLI's ``s`` on such a card: the call runs, nothing is granted,
    so the tool's next ordinary call is still asked about."""
    app = served(
        tmp_path,
        Scripted(shell("rm -rf build"), shell("echo hello"), DONE),
        [Shell()],
    )
    interactions = DesktopInteractions(app)
    answers: list[dict] = []
    granted_after_first: list[bool] = []

    async def on_card(card: dict) -> None:
        answers.append(
            await answer_permission(
                app,
                interactions,
                {
                    "request_id": card["request_id"],
                    "decision": {"behavior": "allow", "scope": "session"},
                },
            )
        )
        if len(answers) == 1:
            granted_after_first.append(interactions.is_granted("s1", "shell"))

    frames = asyncio.run(
        asyncio.wait_for(drive(app, interactions, document(), on_card), WAIT_S)
    )

    cards = [data for kind, data in frames if kind == "permission_request"]
    assert [card["ask_every_time"] for card in cards] == [True, False]
    assert [a["scope"] for a in answers] == ["once", "session"]
    assert granted_after_first == [False]
    assert [r["content"] for r in results(frames)] == [
        "ran rm -rf build",
        "ran echo hello",
    ]


def test_a_second_answer_is_resolved_and_a_finished_exchange_is_expired(tmp_path):
    """Both are ``ok: false`` with HTTP 200, because both are ordinary.

    A double click is ``resolved``; a click on a card whose exchange has
    ended is ``expired``, as is a request id this process never issued
    (for example one from before a restart).
    """
    app = served(tmp_path, Scripted(calling("ask"), DONE), [Asking("ask")])
    interactions = DesktopInteractions(app)
    seen: list[dict] = []

    async def on_card(card: dict) -> None:
        answer = {"request_id": card["request_id"], "decision": {"behavior": "allow"}}
        seen.append(await answer_permission(app, interactions, answer))
        seen.append(await answer_permission(app, interactions, answer))

    async def scenario() -> tuple[dict, dict]:
        await drive(app, interactions, document(), on_card)
        request_id = seen[0]["request_id"]
        # The stream ends when the exchange's last frame is published; the
        # handle is settled a moment later, after the session is saved.
        await app.sessions.handle(request_id.partition("#")[0]).wait()
        late = await answer_permission(
            app,
            interactions,
            {"request_id": request_id, "decision": {"behavior": "deny"}},
        )
        never = await answer_permission(
            app,
            interactions,
            {"request_id": "f" * 32 + "#1", "decision": {"behavior": "allow"}},
        )
        return late, never

    late, never = asyncio.run(asyncio.wait_for(scenario(), WAIT_S))

    assert seen[0]["ok"] is True
    assert seen[1] == {"ok": False, "request_id": seen[0]["request_id"], "status": "resolved"}
    assert late == {"ok": False, "request_id": seen[0]["request_id"], "status": "expired"}
    assert never["status"] == "expired"


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({"decision": {"behavior": "allow"}}, "invalid_request_id"),
        ({"request_id": "a" * 32, "decision": {"behavior": "allow"}}, "invalid_request_id"),
        ({"request_id": "A" * 32 + "#1", "decision": {"behavior": "allow"}}, "invalid_request_id"),
        ({"request_id": "a" * 32 + "#0", "decision": {"behavior": "allow"}}, "invalid_request_id"),
        ({"request_id": "a" * 32 + "#1\n", "decision": {"behavior": "allow"}}, "invalid_request_id"),
        ({"request_id": "a" * 32 + "#1"}, "invalid_decision"),
        ({"request_id": "a" * 32 + "#1", "decision": "allow"}, "invalid_decision"),
        ({"request_id": "a" * 32 + "#1", "decision": {"behavior": "maybe"}}, "invalid_decision"),
        (
            {"request_id": "a" * 32 + "#1", "decision": {"behavior": "allow", "scope": 1}},
            "invalid_decision",
        ),
        (
            {"request_id": "a" * 32 + "#1", "decision": {"behavior": "deny", "message": 7}},
            "invalid_decision",
        ),
        (
            {"request_id": "a" * 32 + "#1", "decision": {"behavior": "allow", "scope": "forever"}},
            "unsupported_scope",
        ),
    ],
)
def test_a_malformed_decision_is_a_422_by_name(tmp_path, body: dict, code: str):
    """An unknown scope is refused rather than downgraded, so a client never
    believes something was granted that was not."""
    app = served(tmp_path, Scripted(), ())

    async def scenario() -> DesktopIngressError:
        with pytest.raises(DesktopIngressError) as caught:
            await answer_permission(app, DesktopInteractions(app), body)
        return caught.value

    error = asyncio.run(scenario())
    assert (error.code, error.status_code) == (code, 422)


# ---- which card the body shows ------------------------------------------


async def _ask(handle: TurnHandle, request: ApprovalRequest) -> tuple[asyncio.Task, TurnEvent]:
    """Raise one question on *handle*'s broker and return its frame."""
    observation = handle.observe()
    task = asyncio.create_task(handle.approvals(request))
    async for event in observation:
        if event.type is TurnEventType.APPROVAL_REQUIRED:
            await observation.aclose()
            return task, event
    raise AssertionError("no approval frame")


def test_admission_shows_outstanding_cards_and_hides_settled_ones(tmp_path):
    """A replayed ``APPROVAL_REQUIRED`` whose request was already answered —
    what a reconnecting cursor reads from the ring — shows no card."""
    app = served(tmp_path, Scripted(), ())
    interactions = DesktopInteractions(app)

    async def scenario() -> tuple[bool, bool, bool]:
        handle = TurnHandle(session_id="s1", turn_id="c" * 32)
        task, event = await _ask(handle, ApprovalRequest(tool_name="bash"))
        shown = interactions.admit_approval(event, handle.approvals)
        remembered = interactions.pending_approval(event.request_id) is not None
        handle.approvals.settle(event.request_id, _allowed())
        await task
        return shown, remembered, interactions.admit_approval(event, handle.approvals)

    shown, remembered, replayed = asyncio.run(scenario())
    assert (shown, remembered, replayed) == (True, True, False)


def test_admission_answers_a_granted_tool_without_a_card(tmp_path):
    app = served(tmp_path, Scripted(), ())
    interactions = DesktopInteractions(app)
    interactions.grant("s1", "bash")

    async def scenario() -> tuple[bool, bool, bool]:
        handle = TurnHandle(session_id="s1", turn_id="c" * 32)
        task, event = await _ask(handle, ApprovalRequest(tool_name="bash"))
        shown = interactions.admit_approval(event, handle.approvals)
        decision = await asyncio.wait_for(task, WAIT_S)

        other = TurnHandle(session_id="s1", turn_id="d" * 32)
        insist_task, insist = await _ask(
            other, ApprovalRequest(tool_name="bash", ask_every_time=True)
        )
        insisted = interactions.admit_approval(insist, other.approvals)
        other.approvals.settle(insist.request_id, _allowed())
        await insist_task
        return shown, decision.approved, insisted

    shown, approved, insisted = asyncio.run(scenario())
    assert (shown, approved, insisted) == (False, True, True)


def _allowed():
    from omicsclaw.tools import ApprovalDecision

    return ApprovalDecision(approved=True)


# ---- /chat/abort --------------------------------------------------------


def test_abort_ends_a_running_exchange_with_cancelled_then_done(tmp_path):
    """Stop is the only way out of a question nobody answers (no deadline)."""
    sleeping = Sleeping()
    app = served(tmp_path, Scripted(calling("sleep"), DONE), [sleeping])
    interactions = DesktopInteractions(app)
    stop = {"session_id": "s1", "source_request_id": KEY}

    async def scenario() -> tuple[list[str], dict, dict, dict]:
        stream = await open_chat_stream(
            app, document(), keepalive_s=None, interactions=interactions
        )
        frames: list[str] = []

        async def read() -> None:
            async with stream.body as body:
                async for raw in body:
                    frames.append(decode(raw)[0])

        reader = asyncio.create_task(read())
        await asyncio.wait_for(sleeping.entered.wait(), WAIT_S)
        first = await abort_chat(app, interactions, stop)
        again = await abort_chat(app, interactions, stop)
        await asyncio.wait_for(reader, WAIT_S)
        await app.sessions.handle(first["turn_id"]).wait()
        after = await abort_chat(app, interactions, stop)
        return frames, first, again, after

    frames, first, again, after = asyncio.run(scenario())

    assert frames[-2:] == ["error", "done"]
    assert first["ok"] is True
    assert first["state"] == "cancelling"
    assert first["turn_id"] and first["source_request_id"] == KEY
    assert again["state"] == "cancelling"
    assert after["state"] == "terminal"


def test_abort_cancels_an_exchange_still_queued_without_running_it(tmp_path):
    """The queued one ends ``cancelled`` when its turn comes, and never calls
    the model: the provider is called once, for the exchange ahead of it."""
    provider = Paused()
    app = served(tmp_path, provider, ())
    interactions = DesktopInteractions(app)

    async def scenario() -> tuple[dict, list[str], str]:
        ahead = await open_chat_stream(
            app, document(), keepalive_s=None, interactions=interactions
        )
        await asyncio.wait_for(provider.started.wait(), WAIT_S)
        queued = await open_chat_stream(
            app,
            document(source_request_id=OTHER_KEY),
            keepalive_s=None,
            interactions=interactions,
        )
        answer = await abort_chat(
            app, interactions, {"session_id": "s1", "source_request_id": OTHER_KEY}
        )
        provider.release.set()

        async def kinds_of(stream) -> list[str]:
            async with stream.body as body:
                return [decode(raw)[0] async for raw in body]

        _, tail = await asyncio.wait_for(
            asyncio.gather(kinds_of(ahead), kinds_of(queued)), WAIT_S
        )
        return answer, tail, app.sessions.handle(queued.turn_id).terminal or ""

    answer, tail, terminal = asyncio.run(scenario())
    assert answer["state"] == "cancelling"
    assert tail[-2:] == ["error", "done"]
    assert terminal == "cancelled"
    assert provider.calls == 1


@pytest.mark.parametrize(
    ("body", "code", "status"),
    [
        ({"session_id": "s1", "source_request_id": "c" * 32}, "turn_not_found", 404),
        ({"session_id": "other", "source_request_id": KEY}, "turn_not_found", 404),
        ({"source_request_id": KEY}, "invalid_session_id", 422),
        ({"session_id": "s1"}, "invalid_source_request_id", 422),
        ({"session_id": "s1", "source_request_id": "nope"}, "invalid_source_request_id", 422),
    ],
)
def test_abort_names_what_it_could_not_find(tmp_path, body: dict, code: str, status: int):
    """Keyed by *session and* request id, as the stream was opened."""
    app = served(tmp_path, Scripted(), ())
    interactions = DesktopInteractions(app)

    async def scenario() -> DesktopIngressError:
        stream = await open_chat_stream(
            app, document(), keepalive_s=None, interactions=interactions
        )
        async with stream.body as frames:
            async for _ in frames:
                pass
        with pytest.raises(DesktopIngressError) as caught:
            await abort_chat(app, interactions, body)
        return caught.value

    error = asyncio.run(asyncio.wait_for(scenario(), WAIT_S))
    assert (error.code, error.status_code) == (code, status)


# ---- the bounds ---------------------------------------------------------


class _Handle:
    def __init__(self, done: bool, pending: tuple[str, ...] = ()) -> None:
        self.done = done
        self.approvals = SimpleNamespace(pending=lambda: pending)


def _stub_app(handles: dict[str, _Handle], max_sessions: int = 2) -> Any:
    def handle(turn_id: str) -> _Handle:
        return handles[turn_id]

    return SimpleNamespace(
        sessions=SimpleNamespace(handle=handle),
        config=SimpleNamespace(max_sessions=max_sessions),
    )


def test_the_request_map_drops_only_exchanges_no_longer_retained_past_its_bound():
    """A retained exchange stays abortable and resumable however many
    requests follow it, finished or not; one the registry dropped goes."""
    handles = {"live": _Handle(done=False), "ended": _Handle(done=True)}
    interactions = DesktopInteractions(_stub_app(handles), max_requests=2)

    interactions.remember_request("s", "1" * 32, "live")
    interactions.remember_request("s", "2" * 32, "ended")
    interactions.remember_request("s", "3" * 32, "gone")  # aged out of the registry

    # Every entry is retained or just recorded, so the map runs past its bound.
    assert interactions.turn_for("s", "1" * 32) == "live"
    assert interactions.turn_for("s", "2" * 32) == "ended"
    assert interactions.turn_for("s", "3" * 32) == "gone"

    interactions.remember_request("s", "4" * 32, "live")
    assert interactions.turn_for("s", "1" * 32) == "live"
    assert interactions.turn_for("s", "2" * 32) == "ended"
    assert interactions.turn_for("s", "3" * 32) is None
    assert interactions.turn_for("s", "4" * 32) == "live"


def test_the_pending_cache_drops_only_settled_requests_past_its_bound():
    turn = "e" * 32
    handles = {turn: _Handle(done=False, pending=(f"{turn}#1", f"{turn}#3"))}
    interactions = DesktopInteractions(_stub_app(handles), max_pending=2)

    def event(n: int) -> TurnEvent:
        return TurnEvent.approval_required(
            ApprovalRequest(tool_name="bash"), f"{turn}#{n}", session_id="s", turn_id=turn
        )

    live = SimpleNamespace(pending=lambda: tuple(f"{turn}#{n}" for n in (1, 2, 3)))
    for n in (1, 2, 3):
        interactions.admit_approval(event(n), live)  # type: ignore[arg-type]

    assert interactions.pending_approval(f"{turn}#1") is not None
    assert interactions.pending_approval(f"{turn}#2") is None
    assert interactions.pending_approval(f"{turn}#3") is not None


def test_session_grants_are_bounded_least_recently_used_first():
    """Dropping a grant costs a question, never a permission."""
    interactions = DesktopInteractions(_stub_app({}), max_granted_sessions=2)
    interactions.grant("a", "bash")
    interactions.grant("b", "bash")
    assert interactions.is_granted("a", "bash")  # touches "a"
    interactions.grant("c", "bash")

    assert interactions.is_granted("a", "bash")
    assert not interactions.is_granted("b", "bash")
    assert interactions.is_granted("c", "bash")
    assert not interactions.is_granted("c", "write_file")


def test_the_usage_ledgers_drop_only_exchanges_no_longer_retained():
    """A retained exchange can still be resumed, finished or not, and a
    resumed stream reports usage out of its ledger."""
    handles = {"live": _Handle(done=False), "ended": _Handle(done=True)}
    interactions = DesktopInteractions(_stub_app(handles), max_requests=2)

    live = interactions.usage_for("live")
    ended = interactions.usage_for("ended")
    gone = interactions.usage_for("gone")  # aged out of the registry

    assert interactions.usage_for("live") is live
    assert interactions.usage_for("ended") is ended
    assert interactions.usage_for("gone") is gone

    interactions.usage_for("next")
    assert interactions.usage_for("live") is live
    assert interactions.usage_for("ended") is ended
    assert interactions.usage_for("gone") is not gone


def test_a_model_call_read_twice_counts_once():
    ledger = TurnUsage()
    ledger.record_call(2, {"input_tokens": 10, "output_tokens": 2})
    ledger.record_call(2, {"input_tokens": 99, "output_tokens": 99})
    ledger.record_call(5, {"input_tokens": 20, "output_tokens": 3, "cache_read_tokens": 4})
    ledger.cover(1, 7)

    assert ledger.result(7) == {
        "usage": {
            "input_tokens": 30,
            "output_tokens": 5,
            "cache_read_tokens": 4,
            "cache_write_tokens": 0,
        },
        "usage_reported": True,
        "model_calls": 2,
    }


def test_a_call_that_reported_no_usage_leaves_the_sum_unreported():
    ledger = TurnUsage()
    ledger.record_call(2, None)
    ledger.record_call(3, {"input_tokens": 7})
    ledger.cover(1, 4)

    result = ledger.result(4)
    assert (result["usage"]["input_tokens"], result["usage_reported"]) == (7, False)

    silent = TurnUsage()
    silent.record_call(2, None)
    silent.cover(1, 3)
    assert silent.result(3)["usage"] is None


@pytest.mark.parametrize(
    ("spans", "end", "covered"),
    [
        ([(1, 4), (5, 9)], 9, True),  # adjacent spans join
        ([(5, 9), (1, 6)], 9, True),  # a later body started earlier
        ([(1, 4), (3, 9)], 9, True),  # overlapping bodies
        ([(1, 4), (6, 9)], 9, False),  # seq 5 was never read
        ([(2, 9)], 9, False),  # nothing read the first event
        ([(1, 8)], 9, False),  # nor the last
        ([], 1, False),
    ],
)
def test_the_read_spans_of_several_bodies_are_joined(spans, end, covered):
    ledger = TurnUsage()
    ledger.record_call(1, {"input_tokens": 1})
    for start, stop in spans:
        ledger.cover(start, stop)

    assert ledger.covers(end) is covered
    assert ledger.result(end)["usage_reported"] is covered


def test_no_model_call_means_no_reported_usage():
    ledger = TurnUsage()
    ledger.cover(1, 3)
    assert ledger.result(3) == {"usage": None, "usage_reported": False, "model_calls": 0}


# ---- /workspace -----------------------------------------------------------


def test_the_workspace_is_reported_with_no_trusted_dirs(tmp_path):
    app = served(tmp_path, Scripted(), ())
    assert workspace_payload(app) == {"workspace": str(tmp_path), "trusted_dirs": []}


def test_another_spelling_of_the_same_workspace_is_accepted(tmp_path):
    workspace = tmp_path / "ws"
    (workspace / "sub").mkdir(parents=True)
    (tmp_path / "link").symlink_to(workspace)
    app = served(workspace, Scripted(), ())

    for spelling in (
        str(workspace) + "/",
        str(workspace / "sub" / ".."),
        str(tmp_path / "link"),
    ):
        assert change_workspace(app, {"workspace": spelling}) == workspace_payload(app)


def test_another_workspace_needs_a_restart(tmp_path):
    """One process serves one workspace; switching is a restart."""
    app = served(tmp_path, Scripted(), ())
    for body, code, status in (
        ({"workspace": str(tmp_path / "elsewhere")}, "workspace_change_requires_restart", 409),
        ({"workspace": ""}, "workspace_required", 422),
        ({}, "workspace_required", 422),
        ({"workspace": 3}, "workspace_required", 422),
    ):
        with pytest.raises(DesktopIngressError) as caught:
            change_workspace(app, body)
        assert (caught.value.code, caught.value.status_code) == (code, status)


def test_a_workspace_that_is_not_a_path_is_refused(tmp_path):
    app = served(tmp_path, Scripted(), ())
    with pytest.raises(DesktopIngressError) as caught:
        change_workspace(app, {"workspace": str(tmp_path) + "\x00"})
    assert (caught.value.code, caught.value.status_code) == ("invalid_workspace", 422)


def test_a_symlink_loop_is_a_refusal_not_a_crash(tmp_path):
    """Python 3.11 cannot resolve a loop at all; 3.13 resolves it to the
    loop's own path. Either way the answer is a refusal."""
    loop = tmp_path / "loop"
    loop.symlink_to(tmp_path / "back")
    (tmp_path / "back").symlink_to(loop)
    app = served(tmp_path, Scripted(), ())

    with pytest.raises(DesktopIngressError) as caught:
        change_workspace(app, {"workspace": str(loop)})
    assert (caught.value.code, caught.value.status_code) in {
        ("invalid_workspace", 422),
        ("workspace_change_requires_restart", 409),
    }


# ---- full access ----------------------------------------------------------


def cards_of(frames: list[tuple[str, Any]]) -> list[dict]:
    return [data for kind, data in frames if kind == "permission_request"]


def test_full_access_runs_an_ordinary_command_without_a_card_but_asks_about_a_dangerous_one(
    tmp_path,
):
    """The acceptance line of full access: the gate's ``ask_every_time``
    questions — a dangerous command here — still reach the person."""
    app = served(
        tmp_path,
        Scripted(shell("echo hello"), shell("rm -rf build"), DONE),
        [Shell()],
    )
    interactions = DesktopInteractions(app)
    answers: list[dict] = []

    frames = asyncio.run(
        asyncio.wait_for(
            drive(
                app,
                interactions,
                document(permission_profile="full_access"),
                allow()(app, interactions, answers),
            ),
            WAIT_S,
        )
    )

    (card,) = cards_of(frames)
    assert json.loads(card["arguments"]) == {"command": "rm -rf build"}
    assert card["ask_every_time"] is True
    assert [r["content"] for r in results(frames)] == ["ran echo hello", "ran rm -rf build"]
    assert interactions.permission_profile("s1") == "full_access"
    assert interactions.permission_profile("s2") == "default"


def test_the_default_profile_asks_about_the_same_ordinary_command(tmp_path):
    app = served(tmp_path, Scripted(shell("echo hello"), DONE), [Shell()])
    interactions = DesktopInteractions(app)
    answers: list[dict] = []

    frames = asyncio.run(
        asyncio.wait_for(
            drive(
                app,
                interactions,
                document(permission_profile="default"),
                allow()(app, interactions, answers),
            ),
            WAIT_S,
        )
    )

    assert len(cards_of(frames)) == 1
    assert [r["content"] for r in results(frames)] == ["ran echo hello"]


def test_switching_to_full_access_releases_the_waiting_request(tmp_path):
    """The card on screen is answered by the switch, and the next ordinary
    call of the same exchange shows none; switching back settles nothing."""
    app = served(
        tmp_path, Scripted(calling("ask"), calling("ask"), DONE), [Asking("ask")]
    )
    interactions = DesktopInteractions(app)
    switched: list[dict] = []

    async def on_card(card: dict) -> None:
        switched.append(
            await change_permission_profile(
                app,
                interactions,
                {"session_id": "s1", "permission_profile": "full_access"},
            )
        )

    async def scenario() -> tuple[list[tuple[str, Any]], dict]:
        frames = await drive(app, interactions, document(), on_card)
        back = await change_permission_profile(
            app, interactions, {"session_id": "s1", "permission_profile": "default"}
        )
        return frames, back

    frames, back = asyncio.run(asyncio.wait_for(scenario(), WAIT_S))

    assert len(cards_of(frames)) == 1
    assert switched == [
        {
            "ok": True,
            "session_id": "s1",
            "permission_profile": "full_access",
            "active": True,
            "auto_approved_requests": 1,
        }
    ]
    assert [r["content"] for r in results(frames)] == ["ask ran", "ask ran"]
    assert back["auto_approved_requests"] == 0
    assert back["permission_profile"] == "default"
    assert interactions.permission_profile("s1") == "default"


def test_full_access_in_one_session_does_not_reach_another(tmp_path):
    app = served(tmp_path, Scripted(), ())
    interactions = DesktopInteractions(app)

    async def scenario() -> tuple[bool, bool]:
        interactions.set_permission_profile("s1", "full_access")
        handle = TurnHandle(session_id="s2", turn_id="c" * 32)
        task, event = await _ask(handle, ApprovalRequest(tool_name="bash"))
        shown = interactions.admit_approval(event, handle.approvals)
        handle.approvals.settle(event.request_id, _allowed())
        await task
        mine = TurnHandle(session_id="s1", turn_id="d" * 32)
        task, event = await _ask(mine, ApprovalRequest(tool_name="bash"))
        mine_shown = interactions.admit_approval(event, mine.approvals)
        await asyncio.wait_for(task, WAIT_S)
        return shown, mine_shown

    assert asyncio.run(scenario()) == (True, False)


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({"permission_profile": "full_access"}, "invalid_session_id"),
        ({"session_id": "", "permission_profile": "full_access"}, "invalid_session_id"),
        ({"session_id": "s1"}, "invalid_permission_profile"),
        ({"session_id": "s1", "permission_profile": "bypass-all"}, "invalid_permission_profile"),
        ({"session_id": "s1", "permission_profile": 1}, "invalid_permission_profile"),
    ],
)
def test_a_malformed_profile_change_is_a_422_by_name(tmp_path, body: dict, code: str):
    app = served(tmp_path, Scripted(), ())

    async def scenario() -> DesktopIngressError:
        with pytest.raises(DesktopIngressError) as caught:
            await change_permission_profile(app, DesktopInteractions(app), body)
        return caught.value

    error = asyncio.run(scenario())
    assert (error.code, error.status_code) == (code, 422)


def test_a_bounded_profile_map_forgets_full_access_least_recently_used_first():
    """Forgetting costs a question, never a permission; the client re-sends
    the profile with every message."""
    interactions = DesktopInteractions(_stub_app({}), max_granted_sessions=2)
    for session in ("a", "b", "c"):
        interactions.set_permission_profile(session, "full_access")
    assert [interactions.permission_profile(s) for s in "abc"] == [
        "default",
        "full_access",
        "full_access",
    ]


# ---- always allow ---------------------------------------------------------


def test_always_writes_a_rule_and_the_next_identical_call_is_not_asked(tmp_path):
    """The second call is allowed by the permission gate reading the rule
    file, not by anything the desktop remembers."""
    app = served(
        tmp_path, Scripted(calling("ask"), calling("ask"), DONE), [Asking("ask")]
    )
    interactions = DesktopInteractions(app)
    answers: list[dict] = []

    frames = asyncio.run(
        asyncio.wait_for(
            drive(app, interactions, document(), allow("always")(app, interactions, answers)),
            WAIT_S,
        )
    )

    (card,) = cards_of(frames)
    assert card["can_remember"] is True
    assert answers[0]["scope"] == "always"
    assert answers[0]["remembered_pattern"] == "ask({})"
    assert [r["content"] for r in results(frames)] == ["ask ran", "ask ran"]
    assert not interactions.is_granted("s1", "ask")
    written = tmp_path / ".omicsclaw" / "settings.json"
    assert "ask({})" in written.read_text(encoding="utf-8")


def test_always_applies_once_to_a_call_that_changes_a_protected_file(tmp_path):
    """No rule reaches such a call, so the card says so and nothing is
    written that would be reported as remembered and never consulted."""
    app = served(
        tmp_path,
        Scripted(shell("echo X=1 >> .env"), shell("echo X=1 >> .env"), DONE),
        [Shell()],
    )
    interactions = DesktopInteractions(app)
    answers: list[dict] = []

    frames = asyncio.run(
        asyncio.wait_for(
            drive(app, interactions, document(), allow("always")(app, interactions, answers)),
            WAIT_S,
        )
    )

    cards = cards_of(frames)
    assert len(cards) == 2
    assert all(card["can_remember"] is False for card in cards)
    assert [a["scope"] for a in answers] == ["once", "once"]
    assert [a["remembered_pattern"] for a in answers] == [None, None]
    assert not (tmp_path / ".omicsclaw" / "settings.json").exists()


def test_always_applies_once_when_there_is_nowhere_to_write_the_rule(tmp_path):
    app = attach_sessions(
        dataclasses.replace(
            make_app(tmp_path, Scripted(calling("ask"), DONE), tools=[Asking("ask")]),
            permission=None,
        ),
        abandon_grace_s=None,
    )
    interactions = DesktopInteractions(app)
    answers: list[dict] = []

    frames = asyncio.run(
        asyncio.wait_for(
            drive(app, interactions, document(), allow("always")(app, interactions, answers)),
            WAIT_S,
        )
    )

    assert answers[0]["ok"] is True
    assert (answers[0]["scope"], answers[0]["remembered_pattern"]) == ("once", None)
    assert [r["content"] for r in results(frames)] == ["ask ran"]


# ---- /compact ---------------------------------------------------------------


def test_compact_is_a_compaction_not_a_message_and_always_reports(tmp_path):
    """A short conversation compacts to nothing, which publishes no
    ``COMPACTION`` event; the body still sends one ``status`` frame so the
    command is never silent. The model is never sent ``/compact``."""
    provider = Scripted()
    app = served(tmp_path, provider, ())
    interactions = DesktopInteractions(app)

    async def scenario() -> tuple[list[tuple[str, Any]], list[tuple[str, Any]]]:
        first = await drive(app, interactions, document(content="  /compact\n"), _no_card)
        again = await drive(app, interactions, document(content="/compact"), _no_card)
        return first, again

    first, again = asyncio.run(asyncio.wait_for(scenario(), WAIT_S))

    assert kinds(first) == ["status", "result", "done"]
    status = first[0][1]
    assert status["kind"] == "compaction"
    assert status["written_back"] is False
    assert status["session_id"] == "s1"
    assert provider.calls == 0
    # The same source_request_id is a redelivery of the same compaction.
    assert again[0][1]["turn_id"] == status["turn_id"]


def test_text_that_merely_mentions_compact_is_a_message(tmp_path):
    provider = Scripted()
    app = served(tmp_path, provider, ())
    interactions = DesktopInteractions(app)

    frames = asyncio.run(
        asyncio.wait_for(
            drive(app, interactions, document(content="/compact please"), _no_card),
            WAIT_S,
        )
    )

    assert kinds(frames) == ["text", "result", "done"]
    assert provider.calls == 1


async def _no_card(card: dict) -> None:
    raise AssertionError(f"unexpected card {card}")
