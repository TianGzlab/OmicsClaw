"""Kaplan-Meier and log-rank calculations for the Python survival backend."""
from __future__ import annotations
import logging
import numpy as np
from scipy import stats as sp_stats
logger = logging.getLogger(__name__)

def _kaplan_meier(time: np.ndarray, event: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute Kaplan-Meier survival curve.

    Returns: (times, survival_prob, se)
    """
    order = np.argsort(time)
    t_sorted = time[order]
    e_sorted = event[order]

    unique_times = np.unique(t_sorted[e_sorted == 1])
    km_times = [0.0]
    km_surv = [1.0]
    km_se = [0.0]

    n_at_risk = len(time)
    surv = 1.0
    var_sum = 0.0

    for t in unique_times:
        # Number of events at this time
        d = int(np.sum((t_sorted == t) & (e_sorted == 1)))
        # Subjects censored at an earlier event time leave the next risk set.
        n_at_risk = int(np.sum(t_sorted >= t))

        if n_at_risk <= 0:
            break

        surv *= (1 - d / n_at_risk)
        var_sum += d / (n_at_risk * max(n_at_risk - d, 1))  # Greenwood
        se = surv * np.sqrt(var_sum)

        km_times.append(float(t))
        km_surv.append(surv)
        km_se.append(se)

        n_at_risk -= d

    return np.array(km_times), np.array(km_surv), np.array(km_se)

def _log_rank_test(time1: np.ndarray, event1: np.ndarray,
                   time2: np.ndarray, event2: np.ndarray) -> tuple[float, float]:
    """Two-sample log-rank test.

    Returns: (chi2_statistic, p_value)
    """
    all_times = np.unique(np.concatenate([time1[event1 == 1], time2[event2 == 1]]))

    observed1 = 0
    expected1 = 0.0

    for t in all_times:
        d1 = np.sum((time1 == t) & (event1 == 1))
        d2 = np.sum((time2 == t) & (event2 == 1))
        n1 = np.sum(time1 >= t)
        n2 = np.sum(time2 >= t)
        d_total = d1 + d2
        n_total = n1 + n2

        if n_total == 0:
            continue

        observed1 += d1
        expected1 += d_total * n1 / n_total

    if expected1 == 0:
        return 0.0, 1.0

    # Variance (Greenwood-type)
    variance = 0.0
    for t in all_times:
        d1 = np.sum((time1 == t) & (event1 == 1))
        d2 = np.sum((time2 == t) & (event2 == 1))
        n1 = np.sum(time1 >= t)
        n2 = np.sum(time2 >= t)
        d_total = d1 + d2
        n_total = n1 + n2

        if n_total <= 1:
            continue

        variance += (d_total * n1 * n2 * (n_total - d_total)) / \
                    (n_total * n_total * (n_total - 1))

    if variance <= 0:
        return 0.0, 1.0

    chi2 = (observed1 - expected1) ** 2 / variance
    pval = float(1 - sp_stats.chi2.cdf(chi2, df=1))
    return float(chi2), pval

def analyze_gene(gene: str, expression: np.ndarray, time: np.ndarray,
                 event: np.ndarray, cutoff_method: str = "median") -> dict:
    """Run survival analysis for a single gene."""
    if cutoff_method == "median":
        cutoff = float(np.median(expression))
    else:
        # Optimal cutoff: maximize log-rank chi2
        sorted_expr = np.sort(np.unique(expression))
        best_chi2 = 0.0
        best_cut = float(np.median(expression))
        for c in sorted_expr[1:-1]:
            mask_high = expression >= c
            if mask_high.sum() < 5 or (~mask_high).sum() < 5:
                continue
            chi2, _ = _log_rank_test(time[mask_high], event[mask_high],
                                     time[~mask_high], event[~mask_high])
            if chi2 > best_chi2:
                best_chi2 = chi2
                best_cut = float(c)
        cutoff = best_cut

    high_mask = expression >= cutoff
    low_mask = ~high_mask

    n_high = int(high_mask.sum())
    n_low = int(low_mask.sum())

    if n_high < 2 or n_low < 2:
        return {"gene": gene, "status": "insufficient_samples",
                "n_high": n_high, "n_low": n_low}

    chi2, pval = _log_rank_test(time[high_mask], event[high_mask],
                                time[low_mask], event[low_mask])

    # Median survival per group
    km_high_t, km_high_s, km_high_se = _kaplan_meier(time[high_mask], event[high_mask])
    km_low_t, km_low_s, km_low_se = _kaplan_meier(time[low_mask], event[low_mask])

    median_high = _median_survival(km_high_t, km_high_s)
    median_low = _median_survival(km_low_t, km_low_s)

    # Landmark survival (from Biomni survival best practices)
    landmarks_high = _landmark_survival(km_high_t, km_high_s, km_high_se)
    landmarks_low = _landmark_survival(km_low_t, km_low_s, km_low_se)

    # Censoring rate warning (from Biomni risk-stratification-guide.md)
    censor_rate = 1.0 - event.mean()
    censor_note = None
    if censor_rate > 0.8:
        censor_note = f"Heavy censoring ({censor_rate:.0%}). KM tail estimates may be unreliable."
        logger.warning("%s: %s", gene, censor_note)

    # Simple hazard ratio estimate (events/time ratio)
    events_high = event[high_mask].sum()
    events_low = event[low_mask].sum()
    time_high = time[high_mask].sum()
    time_low = time[low_mask].sum()
    hr = (events_high / max(time_high, 1)) / max(events_low / max(time_low, 1), 1e-10)

    return {
        "gene": gene,
        "status": "ok",
        "cutoff": round(cutoff, 4),
        "n_high": n_high,
        "n_low": n_low,
        "log_rank_chi2": round(chi2, 4),
        "log_rank_pval": pval,
        "median_survival_high": median_high["value"],
        "median_survival_low": median_low["value"],
        "median_high_note": median_high["note"],
        "median_low_note": median_low["note"],
        "landmark_survival_high": landmarks_high,
        "landmark_survival_low": landmarks_low,
        "hazard_ratio": round(hr, 4),
        "censoring_rate": round(censor_rate, 4),
        "censoring_note": censor_note,
        "km_high": (km_high_t, km_high_s),
        "km_low": (km_low_t, km_low_s),
    }

def _median_survival(km_times: np.ndarray, km_surv: np.ndarray) -> dict:
    """Find median survival time with reliability check.

    Returns dict with 'value' (float or None) and 'note' (reliability message).
    From Biomni survival best practices: if KM never crosses 50%, median is
    unreliable — use landmark survival instead.
    """
    below = np.where(km_surv <= 0.5)[0]
    if len(below) == 0:
        return {"value": None, "note": "Not reached (KM curve never crosses 50%)"}
    return {"value": float(km_times[below[0]]), "note": "Reached"}

def _landmark_survival(
    km_times: np.ndarray, km_surv: np.ndarray, km_se: np.ndarray,
    landmarks: list[float] | None = None,
) -> list[dict]:
    """Compute survival probability at fixed landmark time points.

    More robust than median survival when median is not reached or when
    censoring is heavy. Returns S(t) with 95% CI at each landmark.

    From Biomni survival-analysis-clinical best practices.
    """
    if landmarks is None:
        # Auto-select landmarks based on data range
        max_time = float(km_times[-1]) if len(km_times) > 0 else 0
        if max_time > 60:
            landmarks = [12.0, 36.0, 60.0]  # 1yr, 3yr, 5yr
        elif max_time > 24:
            landmarks = [6.0, 12.0, 24.0]
        else:
            landmarks = [max_time * 0.25, max_time * 0.5, max_time * 0.75]

    results = []
    for t in landmarks:
        # Find S(t): last KM value at or before time t
        valid = km_times <= t
        if not np.any(valid):
            results.append({"time": t, "survival": None, "ci_lower": None, "ci_upper": None})
            continue

        idx = np.where(valid)[0][-1]
        s = float(km_surv[idx])
        se = float(km_se[idx]) if idx < len(km_se) else 0.0
        ci_lower = max(0, s - 1.96 * se)
        ci_upper = min(1, s + 1.96 * se)
        results.append({
            "time": round(t, 1),
            "survival": round(s, 4),
            "ci_lower": round(ci_lower, 4),
            "ci_upper": round(ci_upper, 4),
        })

    return results
