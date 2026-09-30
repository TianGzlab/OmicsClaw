"""Shared synthetic evidence, markers and inputs for the prompt and pipeline tests."""

from __future__ import annotations

from omicsclaw.ensemble.tuning.evidence import load_evidence
from omicsclaw.ensemble.tuning.prompts import DataSummary, KDecisionInput, ProposeInput, SkillText

GRID = tuple(range(3, 17))
STABLE = (4, 6)

SKILL_MD = (
    "# spatial-domains\n\nIdentify tissue regions. The default number of domains is 7 when "
    "--n-domains is omitted; typical cortex sections show 7 layers.\n"
)
PARAMETERS_MD = "Use a larger spatial_weight for smoother domains.\n"


def stability_document(stable=STABLE):
    rows = {}
    for k in GRID:
        pf = 0.8 if k in stable else 0.1
        rows[str(k)] = {
            "k": k, "f": 0.05 + 0.01 * (k % 3), "f_lo": 0.02, "f_hi": 0.1,
            "c": 0.5 + 0.02 * (k % 4), "c_lo": 0.4, "c_hi": 0.7,
            "a": 0.4 + 0.01 * k if k < 15 else None, "a_lo": 0.3, "a_hi": 0.6,
            "runs": 10, "a_members": ["spagcn", "leiden", "louvain"] if k < 15 else ["spagcn"],
            "peak_frequency": {"f": pf, "c": 0.0, "a": 0.0},
        }
    return {"grid": list(GRID), "min_f": 0.025, "per_k": rows}


def _domains(k, full):
    out = []
    for d in range(k):
        genes = [f"G{k}_{d}_{i}" for i in range(5 if full else 3)]
        if full:
            out.append({"domain": str(d), "share": round(1 / k, 4), "same_label_neighbours": 0.8,
                        "centroid": [0.1 * d, 0.5],
                        "markers": [{"gene": g, "log2fc": 2.0, "pct_in": 0.6, "pct_out": 0.1} for g in genes]})
        else:
            out.append({"domain": str(d), "share": round(1 / k, 4), "genes": genes})
    return out


def markers_document(full=STABLE):
    return {
        "data": {"n_obs": 3000, "n_vars": 2000, "median_counts": 5000.0, "median_genes": 2000.0,
                 "x_span": 100.0, "y_span": 80.0, "species": "human",
                 "preprocessing": {"max_mt_pct": 100.0, "n_neighbors": 15}, "obsm_keys": ["X_pca", "spatial"],
                 "n_batches": 1},
        "compact": {str(k): {"k": k, "method": "spagcn", "trial": "t0001", "params": {"n_domains": k},
                             "domains": _domains(k, False)} for k in GRID},
        "full": {str(k): {"k": k, "method": "spagcn", "trial": "t0001", "params": {"n_domains": k},
                          "domains": _domains(k, True)} for k in full},
        "nesting": [{"coarse": 4, "fine": 6, "rows": [{"domain": "0", "into": "0", "share": 1.0}]}],
    }


def k_input(tissue="human dorsolateral prefrontal cortex"):
    markers = markers_document()
    return KDecisionInput(
        grid=GRID,
        skill=SkillText(SKILL_MD, PARAMETERS_MD),
        data=DataSummary.from_description(markers["data"], platform="visium"),
        tissue=tissue,
        evidence=load_evidence(stability_document()),
        markers=markers,
    )


def propose_input(tissue="human dorsolateral prefrontal cortex"):
    markers = markers_document()
    return ProposeInput(
        method="spagcn",
        k=7,
        method_summary="method spagcn:\n  spagcn_p: float in [0.1, 0.9], default 0.5\n  epochs: int in [50, 400] (log scale), default 100",
        fixed={"n_domains": 7},
        dimensions=("spagcn_p", "epochs"),
        k_control="The number of domains is set directly by n_domains.",
        default_result={"params": {"n_domains": 7, "spagcn_p": 0.5, "epochs": 100}, "n_labels": 7,
                        "fixed_k_score": 0.5, "se": 0.02, "pas": 0.8, "silhouette": 0.1},
        sweeps=({"spagcn_p": 0.1}, {"spagcn_p": 0.9}, {"epochs": 400}),
        resolution_map=None,
        skill=SkillText(SKILL_MD, PARAMETERS_MD),
        data=DataSummary.from_description(markers["data"], platform="visium"),
        tissue=tissue,
    )


def decision(k=7, **extra):
    import json

    body = {
        "chosen_k": k, "rationale": "markers separate the layers",
        "evidence": [{"k": 4, "kind": "markers", "domain": "1", "genes": ["G4_1_0"], "reading": "x"},
                     {"k": k, "kind": "curve", "curve": "f", "reading": "flat"},
                     {"k": k, "kind": "skill_md", "quote": "The default number of domains is 7", "reading": "prior"}],
        "confidence": "medium",
    }
    body.update(extra)
    return json.dumps(body)
