from __future__ import annotations

import asyncio
import sys
import types

import numpy as np
import pandas as pd
import pytest
from anndata import AnnData

if "openai" not in sys.modules:
    sys.modules["openai"] = types.SimpleNamespace(AsyncOpenAI=object, APIError=Exception)

import bot.core as core


def _write_test_h5ad(
    path,
    obs: pd.DataFrame,
    *,
    standardized: bool = False,
    preprocessed: bool = False,
) -> None:
    adata = AnnData(
        X=np.ones((len(obs), 4), dtype=float),
        obs=obs.copy(),
        var=pd.DataFrame(index=[f"gene_{i}" for i in range(4)]),
    )
    if standardized:
        adata.uns["omicsclaw_input_contract"] = {
            "version": "1.0",
            "domain": "singlecell",
            "standardized": True,
            "standardized_by": "sc-standardize-input",
        }
    if preprocessed:
        adata.obsm["X_pca"] = np.ones((len(obs), 2), dtype=float)
        adata.obs["leiden"] = pd.Categorical(["0"] * len(obs))
    adata.write_h5ad(path)


def test_find_batch_key_candidates_prefers_batch_like_obs_columns(tmp_path):
    h5ad_path = tmp_path / "integration_input.h5ad"
    obs = pd.DataFrame(
        {
            "sample_id": ["S1", "S1", "S2", "S2", "S3", "S3"],
            "patient_id": ["P1", "P1", "P1", "P1", "P2", "P2"],
            "condition": ["ctrl", "ctrl", "stim", "stim", "ctrl", "ctrl"],
            "leiden": ["0", "0", "1", "1", "2", "2"],
        },
        index=[f"cell_{i}" for i in range(6)],
    )
    _write_test_h5ad(h5ad_path, obs)

    result = core._find_batch_key_candidates(h5ad_path)
    candidate_names = [item["column"] for item in result["candidates"]]

    assert "sample_id" in candidate_names
    assert "patient_id" in candidate_names
    assert "condition" in candidate_names
    assert "leiden" not in candidate_names


def test_batch_key_clarification_is_returned_when_batch_key_missing(tmp_path, monkeypatch):
    h5ad_path = tmp_path / "needs_choice.h5ad"
    obs = pd.DataFrame(
        {
            "sample_id": ["S1", "S1", "S2", "S2"],
            "patient_id": ["P1", "P1", "P2", "P2"],
            "condition": ["ctrl", "ctrl", "stim", "stim"],
        },
        index=[f"cell_{i}" for i in range(4)],
    )
    _write_test_h5ad(h5ad_path, obs)

    monkeypatch.setattr(core, "TRUSTED_DATA_DIRS", [tmp_path])

    message = core._maybe_require_batch_key_selection(
        "sc-batch-integration",
        str(h5ad_path),
        {},
    )

    assert "Batch-key clarification needed" in message
    assert "`sample_id`" in message
    assert "`patient_id`" in message
    assert "`condition`" in message
    assert "I have not started the integration yet" in message


def test_execute_omicsclaw_pauses_before_running_when_batch_key_missing(tmp_path, monkeypatch):
    h5ad_path = tmp_path / "needs_user_choice.h5ad"
    obs = pd.DataFrame(
        {
            "sample_id": ["S1", "S1", "S2", "S2"],
            "patient_id": ["P1", "P1", "P2", "P2"],
            "condition": ["ctrl", "ctrl", "stim", "stim"],
        },
        index=[f"cell_{i}" for i in range(4)],
    )
    _write_test_h5ad(h5ad_path, obs)

    monkeypatch.setattr(core, "TRUSTED_DATA_DIRS", [tmp_path])

    called = {"subprocess": False}

    async def _fake_create_subprocess_exec(*_args, **_kwargs):
        called["subprocess"] = True
        raise AssertionError("subprocess should not start before batch_key is chosen")

    monkeypatch.setattr(core.asyncio, "create_subprocess_exec", _fake_create_subprocess_exec)

    result = asyncio.run(
        core.execute_omicsclaw(
            {
                "skill": "sc-batch-integration",
                "mode": "path",
                "file_path": str(h5ad_path),
                "method": "harmony",
            },
            chat_id="test-chat",
        )
    )

    assert "Workflow check paused before running `sc-batch-integration`." in result
    assert "`sc-standardize-input`" in result
    assert "`sc-preprocessing`" in result
    assert called["subprocess"] is False


def test_batch_key_clarification_is_skipped_when_valid_batch_key_is_provided(tmp_path):
    h5ad_path = tmp_path / "explicit_batch_key.h5ad"
    obs = pd.DataFrame(
        {
            "sample_id": ["S1", "S1", "S2", "S2"],
            "condition": ["ctrl", "ctrl", "stim", "stim"],
        },
        index=[f"cell_{i}" for i in range(4)],
    )
    _write_test_h5ad(h5ad_path, obs)

    message = core._maybe_require_batch_key_selection(
        "sc-batch-integration",
        str(h5ad_path),
        {"batch_key": "sample_id"},
    )

    assert message == ""


def test_non_h5ad_input_prompts_standardize_then_preprocess_workflow(tmp_path):
    csv_path = tmp_path / "counts.csv"
    csv_path.write_text("gene,c1,c2\nG1,1,2\nG2,3,4\n", encoding="utf-8")

    message = core._maybe_require_batch_integration_workflow(
        "sc-batch-integration",
        str(csv_path),
        {},
    )

    assert "Workflow check paused before running `sc-batch-integration`." in message
    assert "`sc-standardize-input`" in message
    assert "`sc-preprocessing`" in message


def test_unstandardized_h5ad_prompts_workflow_before_batch_selection(tmp_path):
    h5ad_path = tmp_path / "raw_like_input.h5ad"
    obs = pd.DataFrame(
        {
            "sample_id": ["S1", "S1", "S2", "S2"],
        },
        index=[f"cell_{i}" for i in range(4)],
    )
    _write_test_h5ad(h5ad_path, obs, standardized=False, preprocessed=False)

    message = core._maybe_require_batch_integration_workflow(
        "sc-batch-integration",
        str(h5ad_path),
        {},
    )

    assert "was not marked as standardized" in message
    assert "does not show the usual preprocessing markers" in message


def test_standardized_preprocessed_h5ad_does_not_pause_workflow(tmp_path):
    h5ad_path = tmp_path / "ready_input.h5ad"
    obs = pd.DataFrame(
        {
            "sample_id": ["S1", "S1", "S2", "S2"],
        },
        index=[f"cell_{i}" for i in range(4)],
    )
    _write_test_h5ad(h5ad_path, obs, standardized=True, preprocessed=True)

    message = core._maybe_require_batch_integration_workflow(
        "sc-batch-integration",
        str(h5ad_path),
        {},
    )

    assert message == ""


def test_validate_input_path_accepts_trusted_directories_when_allowed(tmp_path, monkeypatch):
    tenx_dir = tmp_path / "tenx_dir"
    tenx_dir.mkdir()

    monkeypatch.setattr(core, "TRUSTED_DATA_DIRS", [tmp_path])

    assert core.validate_input_path(str(tenx_dir), allow_dir=True) == tenx_dir.resolve()
    assert core.validate_input_path(str(tenx_dir), allow_dir=False) is None


def test_auto_prepare_sc_batch_integration_runs_upstream_workflow(tmp_path, monkeypatch):
    input_path = tmp_path / "raw_input.h5ad"
    _write_test_h5ad(input_path, pd.DataFrame(index=["c1", "c2"]))

    standardize_out = tmp_path / "std_out"
    preprocess_out = tmp_path / "prep_out"
    standardize_out.mkdir()
    preprocess_out.mkdir()
    (standardize_out / "processed.h5ad").write_text("ok", encoding="utf-8")
    (preprocess_out / "processed.h5ad").write_text("ok", encoding="utf-8")

    monkeypatch.setattr(
        core,
        "_get_sc_batch_integration_workflow_plan",
        lambda skill_key, input_path, args: {
            "file_path": input_path and core.Path(input_path),
            "reasons": ["needs standardization", "needs preprocessing"],
            "start_step": 1,
        },
    )

    calls = []

    async def _fake_run_step(**kwargs):
        calls.append(kwargs["skill_key"])
        if kwargs["skill_key"] == "sc-standardize-input":
            return {
                "success": True,
                "returncode": 0,
                "out_dir": standardize_out,
                "guidance_block": "",
                "error_text": "",
            }
        return {
            "success": True,
            "returncode": 0,
            "out_dir": preprocess_out,
            "guidance_block": "",
            "error_text": "",
        }

    monkeypatch.setattr(core, "_run_omics_skill_step", _fake_run_step)
    monkeypatch.setattr(core, "_maybe_require_batch_key_selection", lambda *args, **kwargs: "")

    async def _fake_execute(args, session_id=None, chat_id=0):
        assert args["confirm_workflow_skip"] is True
        assert args["auto_prepare"] is False
        assert args["file_path"] == str(preprocess_out / "processed.h5ad")
        return "final integration ran"

    monkeypatch.setattr(core, "execute_omicsclaw", _fake_execute)

    result = asyncio.run(
        core._auto_prepare_sc_batch_integration(
            args={"auto_prepare": True, "batch_key": "sample_id"},
            skill_key="sc-batch-integration",
            input_path=str(input_path),
            session_id=None,
            chat_id="chat",
        )
    )

    assert calls == ["sc-standardize-input", "sc-preprocessing"]
    assert "Automatic preparation workflow completed" in result
    assert "final integration ran" in result


def test_auto_prepare_sc_batch_integration_stops_for_batch_choice_after_upstream_steps(tmp_path, monkeypatch):
    input_path = tmp_path / "raw_input.h5ad"
    _write_test_h5ad(input_path, pd.DataFrame(index=["c1", "c2"]))

    preprocess_out = tmp_path / "prep_out"
    preprocess_out.mkdir()
    (preprocess_out / "processed.h5ad").write_text("ok", encoding="utf-8")

    monkeypatch.setattr(
        core,
        "_get_sc_batch_integration_workflow_plan",
        lambda skill_key, input_path, args: {
            "file_path": input_path and core.Path(input_path),
            "reasons": ["needs preprocessing"],
            "start_step": 2,
        },
    )

    async def _fake_run_step(**kwargs):
        return {
            "success": True,
            "returncode": 0,
            "out_dir": preprocess_out,
            "guidance_block": "",
            "error_text": "",
        }

    monkeypatch.setattr(core, "_run_omics_skill_step", _fake_run_step)
    monkeypatch.setattr(
        core,
        "_maybe_require_batch_key_selection",
        lambda *args, **kwargs: "Please tell me which column should be used as `batch_key`.",
    )

    called = {"final": False}

    async def _fake_execute(args, session_id=None, chat_id=0):
        called["final"] = True
        return "should not run"

    monkeypatch.setattr(core, "execute_omicsclaw", _fake_execute)

    result = asyncio.run(
        core._auto_prepare_sc_batch_integration(
            args={"auto_prepare": True},
            skill_key="sc-batch-integration",
            input_path=str(input_path),
            session_id=None,
            chat_id="chat",
        )
    )

    assert "Automatic preparation workflow completed" in result
    assert "Please tell me which column should be used as `batch_key`." in result
    assert called["final"] is False


def test_resume_pending_preflight_request_replays_skill_with_mapped_args(monkeypatch):
    core.pending_preflight_requests.clear()
    core.pending_preflight_requests["chat-preflight"] = {
        "tool_name": "omicsclaw",
        "original_args": {
            "skill": "sc-de",
            "mode": "path",
            "file_path": "/tmp/input.h5ad",
            "extra_args": ["--method", "deseq2_r"],
        },
        "payload": {
            "kind": "preflight",
            "skill_name": "sc-de",
            "status": "needs_user_input",
            "guidance": [],
            "confirmations": [],
            "missing_requirements": [],
            "pending_fields": [
                {"key": "groupby", "flag": "--groupby", "value_type": "string", "choices": [], "aliases": ["groupby"], "prompt": "confirm groupby"},
                {"key": "group1", "flag": "--group1", "value_type": "string", "choices": [], "aliases": ["group1"], "prompt": "confirm group1"},
                {"key": "group2", "flag": "--group2", "value_type": "string", "choices": [], "aliases": ["group2"], "prompt": "confirm group2"},
            ],
        },
        "pending_fields": [
            {"key": "groupby", "flag": "--groupby", "value_type": "string", "choices": [], "aliases": ["groupby"], "prompt": "confirm groupby"},
            {"key": "group1", "flag": "--group1", "value_type": "string", "choices": [], "aliases": ["group1"], "prompt": "confirm group1"},
            {"key": "group2", "flag": "--group2", "value_type": "string", "choices": [], "aliases": ["group2"], "prompt": "confirm group2"},
        ],
        "answers": {},
    }

    async def _fake_execute(args, session_id=None, chat_id=0):
        assert args["skill"] == "sc-de"
        assert "--groupby" in args["extra_args"]
        assert "condition" in args["extra_args"]
        assert "treated" in args["extra_args"]
        assert "control" in args["extra_args"]
        return "analysis done"

    monkeypatch.setattr(core, "execute_omicsclaw", _fake_execute)

    result = asyncio.run(
        core._maybe_resume_pending_preflight_request(
            chat_id="chat-preflight",
            user_content="groupby=condition\ngroup1=treated\ngroup2=control",
            session_id=None,
        )
    )

    assert result == "analysis done"
    assert "chat-preflight" not in core.pending_preflight_requests


def test_resume_pending_preflight_request_keeps_remaining_questions(monkeypatch):
    core.pending_preflight_requests.clear()
    core.pending_preflight_requests["chat-preflight"] = {
        "tool_name": "omicsclaw",
        "original_args": {
            "skill": "sc-de",
            "mode": "path",
            "file_path": "/tmp/input.h5ad",
            "extra_args": ["--method", "deseq2_r"],
        },
        "payload": {
            "kind": "preflight",
            "skill_name": "sc-de",
            "status": "needs_user_input",
            "guidance": [],
            "confirmations": [],
            "missing_requirements": [],
            "pending_fields": [
                {"key": "groupby", "flag": "--groupby", "value_type": "string", "choices": [], "aliases": ["groupby"], "prompt": "Which groupby column should be used"},
                {"key": "group1", "flag": "--group1", "value_type": "string", "choices": [], "aliases": ["group1"], "prompt": "What is group1"},
            ],
        },
        "pending_fields": [
            {"key": "groupby", "flag": "--groupby", "value_type": "string", "choices": [], "aliases": ["groupby"], "prompt": "Which groupby column should be used"},
            {"key": "group1", "flag": "--group1", "value_type": "string", "choices": [], "aliases": ["group1"], "prompt": "What is group1"},
        ],
        "answers": {},
    }

    async def _fake_execute(args, session_id=None, chat_id=0):
        raise AssertionError("should not execute until all required answers are present")

    monkeypatch.setattr(core, "execute_omicsclaw", _fake_execute)

    result = asyncio.run(
        core._maybe_resume_pending_preflight_request(
            chat_id="chat-preflight",
            user_content="groupby=condition",
            session_id=None,
        )
    )

    assert "## Accepted answers" in result
    assert "What is group1?" in result
    assert core.pending_preflight_requests["chat-preflight"]["answers"]["groupby"] == "condition"


def test_resume_pending_preflight_request_replays_confirmation_only_prompt(monkeypatch):
    core.pending_preflight_requests.clear()
    core.pending_preflight_requests["chat-preflight"] = {
        "tool_name": "omicsclaw",
        "original_args": {
            "skill": "sc-preprocessing",
            "mode": "path",
            "file_path": "/tmp/pbmc3k_raw.h5ad",
            "extra_args": ["--method", "scanpy"],
        },
        "payload": {
            "kind": "preflight",
            "skill_name": "sc-preprocessing",
            "status": "needs_user_input",
            "guidance": [],
            "confirmations": [
                "Confirm that the default first-pass filtering thresholds are acceptable."
            ],
            "missing_requirements": [],
            "pending_fields": [],
        },
        "pending_fields": [],
        "answers": {},
    }

    async def _fake_execute(args, session_id=None, chat_id=0):
        assert args["skill"] == "sc-preprocessing"
        assert args["confirmed_preflight"] is True
        return "preprocessing done"

    monkeypatch.setattr(core, "execute_omicsclaw", _fake_execute)

    result = asyncio.run(
        core._maybe_resume_pending_preflight_request(
            chat_id="chat-preflight",
            user_content="确认，可以继续使用默认阈值",
            session_id=None,
        )
    )

    assert result == "preprocessing done"
    assert "chat-preflight" not in core.pending_preflight_requests


def test_resume_pending_preflight_request_does_not_treat_new_request_as_confirmation(monkeypatch):
    core.pending_preflight_requests.clear()
    core.pending_preflight_requests["chat-preflight"] = {
        "tool_name": "omicsclaw",
        "original_args": {
            "skill": "sc-preprocessing",
            "mode": "path",
            "file_path": "/tmp/pbmc3k_raw.h5ad",
            "extra_args": ["--method", "scanpy"],
        },
        "payload": {
            "kind": "preflight",
            "skill_name": "sc-preprocessing",
            "status": "needs_user_input",
            "guidance": [],
            "confirmations": [
                "Confirm that the default first-pass filtering thresholds are acceptable."
            ],
            "missing_requirements": [],
            "pending_fields": [],
        },
        "pending_fields": [],
        "answers": {},
    }

    async def _fake_execute(args, session_id=None, chat_id=0):
        raise AssertionError("should not execute without an affirmative confirmation")

    monkeypatch.setattr(core, "execute_omicsclaw", _fake_execute)

    result = asyncio.run(
        core._maybe_resume_pending_preflight_request(
            chat_id="chat-preflight",
            user_content="先跑 sc-qc 看一下质控",
            session_id=None,
        )
    )

    assert result is None
    assert "chat-preflight" not in core.pending_preflight_requests
