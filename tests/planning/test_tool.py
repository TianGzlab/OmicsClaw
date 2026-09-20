"""``plan_write``: two modes, one refusal path, one session per call."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from omicsclaw.planning import (
    PLAN_WRITE_SCHEMA,
    PLAN_WRITE_TOOL_NAME,
    PlanBook,
    PlanItem,
    PlanStatus,
    plan_write_tool,
)
from omicsclaw.tools import ApprovalMode, RiskLevel, ToolRegistry
from omicsclaw.tools.context import use_tool_context
from omicsclaw.schema import ToolCall

P, R, C, X = (
    PlanStatus.PENDING,
    PlanStatus.IN_PROGRESS,
    PlanStatus.COMPLETED,
    PlanStatus.CANCELLED,
)


def _call(tool: Any, payload: dict[str, Any], *, session: str = "") -> str:
    async def go() -> str:
        with use_tool_context(values={"session_id": session}):
            return await tool.execute(json.dumps(payload))

    return asyncio.run(go())


def _steps(*specs: tuple[str, str, str]) -> list[dict[str, str]]:
    return [{"id": i, "content": c, "status": s} for i, c, s in specs]


# ---- shape ---------------------------------------------------------------


def test_the_tool_names_itself_consistently():
    tool = plan_write_tool(PlanBook())

    assert tool.name == PLAN_WRITE_TOOL_NAME == tool.definition().name


def test_steps_is_optional_because_that_is_how_read_mode_is_expressed():
    assert "required" not in PLAN_WRITE_SCHEMA


def test_the_schema_offers_exactly_the_four_statuses():
    statuses = PLAN_WRITE_SCHEMA["properties"]["steps"]["items"]["properties"][
        "status"
    ]["enum"]

    assert statuses == ["pending", "in_progress", "completed", "cancelled"]


def test_the_policy_is_declared_rather_than_defaulted():
    """Defaults are ``HIGH``/``ASK`` and approval fails closed.

    Left alone, every plan update would wait on a human — which would not
    make a deployment safer, it would stop the model planning.
    """
    registry = ToolRegistry()
    registry.register(plan_write_tool(PlanBook()))

    policy = registry.policy_for(PLAN_WRITE_TOOL_NAME)
    assert policy.risk_level is RiskLevel.LOW
    assert policy.approval_mode is ApprovalMode.AUTO


def test_the_tool_is_a_barrier_so_two_writes_cannot_lose_an_update():
    registry = ToolRegistry()
    registry.register(plan_write_tool(PlanBook()))

    assert not registry.is_concurrency_safe(PLAN_WRITE_TOOL_NAME)


def test_no_policy_field_name_reaches_the_definition():
    """What the machine may do is never what the model is told."""
    rendered = json.dumps(plan_write_tool(PlanBook()).definition().input_schema)

    for leaked in ("risk_level", "approval_mode", "writes_config", "read_only"):
        assert leaked not in rendered


# ---- read mode -----------------------------------------------------------


def test_omitting_steps_reads_without_changing_anything():
    book = PlanBook()
    book.for_session("s").write((PlanItem("1", "step", R),))
    tool = plan_write_tool(book)

    out = _call(tool, {}, session="s")

    assert json.loads(out) == [
        {"id": "1", "content": "step", "status": "in_progress"}
    ]
    assert len(book.for_session("s").read()) == 1


def test_an_empty_array_reads_rather_than_erasing_the_plan():
    """Otherwise the model can lose every item by sending a valid value."""
    book = PlanBook()
    book.for_session("s").write((PlanItem("1", "step", R),))

    _call(plan_write_tool(book), {"steps": []}, session="s")

    assert len(book.for_session("s").read()) == 1


def test_an_empty_plan_reads_back_as_an_array_not_as_null():
    """``null`` makes the model guess whether the call worked."""
    assert _call(plan_write_tool(PlanBook()), {}) == "[]"


# ---- write mode ----------------------------------------------------------


def test_a_write_stores_the_items_and_returns_them():
    book = PlanBook()

    out = _call(
        plan_write_tool(book),
        {"steps": _steps(("1", "load", "in_progress"), ("2", "qc", "pending"))},
        session="s",
    )

    assert [entry["id"] for entry in json.loads(out)] == ["1", "2"]
    assert [i.id for i in book.for_session("s").read()] == ["1", "2"]


def test_a_partial_update_keeps_the_items_that_were_started():
    book = PlanBook()
    tool = plan_write_tool(book)
    _call(
        tool,
        {"steps": _steps(("1", "load", "completed"), ("2", "qc", "in_progress"))},
        session="s",
    )

    out = _call(tool, {"steps": _steps(("2", "qc", "completed"))}, session="s")

    assert [entry["id"] for entry in json.loads(out)] == ["1", "2"]


def test_a_batch_of_fabricated_completions_is_refused():
    book = PlanBook()

    with pytest.raises(Exception) as caught:
        _call(
            plan_write_tool(book),
            {
                "steps": _steps(
                    ("1", "a", "completed"),
                    ("2", "b", "completed"),
                    ("3", "c", "completed"),
                )
            },
            session="s",
        )

    assert "completed" in str(caught.value)
    assert book.for_session("s").read() == (), "a refused write must store nothing"


def test_a_refusal_is_correctable_by_the_model():
    """It reaches the model as an ``is_error`` Observation, not as a crash."""
    registry = ToolRegistry()
    registry.register(plan_write_tool(PlanBook()))

    async def go():
        with use_tool_context(values={"session_id": "s"}):
            return await registry.execute(
                ToolCall(
                    id="c1",
                    name=PLAN_WRITE_TOOL_NAME,
                    arguments=json.dumps(
                        {
                            "steps": _steps(
                                ("1", "a", "completed"), ("2", "b", "completed")
                            )
                        }
                    ),
                )
            )

    result = asyncio.run(go())

    assert result.is_error
    assert "one item per call" in result.output


def test_a_cancelled_item_cannot_be_completed_through_the_tool():
    book = PlanBook()
    tool = plan_write_tool(book)
    _call(tool, {"steps": _steps(("1", "a", "cancelled"))}, session="s")

    with pytest.raises(Exception) as caught:
        _call(tool, {"steps": _steps(("1", "a", "completed"))}, session="s")

    assert "cancelled" in str(caught.value)


# ---- malformed input -----------------------------------------------------


def test_a_bad_item_names_its_position():
    """A model that sent eight items needs to know which one is wrong."""
    with pytest.raises(Exception) as caught:
        _call(
            plan_write_tool(PlanBook()),
            {"steps": [{"id": "1", "content": "a", "status": "pending"}, {"id": "2"}]},
        )

    assert "steps[1]" in str(caught.value)


def test_an_unknown_status_lists_the_ones_that_exist():
    with pytest.raises(Exception) as caught:
        _call(plan_write_tool(PlanBook()), {"steps": _steps(("1", "a", "blocked"))})

    assert "in_progress" in str(caught.value)


def test_an_empty_id_is_refused_by_name():
    """The id is what ties an update to the item it updates."""
    with pytest.raises(Exception) as caught:
        _call(plan_write_tool(PlanBook()), {"steps": _steps(("  ", "a", "pending"))})

    assert "id" in str(caught.value)


def test_steps_that_is_not_an_array_says_so():
    with pytest.raises(Exception) as caught:
        _call(plan_write_tool(PlanBook()), {"steps": "one, two"})

    assert "array" in str(caught.value)


def test_a_non_object_item_says_so():
    with pytest.raises(Exception) as caught:
        _call(plan_write_tool(PlanBook()), {"steps": ["just a string"]})

    assert "steps[0]" in str(caught.value)


# ---- the session seam ----------------------------------------------------


def test_the_call_resolves_its_own_session():
    """One registry serves every conversation; the plan is per session."""
    book = PlanBook()
    tool = plan_write_tool(book)

    _call(tool, {"steps": _steps(("1", "alice's step", "pending"))}, session="alice")
    _call(tool, {"steps": _steps(("2", "bob's step", "pending"))}, session="bob")

    assert [i.id for i in book.for_session("alice").read()] == ["1"]
    assert [i.id for i in book.for_session("bob").read()] == ["2"]


def test_no_session_in_the_context_is_the_anonymous_store_not_a_failure():
    book = PlanBook()

    async def go() -> str:
        return await plan_write_tool(book).execute(
            json.dumps({"steps": _steps(("1", "a", "pending"))})
        )

    asyncio.run(go())

    assert [i.id for i in book.for_session("").read()] == ["1"]
