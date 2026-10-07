"""Peak detection on retention-time ordered sample signals."""
import numpy as np
import pandas as pd
from scipy.signal import find_peaks

def detect_peaks(
    intensities: np.ndarray,
    *,
    prominence: float = 1e4,
    height: float | None = None,
    distance: int = 5,
    rel_height: float = 0.5,
) -> dict:
    """Detect peaks in a 1-D intensity array using scipy.signal.find_peaks.

    Parameters
    ----------
    intensities : 1-D array-like
        Signal intensity values sorted by retention time.
    prominence : float
        Minimum prominence a peak must have to be detected.
    height : float or None
        Minimum absolute intensity for a peak.
    distance : int
        Minimum number of data points between neighbouring peaks.
    rel_height : float
        Relative height at which the peak width is measured (0–1).

    Returns
    -------
    dict with keys *peak_indices*, *properties* (from scipy), *n_peaks*.
    """
    intensities = np.asarray(intensities, dtype=float)
    peak_kwargs: dict = {"prominence": prominence, "distance": distance}
    if height is not None:
        peak_kwargs["height"] = height

    indices, properties = find_peaks(intensities, **peak_kwargs)

    # Measure peak widths at rel_height
    if len(indices) > 0:
        from scipy.signal import peak_widths
        widths, width_heights, left_ips, right_ips = peak_widths(
            intensities, indices, rel_height=rel_height,
        )
        properties["widths"] = widths
        properties["width_heights"] = width_heights
        properties["left_ips"] = left_ips
        properties["right_ips"] = right_ips

    return {
        "peak_indices": indices,
        "properties": properties,
        "n_peaks": len(indices),
    }


def detect_peaks_table(
    df: pd.DataFrame,
    *,
    sample_cols: list[str] | None = None,
    prominence: float = 1e4,
    height: float | None = None,
    distance: int = 5,
) -> pd.DataFrame:
    """Run peak detection on a tabular feature matrix.

    For each sample column, sort by retention time, run ``detect_peaks``,
    and aggregate per-feature peak calls.

    Parameters
    ----------
    df : DataFrame
        Must contain 'mz' and 'rt' columns.  Additional numeric columns
        are treated as sample intensities.
    sample_cols : list[str] or None
        Which columns to treat as sample intensities.  If *None*, all
        columns containing 'intensity' or starting with 'sample' are used.
    prominence, height, distance
        Forwarded to :func:`detect_peaks`.

    Returns
    -------
    DataFrame with one row per detected peak, columns:
        mz, rt, sample, intensity, prominence, width
    """
    if sample_cols is None:
        sample_cols = [
            c for c in df.columns
            if "intensity" in c.lower() or c.lower().startswith("sample")
        ]

    if not sample_cols:
        raise ValueError(
            "No sample/intensity columns detected. Supply --sample-prefix "
            "or ensure columns contain 'intensity' or start with 'sample'."
        )

    # Sort by retention time to ensure signal ordering is meaningful
    df_sorted = df.sort_values("rt").reset_index(drop=True)

    peak_records: list[dict] = []
    for col in sample_cols:
        result = detect_peaks(
            df_sorted[col].values,
            prominence=prominence,
            height=height,
            distance=distance,
        )
        idxs = result["peak_indices"]
        props = result["properties"]

        for i, idx in enumerate(idxs):
            record = {
                "mz": float(df_sorted.loc[idx, "mz"]),
                "rt": float(df_sorted.loc[idx, "rt"]),
                "sample": col,
                "intensity": float(df_sorted.loc[idx, col]),
                "prominence": float(props["prominences"][i]),
            }
            if "widths" in props:
                record["width"] = float(props["widths"][i])
            peak_records.append(record)

    return pd.DataFrame(peak_records, columns=["mz", "rt", "sample", "intensity", "prominence", "width"])
