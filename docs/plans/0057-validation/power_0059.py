"""The 0059 sample size from the 0057 hold-out D2 (plan §4.9).

``delta`` = lower end of the 80% two-sided t interval of mean D2; ``sigma`` =
the 80% upper confidence bound of the standard deviation (chi-square). The
number of units is the smallest n whose one-sided (alpha = 0.05) t test has
power >= 0.80 under the non-central t distribution, checked by the Monte Carlo
power of the exact one-sided sign-flip test (normal draws, 10,000 runs).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ALPHA = 0.05
POWER = 0.80
SEED = 20260926


def plan_inputs(d2: list[float]) -> dict:
    from scipy import stats

    n = len(d2)
    mean = sum(d2) / n
    sd = stats.tstd(d2)
    lower80 = mean - stats.t.ppf(0.90, n - 1) * sd / math.sqrt(n)
    sigma = sd * math.sqrt((n - 1) / stats.chi2.ppf(0.20, n - 1))
    return {"n": n, "mean": mean, "sd": sd, "delta": lower80, "sigma": sigma}


def t_power(n: int, delta: float, sigma: float) -> float:
    from scipy import stats

    df = n - 1
    critical = stats.t.ppf(1 - ALPHA, df)
    return float(1 - stats.nct.cdf(critical, df, delta / sigma * math.sqrt(n)))


def sign_flip_power(n: int, delta: float, sigma: float, runs: int = 10_000) -> float:
    import numpy as np

    rng = np.random.default_rng(SEED)
    signs = None
    if n <= 16:
        grid = np.array(np.meshgrid(*[[1, -1]] * n)).T.reshape(-1, n)
        signs = grid
    hits = 0
    for _ in range(runs):
        x = rng.normal(delta, sigma, n)
        observed = x.mean()
        flips = signs if signs is not None else rng.choice([1, -1], size=(4096, n))
        p = float(((flips * x).mean(axis=1) >= observed - 1e-12).mean())
        hits += p <= ALPHA
    return hits / runs


def required_n(delta: float, sigma: float, limit: int = 200) -> int | None:
    if delta <= 0:
        return None
    for n in range(3, limit + 1):
        if t_power(n, delta, sigma) >= POWER:
            return n
    return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", type=Path, required=True, help="analyse.py output of the hold-out")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from evaluate import unit_means

    document = json.loads(args.analysis.read_text())
    units = document["groups"]["DLPFC"]["units"]
    d2 = [unit_means(document["scores"][u], "A1")["D2"] for u in units if document["scores"][u]["arms"].get("A1")]
    if len(d2) < 2:
        print(json.dumps({"n": len(d2), "verdict": "fewer than two DLPFC units"}))
        return 0
    inputs = plan_inputs(d2)
    n = required_n(inputs["delta"], inputs["sigma"])
    result = {**inputs, "required_n": n,
              "sign_flip_power_at_n": sign_flip_power(n, inputs["delta"], inputs["sigma"]) if n and n <= 16 else None,
              "verdict": None if n else "the effect cannot be confirmed with a feasible number of units"}
    print(json.dumps(result, indent=1))
    if args.output:
        args.output.write_text(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
