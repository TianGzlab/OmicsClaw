"""Phase 4 (Task 4.4) tests for the 7 predicate-gated context layers.

Each layer has a deterministic trigger (its predicate) and ships a small
rule_text block. The tests verify two things per layer:

  1. The layer appears in the assembled prompt only when its predicate
     fires.
  2. The rule_text covers the substance of the corresponding section
     from the deleted ``execution_discipline`` / ``skill_contract`` /
     ``role_guardrails`` layers, preventing silent rule loss during the
     migration.

Layer name -> canonical home table reference (Q9):

  | Predicate                              | Layer                          |
  |----------------------------------------|--------------------------------|
  | implementation_intent                  | scope_and_minimal_change_rule  |
  | anndata_or_file_path_in_query          | file_path_and_inspect_rule     |
  | pdf_or_paper_intent                    | parse_literature_rule          |
  | workspace_active                       | workspace_continuity_rule      |
  | chat_surface                           | chat_mode_rule                 |
  | memory_in_use                          | memory_hygiene_rule            |
  | non_trivial_no_capability              | capability_routing_hint_rule   |
"""

from __future__ import annotations

import pytest

from omicsclaw.runtime.context_assembler import assemble_prompt_context
from omicsclaw.runtime.context_layers import ContextAssemblyRequest


def _layer_names(req: ContextAssemblyRequest) -> set[str]:
    asm = assemble_prompt_context(request=req)
    return {layer.name for layer in asm.layers}


def _layer_text(req: ContextAssemblyRequest, name: str) -> str:
    for layer in assemble_prompt_context(request=req).layers:
        if layer.name == name:
            return layer.content
    return ""


# --- implementation_intent → scope_and_minimal_change_rule ------------------


def test_scope_and_minimal_change_rule_fires_on_implementation_intent() -> None:
    req = ContextAssemblyRequest(surface="bot", query="implement a new sc-de variant")
    assert "scope_and_minimal_change_rule" in _layer_names(req)


def test_scope_and_minimal_change_rule_quiet_on_plain_question() -> None:
    req = ContextAssemblyRequest(surface="bot", query="what is UMAP")
    assert "scope_and_minimal_change_rule" not in _layer_names(req)


def test_scope_and_minimal_change_rule_content() -> None:
    req = ContextAssemblyRequest(surface="bot", query="implement a new sc-de variant")
    text = _layer_text(req, "scope_and_minimal_change_rule").lower()
    assert "smallest" in text or "minimal" in text
    assert "scope" in text or "stated request" in text


# --- anndata_or_file_path_in_query → file_path_and_inspect_rule -------------


def test_file_path_and_inspect_rule_fires_on_h5ad() -> None:
    req = ContextAssemblyRequest(surface="bot", query="run sc-de on /tmp/sample.h5ad")
    assert "file_path_and_inspect_rule" in _layer_names(req)


def test_file_path_and_inspect_rule_quiet_on_plain_question() -> None:
    req = ContextAssemblyRequest(surface="bot", query="what is UMAP")
    assert "file_path_and_inspect_rule" not in _layer_names(req)


def test_file_path_and_inspect_rule_content() -> None:
    req = ContextAssemblyRequest(surface="bot", query="run sc-de on /tmp/sample.h5ad")
    text = _layer_text(req, "file_path_and_inspect_rule").lower()
    assert "exact" in text or "exactly" in text
    assert "inspect_data" in text


# --- pdf_or_paper_intent → parse_literature_rule ----------------------------


def test_parse_literature_rule_fires_on_pdf_query() -> None:
    req = ContextAssemblyRequest(surface="bot", query="extract GEO accession from /tmp/paper.pdf")
    assert "parse_literature_rule" in _layer_names(req)


def test_parse_literature_rule_quiet_on_unrelated_query() -> None:
    req = ContextAssemblyRequest(surface="bot", query="run sc-de on data")
    assert "parse_literature_rule" not in _layer_names(req)


def test_parse_literature_rule_content() -> None:
    req = ContextAssemblyRequest(surface="bot", query="extract GEO accession from /tmp/paper.pdf")
    text = _layer_text(req, "parse_literature_rule").lower()
    assert "parse_literature" in text


# --- workspace_active → workspace_continuity_rule ---------------------------


def test_workspace_continuity_rule_fires_when_workspace_set() -> None:
    req = ContextAssemblyRequest(surface="interactive", workspace="/tmp/run42")
    assert "workspace_continuity_rule" in _layer_names(req)


def test_workspace_continuity_rule_quiet_when_no_workspace() -> None:
    req = ContextAssemblyRequest(surface="interactive")
    assert "workspace_continuity_rule" not in _layer_names(req)


def test_workspace_continuity_rule_content() -> None:
    req = ContextAssemblyRequest(surface="interactive", pipeline_workspace="/tmp/p")
    text = _layer_text(req, "workspace_continuity_rule").lower()
    assert "plan.md" in text or "workspace" in text
    assert "source of truth" in text or "rerun" in text


# --- chat_surface → chat_mode_rule ------------------------------------------


def test_chat_mode_rule_fires_on_bot_surface() -> None:
    req = ContextAssemblyRequest(surface="bot", query="explain UMAP to me")
    assert "chat_mode_rule" in _layer_names(req)


def test_chat_mode_rule_quiet_on_interactive_surface() -> None:
    req = ContextAssemblyRequest(surface="interactive", query="explain UMAP to me")
    assert "chat_mode_rule" not in _layer_names(req)


def test_chat_mode_rule_content() -> None:
    req = ContextAssemblyRequest(surface="bot", query="explain UMAP")
    text = _layer_text(req, "chat_mode_rule").lower()
    assert "explanation" in text or "explain" in text
    assert "artifact" in text or "saved" in text


# --- memory_in_use → memory_hygiene_rule ------------------------------------


def test_memory_hygiene_rule_fires_on_remember_keyword() -> None:
    req = ContextAssemblyRequest(surface="bot", query="please remember that I prefer DESeq2")
    assert "memory_hygiene_rule" in _layer_names(req)


def test_memory_hygiene_rule_quiet_on_unrelated_query() -> None:
    req = ContextAssemblyRequest(surface="bot", query="run sc-de")
    assert "memory_hygiene_rule" not in _layer_names(req)


def test_memory_hygiene_rule_content() -> None:
    req = ContextAssemblyRequest(surface="bot", query="please remember my preference")
    text = _layer_text(req, "memory_hygiene_rule").lower()
    assert "secret" in text or "credential" in text or "pii" in text
    assert "scoped" in text or "preference" in text or "transient" in text


def test_memory_hygiene_rule_disambiguates_task_create() -> None:
    """Regression for the chat path where the LLM routed "记住 X" requests
    to ``task_create`` instead of ``remember`` (session 945434f1 in the
    desktop trace). The rule must explicitly name the wrong tool so the
    model breaks the tie correctly when both are visible.
    """
    req = ContextAssemblyRequest(surface="bot", query="please remember my preference")
    text = _layer_text(req, "memory_hygiene_rule")
    assert "remember" in text.lower()
    assert "task_create" in text.lower(), (
        "memory_hygiene_rule must name ``task_create`` explicitly as the "
        "wrong tool — naming only ``remember`` is not enough to break the "
        "ambiguity in practice."
    )


# --- non_trivial_no_capability → capability_routing_hint_rule ---------------


def test_capability_routing_hint_fires_on_substantive_query_without_capability() -> None:
    req = ContextAssemblyRequest(
        surface="bot",
        query="do differential expression on this single-cell dataset",
        capability_context="",
    )
    assert "capability_routing_hint_rule" in _layer_names(req)


def test_capability_routing_hint_quiet_when_capability_already_present() -> None:
    req = ContextAssemblyRequest(
        surface="bot",
        query="do differential expression on this single-cell dataset",
        capability_context="## Deterministic Capability Assessment\n- coverage: exact_skill",
    )
    assert "capability_routing_hint_rule" not in _layer_names(req)


def test_capability_routing_hint_content() -> None:
    req = ContextAssemblyRequest(
        surface="bot",
        query="do differential expression on this single-cell dataset",
        capability_context="",
    )
    text = _layer_text(req, "capability_routing_hint_rule").lower()
    assert "resolve_capability" in text
    assert "canonical" in text or "alias" in text


# --- Layer size budgets ------------------------------------------------------


@pytest.mark.parametrize(
    "name,trigger_req",
    [
        ("scope_and_minimal_change_rule",
         ContextAssemblyRequest(surface="bot", query="implement a new sc-de variant")),
        ("file_path_and_inspect_rule",
         ContextAssemblyRequest(surface="bot", query="run sc-de on /tmp/sample.h5ad")),
        ("parse_literature_rule",
         ContextAssemblyRequest(surface="bot", query="extract GEO accession from /tmp/paper.pdf")),
        ("workspace_continuity_rule",
         ContextAssemblyRequest(surface="interactive", workspace="/tmp/run42")),
        ("chat_mode_rule",
         ContextAssemblyRequest(surface="bot", query="explain UMAP")),
        ("memory_hygiene_rule",
         ContextAssemblyRequest(surface="bot", query="please remember my preference")),
        ("capability_routing_hint_rule",
         ContextAssemblyRequest(
             surface="bot",
             query="do differential expression on this single-cell dataset",
             capability_context="",
         )),
    ],
)
def test_predicate_gated_rule_under_400_chars(name: str, trigger_req: ContextAssemblyRequest) -> None:
    text = _layer_text(trigger_req, name)
    assert text, f"{name} did not fire even with its trigger request"
    assert len(text) <= 400, f"{name} payload {len(text)} chars; budget is 400"
