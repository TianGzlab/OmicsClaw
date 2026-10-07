"""Adduct mass matching for an explicit metabolite reference."""
import logging
import numpy as np
import pandas as pd
logger = logging.getLogger(__name__)

_PROTON = 1.00727646677

ADDUCT_RULES: dict[str, float] = {
    "[M+H]+":  _PROTON,           # M + H
    "[M-H]-": -_PROTON,           # M - H
    "[M+Na]+": 22.98922,          # M + Na (22.98922 = Na - e)
    "[M+K]+":  38.96316,          # M + K
    "[M+NH4]+": 18.03437,         # M + NH4
}

# ---------------------------------------------------------------------------
# Demo metabolite database
# Monoisotopic *neutral* masses from HMDB / PubChem
# ---------------------------------------------------------------------------
DEMO_METABOLITES = [
    # (name, neutral_monoisotopic_mass, hmdb_id, molecular_formula)
    ("D-Glucose",       180.063388, "HMDB0000122", "C6H12O6"),
    ("L-Lactic acid",    90.031694, "HMDB0000190", "C3H6O3"),
    ("L-Alanine",        89.047678, "HMDB0000161", "C3H7NO2"),
    ("Glycine",          75.032028, "HMDB0000123", "C2H5NO2"),
    ("L-Serine",        105.042593, "HMDB0000187", "C3H7NO3"),
    ("L-Proline",       115.063329, "HMDB0000162", "C5H9NO2"),
    ("L-Valine",        117.078979, "HMDB0000883", "C5H11NO2"),
    ("L-Leucine",       131.094629, "HMDB0000687", "C6H13NO2"),
    ("L-Isoleucine",    131.094629, "HMDB0000172", "C6H13NO2"),
    ("L-Threonine",     119.058243, "HMDB0000167", "C4H9NO3"),
    ("Pyruvic acid",     88.016044, "HMDB0000243", "C3H4O3"),
    ("Citric acid",     192.027003, "HMDB0000094", "C6H8O7"),
    ("Succinic acid",   118.026609, "HMDB0000254", "C4H6O4"),
    ("L-Glutamic acid", 147.053158, "HMDB0000148", "C5H9NO4"),
    ("L-Tryptophan",    204.089878, "HMDB0000929", "C11H12N2O2"),
]


def _compute_adduct_mz(neutral_mass: float, adduct: str) -> float:
    """Compute the expected m/z for a given adduct type."""
    return neutral_mass + ADDUCT_RULES[adduct]


# ---------------------------------------------------------------------------
# Core annotation
# ---------------------------------------------------------------------------

def annotate_mz(
    mz_values: pd.Series,
    database: str = "hmdb",
    ppm: float = 10.0,
    adducts: list[str] | None = None,
    reference=None,
) -> pd.DataFrame:
    """Annotate observed m/z values against the metabolite database.

    Parameters
    ----------
    mz_values : Series
        Observed m/z values.
    database : str
        Database name (informational label; we use DEMO_METABOLITES for the demo).
    ppm : float
        Mass tolerance in parts-per-million.
    adducts : list[str] or None
        Which adducts to consider.  Defaults to ``["[M+H]+", "[M-H]-"]``.

    Returns
    -------
    DataFrame with columns: query_mz, name, formula, database_id,
        adduct, theoretical_mz, ppm_error, confidence.

    All matches within tolerance are reported (not just the first).
    """
    if reference is None:
        raise ValueError('An explicit reference is required')
    if adducts is None:
        adducts = ["[M+H]+", "[M-H]-"]

    logger.info(
        "Annotating %d features against %s (ppm=%.1f, adducts=%s)",
        len(mz_values), database, ppm, adducts,
    )

    annotations: list[dict] = []

    for mz in mz_values:
        matched = False
        for name, neutral_mass, db_id, formula in reference:
            for adduct in adducts:
                theo_mz = _compute_adduct_mz(neutral_mass, adduct)
                error_ppm = abs(mz - theo_mz) / theo_mz * 1e6

                if error_ppm <= ppm:
                    confidence = "high" if error_ppm < 3 else ("medium" if error_ppm < 7 else "low")
                    annotations.append({
                        "query_mz": mz,
                        "name": name,
                        "formula": formula,
                        "database_id": db_id,
                        "adduct": adduct,
                        "theoretical_mz": round(theo_mz, 6),
                        "ppm_error": round(error_ppm, 2),
                        "confidence": confidence,
                    })
                    matched = True
                    # Do NOT break — report all matches

        if not matched:
            annotations.append({
                "query_mz": mz,
                "name": "Unknown",
                "formula": "",
                "database_id": "",
                "adduct": "",
                "theoretical_mz": np.nan,
                "ppm_error": np.nan,
                "confidence": "none",
            })

    return pd.DataFrame(annotations)
