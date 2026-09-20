"""Re-injection before every model call, and the planning gate."""

from __future__ import annotations

import asyncio

from omicsclaw.planning import (
    DEFAULT_GATE_TURNS,
    INJECTION_HEADER,
    PLANNING_GATE_TEXT,
    PROGRESS_TOOL_NAMES,
    PlanBook,
    PlanInjector,
    PlanItem,
    PlanStatus,
)
from omicsclaw.schema import Message, Role, ToolCall

P, R, C = PlanStatus.PENDING, PlanStatus.IN_PROGRESS, PlanStatus.COMPLETED


def _store(*items: PlanItem):
    store = PlanBook().for_session("s")
    if items:
        store.write(items)
    return store


def _augment(injector: PlanInjector, history=()) -> tuple[Message, ...]:
    return asyncio.run(injector.augment(tuple(history), ()))


def _acted(*names: str) -> Message:
    return Message(
        role=Role.ASSISTANT,
        content="",
        tool_calls=tuple(
            ToolCall(id=f"c{n}", name=name, arguments="{}")
            for n, name in enumerate(names)
        ),
    )


def _said(text: str = "thinking") -> Message:
    return Message(role=Role.ASSISTANT, content=text)


def _read_only_turns(count: int) -> tuple[Message, ...]:
    turns: list[Message] = [Message(role=Role.USER, content="do the analysis")]
    for _ in range(count):
        turns.append(_acted("read_file"))
        turns.append(Message(role=Role.USER, content="…file contents…"))
    return tuple(turns)


# ---- the plan block ------------------------------------------------------


def test_no_plan_means_nothing_is_appended():
    assert _augment(PlanInjector(_store(), gate_turns=0)) == ()


def test_a_finished_plan_appends_nothing():
    store = _store(PlanItem("1", "done", C))

    assert _augment(PlanInjector(store, gate_turns=0)) == ()


def test_an_outstanding_plan_is_appended_as_one_user_message():
    store = _store(PlanItem("1", "load the matrix", R))

    appended = _augment(PlanInjector(store, gate_turns=0))

    assert len(appended) == 1
    assert appended[0].role is Role.USER
    assert appended[0].content.startswith(INJECTION_HEADER)
    assert "load the matrix" in appended[0].content


def test_the_block_is_recomputed_every_call_so_a_write_shows_up_next_turn():
    store = _store(PlanItem("1", "first", R))
    injector = PlanInjector(store, gate_turns=0)
    _augment(injector)

    store.write((PlanItem("1", "first", C), PlanItem("2", "second", R)))

    assert "second" in _augment(injector)[0].content


def test_nothing_accumulates_across_calls():
    """Each call starts from the conversation again; the block is not history."""
    store = _store(PlanItem("1", "step", R))
    injector = PlanInjector(store, gate_turns=0)

    first = _augment(injector)
    second = _augment(injector)

    assert first == second
    assert len(second) == 1


def test_the_injector_never_writes_to_the_plan():
    store = _store(PlanItem("1", "step", R))
    before = store.read()

    _augment(PlanInjector(store, gate_turns=0), _read_only_turns(20))

    assert store.read() == before


# ---- the planning gate ---------------------------------------------------


def test_the_gate_fires_after_enough_read_only_turns():
    injector = PlanInjector(_store(), gate_turns=3)

    appended = _augment(injector, _read_only_turns(3))

    assert [m.content for m in appended] == [PLANNING_GATE_TEXT]


def test_the_gate_does_not_fire_early():
    injector = PlanInjector(_store(), gate_turns=3)

    assert _augment(injector, _read_only_turns(2)) == ()


def test_the_gate_fires_at_most_once_per_exchange():
    injector = PlanInjector(_store(), gate_turns=2)
    _augment(injector, _read_only_turns(5))

    assert _augment(injector, _read_only_turns(9)) == ()


def test_a_session_that_already_has_a_plan_is_never_nudged():
    """It is being told about the plan every turn; nudging it is confusing.

    This also covers a plan restored from a previous session, which the
    reference harness's in-engine counter cannot see.
    """
    injector = PlanInjector(_store(PlanItem("1", "step", R)), gate_turns=2)

    appended = _augment(injector, _read_only_turns(9))

    assert len(appended) == 1
    assert appended[0].content.startswith(INJECTION_HEADER)


def test_a_completed_plan_still_counts_as_having_planned():
    injector = PlanInjector(_store(PlanItem("1", "step", C)), gate_turns=2)

    assert _augment(injector, _read_only_turns(9)) == ()


def test_a_recent_write_disarms_the_gate():
    injector = PlanInjector(_store(), gate_turns=3)
    history = (*_read_only_turns(3), _acted("write_file"))

    assert _augment(injector, history) == ()


def test_a_recent_plan_write_disarms_the_gate():
    injector = PlanInjector(_store(), gate_turns=3)
    history = (*_read_only_turns(3), _acted("plan_write"))

    assert _augment(injector, history) == ()


def test_bash_does_not_count_as_progress():
    """It is how you run a script and how you grep; counting it disarms
    the gate for a model that is only exploring."""
    injector = PlanInjector(_store(), gate_turns=2)
    history = (_acted("bash"), _acted("bash"), _acted("bash"))

    assert _augment(injector, history) != ()


def test_progress_tools_are_the_two_that_change_the_workspace():
    assert PROGRESS_TOOL_NAMES == frozenset({"write_file", "edit_file"})


def test_a_turn_that_only_talked_counts_as_read_only():
    injector = PlanInjector(_store(), gate_turns=2)

    assert _augment(injector, (_said(), _said())) != ()


def test_zero_turns_disables_the_gate_and_leaves_the_block():
    store = _store(PlanItem("1", "step", R))
    injector = PlanInjector(store, gate_turns=0)

    appended = _augment(injector, _read_only_turns(30))

    assert len(appended) == 1
    assert appended[0].content.startswith(INJECTION_HEADER)


def test_a_history_shortened_by_compaction_does_not_fire_the_gate():
    """Named in plan 0039 §4.4 rather than fixed.

    A compaction has just handed the model a fresh summary, which is the
    one turn on which an extra instruction is least likely to help.
    """
    injector = PlanInjector(_store(), gate_turns=4)
    compacted = (Message(role=Role.USER, content="[summary of 20 turns]"),)

    assert _augment(injector, compacted) == ()


def test_the_nudge_names_the_tool_it_is_asking_for():
    assert "plan_write" in PLANNING_GATE_TEXT


def test_the_default_gate_is_a_fraction_of_the_turn_budget():
    """Re-derived from ``EngineConfig.max_turns``, not ported from 12.

    If the budget moves, this number should be reconsidered; the test
    exists so that moving one without the other is visible.
    """
    from omicsclaw.engine import EngineConfig

    assert 0 < DEFAULT_GATE_TURNS < EngineConfig().max_turns // 4


# ---- both at once --------------------------------------------------------


def test_the_nudge_comes_before_the_block_when_both_would_appear():
    """They never co-occur today — the gate only fires with no plan — but
    if that changes, "make a plan" must precede the plan it asks for."""
    store = _store()
    injector = PlanInjector(store, gate_turns=2)

    async def go():
        history = _read_only_turns(3)
        # The gate is evaluated against an empty plan, then the plan is
        # read; writing between the two is what makes both appear.
        original = store.is_empty

        class _Racing:
            @property
            def is_empty(self):
                return original

            def read(self):
                return (PlanItem("1", "step", R),)

        return await PlanInjector(_Racing(), gate_turns=2).augment(history, ())

    appended = asyncio.run(go())

    assert appended[0].content == PLANNING_GATE_TEXT
    assert appended[1].content.startswith(INJECTION_HEADER)
