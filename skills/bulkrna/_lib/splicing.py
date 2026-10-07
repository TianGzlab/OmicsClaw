"""Splicing event aggregation shared by both entry points."""
import pandas as pd

def core_analysis(
    events_df: pd.DataFrame,
    *,
    dpsi_cutoff: float = 0.1,
    padj_cutoff: float = 0.05,
) -> dict:
    """Analyse splicing events and return a summary dict.

    Parameters
    ----------
    events_df : pd.DataFrame
        Must contain columns: event_type, gene, delta_psi, padj.
    dpsi_cutoff : float
        Minimum |delta_psi| for significance.
    padj_cutoff : float
        Maximum adjusted p-value for significance.

    Returns
    -------
    dict with keys: n_events, n_genes_affected, event_type_counts,
        n_significant, n_up, n_down, significant_events_df, top_events.
    """
    n_events = len(events_df)
    n_genes_affected = events_df["gene"].nunique()

    event_type_counts = events_df["event_type"].value_counts().to_dict()

    sig_mask = (events_df["delta_psi"].abs() > dpsi_cutoff) & (events_df["padj"] < padj_cutoff)
    sig_df = events_df[sig_mask].copy()

    n_significant = len(sig_df)
    n_up = int((sig_df["delta_psi"] > 0).sum())
    n_down = int((sig_df["delta_psi"] < 0).sum())

    top_events = (
        events_df
        .assign(_abs_dpsi=events_df["delta_psi"].abs())
        .nlargest(20, "_abs_dpsi")
        .drop(columns=["_abs_dpsi"])
    )

    return {
        "n_events": n_events,
        "n_genes_affected": n_genes_affected,
        "event_type_counts": event_type_counts,
        "n_significant": n_significant,
        "n_up": n_up,
        "n_down": n_down,
        "dpsi_cutoff": dpsi_cutoff,
        "padj_cutoff": padj_cutoff,
        "significant_events_df": sig_df,
        "top_events": top_events,
        "events_df": events_df,
    }
