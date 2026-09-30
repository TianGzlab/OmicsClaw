"""Measured cost of the 0057 runs and its extrapolation to the hold-out (plan §4.8).

Sums, per unit, the probe's and each arm's GPU seconds (trials holding a GPU
lease), reserved-CPU seconds (wall time x reserved CPUs), new runs, model
calls and tokens, and extrapolates to 42 units x (A1 3 + A2 3 + A6 3 + A3 2).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import ARMS, read_json  # noqa: E402

HOLDOUT_UNITS = 42
CPUS = {"leiden": 2, "louvain": 2, "spagcn": 8, "graphst": 8, "cellcharter": 8}


def collect(root: Path, uids) -> dict:
    out = {}
    for uid in uids:
        probe = read_json(root / uid / "probe" / "result.json")
        entry = {"probe": {"gpu_h": probe["gpu_s"] / 3600, "core_h": probe["cpu_s"] / 3600,
                           "trials": probe["trials"], "wall_h": probe["wall_s"] / 3600}, "arms": {}}
        for arm in ARMS:
            reps = []
            for path in sorted((root / uid / arm).glob("r*/result.json")):
                r = read_json(path)
                if arm == "A3":
                    gpu = core = runs = 0.0
                    for trials in path.parent.glob("ws/ensemble_runs/*-a3-*/trials.jsonl"):
                        for line in trials.read_text().splitlines():
                            t = json.loads(line)
                            runs += 1
                            gpu += t["wall_s"] if t.get("lease_gpu") is not None else 0.0
                            core += t["wall_s"] * CPUS.get(t["method"], 8)
                    reps.append({"tokens": r.get("tokens"), "input": r["usage"]["input"], "output": r["usage"]["output"],
                                 "cache_read": r["usage"]["cache_read"], "wall_h": r["wall_s"] / 3600,
                                 "gpu_h": gpu / 3600, "core_h": core / 3600, "new_runs": runs,
                                 "status": r["status"], "reminded": r.get("reminded"), "capped": r.get("capped")})
                else:
                    budget = r.get("budget") or {}
                    reps.append({"gpu_h": budget.get("gpu_s", 0) / 3600, "core_h": budget.get("cpu_s", 0) / 3600,
                                 "new_runs": sum((budget.get("used") or {}).values()),
                                 "llm_calls": r["llm"]["calls"], "input": r["llm"]["input"],
                                 "output": r["llm"]["output"], "cache_read": r["llm"].get("cache_read", 0),
                                 "wall_h": r["wall_s"] / 3600})
            if reps:
                entry["arms"][arm] = reps
        out[uid] = entry
    return out


def extrapolate(measured: dict) -> dict:
    n = len(measured)
    def mean(values):
        values = [v for v in values if v is not None]
        return sum(values) / len(values) if values else 0.0
    probe_gpu = mean([m["probe"]["gpu_h"] for m in measured.values()])
    probe_core = mean([m["probe"]["core_h"] for m in measured.values()])
    arm = {}
    for name, (_, _, reps) in ARMS.items():
        runs = [r for m in measured.values() for r in m["arms"].get(name, [])]
        if not runs:
            continue
        arm[name] = {key: mean([r.get(key) for r in runs]) for key in ("gpu_h", "core_h", "input", "output", "tokens")}
        arm[name]["reps"] = reps
    total = {
        "gpu_h": HOLDOUT_UNITS * (probe_gpu + sum(a.get("gpu_h", 0) * a["reps"] for a in arm.values())),
        "core_h": HOLDOUT_UNITS * (probe_core + sum(a.get("core_h", 0) * a["reps"] for a in arm.values())),
        "input_tokens": HOLDOUT_UNITS * sum((a.get("input") or 0) * a["reps"] for a in arm.values()),
        "output_tokens": HOLDOUT_UNITS * sum((a.get("output") or 0) * a["reps"] for a in arm.values()),
    }
    return {"units_measured": n, "per_unit_probe": {"gpu_h": probe_gpu, "core_h": probe_core},
            "per_arm_run": arm, "holdout_total": total}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--units", nargs="+", required=True)
    args = parser.parse_args(argv)
    measured = collect(args.root, args.units)
    print(json.dumps({"measured": measured, "extrapolation": extrapolate(measured)}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
