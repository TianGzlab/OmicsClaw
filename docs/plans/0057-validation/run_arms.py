"""Run the arms of the 0057 validation on prepared units.

Layout under ``--root``::

    units.json                       uid -> input, tissue, data_type (no truth)
    units/<uid>/input.h5ad           preprocessed input, obs = batch only
    <uid>/probe/ws/                  the shared probe (A0 and the probe of every arm)
    <uid>/<arm>/r<k>/ws/             one workspace per unit x arm x repetition
    <uid>/<arm>/r<k>/result.json     what the arm produced (no truth)

Subcommands::

    probe   <uid>                    run the probe once (stability, reference, markers)
    a0k     <uid>                    cellcharter with --auto-k, once
    det     <uid> <arm> <rep>        A1 / A2 (model) or A6 (random, seed = rep)
    free    <uid> <rep>              A3: the agent with run_skill, inspect_trials, select_result
    a0check <uid>                    run each method directly with its defaults; compare with the probe's A0
    batch   <uid,uid> <arm,arm>      every repetition of the deterministic arms, concurrently, one pool

The deterministic arms call :class:`TuningPipeline` directly; A3 drives the
agent through ``open_app`` and the streaming ``TurnRunner``.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    ARMS,
    DOMAINS,
    REPO,
    RUNNABLE,
    SKILL_PYTHON,
    Unit,
    copy_probe,
    load_env_file,
    make_pool,
    make_runner,
    read_json,
    real_model,
    sha256,
    skill_text,
    write_json,
)

SKILL = "spatial-domains"
REMINDER = "Please finish now by calling select_result."
REMINDER_TURNS = 2
A3_CPUS = 32
"""CPUs the A3 deployment's own trial pool may hand out, so it can run beside the other arms."""
A3_MAX_TURNS = 50
A3_TOKEN_CAP = int(os.environ.get("OMICSCLAW_0057_A3_TOKEN_CAP", "3000000"))


def units(root: Path) -> dict[str, Unit]:
    table = read_json(root / "units.json")
    return {uid: Unit(uid=uid, input=Path(v["input"]), tissue=v["tissue"], data_type=v["data_type"])
            for uid, v in table.items()}


def _settings(**overrides):
    from omicsclaw.ensemble.tuning.pipeline import TuningSettings

    return TuningSettings(**overrides)


def _pipeline(runner, model=None, llm=None):
    from omicsclaw.ensemble.tuning.pipeline import TuningPipeline

    return TuningPipeline(runner, model=model, llm_settings=llm, skill_text=skill_text(),
                          settings=_settings(), obs_allowlist=("batch",),
                          code_paths=(REPO / "omicsclaw" / "ensemble",))


def _workspace_input(unit: Unit, ws: Path) -> Path:
    target = ws / "data" / "input.h5ad"
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(unit.input, target)
    return target


# ---- the probe -------------------------------------------------------------------------------


async def probe(root: Path, unit: Unit, pool) -> dict[str, Any]:
    if (root / unit.uid / "probe" / "result.json").exists():
        return read_json(root / unit.uid / "probe" / "result.json")
    ws = root / unit.uid / "probe" / "ws"
    runner = make_runner(ws, pool)
    source = _workspace_input(unit, ws)
    pipeline = _pipeline(runner)
    began = time.monotonic()
    bundle = await pipeline.prepare_evidence(runner.catalog.get(SKILL), RUNNABLE, source, probe_base=unit.uid,
                                             context=unit.context, platform=unit.data_type)
    summary = {
        "uid": unit.uid, "wall_s": round(time.monotonic() - began, 1), "reused": bundle.reused,
        "trials": len(bundle.trials), "failed": sum(t.status != "ok" for t in bundle.trials),
        "stable_peaks": bundle.evidence.stable_peaks, "fallback_k": bundle.evidence.fallback_k,
        "gpu_s": sum(t.wall_s for t in bundle.trials if t.lease_gpu is not None),
        "cpu_s": sum(t.wall_s * t.cpus for t in bundle.trials),
        "a0": a0_from_probe(bundle, runner.catalog.get(SKILL)),
    }
    write_json(root / unit.uid / "probe" / "result.json", summary)
    return summary


def a0_from_probe(bundle, spec) -> dict[str, Any]:
    """Each method's default-parameter trial: exact methods at their default K, calibrated at resolution 1.0."""
    out = {}
    for method in RUNNABLE:
        control = spec.method(method).k_control
        if control.kind == "exact":
            default_k = spec.method(method).params[control.param].default
            trial = next((t for t in bundle.trials if t.method == method and t.kind == "exact"
                          and t.requested_k == default_k), None)
        else:
            default = spec.method(method).params[control.param].default
            trial = next((t for t in bundle.trials if t.method == method and t.kind == "full"
                          and t.resolution == default), None)
        out[method] = None if trial is None else {
            "status": trial.status, "run_id": trial.run_id, "trial": trial.trial, "labels": trial.labels,
            "n_labels": trial.n_labels, "params": trial.params,
        }
    return out


async def a0k(root: Path, unit: Unit, pool) -> dict[str, Any]:
    if (root / unit.uid / "a0k" / "result.json").exists():
        return read_json(root / unit.uid / "a0k" / "result.json")
    ws = root / unit.uid / "probe" / "ws"
    runner = make_runner(ws, pool)
    source = _workspace_input(unit, ws)
    spec = runner.prepare(skill=SKILL, method="cellcharter", input=source,
                          params={**unit.context, "auto_k": True}, run_id=f"{unit.uid}-a0k")
    result = await runner.run(spec)
    summary = {"status": result.status, "trial": result.trial, "run_id": result.run_id,
               "labels": str(Path(result.output_dir) / "labels.csv.gz"),
               "n_labels": (result.metrics or {}).get("n_labels"), "wall_s": result.wall_s,
               "gpu": result.lease_gpu is not None}
    write_json(root / unit.uid / "a0k" / "result.json", summary)
    return summary


# ---- deterministic arms -------------------------------------------------------------------------


async def det(root: Path, unit: Unit, arm: str, rep: int, pool, model=None, llm=None):
    from omicsclaw.ensemble.tuning.pipeline import TuningRequest

    kind, tissue_given, _ = ARMS[arm]
    base = root / unit.uid / arm / f"r{rep}"
    ws = base / "ws"
    if (base / "result.json").exists():
        return read_json(base / "result.json")
    if ws.exists():
        shutil.rmtree(ws)
    runner = make_runner(ws, pool)
    copy_probe(root / unit.uid / "probe" / "ws" / "ensemble_runs", runner.store.root, unit.uid)
    source = _workspace_input(unit, ws)
    pipeline = _pipeline(runner, model if kind == "det" else None, llm)
    request = TuningRequest(
        skill=SKILL, input=source, run_id=f"{unit.uid}-{arm.lower()}-r{rep}", methods=RUNNABLE,
        tissue=unit.tissue if tissue_given else None, arm=kind,
        random_index=rep if kind == "random" else None, context=unit.context, probe_base=unit.uid,
        tissue_withheld=arm == "A2",
    )
    began = time.monotonic()
    selection = await pipeline.run(request)
    tuning = runner.store.run_dir(request.run_id) / "tuning"
    usage = _llm_usage(tuning)
    if usage["provider_errors"]:
        write_json(base / "result.provider_error.json", {"errors": usage["provider_errors"], "selection": str(tuning)})
        raise ProviderOutage(f"{usage['provider_errors']} model calls failed with a provider error; "
                             "the run is not kept and is redone on the next resume")
    summary = {
        "uid": unit.uid, "arm": arm, "rep": rep, "status": selection.status,
        "selection": str(tuning / "selection.json"), "k": selection.k, "final": selection.final,
        "methods": selection.methods, "budget": selection.budget, "wall_s": round(time.monotonic() - began, 1),
        "llm": usage,
    }
    write_json(base / "result.json", summary)
    return summary


class ProviderOutage(RuntimeError):
    """A deterministic arm whose model calls failed; its fallback result would not be the arm's."""


def provider_errors(tuning: Path) -> int:
    """Model calls of a tuning run that ended in a provider error."""
    return _llm_usage(tuning)["provider_errors"]


def _llm_usage(tuning: Path) -> dict[str, int]:
    totals = {"calls": 0, "input": 0, "output": 0, "cache_read": 0, "provider_errors": 0}
    ledger = tuning / "ledger.jsonl"
    if not ledger.is_file():
        return totals
    for line in ledger.read_text().splitlines():
        event = json.loads(line)
        if event.get("kind") != "llm_call":
            continue
        totals["calls"] += 1
        totals["provider_errors"] += bool(event.get("provider_error"))
        for key in ("input", "output", "cache_read"):
            totals[key] += int((event.get("usage") or {}).get(key) or 0)
    return totals


# ---- A3: free orchestration --------------------------------------------------------------------


RULES = {"permissions": {"deny": ["bash", "web_fetch", "web_search"]}}


async def free(root: Path, unit: Unit, rep: int, *, token_cap: int = A3_TOKEN_CAP, model: str = "") -> dict[str, Any]:
    """One A3 run in a fresh workspace; refuses to count a turn whose usage was not reported."""
    from omicsclaw.ensemble.tuning.budget import caps
    from omicsclaw.ensemble.tuning.evidence import load_evidence
    from omicsclaw.ensemble.tuning.probe import probe_run_id
    from omicsclaw.ensemble.tuning.prompts import DataSummary, FreeTaskInput, KDecisionInput, render_free_task
    from omicsclaw.entry import open_app

    base = root / unit.uid / "A3" / f"r{rep}"
    if (base / "result.json").exists():
        return read_json(base / "result.json")
    ws = base / "ws"
    if ws.exists():
        shutil.rmtree(ws)
    (ws / ".omicsclaw").mkdir(parents=True)
    (ws / ".omicsclaw" / "settings.json").write_text(json.dumps(RULES))
    assert not (ws / ".omicsclaw" / "memory.db").exists()
    source = _workspace_input(unit, ws)
    probe_runs = root / unit.uid / "probe" / "ws" / "ensemble_runs"
    copy_probe(probe_runs, ws / "ensemble_runs", unit.uid)
    evidence_dir = ws / "ensemble_runs" / probe_run_id(unit.uid) / "evidence"
    run_id = f"{unit.uid}-a3-r{rep}"
    (ws / "ensemble_runs" / run_id / "tuning").mkdir(parents=True)
    shutil.copyfile(evidence_dir / "reference.json", ws / "ensemble_runs" / run_id / "tuning" / "reference.json")

    from omicsclaw.ensemble.space import TuningCatalog
    from omicsclaw.skills import load_skills

    spec = TuningCatalog.from_skills(load_skills(REPO / "skills")).get(SKILL)
    budget = caps({m: spec.method(m).k_control.kind for m in RUNNABLE})
    markers = read_json(evidence_dir / "markers.json")
    evidence = load_evidence(read_json(evidence_dir / "stability.json"))
    done = read_json(evidence_dir / "probe_done.json")
    maps: dict[str, dict[float, int]] = {}
    for t in done["trials"]:
        if t["kind"] == "full" and t["status"] == "ok":
            maps.setdefault(t["method"], {})[float(t["resolution"])] = int(t["n_labels"])
    decision = KDecisionInput(grid=tuple(evidence.grid), skill=skill_text()(SKILL),
                              data=DataSummary.from_description(markers.get("data") or {}, platform=unit.data_type),
                              tissue=unit.tissue, evidence=evidence, markers=markers)
    task = render_free_task(FreeTaskInput(
        skill_name=SKILL, input_path="data/input.h5ad", run_id=run_id, probe_run_id=probe_run_id(unit.uid),
        decision=decision,
        methods={m: spec.method(m).summary() for m in RUNNABLE},
        budgets=budget, resolution_map=maps,
    ))
    (base / "task.md").write_text(task)
    config = a3_config(base, ws, budget, model=model)
    began = time.monotonic()
    selection_path = ws / "ensemble_runs" / run_id / "tuning" / "selection.json"
    app = await open_app(config)
    system_prompt = app.prompt.render().system_prompt
    (base / "system_prompt.txt").write_text(system_prompt, encoding="utf-8")
    try:
        driven = await drive_a3(app, f"a3-{unit.uid}-r{rep}", task, token_cap=token_cap,
                                finished=selection_path.exists)
    finally:
        await app.aclose()
    usage, reminded, transcript = driven["usage"], driven["reminded"], driven["tool_calls"]
    status = "ok" if selection_path.exists() else "failed"
    summary = {
        "uid": unit.uid, "arm": "A3", "rep": rep, "status": status, "reminded": reminded,
        "system_prompt_sha256": hashlib.sha256(system_prompt.encode("utf-8")).hexdigest(),
        "system_prompt_sha256_normalised": hashlib.sha256(
            system_prompt.replace(str(ws), "<workspace>").replace(time.strftime("%Y-%m-%d"), "<today>").encode("utf-8")
        ).hexdigest(),
        "capped": driven["capped"],
        "usage": usage, "tokens": usage["input"] + usage["output"],
        "billed_input_uncached": usage["input"] - usage["cache_read"],
        "token_cap": token_cap, "wall_s": round(time.monotonic() - began, 1),
        "selection": str(ws / "ensemble_runs" / run_id / "tuning" / "selection.json") if status == "ok" else None,
        "tool_calls": transcript,
    }
    write_json(base / "result.json", summary)
    return summary


def a3_config(base: Path, ws: Path, budget: dict[str, int], *, model: str = "", skills_dir: Path | None = None):
    """The A3 deployment: free tools, per-method budget, MCP off, rules deny bash and the web.

    The system prompt's front matter is pinned to one empty file written in
    *base* (outside the workspace), so the prompt does not depend on whatever
    persona or contract files a deployment would otherwise read.
    """
    from omicsclaw.entry.config import AppConfig
    from omicsclaw.permission import PermissionMode

    empty = base / "empty_front_matter.txt"
    base.mkdir(parents=True, exist_ok=True)
    empty.write_text("", encoding="utf-8")
    return AppConfig(
        workspace=ws, skills_dir=skills_dir or REPO / "skills", ensemble=True, ensemble_tools="free",
        ensemble_run_budget=",".join(f"{m}:{n}" for m, n in budget.items()),
        ensemble_python=SKILL_PYTHON, ensemble_obs_allowlist="batch", max_turns=A3_MAX_TURNS,
        ensemble_cpus=A3_CPUS,
        mcp_config=Path("/nonexistent/mcp.json"), permission_mode=PermissionMode.AUTO_APPROVE,
        system_prompt_files=(empty,),
        **({"model": model} if model else {}),
    )


class UsageNotReported(RuntimeError):
    """A turn of the A3 agent (or of a sub-agent it delegated to) came back without usage."""


STOP_TEXT = "(stopped: the token budget of this run is spent)"


class _Stoppable:
    """The deployment's provider, until :attr:`stop` is set: then every call ends the exchange.

    Ending the exchange this way (a final reply with no tool call) lets the
    engine commit the trajectory, so the reminder that follows sees it.
    """

    def __init__(self, inner) -> None:
        self._inner = inner
        self.stop = False

    @property
    def name(self) -> str:
        return self._inner.name

    def _stopped(self):
        from omicsclaw.provider import Completion
        from omicsclaw.schema import Message, Role

        return Completion(message=Message(role=Role.ASSISTANT, content=STOP_TEXT), finish_reason="stop")

    async def generate(self, messages, tools=None):
        if self.stop:
            return self._stopped()
        return await self._inner.generate(messages, tools)

    def generate_stream(self, messages, tools=None):
        if not self.stop:
            return self._inner.generate_stream(messages, tools)

        async def stream():
            from omicsclaw.schema import StreamChunk, StreamChunkType

            from omicsclaw.schema import Usage

            completion = self._stopped()
            yield StreamChunk(type=StreamChunkType.DONE, message=completion.message, finish_reason="stop",
                              usage=Usage())

        return stream()

    def bind(self, **overrides):
        return self._inner.bind(**overrides)


def _turn_runner(app, session_id: str, provider: "_Stoppable"):
    """``async for event in run(message, max_turns=n)``: streamed exchanges of one conversation.

    Each call is one exchange on the engine's streaming path over *provider*,
    with the history of the previous exchanges carried forward. The history is
    taken over however the exchange ends, abandoned ones included.
    """
    import dataclasses

    from omicsclaw.engine import AgentEngine
    from omicsclaw.entry.turn import _assemble, _session_bound

    history: list = []

    async def run(message: str, *, max_turns: int):
        engine = AgentEngine(provider, app.registry,
                             dataclasses.replace(app.config.engine_config(), max_turns=max_turns),
                             prompt=app.prompt)
        exchange = _assemble(app, tuple(history), session_id=session_id)
        try:
            with _session_bound(session_id):
                async for event in engine.exchange_stream(
                    message, conversation=exchange.conversation, prompt=app.prompt,
                    compactor=exchange.compactor, augmentor=exchange.augmentor,
                ):
                    yield event
        finally:
            history[:] = list(exchange.conversation.carried)

    run.history = history
    return run


async def drive_a3(app, session_id: str, task: str, *, token_cap: int, finished,
                   max_turns: int = A3_MAX_TURNS, reminder_turns: int = REMINDER_TURNS) -> dict[str, Any]:
    """Run the A3 task, and the reminder when the task ended without a selection.

    Tokens are the input plus output of every main-engine ``turn_end`` and every
    sub-agent turn, cache hits in full. Past *token_cap* the exchange is ended at
    the next model call (a stop reply that costs no tokens) and the reminder follows.

    :raises UsageNotReported: A turn arrived without usage; the unit is refused.
    """
    from omicsclaw.engine.types import EngineEventType
    from omicsclaw.tools.context import use_usage_sink

    usage = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0, "turns": 0, "child_turns": 0}
    provider = _Stoppable(app.provider)
    runner = _turn_runner(app, session_id, provider)
    transcript: list[dict[str, Any]] = []

    def add(u, child=False):
        if u is None:
            raise UsageNotReported("a turn came back without usage; the unit is refused")
        usage["input"] += u.input_tokens
        usage["output"] += u.output_tokens
        usage["cache_read"] += u.cache_read_tokens
        usage["cache_write"] += u.cache_write_tokens
        usage["child_turns" if child else "turns"] += 1
        if usage["input"] + usage["output"] > token_cap:
            provider.stop = True

    reminded = False
    capped = False
    for message, turns in ((task, max_turns), (REMINDER, reminder_turns)):
        if message == REMINDER:
            if finished():
                break
            reminded = True
            capped = provider.stop
            provider.stop = False
        with use_usage_sink(lambda u: add(u, child=True)):
            async with contextlib.aclosing(runner(message, max_turns=turns)) as events:
                async for event in events:
                    if event.type is EngineEventType.TURN_END:
                        add(event.usage)
                    elif event.type is EngineEventType.TOOL_START and event.tool_call:
                        transcript.append({"tool": event.tool_call.name,
                                           "arguments": event.tool_call.arguments[:2000]})
    capped = capped or provider.stop
    return {"usage": usage, "reminded": reminded, "capped": capped, "tool_calls": transcript,
            "history": list(runner.history)}


# ---- T10 step 1: A0 equivalence ---------------------------------------------------------------------


def a0check(root: Path, unit: Unit) -> dict[str, Any]:
    """Run each method directly (no n_domains, resolution or spatial_weight given) in the frozen
    seed environment of the trials, and compare its labels with the probe's A0 trial.

    The direct run gets the same seeding variables and thread counts as a trial of that
    method, and a GPU (a different one from the probe's lease where it had one).
    """
    from omicsclaw.ensemble.space import TuningCatalog
    from omicsclaw.skills import load_skills

    probe_result = read_json(root / unit.uid / "probe" / "result.json")
    out_root = root / unit.uid / "a0check"
    spec = TuningCatalog.from_skills(load_skills(REPO / "skills")).get(SKILL)
    seeded = make_runner(root / "unused", pool=None).seed_environment()
    results = {}
    for method in RUNNABLE:
        a0 = probe_result["a0"].get(method)
        out = out_root / method
        if out.exists():
            shutil.rmtree(out)
        command = [SKILL_PYTHON, str(DOMAINS), "--input", str(unit.input), "--output", str(out), "--method", method]
        if unit.data_type:
            command += ["--data-type", unit.data_type]
        threads = str(spec.method(method).resources.cpus)
        gpu = "3" if spec.method(method).resources.gpu != "none" else ""
        env = {**os.environ, "PYTHONPATH": str(REPO), **seeded, "CUDA_VISIBLE_DEVICES": gpu,
               "OMP_NUM_THREADS": threads, "MKL_NUM_THREADS": threads, "OPENBLAS_NUM_THREADS": threads,
               "NUMBA_NUM_THREADS": threads}
        done = subprocess.run(command, capture_output=True, text=True, env=env)
        entry: dict[str, Any] = {"exit": done.returncode}
        table = out / "tables" / "domain_assignments.csv"
        if done.returncode == 0 and table.is_file() and a0 and a0.get("status") == "ok":
            import pandas as pd
            from sklearn.metrics import adjusted_rand_score

            direct = pd.read_csv(table, dtype=str).set_index("observation")["spatial_domain"]
            probe = pd.read_csv(a0["labels"], dtype=str).set_index("obs_id")["label"]
            common = probe.index.intersection(direct.index)
            ari = float(adjusted_rand_score(probe.loc[common], direct.loc[common]))
            entry.update(n=len(common), n_probe=len(probe), n_direct=len(direct), ari=ari,
                         identical=ari == 1.0 and len(common) == len(probe) == len(direct),
                         probe_trial=f"{a0['run_id']}/{method}/{a0['trial']}", probe_params=a0["params"])
        else:
            entry["error"] = done.stderr[-1500:]
        results[method] = entry
    write_json(out_root / "result.json", results)
    return results


async def batch(root: Path, uids, arms, pool, *, model_name: str = "") -> list:
    """Every repetition of the deterministic *arms* on *uids*, concurrently, over one pool."""
    table = units(root)
    model = llm = None
    if any(ARMS[a][0] == "det" for a in arms):
        model, llm = real_model(model_name)
    jobs = []
    for uid in uids:
        for arm in arms:
            kind, _, reps = ARMS[arm]
            for rep in range(1, reps + 1):
                jobs.append(det(root, table[uid], arm, rep, pool, model if kind == "det" else None, llm))
    return await asyncio.gather(*jobs, return_exceptions=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("command", choices=["probe", "a0k", "det", "free", "a0check", "batch"])
    parser.add_argument("uid")
    parser.add_argument("arm", nargs="?")
    parser.add_argument("rep", nargs="?", type=int)
    parser.add_argument("--model", default="")
    args = parser.parse_args(argv)
    load_env_file()
    if args.command == "batch":
        results = asyncio.run(batch(args.root, args.uid.split(","), args.arm.split(","), make_pool(),
                                    model_name=args.model))
        for item in results:
            print(repr(item)[:300] if isinstance(item, BaseException) else
                  json.dumps({k: item.get(k) for k in ("uid", "arm", "rep", "status", "final", "wall_s")}))
        return 0
    unit = units(args.root)[args.uid]
    if args.command == "a0check":
        print(json.dumps(a0check(args.root, unit), indent=1))
        return 0
    if args.command == "free":
        print(json.dumps(asyncio.run(free(args.root, unit, int(args.arm), model=args.model)), indent=1, default=str))
        return 0
    pool = make_pool()
    if args.command == "probe":
        result = asyncio.run(probe(args.root, unit, pool))
    elif args.command == "a0k":
        result = asyncio.run(a0k(args.root, unit, pool))
    else:
        model = llm = None
        if ARMS[args.arm][0] == "det":
            model, llm = real_model(args.model)
        result = asyncio.run(det(args.root, unit, args.arm, args.rep, pool, model, llm))
    print(json.dumps(result, indent=1, default=str)[:4000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
