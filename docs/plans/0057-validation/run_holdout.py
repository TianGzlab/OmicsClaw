"""Run the 0057 hold-out: ``run_holdout.py run --root <root>``; ``run_holdout.py status --root <root>``.

The units must already be prepared (``prepare_dlpfc.py units``,
``prepare_cosmx.py``, ``define_population.py``; they write ``units.json``).
``run`` records the settings of the run (``frozen_settings.json``, model,
seed, git state and a digest of the code) under ``<root>/runs/<timestamp>/``
and runs every unit of ``--units`` (default: all): the probe, A0k,
then all repetitions of A1, A2 and A6 together with the A3 repetitions one
after the other. Several units run at once over one resource pool. Every
step writes its ``result.json`` when it finishes and is skipped when that file
exists, so an interrupted run continues where it stopped; a step interrupted
half-way is redone. Failures are appended to ``<root>/errors.jsonl`` and do not
stop the other steps. Model calls are retried with back-off on transient
failures (connection, time-out); a step that still fails on one is retried a
few times, and otherwise left without a result so the next resume redoes it. A
deterministic arm whose model calls failed (its K would silently be the
fallback) is not kept, and results of that kind from earlier runs are set
aside at the start of every run, so they are redone too.

Nothing here compares the code or the environment with an earlier state:
the settings are recorded, not checked. ``status`` prints what is done.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import shutil
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import ARMS, REPO, TRIAL_SEED, read_json, write_json  # noqa: E402

HERE = Path(__file__).resolve().parent
CODE_GLOBS = (
    "omicsclaw/ensemble/**/*", "omicsclaw/entry/**/*", "omicsclaw/provider/**/*",
    "skills/spatial/spatial-domains/**/*", "skills/spatial/spatial-preprocess/**/*",
    "skills/spatial/_lib/**/*", "docs/plans/0057-validation/*.py",
)


def code_digest() -> dict[str, Any]:
    """sha256 of every file under :data:`CODE_GLOBS` and of the list, for the record."""
    files = {}
    for pattern in CODE_GLOBS:
        for path in REPO.glob(pattern):
            if path.is_file() and "__pycache__" not in path.parts:
                files[str(path.relative_to(REPO))] = hashlib.sha256(path.read_bytes()).hexdigest()
    total = hashlib.sha256("".join(f"{k}\t{v}\n" for k, v in sorted(files.items())).encode()).hexdigest()
    return {"total": total, "files": dict(sorted(files.items()))}


def git_state() -> dict[str, Any]:
    def run(*args: str) -> str:
        done = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)
        return done.stdout.strip()

    return {"head": run("rev-parse", "HEAD"), "status": run("status", "--short").splitlines()}


def record_run(root: Path, llm: dict[str, Any]) -> Path:
    """Write the settings this run uses into ``<root>/runs/<timestamp>/``; returns that directory."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    directory = root / "runs" / stamp
    directory.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(HERE / "frozen_settings.json", directory / "frozen_settings.json")
    write_json(directory / "run.json", {
        "started_at": stamp, "llm": llm, "trial_seed": TRIAL_SEED, "git": git_state(),
        "code_digest": code_digest(), "argv": sys.argv,
    })
    return directory


def _error(root: Path, uid: str, step: str, exc: BaseException) -> None:
    with open(root / "errors.jsonl", "a", encoding="utf-8") as sink:
        sink.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "uid": uid,
                               "step": step, "error": f"{type(exc).__name__}: {exc}",
                               "trace": traceback.format_exc()[-3000:]}) + "\n")


STEP_RETRIES = 3
STEP_BACKOFF_S = 120.0


async def _step(root: Path, uid: str, step: str, make, *, retries: int = STEP_RETRIES,
                backoff_s: float = STEP_BACKOFF_S) -> Any:
    """Await ``make()``; a transient model failure is retried *retries* times with back-off.

    Every failure is logged; the last one leaves the step without a result, so the
    next resume redoes it.
    """
    from common import is_transient

    for attempt in range(retries + 1):
        try:
            return await make()
        except asyncio.CancelledError:
            raise
        except BaseException as exc:  # noqa: BLE001 - one failed step must not stop the others
            _error(root, uid, step, exc)
            if attempt == retries or not is_transient(exc):
                return None
            await asyncio.sleep(backoff_s * 2 ** attempt)
    return None


def invalidate_provider_failures(root: Path) -> list[str]:
    """Set aside finished deterministic-arm results whose model calls failed, so they are redone.

    Their ``result.json`` is renamed ``result.provider_error.json``; returns the steps.
    """
    import run_arms

    redone = []
    for result in sorted(root.glob("*/A[126]/r*/result.json")):
        tuning = Path(read_json(result)["selection"]).parent
        if run_arms.provider_errors(tuning):
            result.rename(result.with_name("result.provider_error.json"))
            redone.append(str(result.parent.relative_to(root)))
    return redone


async def run_unit(root: Path, unit, pool, model, llm, token_cap: int) -> None:
    import run_arms

    uid = unit.uid
    if await _step(root, uid, "probe", lambda: run_arms.probe(root, unit, pool)) is None:
        return
    jobs = [_step(root, uid, "a0k", lambda: run_arms.a0k(root, unit, pool))]
    for arm, (kind, _, reps) in ARMS.items():
        if arm == "A3":
            continue
        for rep in range(1, reps + 1):
            jobs.append(_step(root, uid, f"{arm}r{rep}",
                              lambda arm=arm, rep=rep, kind=kind: run_arms.det(
                                  root, unit, arm, rep, pool, model if kind == "det" else None, llm)))

    async def free_reps():
        for rep in range(1, ARMS["A3"][2] + 1):
            await _step(root, uid, f"A3r{rep}", lambda rep=rep: run_arms.free(root, unit, rep, token_cap=token_cap,
                                                                             model=llm.model))

    jobs.append(free_reps())
    await asyncio.gather(*jobs)


async def run_all(root: Path, uids: list[str], parallel: int, pool) -> None:
    import run_arms
    from common import load_env_file, real_model

    load_env_file()
    settings = read_json(HERE / "frozen_settings.json")
    model, llm = real_model(settings["llm"]["model"], settings["llm"]["provider"])
    redone = invalidate_provider_failures(root)
    directory = record_run(root, llm.to_json())
    write_json(directory / "redone_provider_failures.json", redone)
    token_cap = int(settings["a3"]["token_cap"])
    units = run_arms.units(root)
    gate = asyncio.Semaphore(parallel)

    async def one(uid: str) -> None:
        async with gate:
            began = time.monotonic()
            await run_unit(root, units[uid], pool, model, llm, token_cap)
            with open(root / "unit_times.jsonl", "a", encoding="utf-8") as sink:
                sink.write(json.dumps({"uid": uid, "wall_h": round((time.monotonic() - began) / 3600, 3)}) + "\n")

    await asyncio.gather(*(one(uid) for uid in uids))


def status(root: Path) -> dict[str, Any]:
    """Which steps of which units have a result, and the failures logged so far."""
    units = read_json(root / "units.json")
    steps = ["probe", "a0k"] + [f"{a}/r{r}" for a, (_, _, reps) in ARMS.items() for r in range(1, reps + 1)]
    table = {}
    for uid in units:
        done = [s for s in steps if (root / uid / s / "result.json").exists()]
        table[uid] = f"{len(done)}/{len(steps)}"
    errors = []
    if (root / "errors.jsonl").exists():
        errors = [json.loads(line) for line in (root / "errors.jsonl").read_text().splitlines() if line.strip()]
    complete = sum(v == f"{len(steps)}/{len(steps)}" for v in table.values())
    return {"units_complete": f"{complete}/{len(table)}", "per_unit": table,
            "errors": [{k: e[k] for k in ("at", "uid", "step", "error")} for e in errors[-10:]],
            "n_errors": len(errors)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["run", "status"])
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--units", default="", help="comma-separated uids; empty = every unit in units.json")
    parser.add_argument("--parallel", type=int, default=3)
    args = parser.parse_args(argv)
    if args.command == "status":
        print(json.dumps(status(args.root), indent=1))
        return 0
    uids = [u for u in args.units.split(",") if u] or list(read_json(args.root / "units.json"))
    from common import make_pool

    asyncio.run(run_all(args.root, uids, args.parallel, make_pool()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
