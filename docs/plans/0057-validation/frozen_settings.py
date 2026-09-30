"""Write ``frozen_settings.json``: the settings the hold-out runs with, item by item of the plan's §4.6 list.

A record, not a check. Values that are constants in the code are read from
it, so the file cannot drift from what runs; the rest (arms, estimators,
statistics, the stop line, owner decisions) are written here once.
``run_holdout.py`` copies it, with the model, seed and git state, into the run
directory when a run starts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from common import ARMS, DLPFC_TISSUE, REPO, RUNNABLE, TRIAL_SEED  # noqa: E402

sys.path.insert(0, str(REPO))


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def settings(*, manifest: Path | None, measured: dict | None = None) -> dict:
    from omicsclaw.ensemble.metrics import SPATIAL_DOMAINS
    from omicsclaw.ensemble.runner import SEED_DIR_RELATIVE
    from omicsclaw.ensemble.tuning import probe as P
    from omicsclaw.ensemble.tuning.budget import CALIBRATION_RUNS, GROUPS_PER_METHOD, caps
    from omicsclaw.ensemble.tuning.evidence import STABLE_PEAK
    from omicsclaw.ensemble.tuning.llm import RETRIES
    from omicsclaw.ensemble.tuning.prompts import COUNT_PATTERNS, template_sha256
    from omicsclaw.ensemble.tuning.search import GRID_POINTS, MAX_DIMENSIONS, NEIGHBOURHOOD_STEP
    from omicsclaw.ensemble.tuning.stability import PAC_HIGH, PAC_LOW
    from omicsclaw.provider import resolve_config
    import prepare_cosmx
    import prepare_dlpfc
    import run_arms
    import evaluate

    env = {}
    dotenv = REPO / ".env"
    if dotenv.is_file():
        for line in dotenv.read_text().splitlines():
            key, sep, value = line.strip().partition("=")
            if sep and not key.startswith("#"):
                env[key.strip()] = value.strip()
    resolved = resolve_config(env=env)
    seed_file = REPO / SEED_DIR_RELATIVE / "sitecustomize.py"
    return {
        "plan": "docs/plans/0057-ensemble-tuning.md v3.1, with the owner rulings of 2026-09-27 (N1-N4)",
        "probe": {
            **P.PROBE_CONSTANTS,
            "resolution_grid_generation": "[round(0.10 + 0.05*i, 2) for i in range(39)]",
            "stable_peak_threshold": STABLE_PEAK,
            "pac_interval": f"({PAC_LOW}, {PAC_HIGH}]  (MultiK Fn(0.9) - Fn(0.1))",
            "curves": {
                "f": "share of subsample runs with K labels",
                "c": "1 - rPAC over pairs present together at least once; rPAC = PAC / (1 - prop_zeroes)",
                "a": "mean pairwise AMI; members: exact methods' probe trial at K, calibrated methods' "
                     "full-input trial at K of median resolution; >= 3 partitions",
            },
            "peaks": "not below the neighbouring K among the K where the curve is defined; f and c only where f >= min_f",
            "fallback_k": ">= 2 curves defined; best mean rank among defined K; ties: larger a, then smaller K",
            "marker_request": "once, 1-2 K of the grid not in the stable peaks; the 2 retries span both steps",
            "subsample_preprocessing": "80% of observations; neighbour graph rebuilt from the input X_pca, PCA not recomputed",
            "markers": "scanpy wilcoxon on X; compact top 3 for every K, full top 5 for the stable peaks and requested K",
        },
        "panel": {
            "version": SPATIAL_DOMAINS.version,
            "members": ["pas (chance-corrected)", "silhouette_pca (raw, sample of 5000, seed 0)"],
            "combination": "N1: mean of members normalised by the range of the probe's ok trials with K labels; "
                           "not clipped; a member with an empty range or < 2 reference trials leaves the mean. "
                           "N2 (within-group ranks) was compared on the development units and not adopted.",
            "se": "SE_pas = sqrt(PAS(1-PAS)/n)/E[PAS]; SE_sil = sd/sqrt(m); SE = sqrt(sum_j (SE_j/range_j)^2)/members",
        },
        "search": {
            "max_dimensions": MAX_DIMENSIONS,
            "dimensions": "active under the defaults and pins, not the K parameter, not pinned, by priority",
            "one_dimension": {"grid_points": GRID_POINTS,
                              "spatial_weight": [round(0.075 * i, 3) for i in range(13)],
                              "n_layers": [1, 2, 3, 4, 5], "llm": False},
            "stage1": "3 one-parameter sweeps (2-D: both ends of priority 1, far end of priority 2; "
                      "3-D: far end of each; ties to the larger value) + 3 model proposals, run together",
            "proposal_checks": "validate_params; pins equal; not the default, a sweep or another proposal; "
                               "a refused item is dropped without a retry and topped up by random search "
                               "(seed sha256(run_id|method|stage1)); an unreadable batch retries at most 2 times",
            "skip_rule": "skip stage 2 unless a stage-1 trial scores above default score + default SE",
            "stage2": {"step": NEIGHBOURHOOD_STEP, "centre": "best stage-1 trial (ties: fewer deviations)",
                       "2-D": "4 axis points + 2 diagonals along and against default->centre",
                       "3-D": "6 axis points",
                       "clipped_duplicates": "2 steps the other way, else dropped"},
            "groups_per_method": GROUPS_PER_METHOD,
            "calibration_runs": CALIBRATION_RUNS,
            "new_run_caps": caps({"exact": "exact", "calibrate": "calibrate"}),
            "calibration": "bisection on the log scale between the largest value below K and the smallest above; "
                           "initial value from the probe's resolution map; off_k / unreachable_k not selectable",
            "simplicity": "among eligible trials with score >= best - SE(best): fewest parameters differing from "
                          "the defaults (K and pins not counted), then the smallest sum of distances "
                          "|x - default|/(high - low) (log scale for log parameters; 1 for categorical/bool), "
                          "then the earliest",
            "no_eligible_trial": "the method's default trial (fallback_default), which may not have K labels",
            "cross_method": "highest fixed-K score among method answers with K labels",
        },
        "seeding": {
            "trial_seed": TRIAL_SEED,
            "determinism": "strict (torch.use_deterministic_algorithms(True))",
            "sitecustomize": str(SEED_DIR_RELATIVE / "sitecustomize.py"),
            "sitecustomize_sha256": _sha(seed_file),
            "environment": {"PYTHONHASHSEED": "0", "CUBLAS_WORKSPACE_CONFIG": ":4096:8"},
            "a0_definition": "the probe's default-parameter trial, which equals running the skill directly with its "
                             "defaults in the same seed environment (verified, T10-1)",
        },
        "llm": {
            "provider": resolved.provider,
            "model": resolved.model,
            "model_date": "as served by the provider on the run date; the date is recorded per call in llm/NNNN.json",
            "temperature": resolved.temperature,
            "max_tokens": resolved.max_tokens or None,
            "max_tokens_behaviour": "not sent; the endpoint uses the model's own output ceiling (owner ruling N4)",
            "thinking_budget": resolved.thinking_budget_tokens or None,
            "thinking_behaviour": "none configured; the model's default reasoning is returned as reasoning_content "
                                  "and counted as output tokens (owner ruling N4)",
            "retries": RETRIES,
            "templates_sha256": template_sha256(),
            "output_schema": {"k_decision": "chosen_k, rationale, evidence[1..10] (markers|curve|skill_md), confidence",
                              "proposals": "exactly 3 {params, why}"},
            "images": False,
        },
        "a3": {
            "token_cap": 3_000_000,
            "token_cap_basis": "plan initial value, kept by owner ruling N3 (not tightened to the development p95)",
            "token_count": "input + output of every main-engine turn_end and every sub-agent turn; cache hits in full; "
                           "billed (uncached) input reported apart; a turn without usage refuses the unit",
            "max_turns": run_arms.A3_MAX_TURNS,
            "reminder": run_arms.REMINDER,
            "reminder_max_turns": run_arms.REMINDER_TURNS,
            "past_the_cap": "the running exchange ends at its next model call; the reminder follows with its history",
            "rules": run_arms.RULES,
            "mcp": "off",
            "permission_mode": "auto-approve (deny rules still apply)",
            "system_prompt_front_matter": "one empty file (no product contract)",
            "task_template": "free_task.txt",
        },
        "leak": {
            "patterns": [p.pattern for p in COUNT_PATTERNS],
            "fields": ["tissue", "data summary", "templates", "free-orchestration task"],
            "not_checked": ["SKILL.md and parameters.md", "trial outputs"],
            "tissue": {"DLPFC": DLPFC_TISSUE, "CosMx": prepare_cosmx.TISSUE},
            "opaque_ids": "units u01.. (DLPFC), c01.. (CosMx), w01 (warm-up); batch b0",
        },
        "data": {
            "dlpfc_holdout": list(prepare_dlpfc.HOLDOUT),
            "dlpfc_expected_spots": prepare_dlpfc.EXPECTED_SPOTS,
            "dlpfc_donors": {"Br5292": ["151507", "151508", "151509", "151510"],
                             "Br5595": ["151669", "151670", "151671", "151672"],
                             "Br8100": ["151675", "151676"]},
            "dlpfc_truth_column": prepare_dlpfc.TRUTH_COLUMN,
            "root": "/workspace/dataset/private/zhouwg_data/0057_runs/holdout",
            "manifest": str(manifest) if manifest else None,
            "manifest_sha256": _sha(manifest) if manifest and manifest.is_file() else None,
            "cosmx": {"source": str(prepare_cosmx.SOURCE),
                      "source_sha256": "abd2c6938ede844cb7b18d2a948a3af58e0de69ede3772c37133cff3f21689ed",
                      "source_shape": "793318 cells x 999 genes; X from layers['counts']; slide_id 1/2; FOV in donor_id",
                      "eligible_blocks": {"slide 1": 269, "slide 2": 376},
                      "eligible_min_cells": prepare_cosmx.MIN_CELLS,
                      "primary": "K* >= 3, 12 per slide", "single": "K* = 2, 4 per slide", "k1": "excluded",
                      "seed": prepare_cosmx.SEED, "warmup": "drawn from slide 1 first (slide 1, FOV 41) and removed",
                      "k_star_sensitivity": "niches with a share >= 5%",
                      "qc_loss_limit": prepare_cosmx.QC_LOSS_LIMIT},
            "preprocess": {"DLPFC": "--data-type visium --species human --max-mt-pct 100",
                           "CosMx": "--data-type generic --species human; X = layers['counts']"},
            "obs_allowlist": ["batch"],
        },
        "arms": {name: {"pipeline_arm": kind, "tissue_given": tissue, "repetitions": reps}
                 for name, (kind, tissue, reps) in ARMS.items()}
                | {"A6_seeds": [1, 2, 3], "A0": "probe default trials", "A0k": "cellcharter --auto-k, once",
                   "methods": list(RUNNABLE)},
        "estimators": {
            "inclusion": "methods whose default trial ended ok (others excluded from D1, D2, D3)",
            "D1": "mean over included methods of ARI(tun_m) - ARI(def_m); fallback_default or failed tuning contributes 0",
            "D1_sensitivity": "the same with fallback_default / failed methods removed",
            "D2": "ARI(fin) - median over included methods of ARI(def_m)",
            "D3": "ARI(fin) - max over included methods of ARI(def_m)",
            "failure": "no fin -> ARI 0; sensitivity: median def",
            "repetitions": "averaged per unit before any statistic; spread reported",
            "secondary": ["A1-A2", "A1-A3", "A1-A6 differences of ARI(fin)", "A1 tun_cellcharter vs A0k"],
            "descriptive": ["regret vs oracle over all arms and vs the probe only",
                            "Spearman rho of fixed-K score and ARI at the chosen K (n >= 5)",
                            "chosen K distribution, share in stable peaks vs |M|/|G|, requests, fallbacks, |K - K*|",
                            "share of skipped stage 2; source of final choices", "cost"],
        },
        "statistics": {
            "t": "95% t interval, df = n - 1",
            "bca": f"95% BCa bootstrap, {evaluate.BOOT_N} resamples, seed {evaluate.BOOT_SEED}",
            "sign_flip": "exact two-sided sign-flip p (descriptive; no multiplicity correction)",
            "dlpfc": "10 units main; split by donor; sensitivity without Br8100",
            "cosmx": "per slide (n = 12 each); slide-stratified mean with within-slide bootstrap as description; "
                     "K* = 2 blocks listed with their median",
            "j1": "share choosing K = 7 by K* (A1, A2, A6; DLPFC K*=5 group 151669-151672 vs K*=7; CosMx by K* both "
                  "definitions); D1/D2 by K*; D1 given chosen K = 7; sentence required if A1's share at K*=5 >= A6's",
        },
    "technical_freeze": "none (owner ruling 2026-09-27): settings are recorded in each run directory, not checked",
    "stop_line": "if the 95% t intervals of D1 and D2 on the DLPFC hold-out both have upper bounds < 0, "
                     "do not proceed to the 0059 confirmation (t interval decides when it and BCa disagree)",
        "report": {"template": "report.py", "template_sha256": _sha(HERE / "report.py"),
                   "sections": ["per unit", "primary estimators and stop line", "secondary", "K choice and J1",
                                "donor / slide splits", "descriptive", "cost", "0059 power inputs",
                                "deviations, failures, leak refusals"]},
        "measured_on_development": measured or {},
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--measured", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=HERE / "frozen_settings.json")
    args = parser.parse_args(argv)
    measured = json.loads(args.measured.read_text()) if args.measured else None
    document = settings(manifest=args.manifest, measured=measured)
    args.out.write_text(json.dumps(document, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
