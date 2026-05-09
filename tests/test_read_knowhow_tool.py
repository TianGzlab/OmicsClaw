"""Tests for the ``read_knowhow(name)`` RAG tool.

Phase 2 (Task 2.3) of the system-prompt-compression refactor. Pairs with
the headline-only mode (Task 2.2): the system prompt only ships
``→ {label}: {critical_rule}`` summaries; the model fetches the full
body on demand by name.

These tests pin three behaviors:
1. ``KnowHowInjector.read_knowhow(name)`` resolves by filename, doc_id,
   or human-readable label and returns the full markdown body.
2. Unknown names return a clear error message — not an exception — so
   tool-call failures don't stall the conversation.
3. The runtime tool spec is registered with the right description hint
   so the model knows when to call it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omicsclaw.knowledge.knowhow import KnowHowInjector

ROOT = Path(__file__).resolve().parent.parent
KNOWHOW_DIR = ROOT / "knowledge_base" / "knowhows"


def _injector() -> KnowHowInjector:
    return KnowHowInjector(knowhows_dir=KNOWHOW_DIR)


# --- KnowHowInjector.read_knowhow --------------------------------------------


def test_read_knowhow_resolves_by_full_filename() -> None:
    body = _injector().read_knowhow("KH-sc-de-guardrails.md")
    assert body, "expected non-empty body for known KH filename"
    assert "Single-Cell Differential Expression Guardrails" in body


def test_read_knowhow_resolves_by_doc_id() -> None:
    body = _injector().read_knowhow("sc-de-guardrails")
    assert body, "expected non-empty body when called with doc_id"
    assert "Single-Cell Differential Expression Guardrails" in body


def test_read_knowhow_resolves_by_label() -> None:
    body = _injector().read_knowhow("Single-Cell Differential Expression Guardrails")
    assert body, "expected non-empty body when called with label"
    assert "marker ranking" in body.lower() or "differential expression" in body.lower()


def test_read_knowhow_unknown_name_returns_empty_not_exception() -> None:
    body = _injector().read_knowhow("does-not-exist")
    assert body == "", "unknown name should return empty string, not raise"


def test_read_knowhow_empty_input_returns_empty() -> None:
    assert _injector().read_knowhow("") == ""
    assert _injector().read_knowhow("   ") == ""


# --- ToolSpec registration ----------------------------------------------------


def test_read_knowhow_tool_spec_is_registered() -> None:
    """The bot-surface ToolSpec for read_knowhow must exist with a name
    parameter and a description that hints to the model when to call it."""
    from omicsclaw.runtime.bot_tools import BotToolContext, build_bot_tool_specs

    specs = build_bot_tool_specs(
        BotToolContext(
            skill_names=("sc-de", "spatial-domains"),
            domain_briefing="(test briefing)",
        )
    )
    by_name = {spec.name: spec for spec in specs}
    assert "read_knowhow" in by_name, (
        f"read_knowhow not registered; registered tools: {sorted(by_name)}"
    )
    spec = by_name["read_knowhow"]
    # Schema sanity
    assert spec.parameters.get("type") == "object"
    properties = spec.parameters.get("properties", {})
    assert "name" in properties, "read_knowhow must accept a 'name' parameter"
    required = spec.parameters.get("required", [])
    assert "name" in required, "'name' must be a required parameter"
    # Description should advertise the trigger
    assert "headline" in spec.description.lower() or "guard" in spec.description.lower()
    # Read-only and concurrency-safe (just file reads)
    assert spec.read_only is True
    assert spec.concurrency_safe is True


def test_read_knowhow_tool_spec_lists_bot_surface() -> None:
    from omicsclaw.runtime.bot_tools import BotToolContext, build_bot_tool_specs

    specs = {s.name: s for s in build_bot_tool_specs(
        BotToolContext(skill_names=(), domain_briefing="(t)")
    )}
    spec = specs["read_knowhow"]
    assert "bot" in spec.surfaces


# --- Headline hint text -------------------------------------------------------


def test_headline_only_output_mentions_read_knowhow_tool() -> None:
    """Headline-only output must tell the model how to fetch the full body."""
    text = _injector().get_constraints(
        skill="sc-de",
        query="run sc-de differential expression",
        domain="singlecell",
        headline_only=True,
    )
    assert "read_knowhow" in text, (
        "headline-only constraints must reference the read_knowhow tool "
        "so the model knows the fetch path"
    )


def test_headline_only_hint_covers_non_bot_surfaces_with_file_path_fallback() -> None:
    """The headline hint is injected on bot/interactive/pipeline surfaces but
    ``read_knowhow`` is only registered for the bot surface. The hint must
    therefore also point at a surface-agnostic fallback (the on-disk markdown
    path) so interactive / pipeline agents can still resolve the guard
    without inventing a non-existent tool call.
    """
    text = _injector().get_constraints(
        skill="sc-de",
        query="run sc-de differential expression",
        domain="singlecell",
        headline_only=True,
    )
    assert "knowledge_base/knowhows" in text, (
        "headline hint must include the markdown file-path fallback so "
        "interactive / pipeline surfaces (where read_knowhow is not a "
        "registered tool) have a working escape hatch."
    )
