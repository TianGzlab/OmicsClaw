"""Behavior of ``_validate_omicsclaw_args``.

The validator runs at the top of ``bot.tool_executors.execute_omicsclaw``
to catch the documented LLM hallucination of nesting tool args under a
``params`` key (instead of using the schema's top-level ``file_path``).
Each test pins one observable behavior of the helper.
"""

from __future__ import annotations

# bot.core must load first so its forward-declared symbols are in place
# before bot.tool_executors completes import (the two modules are
# mutually recursive at module scope — see bot/tool_executors.py:11-25).
import asyncio

import bot.core  # noqa: F401  (load order, see docstring)

from bot.tool_executors import _validate_omicsclaw_args, execute_omicsclaw


def test_minimal_valid_args_returns_empty_string() -> None:
    """Tracer bullet: a valid call passes through silently."""
    assert _validate_omicsclaw_args({"skill": "sc-qc", "mode": "demo"}) == ""


def test_params_nesting_returns_actionable_error_naming_file_path() -> None:
    """Replicates the audit-log LLM hallucination: nesting tool args
    under a ``params`` key. The error must surface the rejected key
    *and* the correct top-level key the LLM should use instead, so the
    next turn fixes the call instead of triggering filesystem
    exploration."""
    result = _validate_omicsclaw_args({
        "skill": "sc-preprocessing",
        "mode": "file",
        "params": {"input": "/x.h5ad"},
    })
    assert result != ""
    assert "params" in result
    assert "file_path" in result


def test_typo_close_to_schema_key_yields_targeted_suggestion() -> None:
    """A near-miss like ``file-path`` (kebab instead of snake_case)
    should produce a targeted suggestion, not just a dump of every
    accepted key — so the LLM sees exactly which key it meant."""
    result = _validate_omicsclaw_args({
        "skill": "sc-qc",
        "mode": "path",
        "file-path": "/x.h5ad",
    })
    assert "file-path" in result
    assert "did you mean" in result.lower()
    assert "file_path" in result


def test_confirmed_preflight_internal_flag_is_silently_accepted() -> None:
    """``confirmed_preflight`` is injected by the preflight chain (not
    in the LLM-facing schema). The validator must whitelist it so the
    auto-prep flow doesn't trip its own guard."""
    assert _validate_omicsclaw_args({
        "skill": "sc-qc",
        "mode": "demo",
        "confirmed_preflight": True,
    }) == ""


def test_full_realistic_args_dict_passes_silently() -> None:
    """A heavy but fully-schema-compliant call (the shape the LLM
    *should* be sending) must not trip the validator. Exercises many
    schema keys at once so additions or renames in
    ``omicsclaw/runtime/bot_tools.py`` surface here as a regression."""
    assert _validate_omicsclaw_args({
        "skill": "sc-batch-integration",
        "mode": "path",
        "file_path": "/abs/path.h5ad",
        "method": "harmony",
        "batch_key": "sample",
        "data_type": "scrna",
        "n_epochs": 30,
        "extra_args": ["--seed", "42"],
        "query": "integrate by sample",
        "return_media": "umap",
        "confirm_workflow_skip": False,
        "auto_prepare": True,
    }) == ""


def test_execute_omicsclaw_short_circuits_on_malformed_params_call() -> None:
    """End-to-end: feed execute_omicsclaw the exact malformed shape
    captured in bot/logs/audit.jsonl. The function must return the
    validator's actionable error (mentioning ``file_path``) and not
    the legacy ``No input file available...`` fallback that previously
    trapped the LLM in a discovery loop."""
    bad_args = {
        "mode": "file",
        "skill": "sc-preprocessing",
        "params": {
            "input": "/data/beifen/zhouwg_data/project/OmicsClaw/data/pbmc3k_raw.h5ad",
            "species": "human",
        },
    }
    result = asyncio.run(
        execute_omicsclaw(bad_args, session_id="__interactive__", chat_id=0)
    )
    assert "file_path" in result
    assert "Upload a file" not in result
