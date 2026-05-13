"""Contract for ``EngineDependencies`` — the engine ↔ bot DI surface.

``omicsclaw/engine/loop.py`` must not import from ``bot/`` (enforced
by ``tests/test_no_reverse_imports.py``). Every bot-side singleton,
constant, and callback the engine needs is therefore funnelled through
this dataclass. Pinning the field list here makes the coupling
visible and forces every new dependency to be added explicitly rather
than smuggled in via global state.
"""

from __future__ import annotations

import dataclasses

import pytest

from omicsclaw.engine import EngineDependencies


# Field name → reason it's needed (kept in sync with run_engine_loop body).
EXPECTED_FIELDS: dict[str, str] = {
    # State stores
    "transcript_store": "history get/append + max_history config",
    "tool_result_store": "passed to run_query_engine",
    # LLM runtime (late-bound at request time)
    "llm": "AsyncOpenAI client; engine returns user-facing message when None",
    "omicsclaw_model": "model id surfaced via identity anchor + QueryEngineConfig",
    "llm_provider_name": "provider name surfaced via identity anchor + deepseek special case",
    "session_manager": "passed to _assemble_chat_context for memory scoping",
    # Path + size constants
    "omicsclaw_dir": "passed to system_prompt builder + tool_runtime context",
    "max_history": "transcript_store sizing",
    "max_history_chars": "transcript_store sizing (None = unlimited)",
    "max_conversations": "transcript_store sizing",
    # Callbacks / functions
    "audit_fn": "tool_call / tool_error / policy_blocked audit events",
    "usage_accumulator": "QueryEngineCallbacks.accumulate_usage",
    # Skill metadata
    "skill_aliases": "passed to _assemble_chat_context for skill routing",
    "deep_learning_methods": "before_tool DL slow-warning gate",
    # Tool plumbing (built once per request by bot)
    "tool_runtime": "passed to run_query_engine",
    "tool_registry": "to_openai_tools_for_request filtering",
    "callbacks_builder": "constructs QueryEngineCallbacks per request",
}


def _make_deps(**overrides) -> EngineDependencies:
    defaults = {name: object() for name in EXPECTED_FIELDS}
    defaults.update(overrides)
    return EngineDependencies(**defaults)


def test_all_expected_fields_present() -> None:
    actual = {f.name for f in dataclasses.fields(EngineDependencies)}
    expected = set(EXPECTED_FIELDS)
    missing = expected - actual
    extra = actual - expected
    assert not missing, f"EngineDependencies is missing required fields: {missing}"
    assert not extra, (
        f"EngineDependencies has fields not documented in EXPECTED_FIELDS: "
        f"{extra}. Either add them to the test's documentation map or drop "
        f"them from the dataclass."
    )


def test_is_frozen() -> None:
    deps = _make_deps()
    with pytest.raises(dataclasses.FrozenInstanceError):
        deps.llm = object()  # type: ignore[misc]


def test_field_count_matches_documentation() -> None:
    """Hard-pinned count: bumps require an explicit acknowledgment that
    a new bot-side dependency leaked into the engine surface."""
    assert len(dataclasses.fields(EngineDependencies)) == 17


def test_construct_with_concrete_values_round_trips() -> None:
    deps = _make_deps(
        omicsclaw_model="m",
        llm_provider_name="p",
        omicsclaw_dir="/tmp/oc",
        max_history=80,
        max_history_chars=None,
        max_conversations=200,
        skill_aliases=("a", "b"),
        deep_learning_methods=frozenset({"scvi", "scgpt"}),
    )
    assert deps.omicsclaw_model == "m"
    assert deps.llm_provider_name == "p"
    assert deps.max_history_chars is None
    assert deps.skill_aliases == ("a", "b")
    assert "scvi" in deps.deep_learning_methods
