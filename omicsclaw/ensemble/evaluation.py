"""Ground-truth metrics for benchmarks: ARI and NMI.

Nothing on the run path imports this module: trials, the tool and the panels
never see ground truth. A benchmark driver calls it after the fact, with a
truth table it keeps outside the workspace.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping


def _aligned(labels: Mapping[str, Any], truth: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    predicted: list[str] = []
    expected: list[str] = []
    for obs_id, label in labels.items():
        true = truth.get(obs_id)
        if true is None or (isinstance(true, float) and true != true) or true == "":
            continue
        predicted.append(str(label))
        expected.append(str(true))
    if not predicted:
        raise ValueError("no observation has both a label and a ground-truth value")
    return predicted, expected


def ari(labels: Mapping[str, Any], truth: Mapping[str, Any]) -> float:
    """Adjusted Rand index over the observations present in both, missing truth ignored."""
    from sklearn.metrics import adjusted_rand_score

    predicted, expected = _aligned(labels, truth)
    return float(adjusted_rand_score(expected, predicted))


def nmi(labels: Mapping[str, Any], truth: Mapping[str, Any]) -> float:
    """Normalised mutual information over the same observations as :func:`ari`."""
    from sklearn.metrics import normalized_mutual_info_score

    predicted, expected = _aligned(labels, truth)
    return float(normalized_mutual_info_score(expected, predicted))


def evaluate(labels: Mapping[str, Any], truth: Mapping[str, Any]) -> Dict[str, float]:
    """Both metrics, and how many observations they were computed on."""
    predicted, _ = _aligned(labels, truth)
    return {"ari": ari(labels, truth), "nmi": nmi(labels, truth), "n_evaluated": float(len(predicted))}


__all__ = ["ari", "evaluate", "nmi"]
