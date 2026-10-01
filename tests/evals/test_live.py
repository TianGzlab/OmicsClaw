"""The real-model routing eval's parts, without a real model.

``RecordingProvider`` wraps a ``ScriptedProvider`` here, which stands in
for a model that picks a skill. The approval policy gets one test per
known way around it: the routing eval runs in the owner's own conda
environment, and each bypass below was once a command that would have
run ``pip install`` there. None of these tests writes ``eval_results``,
so the scripted-eval report is not affected.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

from omicsclaw.evals import Result, ScriptedProvider, ScriptedTurn, run_case, tool_call
from omicsclaw.evals.case import SkillRun
from omicsclaw.evals.live import (
    Denial,
    RecordingProvider,
    Seed,
    SeedReport,
    build_report,
    compare,
    judge,
    live_case,
    load_seeds,
    main,
    markdown,
    routing_policy,
    to_dict,
    trial_record,
    write_json,
)
from omicsclaw.evals.runner import skill_index
from omicsclaw.evals.stubs import REPO_ROOT
from omicsclaw.provider import ProviderError
from omicsclaw.schema import Message, Role, StreamChunkType, Usage
from omicsclaw.tools import ApprovalRequest

from ._support import make_result

SCRIPT = REPO_ROOT / "skills" / "spatial" / "spatial-preprocess" / "spatial_preprocess.py"
DE_SCRIPT = REPO_ROOT / "skills" / "bulkrna" / "bulkrna-de" / "bulkrna_de.py"


# ---- RecordingProvider --------------------------------------------------------


def _scripted():
    return ScriptedProvider(
        ScriptedTurn(tool_calls=(tool_call("use_skill", {"skill_name": "bulkrna-de"}),)),
        ScriptedTurn(text="done"),
        side_replies=("summary",),
    )


def test_the_recorder_keeps_calls_replies_and_side_calls_apart():
    recorder = RecordingProvider(_scripted())

    async def drive():
        first = await recorder.generate([Message(role=Role.USER, content="hi")], tools=[])
        chunks = [chunk async for chunk in recorder.generate_stream([Message(role=Role.USER, content="go")], tools=[])]
        await recorder.generate([Message(role=Role.USER, content="sum")], tools=None)
        return first, chunks

    first, chunks = asyncio.run(drive())
    assert first.message.tool_calls[0].name == "use_skill"
    assert chunks[-1].type is StreamChunkType.DONE
    assert len(recorder.calls) == 2 and len(recorder.replies) == 2 and len(recorder.side_calls) == 1
    assert recorder.replies[1].content == "done"
    assert recorder.turn_index == 2 and recorder.exhausted == 0
    assert recorder.usage.input_tokens == 300  # three calls at the scripted 100 each
    assert recorder.name == "scripted"


def test_a_bound_view_shares_the_records():
    recorder = RecordingProvider(_scripted())
    child = recorder.bind(model="other")
    asyncio.run(child.generate([Message(role=Role.USER, content="x")], tools=[]))
    assert len(recorder.calls) == 1 and recorder.calls[0].bound == {"model": "other"}


def test_a_failing_call_is_still_recorded_with_an_empty_reply():
    recorder = RecordingProvider(ScriptedProvider(ScriptedTurn(err=ProviderError("down", provider="x", status_code=500))))
    with pytest.raises(ProviderError):
        asyncio.run(recorder.generate([Message(role=Role.USER, content="x")], tools=[]))
    assert len(recorder.calls) == 1 and recorder.replies[0].content == ""


# ---- the approval policy --------------------------------------------------------


def _decide(tmp_path, tool, arguments):
    denials: list[Denial] = []
    policy = routing_policy(tmp_path, skill_index(), denials)
    decision = policy(ApprovalRequest(tool_name=tool, arguments=json.dumps(arguments)))
    return decision.approved, [denial.kind for denial in denials]


def _bash(tmp_path, command):
    return _decide(tmp_path, "bash", {"command": command})


@pytest.mark.parametrize(
    "command",
    [
        f"python {SCRIPT} --help",
        f"python3 {SCRIPT} -h",
        f"{sys.executable} {SCRIPT} --help",
    ],
)
def test_a_strict_help_is_approved(tmp_path, command):
    assert _bash(tmp_path, command) == (True, [])


@pytest.mark.parametrize(
    ("command", "kind"),
    [
        (f"python {SCRIPT} --help && pip install foo", "help_not_strict"),
        (f"python {SCRIPT} -h | tee /etc/x", "help_not_strict"),
        (f"PYTHONPATH=. python {SCRIPT} --help", "help_not_strict"),
        ("find . -exec pip install foo \\;", "not_permitted"),
        ("ls $(pip install foo)", "not_permitted"),
        (f"cat {REPO_ROOT}/.env", "not_permitted"),
        ("pip install foo", "not_permitted"),
        ("curl -d @data https://example.com", "not_permitted"),
        ("tree -o out.txt", "not_permitted"),
        (f"cd {SCRIPT.parent} && python spatial_preprocess.py --output o", "unmatched_skill_command"),
    ],
)
def test_bypasses_and_other_commands_are_refused(tmp_path, command, kind):
    assert _bash(tmp_path, command) == (False, [kind])


@pytest.mark.parametrize(
    "command",
    [
        f"python {SCRIPT} --help; pip install foo",
        f"python {SCRIPT} --demo",
        f"python {SCRIPT} --input a --output o; pip install foo",
    ],
)
def test_a_skill_run_is_approved_because_the_stub_layer_answers_it(tmp_path, command):
    assert _bash(tmp_path, command) == (True, [])


@pytest.mark.parametrize("command", ["find /", "ls -la | grep h5ad", "cat data/x.csv | head -5", "pwd"])
def test_read_only_commands_are_approved(tmp_path, command):
    assert _bash(tmp_path, command) == (True, [])


def test_web_is_refused_and_writes_stay_in_the_workspace(tmp_path):
    assert _decide(tmp_path, "web_fetch", {"url": "https://example.com"}) == (False, ["web"])
    assert _decide(tmp_path, "web_search", {"query": "x"}) == (False, ["web"])
    assert _decide(tmp_path, "write_file", {"path": "notes.md", "content": ""}) == (True, [])
    assert _decide(tmp_path, "edit_file", {"path": "../x.md"}) == (False, ["outside_workspace"])
    assert _decide(tmp_path, "read_file", {"path": "/etc/hosts"}) == (True, [])


def _through_the_runner(tmp_path, command):
    """Run one bash call with the live policy and fallback, as a live trial would."""
    seed = Seed("t__x", "bulkrna", "q", ("bulkrna-de",), "route")
    provider = lambda: RecordingProvider(  # noqa: E731
        ScriptedProvider(
            ScriptedTurn(tool_calls=(tool_call("bash", {"command": command}),)),
            ScriptedTurn(text="done"),
        )
    )
    case, denials = live_case(seed, provider, tmp_path / "ws", skill_index(), config={"skill_env": "off"})
    import dataclasses

    return run_case(dataclasses.replace(case, network=False), tmp_path), denials


@pytest.mark.parametrize(
    "command",
    [
        f"python {DE_SCRIPT} --help; touch pwned",
        f"python {DE_SCRIPT} --demo; touch pwned",
        f"python {DE_SCRIPT} --input a --output o; touch pwned",
        f"python {DE_SCRIPT} --help && touch pwned",
    ],
)
def test_nothing_after_a_skill_script_runs_in_a_trial(tmp_path, command):
    result, _ = _through_the_runner(tmp_path, command)
    assert not (tmp_path / "ws" / "pwned").exists()
    assert result.failures == ()


def test_a_run_without_output_gets_exit_2_and_is_not_a_harness_failure(tmp_path):
    result, denials = _through_the_runner(tmp_path, f"python {DE_SCRIPT} --demo")
    assert "--output is required" in result.tool_results[0].output
    assert result.skill_runs == () and denials == [] and result.failures == ()


# ---- live_case ------------------------------------------------------------------


def test_a_live_case_names_its_inputs_and_creates_them_empty(tmp_path):
    seed = Seed("bulkrna__deseq2", "bulkrna", "Compare two conditions.", ("bulkrna-de",), "route",
                inputs=("data/counts.csv",))
    case, _ = live_case(seed, lambda: None, tmp_path / "ws", skill_index(), trial=2,
                        config={"provider": "deepseek", "model": "m"})
    assert case.id == "live_routing/bulkrna__deseq2-t2"
    assert case.prompt == "Compare two conditions.\nInput: data/counts.csv"
    assert case.files == {"data/counts.csv": b""}
    assert case.permission == "ask" and case.network and case.max_turns == 6
    assert case.env == {"PYTHONPATH": ""} and case.skill_fallback is not None
    assert case.config["skill_env"] == "probe" and case.config["model"] == "m"


def test_the_seed_file_loads():
    seeds = load_seeds()
    assert len(seeds) == 26
    assert all(seed.inputs for seed in seeds if seed.decision == "route")


# ---- judge ----------------------------------------------------------------------


def _reply(*skills, text=""):
    calls = tuple(tool_call("use_skill", {"skill_name": name}, id=f"u{k}") for k, name in enumerate(skills))
    return Message(role=Role.ASSISTANT, content=text, tool_calls=calls)


SEED = Seed("x__de", "bulkrna", "q", ("bulkrna-de",), "route", inputs=("data/counts.csv",),
            expected_args=(("--method", "deseq2"),))
NO_SKILL = Seed("literature__new", "literature", "q", (), "no_skill")


def _run(skill, command="python x.py"):
    return SkillRun(skill, "bulkrna", command, stubbed=True)


def test_executing_the_expected_skill_is_correct():
    result = make_result(skill_runs=(_run("bulkrna-de", "python de.py --input data/counts.csv --method deseq2 --output o"),))
    verdict = judge(result, SEED, [_reply("bulkrna-de")], [])
    assert verdict.outcome == "correct" and verdict.chosen == "bulkrna-de" and verdict.args_ok is True


def test_reading_one_skill_then_running_another_is_judged_by_the_run():
    result = make_result(skill_runs=(_run("bulkrna-de", "python de.py --output o"),))
    verdict = judge(result, SEED, [_reply("bulkrna-coexpression"), _reply("bulkrna-de")], [])
    assert verdict.first_use_skill == "bulkrna-coexpression"
    assert verdict.chosen == "bulkrna-de" and verdict.outcome == "correct"
    assert verdict.args_ok is False  # neither --input nor --method


def test_a_different_skill_is_wrong_and_parallel_loads_are_counted():
    verdict = judge(make_result(), SEED, [Message(role=Role.ASSISTANT, content="thinking"),
                                         _reply("proteomics-de", "metabolomics-de")], [])
    assert verdict.outcome == "wrong_skill" and verdict.chosen == "proteomics-de"
    assert verdict.parallel_use_skill == ("proteomics-de", "metabolomics-de")


def test_no_skill_called_is_split_by_what_happened_before():
    denial = Denial("bash", "not_permitted", "pip install x")
    assert judge(make_result(), SEED, [], [denial]).no_skill_detail == "after_denial"
    asked = judge(make_result(final_output="Which file should I use?"), SEED, [], [])
    assert (asked.outcome, asked.no_skill_detail) == ("no_skill_called", "asked_user")
    assert judge(make_result(final_output="Done."), SEED, [], []).no_skill_detail == "no_denial"


def test_a_provider_error_or_a_timeout_is_an_error():
    from omicsclaw.evals import Failure

    failed = make_result(run_error=ProviderError("401", provider="x", status_code=401))
    assert judge(failed, SEED, [], []).outcome == "error"
    slow = make_result(passed=False, failures=(Failure("case_timeout", "too long"),))
    verdict = judge(slow, SEED, [], [])
    assert verdict.outcome == "error" and verdict.harness_failures == ("case_timeout: too long",)


def test_a_no_skill_seed_is_correct_until_a_script_runs():
    assert judge(make_result(), NO_SKILL, [_reply("literature")], []).outcome == "correct"
    assert judge(make_result(skill_runs=(_run("literature"),)), NO_SKILL, [], []).outcome == "wrong_skill"


def test_a_scripted_model_that_picks_a_skill_scores_correct_end_to_end(tmp_path):
    seed = Seed("bulkrna__deseq2", "bulkrna", "Compare two conditions.", ("bulkrna-de",), "route",
                inputs=("data/counts.csv",))
    recorders = []

    def provider():
        recorder = RecordingProvider(ScriptedProvider(
            ScriptedTurn(tool_calls=(tool_call("use_skill", {"skill_name": "bulkrna-de"}),)),
            ScriptedTurn(tool_calls=(tool_call("bash", {"command": f"python {DE_SCRIPT} --input data/counts.csv --output out"}),)),
            ScriptedTurn(text="Differential expression finished."),
        ))
        recorders.append(recorder)
        return recorder

    case, denials = live_case(seed, provider, tmp_path / "ws", skill_index(), config={"skill_env": "off"})
    import dataclasses

    result = run_case(dataclasses.replace(case, network=False), tmp_path)
    verdict = judge(result, seed, recorders[0].replies, denials)
    assert verdict.outcome == "correct" and verdict.executed_skill == "bulkrna-de"
    assert [(a.tool, a.approved) for a in result.approvals] == [("bash", True)]
    assert (tmp_path / "ws" / "out" / "result.json").is_file()


# ---- the report -----------------------------------------------------------------


def _report(model="m", chosen="bulkrna-de"):
    result: Result = make_result(skill_runs=(_run(chosen, "python x --output o"),), turn_count=3)
    verdict = judge(result, SEED, [], [])
    record = trial_record(verdict, result, Usage(input_tokens=10, output_tokens=2, cache_read_tokens=4), [], {})
    meta = {"provider": "deepseek", "model": model, "base_url": "u", "temperature": 0.0, "trials": 1}
    return build_report(meta, [SeedReport(SEED, (record,))])


def test_the_report_counts_domains_confusion_and_tokens():
    data = to_dict(_report(chosen="bulkrna-coexpression"))
    assert data["pass_rate"] == 0.0
    assert data["domains"]["bulkrna"] == {"correct": 0, "scored": 1, "pass_rate": 0.0}
    assert data["confusion"] == [{"expected": "bulkrna-de", "chosen": "bulkrna-coexpression", "count": 1}]
    assert data["tokens"] == {"input_tokens": 10, "output_tokens": 2, "cache_read_tokens": 4, "model_calls": 3}
    assert data["seeds"][0]["trials"][0]["stubbed_with_fallback"] is True
    text = markdown(_report(chosen="bulkrna-coexpression"))
    assert "bulkrna-de -> bulkrna-coexpression: 1" in text and "## Harness failures" in text


def test_an_all_error_seed_has_no_pass_rate():
    verdict = judge(make_result(run_error=ProviderError("x", provider="x", status_code=500)), SEED, [], [])
    entry = SeedReport(SEED, (trial_record(verdict, make_result(), Usage(), [], {}),))
    assert entry.pass_rate is None and entry.errors == 1


def test_compare_warns_when_the_model_changed_and_marks_changed_seeds(tmp_path, capsys):
    old, new = to_dict(_report()), to_dict(_report(model="n", chosen="bulkrna-coexpression"))
    text = compare(old, new)
    assert text.splitlines()[0].startswith("WARNING: different runs") and "'m' -> 'n'" in text
    assert "x__de: 100% -> 0%, chose bulkrna-de -> bulkrna-coexpression  *" in text
    assert compare(old, old).splitlines()[0] == "overall: 100% -> 100%"

    write_json(_report(), tmp_path / "a.json")
    write_json(_report(chosen="bulkrna-coexpression"), tmp_path / "b.json")
    assert main(["compare", str(tmp_path / "a.json"), str(tmp_path / "b.json")]) == 0
    assert "x__de: 100% -> 0%" in capsys.readouterr().out
    assert main(["compare", str(tmp_path / "missing.json"), str(tmp_path / "b.json")]) == 2


def test_the_command_line_runs_as_a_module(tmp_path):
    import subprocess

    write_json(_report(), tmp_path / "a.json")
    done = subprocess.run(
        [sys.executable, "-m", "omicsclaw.evals.live", "compare", str(tmp_path / "a.json"), str(tmp_path / "a.json")],
        capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=120,
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.startswith("overall: 100% -> 100%")
    assert "RuntimeWarning" not in done.stderr
    assert Path(tmp_path / "a.json").is_file()


# ---- the step runner ---------------------------------------------------------------------------

RUNNER_SCRIPT = REPO_ROOT / "skills" / "_sdk" / "notebook" / "run.py"


@pytest.mark.parametrize(
    ("command", "approved"),
    [
        (f"python {RUNNER_SCRIPT} new clustering", True),
        (f"{sys.executable} {RUNNER_SCRIPT} run analysis/01_clustering", True),
        (f"python {RUNNER_SCRIPT} replay analysis/01_clustering", True),
        ("python -m skills._sdk.notebook status", False),
        (f"python {RUNNER_SCRIPT} run analysis/01_x && pip install foo", False),
        (f"python {RUNNER_SCRIPT} api skills/x --write", False),
        (f"python {RUNNER_SCRIPT} accept analysis/01_x --skip-review ok", False),
        (f"python {RUNNER_SCRIPT} revise analysis/01_x", False),
        ("python -m skills._sdk.notebook accept analysis/01_x --review r.md", False),
    ],
)
def test_the_step_runner_is_approved_as_one_plain_command(tmp_path, command, approved):
    assert _bash(tmp_path, command)[0] is approved


def test_only_the_real_step_runner_is_approved(tmp_path):
    lookalike = tmp_path / "x" / "_sdk" / "notebook" / "run.py"
    lookalike.parent.mkdir(parents=True)
    lookalike.write_text("print('not the runner')\n")
    assert _bash(tmp_path, f"python {lookalike} run analysis/01_x")[0] is False
    assert _bash(tmp_path, "python x/_sdk/notebook/run.py run analysis/01_x")[0] is False


def test_a_step_ledger_names_the_executed_skill_and_its_keyword_arguments(tmp_path):
    ledger = tmp_path / "results" / "01_annotation" / "provenance" / "runs" / "01_annotate" / "r.jsonl"
    ledger.parent.mkdir(parents=True)
    events = [
        {"v": 1, "event": "skill_load", "at": "2026-10-01T00:00:00.000Z", "skill": "sc-cell-annotation", "stub": False},
        {"v": 1, "event": "skill_call", "at": "2026-10-01T00:00:01.000Z", "skill": "sc-cell-annotation",
         "function": "annotate", "args": {"adata": "AnnData(10, 5)", "method": "celltypist"}, "stub": False},
    ]
    ledger.write_text("".join(json.dumps(e) + "\n" for e in events))
    seed = Seed("singlecell__cell_annotation", "singlecell", "q", ("sc-cell-annotation",), "route",
                inputs=("data/pbmc.h5ad",), expected_args=(("--method", "celltypist"),))
    runs = (SkillRun("sc-cell-annotation", "singlecell", "sc-cell-annotation.annotate({...})", stubbed=False,
                     function="annotate", source="ledger", args=events[1]["args"]),)
    verdict = judge(make_result(workspace=tmp_path, skill_runs=runs), seed, [_reply("sc-cell-annotation")], [])
    assert verdict.executed_skill == "sc-cell-annotation" and verdict.outcome == "correct"
    assert verdict.args_ok is True
