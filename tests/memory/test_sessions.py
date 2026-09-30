"""Session round trips, ordering and what deliberately is not stored."""

from __future__ import annotations

import asyncio

from omicsclaw.context import CompactionState
from omicsclaw.context.summary import Anchors
from omicsclaw.memory import Database, SqliteSessionStore, StoredSession
from omicsclaw.schema import Message, Role, ToolCall


def run(coro):
    return asyncio.run(coro)


def store() -> tuple[Database, SqliteSessionStore]:
    db = Database()
    return db, SqliteSessionStore(db)


def test_missing_session_loads_as_none() -> None:
    db, s = store()
    assert run(s.load("nobody")) is None
    db.close()


def test_history_round_trip_has_no_system_message() -> None:
    """A stored system message would stack against the fresh one.

    Prompt assembly composes a system message every turn. Storing one too
    means the next turn loads a stale persona and puts it beside the
    current one, and the byte-exact prefix the provider caches on starts
    at index 1 instead of 0.
    """
    db, s = store()
    run(
        s.save(
            StoredSession(
                session_id="s1",
                history=(
                    Message(role=Role.SYSTEM, content="stale persona"),
                    Message(role=Role.USER, content="hello"),
                    Message(role=Role.ASSISTANT, content="hi"),
                ),
            )
        )
    )
    got = run(s.load("s1"))
    db.close()
    assert [m.role for m in got.history] == [Role.USER, Role.ASSISTANT]
    assert all("stale persona" != m.content for m in got.history)


def test_tool_calls_survive_the_round_trip() -> None:
    db, s = store()
    call = ToolCall(id="c1", name="use_skill", arguments='{"name": "sc-de"}')
    run(
        s.save(
            StoredSession(
                session_id="s1",
                history=(
                    Message(role=Role.ASSISTANT, content="", tool_calls=(call,)),
                    Message(
                        role=Role.TOOL,
                        content="done",
                        tool_call_id="c1",
                        name="use_skill",
                    ),
                ),
            )
        )
    )
    got = run(s.load("s1"))
    db.close()
    assert got.history[0].tool_calls == (call,)
    assert got.history[1].tool_call_id == "c1"
    assert got.history[1].name == "use_skill"


def test_compaction_state_survives_the_round_trip() -> None:
    db, s = store()
    state = CompactionState(
        summary="what happened so far",
        anchors=Anchors(user_intent="QC a Visium slide", next_steps="cluster"),
    )
    run(s.save(StoredSession(session_id="s1", compaction=state)))
    got = run(s.load("s1"))
    db.close()
    assert got.compaction.summary == "what happened so far"
    assert got.compaction.anchors.user_intent == "QC a Visium slide"
    assert got.compaction.anchors.next_steps == "cluster"


def test_json_representable_values_survive_the_round_trip() -> None:
    db, s = store()
    values = {"chat_id": 7, "surface": "telegram", "flags": ["a", "b"],
              "nested": {"depth": 2}, "on": True, "missing": None}
    run(s.save(StoredSession(session_id="s1", values=values)))
    got = run(s.load("s1"))
    db.close()
    assert got.values == values


def test_values_are_only_preserved_as_far_as_json_preserves_them() -> None:
    """The contract is JSON, and JSON is lossy in two specific ways.

    ``values`` is typed ``Mapping[str, object]``, which invites a tuple
    or an int key; both come back changed rather than rejected. Writing
    it down here is what stops a later caller reading the permissive type
    as a promise — and what makes the loss a decision rather than a
    surprise found in production.
    """
    db, s = store()
    run(
        s.save(
            StoredSession(
                session_id="s1", values={"pair": (1, 2), 7: "int key"}
            )
        )
    )
    got = run(s.load("s1"))
    db.close()
    assert got.values["pair"] == [1, 2], "tuples come back as lists"
    assert got.values["7"] == "int key", "non-string keys come back as strings"


def test_saving_twice_replaces_rather_than_appends() -> None:
    db, s = store()
    sess = StoredSession(
        session_id="s1", history=(Message(role=Role.USER, content="one"),)
    )
    run(s.save(sess))
    sess.history = (
        Message(role=Role.USER, content="one"),
        Message(role=Role.ASSISTANT, content="two"),
    )
    run(s.save(sess))
    got = run(s.load("s1"))
    db.close()
    assert [m.content for m in got.history] == ["one", "two"]


def test_message_order_is_preserved() -> None:
    db, s = store()
    history = tuple(
        Message(role=Role.USER, content=f"m{i}") for i in range(30)
    )
    run(s.save(StoredSession(session_id="s1", history=history)))
    got = run(s.load("s1"))
    db.close()
    assert [m.content for m in got.history] == [f"m{i}" for i in range(30)]


def test_list_is_most_recently_active_first() -> None:
    """Ordered by ``updated_at``, not by creation and not by insertion.

    The conversation created first but used last comes first: a resume
    list ordered by creation pushes a long-running conversation off the
    end while it is still the one being worked on.
    """
    db, s = store()
    run(s.save(StoredSession(session_id="old", created_at=100.0, updated_at=900.0)))
    run(s.save(StoredSession(session_id="new", created_at=300.0, updated_at=300.0)))
    run(s.save(StoredSession(session_id="mid", created_at=200.0, updated_at=500.0)))
    got = run(s.list())
    db.close()
    assert [x.session_id for x in got] == ["old", "mid", "new"]


def test_updated_at_is_stored_as_given_and_read_back() -> None:
    """The store keeps the caller's clock rather than reading its own."""
    db, s = store()
    run(s.save(StoredSession(session_id="s1", created_at=1.0, updated_at=42.5)))
    got = run(s.load("s1"))
    listed = run(s.list())
    db.close()
    assert got.updated_at == 42.5
    assert listed[0].updated_at == 42.5


def test_list_isolates_nothing_and_the_file_is_the_whole_boundary() -> None:
    """Two people's conversations in one file are one list, on purpose.

    ``list`` has no ``WHERE`` and the table has no owner column, so the
    only thing deciding what comes back is which database was opened.
    That is the right design while one process serves one workspace, and
    it is a session leak the moment a multi-user surface shares a file
    and offers a ``/resume``. Written down as a passing test rather than
    as a comment so that whoever adds the filter — believing it to be a
    fix — finds out here that it was the documented contract, and has to
    change this test deliberately.
    """
    db, s = store()
    run(s.save(StoredSession(session_id="alice-1", values={"owner": "alice"})))
    run(s.save(StoredSession(session_id="bob-1", values={"owner": "bob"})))
    got = run(s.list())

    other_db, other = store()
    elsewhere = run(other.list())
    db.close()
    other_db.close()

    assert {x.session_id for x in got} == {"alice-1", "bob-1"}
    assert elsewhere == [], "a second database saw the first one's sessions"


def test_list_honours_its_limit() -> None:
    db, s = store()
    for i in range(5):
        run(s.save(StoredSession(session_id=f"s{i}", created_at=float(i))))
    got = run(s.list(limit=2))
    db.close()
    assert [x.session_id for x in got] == ["s4", "s3"]


def test_delete_removes_the_session_and_its_messages() -> None:
    db, s = store()
    run(
        s.save(
            StoredSession(
                session_id="s1",
                history=(Message(role=Role.USER, content="hello"),),
            )
        )
    )
    assert run(s.delete("s1")) is True
    assert run(s.load("s1")) is None
    left = db.run(
        lambda c: c.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    )
    db.close()
    assert left == 0


def test_deleting_an_absent_session_reports_false() -> None:
    db, s = store()
    assert run(s.delete("nobody")) is False
    db.close()


def test_store_satisfies_the_entry_session_store_protocol() -> None:
    """The seam this layer exists to fill, checked against the real one.

    ``attach_sessions`` takes any object carrying these coroutines. The
    protocol is not ``@runtime_checkable``, and an ``isinstance`` check
    against one that were would only compare names — so this reads the
    method names off the protocol itself and insists each is present
    *and* a coroutine function. A store that answered ``load``
    synchronously would satisfy a name check and deadlock the loop.
    """
    import inspect

    from omicsclaw.entry import SessionStore

    db, s = store()
    db.close()

    required = [
        name
        for name, member in vars(SessionStore).items()
        if not name.startswith("_") and inspect.isfunction(member)
    ]
    assert required, "protocol exposes no methods; the check is vacuous"
    for name in required:
        method = getattr(s, name, None)
        assert method is not None, f"store is missing {name}"
        assert inspect.iscoroutinefunction(method), f"{name} is not async"
