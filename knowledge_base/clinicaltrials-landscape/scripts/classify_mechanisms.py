"""
Classify clinical trial interventions by mechanism of action.

Supports config-driven taxonomy (disease-specific patterns loaded from
disease_configs/*.yaml) and generic fallback classification by
intervention type when no config is available.
"""

import re

try:
    from disease_config import get_mechanism_patterns, get_drug_normalization
except ImportError:
    from scripts.disease_config import get_mechanism_patterns, get_drug_normalization


# ============================================================
# MODULE-LEVEL STATE (set by configure())
# ============================================================
# Taxonomy and drug normalization loaded from disease config.
# When empty, classify_mechanism() uses generic intervention-type fallback.

_mechanism_patterns = []
_drug_normalization = {}
_configured = False


def configure(config):
    """
    Load mechanism taxonomy and drug normalization from disease config.

    Parameters
    ----------
    config : dict or None
        Parsed disease config from load_disease_config().
        If None, clears taxonomy (uses generic fallback).
    """
    global _mechanism_patterns, _drug_normalization, _configured
    _mechanism_patterns = get_mechanism_patterns(config)
    _drug_normalization = get_drug_normalization(config)
    _configured = True


# Phase normalization mapping
PHASE_MAP = {
    "EARLY_PHASE1": "Phase 1",
    "PHASE1": "Phase 1",
    "PHASE2": "Phase 2",
    "PHASE3": "Phase 3",
    "PHASE4": "Phase 4",
    "NA": "Not Applicable",
}


def _normalize_drug_name(name):
    """Normalize drug name to canonical form using loaded config."""
    if not name:
        return name
    for pattern, canonical in _drug_normalization.items():
        if re.match(pattern, name.strip()):
            return canonical
    return name.strip()


def _is_biosimilar(interventions, brief_title="", official_title=""):
    """Detect if a trial involves a biosimilar product."""
    corpus = " ".join([
        *[intv.get("name", "") + " " + intv.get("description", "") for intv in interventions],
        brief_title, official_title
    ]).lower()
    biosimilar_patterns = [
        "biosimilar", "ct-p13", "sb2", "sb5", "abp 501", "gp2017",
        "remsima", "inflectra", "renflexis", "avsola", "ixifi",
        "hadlima", "hyrimoz", "cyltezo", "amjevita", "idacio",
        "similar biologic", "proposed biosimilar",
    ]
    return any(p in corpus for p in biosimilar_patterns)


def classify_mechanism(interventions, brief_title="", official_title=""):
    """
    Classify a trial's mechanism of action from its interventions.

    Uses config-driven taxonomy if configure() has been called with a
    disease config. Falls back to generic intervention-type classification
    when no taxonomy is loaded.

    Parameters
    ----------
    interventions : list of dict
        Each dict has 'type', 'name', 'description'.
    brief_title : str
        Trial brief title (fallback context).
    official_title : str
        Trial official title (fallback context).

    Returns
    -------
    tuple of (str, list of str)
        (mechanism_label, list of matched drug names)
    """
    # Build search corpus from all intervention text + titles
    text_parts = []
    drug_names = []

    for intv in interventions:
        name = intv.get("name", "")
        desc = intv.get("description", "")
        itype = intv.get("type", "")
        text_parts.append(name)
        text_parts.append(desc)
        if itype in ("DRUG", "BIOLOGICAL") and name:
            drug_names.append(name)

    text_parts.append(brief_title)
    text_parts.append(official_title)
    corpus = " ".join(text_parts).lower()

    # Check each mechanism in priority order (config-driven taxonomy)
    for mechanism, patterns in _mechanism_patterns:
        for pattern, is_regex in patterns:
            if is_regex:
                if re.search(pattern, corpus):
                    return mechanism, drug_names
            else:
                if pattern.lower() in corpus:
                    return mechanism, drug_names

    # Fallback classification based on intervention type
    intervention_types = {intv.get("type", "") for intv in interventions}

    if "BIOLOGICAL" in intervention_types:
        return "Other Biologic", drug_names
    elif "DRUG" in intervention_types:
        return "Small Molecule (Other)", drug_names
    elif intervention_types & {"DEVICE", "BEHAVIORAL", "DIETARY_SUPPLEMENT",
                               "PROCEDURE", "RADIATION", "DIAGNOSTIC_TEST",
                               "GENETIC", "COMBINATION_PRODUCT", "OTHER"}:
        return "Non-pharmacological", drug_names

    return "Unclassified", drug_names


def _normalize_phase(phases_list):
    """
    Normalize API phase strings to display labels.

    Handles combined phases like ["PHASE2", "PHASE3"] -> "Phase 2/3".
    """
    if not phases_list:
        return "Not Applicable"

    normalized = []
    for p in phases_list:
        mapped = PHASE_MAP.get(p, p)
        normalized.append(mapped)

    if len(normalized) == 1:
        return normalized[0]

    # Combined phases: extract numbers and join
    nums = []
    for n in normalized:
        match = re.search(r"(\d)", n)
        if match:
            nums.append(match.group(1))

    if len(nums) >= 2:
        return f"Phase {nums[0]}/{nums[-1]}"

    return " / ".join(normalized)


def classify_all(raw_trials, config=None):
    """
    Classify mechanism for all trials.

    Adds fields: mechanism, drug_names, drug_names_normalized,
    phase_normalized, is_industry, is_biosimilar.

    Parameters
    ----------
    raw_trials : list of dict
        Raw trial records from query_trials().
    config : dict or None
        Disease config for taxonomy. If provided, calls configure().

    Returns
    -------
    list of dict
        Trials with added classification fields.

    Verification
    ------------
    Prints "✓ Classified {N} trials by mechanism"
    """
    if config is not None or not _configured:
        configure(config)

    print("Classifying trials by mechanism of action...")

    mechanism_counts = {}

    for trial in raw_trials:
        mechanism, drug_names = classify_mechanism(
            trial.get("interventions", []),
            trial.get("brief_title", ""),
            trial.get("official_title", ""),
        )
        trial["mechanism"] = mechanism
        trial["drug_names"] = drug_names
        trial["drug_names_normalized"] = [_normalize_drug_name(d) for d in drug_names]
        trial["phase_normalized"] = _normalize_phase(trial.get("phases", []))
        trial["is_industry"] = trial.get("sponsor_class", "") == "INDUSTRY"
        trial["is_biosimilar"] = _is_biosimilar(
            trial.get("interventions", []),
            trial.get("brief_title", ""),
            trial.get("official_title", ""),
        )

        mechanism_counts[mechanism] = mechanism_counts.get(mechanism, 0) + 1

    # Summary
    print(f"\n  Mechanism distribution:")
    for mech, count in sorted(mechanism_counts.items(), key=lambda x: -x[1]):
        print(f"    {mech}: {count}")

    print(f"\n✓ Classified {len(raw_trials)} trials by mechanism")

    return raw_trials


if __name__ == "__main__":
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        from disease_config import load_disease_config
    except ImportError:
        from scripts.disease_config import load_disease_config

    # Load IBD config for testing
    config = load_disease_config("ibd")
    configure(config)

    # Test classification on known drugs
    test_cases = [
        (
            [{"type": "DRUG", "name": "Vedolizumab", "description": "anti-integrin antibody"}],
            "Anti-Integrin",
        ),
        (
            [{"type": "BIOLOGICAL", "name": "Risankizumab", "description": "anti-IL-23 p19 antibody"}],
            "Anti-IL-23 (p19)",
        ),
        (
            [{"type": "DRUG", "name": "TEV-48574", "description": "anti-TL1A antibody"}],
            "Anti-TL1A",
        ),
        (
            [{"type": "DRUG", "name": "Tofacitinib", "description": "JAK inhibitor"}],
            "JAK Inhibitor",
        ),
        (
            [{"type": "DRUG", "name": "Infliximab", "description": "anti-TNF monoclonal antibody"}],
            "Anti-TNF",
        ),
        (
            [{"type": "DRUG", "name": "Ozanimod", "description": "S1P receptor modulator"}],
            "S1P Modulator",
        ),
        (
            [{"type": "BIOLOGICAL", "name": "Duvakitug", "description": "formerly PRA023"}],
            "Anti-TL1A",
        ),
        # Biosimilar detection test
        (
            [{"type": "BIOLOGICAL", "name": "CT-P13", "description": "biosimilar infliximab"}],
            "Anti-TNF",
        ),
        # New mechanism categories
        (
            [{"type": "DRUG", "name": "Apremilast", "description": "PDE4 inhibitor"}],
            "PDE4 Inhibitor",
        ),
        (
            [{"type": "BIOLOGICAL", "name": "Spesolimab", "description": "anti-IL-36 receptor antibody"}],
            "Anti-IL-36",
        ),
        (
            [{"type": "DRUG", "name": "Semaglutide", "description": "GLP-1 receptor agonist"}],
            "GLP-1 / Metabolic",
        ),
        # Brand name resolution
        (
            [{"type": "DRUG", "name": "Entyvio", "description": "vedolizumab IV"}],
            "Anti-Integrin",
        ),
        (
            [{"type": "DRUG", "name": "Remicade", "description": "infliximab"}],
            "Anti-TNF",
        ),
    ]

    print("Testing mechanism classification:")
    all_passed = True
    for interventions, expected in test_cases:
        result, _ = classify_mechanism(interventions)
        status = "✓" if result == expected else "✗"
        if result != expected:
            all_passed = False
        drug = interventions[0]["name"]
        print(f"  {status} {drug}: {result} (expected: {expected})")

    # Test drug name normalization
    print("\nTesting drug name normalization:")
    norm_cases = [
        ("Risankizumab-rzaa", "Risankizumab"),
        ("CT-P13", "CT-P13 (biosimilar infliximab)"),
        ("PRA-023", "Duvakitug"),
        ("MK-7240", "Tulisokibart"),
        ("tofacitinib citrate", "Tofacitinib"),
        ("SomeUnknownDrug", "SomeUnknownDrug"),
    ]
    for raw, expected_norm in norm_cases:
        result_norm = _normalize_drug_name(raw)
        status = "✓" if result_norm == expected_norm else "✗"
        if result_norm != expected_norm:
            all_passed = False
        print(f"  {status} '{raw}' -> '{result_norm}' (expected: '{expected_norm}')")

    # Test biosimilar detection
    print("\nTesting biosimilar detection:")
    bio_cases = [
        (
            [{"type": "BIOLOGICAL", "name": "CT-P13", "description": "biosimilar infliximab"}],
            "", "", True,
        ),
        (
            [{"type": "BIOLOGICAL", "name": "Risankizumab", "description": "anti-IL-23 antibody"}],
            "", "", False,
        ),
        (
            [{"type": "BIOLOGICAL", "name": "Infliximab", "description": "Remsima SC"}],
            "", "", True,
        ),
    ]
    for interventions, bt, ot, expected_bio in bio_cases:
        result_bio = _is_biosimilar(interventions, bt, ot)
        status = "✓" if result_bio == expected_bio else "✗"
        if result_bio != expected_bio:
            all_passed = False
        drug = interventions[0]["name"]
        print(f"  {status} {drug}: is_biosimilar={result_bio} (expected: {expected_bio})")

    if all_passed:
        print("\n✓ All classification tests passed!")
    else:
        print("\n✗ Some classification tests failed!")

