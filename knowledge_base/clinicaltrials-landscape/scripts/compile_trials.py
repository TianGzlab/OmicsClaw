"""
Compile, deduplicate, and structure clinical trial data (Step 2b).

Produces a clean DataFrame with normalized phases, mechanisms,
sponsor names, enrollment cleaning, and enriched fields from
the API (geography, study design, arms, endpoints, eligibility).
Deduplicates by NCT ID.
"""

import os
import re
import pandas as pd
import numpy as np


# Sponsor normalization: maps lowercase substrings to canonical names
SPONSOR_NORMALIZATION = {
    "takeda": "Takeda",
    "takeda pharmaceutical": "Takeda",
    "takeda development center": "Takeda",
    "millennium pharmaceuticals": "Takeda",
    "abbvie": "AbbVie",
    "johnson & johnson": "J&J / Janssen",
    "janssen": "J&J / Janssen",
    "janssen research": "J&J / Janssen",
    "janssen-cilag": "J&J / Janssen",
    "janssen biotech": "J&J / Janssen",
    "eli lilly": "Eli Lilly",
    "lilly": "Eli Lilly",
    "pfizer": "Pfizer",
    "bristol-myers squibb": "Bristol-Myers Squibb",
    "bristol myers squibb": "Bristol-Myers Squibb",
    "gilead": "Gilead Sciences",
    "gilead sciences": "Gilead Sciences",
    "roche": "Roche / Genentech",
    "genentech": "Roche / Genentech",
    "astrazeneca": "AstraZeneca",
    "novartis": "Novartis",
    "amgen": "Amgen",
    "merck sharp": "Merck / MSD",
    "merck & co": "Merck / MSD",
    "msd": "Merck / MSD",
    "sanofi": "Sanofi",
    "regeneron": "Regeneron",
    "boehringer ingelheim": "Boehringer Ingelheim",
    "arena pharmaceuticals": "Arena / Pfizer",
    "celgene": "Bristol-Myers Squibb",
    "galapagos": "Galapagos",
    "prometheus biosciences": "Merck / MSD",
    "teva": "Teva",
    "teva branded": "Teva",
    "teva pharmaceutical": "Teva",
}

# Phase numeric ordering
PHASE_NUMERIC = {
    "Phase 1": 1,
    "Phase 1/2": 1.5,
    "Phase 2": 2,
    "Phase 2/3": 2.5,
    "Phase 3": 3,
    "Phase 3/4": 3.5,
    "Phase 4": 4,
    "Not Applicable": 0,
}

# Region mapping for geographic analysis
COUNTRY_TO_REGION = {
    # North America
    "United States": "North America", "Canada": "North America", "Mexico": "North America",
    # Western Europe
    "United Kingdom": "Western Europe", "Germany": "Western Europe", "France": "Western Europe",
    "Italy": "Western Europe", "Spain": "Western Europe", "Netherlands": "Western Europe",
    "Belgium": "Western Europe", "Switzerland": "Western Europe", "Austria": "Western Europe",
    "Ireland": "Western Europe", "Sweden": "Western Europe", "Denmark": "Western Europe",
    "Norway": "Western Europe", "Finland": "Western Europe", "Portugal": "Western Europe",
    "Greece": "Western Europe", "Luxembourg": "Western Europe",
    # Eastern Europe
    "Poland": "Eastern Europe", "Czech Republic": "Eastern Europe", "Czechia": "Eastern Europe",
    "Hungary": "Eastern Europe", "Romania": "Eastern Europe", "Bulgaria": "Eastern Europe",
    "Slovakia": "Eastern Europe", "Croatia": "Eastern Europe", "Serbia": "Eastern Europe",
    "Slovenia": "Eastern Europe", "Estonia": "Eastern Europe", "Latvia": "Eastern Europe",
    "Lithuania": "Eastern Europe", "Ukraine": "Eastern Europe", "Russia": "Eastern Europe",
    "Russian Federation": "Eastern Europe", "Georgia": "Eastern Europe", "Moldova": "Eastern Europe",
    "Bosnia and Herzegovina": "Eastern Europe", "North Macedonia": "Eastern Europe",
    # Asia-Pacific
    "Japan": "Asia-Pacific", "China": "Asia-Pacific", "South Korea": "Asia-Pacific",
    "Korea, Republic of": "Asia-Pacific", "Taiwan": "Asia-Pacific", "India": "Asia-Pacific",
    "Australia": "Asia-Pacific", "New Zealand": "Asia-Pacific", "Singapore": "Asia-Pacific",
    "Malaysia": "Asia-Pacific", "Thailand": "Asia-Pacific", "Philippines": "Asia-Pacific",
    "Vietnam": "Asia-Pacific", "Indonesia": "Asia-Pacific", "Hong Kong": "Asia-Pacific",
    # Latin America
    "Brazil": "Latin America", "Argentina": "Latin America", "Chile": "Latin America",
    "Colombia": "Latin America", "Peru": "Latin America",
    # Middle East & Africa
    "Israel": "Middle East & Africa", "Turkey": "Middle East & Africa", "Türkiye": "Middle East & Africa",
    "South Africa": "Middle East & Africa", "Egypt": "Middle East & Africa",
    "Saudi Arabia": "Middle East & Africa", "Lebanon": "Middle East & Africa",
    "United Arab Emirates": "Middle East & Africa",
}


def _normalize_sponsor(sponsor_name):
    """Normalize sponsor name to canonical form."""
    if not sponsor_name:
        return "Unknown"
    lower = sponsor_name.lower().strip()
    for pattern, canonical in SPONSOR_NORMALIZATION.items():
        if pattern in lower:
            return canonical
    return sponsor_name.strip()


def _get_region(country):
    """Map country to region."""
    return COUNTRY_TO_REGION.get(country, "Other")


def _parse_age_years(age_str):
    """Parse age string like '18 Years' to numeric years."""
    if not age_str:
        return None
    match = re.search(r"(\d+)\s*(year|month|week|day)", str(age_str).lower())
    if not match:
        return None
    value = int(match.group(1))
    unit = match.group(2)
    if unit == "year":
        return value
    elif unit == "month":
        return value / 12
    elif unit == "week":
        return value / 52
    elif unit == "day":
        return value / 365
    return None


def _classify_study_design(allocation, masking, intervention_model, study_type):
    """Derive study design category from design fields."""
    if study_type == "OBSERVATIONAL":
        return "Observational"

    alloc_lower = str(allocation).lower() if allocation else ""
    mask_lower = str(masking).lower() if masking else ""

    if "randomized" in alloc_lower:
        if "double" in mask_lower or "triple" in mask_lower or "quadruple" in mask_lower:
            return "RCT Double-Blind"
        elif "single" in mask_lower:
            return "RCT Single-Blind"
        elif "none" in mask_lower or "open" in mask_lower:
            return "RCT Open-Label"
        else:
            return "RCT (Other)"
    elif "non-randomized" in alloc_lower:
        return "Non-Randomized"

    # Single arm / no randomization info
    model_lower = str(intervention_model).lower() if intervention_model else ""
    if "single" in model_lower:
        return "Single-Arm"

    return "Other Design"


def _detect_arm_features(arms):
    """Detect arm features from trial arms list."""
    if not arms:
        return False, False, False, 0

    has_placebo = False
    has_active_comparator = False
    n_experimental = 0

    for arm in arms:
        arm_type = str(arm.get("type", "")).upper()
        arm_label = str(arm.get("label", "")).lower()
        arm_desc = str(arm.get("description", "")).lower()

        if arm_type == "PLACEBO_COMPARATOR" or "placebo" in arm_label or "placebo" in arm_desc:
            has_placebo = True
        if arm_type == "ACTIVE_COMPARATOR":
            has_active_comparator = True
        if arm_type == "EXPERIMENTAL":
            n_experimental += 1

    is_head_to_head = has_active_comparator and n_experimental >= 1
    n_arms = len(arms)

    return has_placebo, has_active_comparator, is_head_to_head, n_arms


def _clean_enrollment(df):
    """
    Clean enrollment data: flag outliers and create clean enrollment column.

    Registries and observational mega-studies with >50,000 enrollment
    pollute aggregate statistics. This function:
    - Flags pharmacological trials (INTERVENTIONAL + classified mechanism)
    - Caps enrollment at 50,000 for aggregate analysis
    - Preserves raw enrollment for individual trial listings
    """
    # Identify pharmacological trials
    non_pharm_mechanisms = {"Non-pharmacological", "Unclassified"}
    df["is_pharmacological"] = (
        (df["study_type"] == "INTERVENTIONAL") &
        (~df["mechanism"].isin(non_pharm_mechanisms))
    )

    # Create clean enrollment (cap at 50K for aggregate stats)
    df["enrollment_clean"] = df["enrollment"].copy()
    outlier_mask = df["enrollment"] > 50000
    df.loc[outlier_mask, "enrollment_clean"] = np.nan
    df["enrollment_outlier"] = outlier_mask

    n_outliers = outlier_mask.sum()
    if n_outliers > 0:
        print(f"   Flagged {n_outliers} enrollment outliers (>50,000)")

    return df


def compile_trials(classified_trials, output_dir="landscape_results"):
    """
    Convert classified trial dicts into structured DataFrame.

    Parameters
    ----------
    classified_trials : list of dict
        Trials with mechanism classification from classify_all().
    output_dir : str
        Output directory (created if needed).

    Returns
    -------
    pd.DataFrame
        Comprehensive DataFrame with original fields, normalized fields,
        clean enrollment, study design, geographic, arm, endpoint,
        eligibility, and regulatory columns.

    Verification
    ------------
    Prints "✓ Trial data compiled successfully!"
    """
    os.makedirs(output_dir, exist_ok=True)

    print("\n" + "=" * 70)
    print("COMPILING TRIAL DATA")
    print("=" * 70 + "\n")

    n_raw = len(classified_trials)
    print(f"Raw entries: {n_raw}")

    # Convert to DataFrame
    records = []
    for trial in classified_trials:
        # Flatten conditions list to string
        conditions = trial.get("conditions", [])
        conditions_str = "; ".join(conditions) if isinstance(conditions, list) else str(conditions)

        # Flatten drug names (raw)
        drug_names = trial.get("drug_names", [])
        drug_names_str = "; ".join(drug_names) if isinstance(drug_names, list) else str(drug_names)

        # Flatten normalized drug names (Phase 1B)
        drug_names_normalized = trial.get("drug_names_normalized", drug_names)
        drug_names_normalized_str = "; ".join(
            drug_names_normalized
        ) if isinstance(drug_names_normalized, list) else str(drug_names_normalized)

        # Extract start year
        start_date = trial.get("start_date", "")
        start_year = None
        if start_date:
            match = re.search(r"(\d{4})", str(start_date))
            if match:
                start_year = int(match.group(1))

        # --- New fields from Phase 2A ---

        # Countries / geographic
        countries = trial.get("countries", [])
        countries_str = "; ".join(sorted(countries)) if isinstance(countries, list) else ""
        n_countries = len(countries) if isinstance(countries, list) else 0
        regions = list(set(_get_region(c) for c in countries)) if countries else []
        regions_str = "; ".join(sorted(regions)) if regions else ""

        # Study design
        allocation = trial.get("allocation", "")
        masking = trial.get("masking", "")
        intervention_model = trial.get("intervention_model", "")
        study_design_category = _classify_study_design(
            allocation, masking, intervention_model, trial.get("study_type", "")
        )

        # Arms
        arms = trial.get("arms", [])
        has_placebo, has_active_comparator, is_head_to_head, n_arms = _detect_arm_features(arms)

        # Detect combination therapy: 2+ active drug interventions in same trial
        interventions = trial.get("interventions", [])
        active_drug_count = sum(
            1 for intv in interventions
            if intv.get("type", "") in ("DRUG", "BIOLOGICAL") and intv.get("name", "")
        )
        is_combination = active_drug_count >= 2

        # Primary outcomes
        primary_outcomes = trial.get("primary_outcomes", [])
        primary_endpoint = primary_outcomes[0].get("measure", "") if primary_outcomes else ""
        endpoint_timeframe = primary_outcomes[0].get("timeFrame", "") if primary_outcomes else ""

        # Eligibility / patient population
        min_age_str = trial.get("min_age", "")
        max_age_str = trial.get("max_age", "")
        min_age_years = _parse_age_years(min_age_str)
        max_age_years = _parse_age_years(max_age_str)
        sex = trial.get("sex", "")
        is_pediatric = (min_age_years is not None and min_age_years < 18) or (
            max_age_years is not None and max_age_years < 18
        )

        # Regulatory / oversight
        is_fda_regulated = trial.get("is_fda_regulated_drug", None)
        has_dmc = trial.get("has_dmc", None)

        # Collaborators
        collaborators = trial.get("collaborators", [])
        collaborators_str = "; ".join(
            c.get("name", "") for c in collaborators
        ) if isinstance(collaborators, list) else ""

        # Biosimilar flag (Phase 4B, computed in classifier)
        is_biosimilar = trial.get("is_biosimilar", False)

        records.append({
            # Core fields (original)
            "nct_id": trial.get("nct_id", ""),
            "brief_title": trial.get("brief_title", ""),
            "official_title": trial.get("official_title", ""),
            "lead_sponsor": trial.get("lead_sponsor", ""),
            "sponsor_normalized": _normalize_sponsor(trial.get("lead_sponsor", "")),
            "sponsor_class": trial.get("sponsor_class", ""),
            "is_industry": trial.get("is_industry", False),
            "mechanism": trial.get("mechanism", "Unclassified"),
            "drug_names_str": drug_names_str,
            "drug_names_normalized_str": drug_names_normalized_str,
            "phase_normalized": trial.get("phase_normalized", "Not Applicable"),
            "overall_status": trial.get("overall_status", ""),
            "conditions_str": conditions_str,
            "enrollment": trial.get("enrollment"),
            "start_date": start_date,
            "start_year": start_year,
            "completion_date": trial.get("completion_date", ""),
            "study_type": trial.get("study_type", ""),
            # Geographic (Phase 2A/2B)
            "countries_str": countries_str,
            "n_countries": n_countries,
            "regions_str": regions_str,
            # Study design (Phase 2A/2B)
            "allocation": allocation,
            "masking": masking,
            "intervention_model": intervention_model,
            "study_design_category": study_design_category,
            # Arms (Phase 2A/2B)
            "has_placebo_arm": has_placebo,
            "has_active_comparator": has_active_comparator,
            "is_head_to_head": is_head_to_head,
            "n_arms": n_arms,
            "is_combination": is_combination,
            # Endpoints (Phase 2A/2B)
            "primary_endpoint": primary_endpoint,
            "endpoint_timeframe": endpoint_timeframe,
            # Eligibility (Phase 2A/2B)
            "min_age": min_age_str,
            "max_age": max_age_str,
            "min_age_years": min_age_years,
            "max_age_years": max_age_years,
            "sex": sex,
            "is_pediatric": is_pediatric,
            # Regulatory (Phase 2A/2B)
            "is_fda_regulated_drug": is_fda_regulated,
            "has_dmc": has_dmc,
            # Collaborators
            "collaborators_str": collaborators_str,
            # Biosimilar flag (Phase 4B)
            "is_biosimilar": is_biosimilar,
        })

    df = pd.DataFrame(records)

    # Deduplicate by NCT ID
    print("\n1. Deduplicating by NCT ID...")
    before_dedup = len(df)
    df = df.drop_duplicates(subset="nct_id", keep="first")
    n_removed = before_dedup - len(df)
    print(f"   Removed {n_removed} duplicates ({before_dedup} -> {len(df)} entries)")

    # Add phase_numeric for sorting
    print("\n2. Assigning phase ordering...")
    df["phase_numeric"] = df["phase_normalized"].map(PHASE_NUMERIC).fillna(0)

    # Phase 1A: Clean enrollment data
    print("\n3. Cleaning enrollment data...")
    df = _clean_enrollment(df)

    # Sort by phase descending (Phase 3 first), then by sponsor
    print("\n4. Sorting results...")
    df = df.sort_values(
        ["phase_numeric", "sponsor_normalized", "brief_title"],
        ascending=[False, True, True],
    )
    df = df.reset_index(drop=True)

    # Summary
    print(f"\n--- Compilation Summary ---")
    print(f"   Total trials: {len(df)}")
    print(f"   Unique sponsors: {df['sponsor_normalized'].nunique()}")
    print(f"   Industry-sponsored: {df['is_industry'].sum()}")
    print(f"   Academic/Other: {(~df['is_industry']).sum()}")
    print(f"\n   Trials by phase:")
    for phase, count in df["phase_normalized"].value_counts().items():
        print(f"     {phase}: {count}")

    # New field summaries
    if "n_countries" in df.columns and df["n_countries"].sum() > 0:
        n_with_geo = (df["n_countries"] > 0).sum()
        print(f"\n   Geographic data: {n_with_geo} trials with location data")
        top_countries = df["countries_str"].str.split("; ").explode().value_counts().head(5)
        if not top_countries.empty:
            print(f"   Top countries: {', '.join(f'{c} ({n})' for c, n in top_countries.items() if c)}")

    if "study_design_category" in df.columns:
        design_counts = df["study_design_category"].value_counts()
        print(f"\n   Study design:")
        for design, count in design_counts.head(5).items():
            print(f"     {design}: {count}")

    if "is_combination" in df.columns:
        n_combo = df["is_combination"].sum()
        print(f"\n   Combination therapy trials: {n_combo}")

    if "is_pediatric" in df.columns:
        n_ped = df["is_pediatric"].sum()
        print(f"   Pediatric trials: {n_ped}")

    if "is_biosimilar" in df.columns:
        n_bio = df["is_biosimilar"].sum()
        print(f"   Biosimilar trials: {n_bio}")

    print(f"\n✓ Trial data compiled successfully!")
    print("=" * 70 + "\n")

    return df


if __name__ == "__main__":
    # Test with mock data including new fields
    mock_trials = [
        {
            "nct_id": "NCT00001",
            "brief_title": "Study of Vedolizumab in UC",
            "official_title": "A Phase 3 Study",
            "lead_sponsor": "Takeda Pharmaceutical Company Limited",
            "sponsor_class": "INDUSTRY",
            "conditions": ["Ulcerative Colitis"],
            "interventions": [{"type": "BIOLOGICAL", "name": "Vedolizumab", "description": ""}],
            "enrollment": 500,
            "start_date": "2022-01-15",
            "completion_date": "2025-12-01",
            "study_type": "INTERVENTIONAL",
            "mechanism": "Anti-Integrin",
            "drug_names": ["Vedolizumab"],
            "drug_names_normalized": ["Vedolizumab"],
            "phase_normalized": "Phase 3",
            "is_industry": True,
            "is_biosimilar": False,
            "phases": ["PHASE3"],
            "overall_status": "RECRUITING",
            "countries": ["United States", "Germany", "Japan"],
            "arms": [
                {"label": "Vedolizumab", "type": "EXPERIMENTAL", "description": ""},
                {"label": "Placebo", "type": "PLACEBO_COMPARATOR", "description": ""},
            ],
            "collaborators": [{"name": "Some CRO", "class": "OTHER"}],
            "allocation": "RANDOMIZED",
            "masking": "DOUBLE",
            "intervention_model": "PARALLEL",
            "primary_outcomes": [{"measure": "Clinical remission at Week 52", "timeFrame": "52 weeks"}],
            "min_age": "18 Years",
            "max_age": "80 Years",
            "sex": "ALL",
            "is_fda_regulated_drug": True,
            "has_dmc": True,
            "brief_summary": "A study of vedolizumab in ulcerative colitis.",
        },
        {
            "nct_id": "NCT00002",
            "brief_title": "Study of Risankizumab in CD",
            "official_title": "A Phase 3 Study",
            "lead_sponsor": "AbbVie Inc.",
            "sponsor_class": "INDUSTRY",
            "conditions": ["Crohn's Disease"],
            "interventions": [{"type": "BIOLOGICAL", "name": "Risankizumab", "description": ""}],
            "enrollment": 400,
            "start_date": "2023-03-01",
            "completion_date": "2026-06-01",
            "study_type": "INTERVENTIONAL",
            "mechanism": "Anti-IL-23 (p19)",
            "drug_names": ["Risankizumab"],
            "drug_names_normalized": ["Risankizumab"],
            "phase_normalized": "Phase 3",
            "is_industry": True,
            "is_biosimilar": False,
            "phases": ["PHASE3"],
            "overall_status": "RECRUITING",
            "countries": ["United States", "Canada"],
            "arms": [
                {"label": "Risankizumab", "type": "EXPERIMENTAL", "description": ""},
                {"label": "Placebo", "type": "PLACEBO_COMPARATOR", "description": ""},
            ],
            "collaborators": [],
            "allocation": "RANDOMIZED",
            "masking": "DOUBLE",
            "intervention_model": "PARALLEL",
            "primary_outcomes": [{"measure": "CDAI remission at Week 12", "timeFrame": "12 weeks"}],
            "min_age": "16 Years",
            "max_age": "75 Years",
            "sex": "ALL",
            "is_fda_regulated_drug": True,
            "has_dmc": True,
            "brief_summary": "A study of risankizumab in Crohn's disease.",
        },
        {
            "nct_id": "NCT00003",
            "brief_title": "IBD Registry - National Outcomes",
            "official_title": "A Large Registry Study",
            "lead_sponsor": "National IBD Foundation",
            "sponsor_class": "OTHER",
            "conditions": ["Inflammatory Bowel Disease"],
            "interventions": [{"type": "OTHER", "name": "Registry", "description": ""}],
            "enrollment": 99000000,
            "start_date": "2020-01-01",
            "completion_date": "2030-12-31",
            "study_type": "OBSERVATIONAL",
            "mechanism": "Non-pharmacological",
            "drug_names": [],
            "drug_names_normalized": [],
            "phase_normalized": "Not Applicable",
            "is_industry": False,
            "is_biosimilar": False,
            "phases": [],
            "overall_status": "RECRUITING",
            "countries": [],
            "arms": [],
            "collaborators": [],
            "allocation": "",
            "masking": "",
            "intervention_model": "",
            "primary_outcomes": [],
            "min_age": "",
            "max_age": "",
            "sex": "ALL",
            "is_fda_regulated_drug": False,
            "has_dmc": False,
            "brief_summary": "National IBD outcomes registry.",
        },
    ]

    result = compile_trials(mock_trials, output_dir="/tmp/test_compile")
    print(f"\nResult shape: {result.shape}")
    print(f"Columns: {list(result.columns)}")
    print(f"\nCore fields:")
    print(result[["nct_id", "sponsor_normalized", "mechanism", "phase_normalized"]].to_string())
    print(f"\nEnrollment cleaning:")
    print(result[["nct_id", "enrollment", "enrollment_clean", "enrollment_outlier"]].to_string())
    print(f"\nNew fields:")
    print(result[["nct_id", "n_countries", "study_design_category", "has_placebo_arm", "is_pediatric"]].to_string())

