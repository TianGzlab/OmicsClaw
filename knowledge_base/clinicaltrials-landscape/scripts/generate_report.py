"""
Generate comprehensive markdown landscape report for clinical trials.

Config-driven: loads disease-specific settings (mechanism descriptions,
highlight sections, indication categories) from a YAML config via
disease_config.py. Falls back to generic behavior when no config is provided.

Creates a detailed competitive intelligence report with:
- Executive summary with strategic highlights
- Mechanism deep-dives with drug pipeline tables
- Geographic landscape analysis
- Study design breakdown
- Phase transition funnel
- Combination therapy landscape
- Late-stage pipeline analysis (Phase 3 trials)
- Phase 3 endpoint comparison
- Upcoming readouts / expected completion dates
- Company competitive positioning and portfolio analysis
- Indication breakdown (config-driven or data-driven)
- Patient population analysis
- Trial arms & comparator analysis
- Collaborator network
- Regulatory signals
- Enrollment and investment signals (clean)
- Biosimilar threat assessment
- Whitespace / unmet needs analysis
"""

import re
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

try:
    from disease_config import (
        get_mechanism_descriptions, get_disease_name, get_disease_short,
        get_highlight_mechanisms, get_highlight_sponsors,
        get_executive_highlights, get_indication_categories,
    )
except ImportError:
    from scripts.disease_config import (
        get_mechanism_descriptions, get_disease_name, get_disease_short,
        get_highlight_mechanisms, get_highlight_sponsors,
        get_executive_highlights, get_indication_categories,
    )


# ============================================================
# SAFE COLUMN ACCESS HELPER
# ============================================================

def _safe_col(df, col, default=None):
    """
    Safely access a DataFrame column, returning a Series of `default` if missing.

    This allows backward-compatibility when generating a report from older compiled
    DataFrames that may not contain Phase-2B columns (geographic, study-design, etc.).

    Parameters
    ----------
    df : pd.DataFrame
    col : str
        Column name to look up.
    default : scalar or None
        Value to fill if column is absent.  None -> pd.NA.

    Returns
    -------
    pd.Series
    """
    if col in df.columns:
        return df[col]
    return pd.Series(default, index=df.index, name=col)


def generate_report(trials_df, parameters=None, output_file="landscape_report.md", config=None):
    """
    Generate comprehensive markdown landscape report.

    Parameters
    ----------
    trials_df : pd.DataFrame
        Compiled trials from compile_trials().
    parameters : dict, optional
        Query parameters and metadata.
    output_file : str
        Output file path.
    config : dict, optional
        Disease configuration loaded via load_disease_config().
        When provided, disease-specific names, descriptions, highlight
        sections, and indication categories are drawn from config.
        When None, generic/data-driven fallbacks are used.

    Returns
    -------
    str
        The generated report as a string.
    """
    if parameters is None:
        parameters = {}

    # ------------------------------------------------------------------
    # Load config-driven data (all functions handle config=None gracefully)
    # ------------------------------------------------------------------
    disease_name = get_disease_name(config, default="Clinical Trial")
    disease_short = get_disease_short(config, default="")
    mechanism_descriptions = get_mechanism_descriptions(config)
    highlight_mechanisms = get_highlight_mechanisms(config)
    highlight_sponsors = get_highlight_sponsors(config)
    exec_highlights = get_executive_highlights(config)
    indication_cats = get_indication_categories(config)

    sections = []
    now = datetime.now()

    # ==========================================
    # TITLE
    # ==========================================
    sections.append(f"# {disease_name} Clinical Trial Landscape Report\n")
    sections.append(f"*Competitive Intelligence Report \u2014 Generated: {now.strftime('%Y-%m-%d %H:%M')}*\n")
    sections.append("---\n")

    # ==========================================
    # TABLE OF CONTENTS (dynamic based on config highlight sections)
    # ==========================================
    sections.append("## Table of Contents\n")

    # Fixed sections 1-11
    toc_entries = [
        "Executive Summary",
        "Mechanism \u00d7 Phase Overview",
        "Mechanism Deep Dives",
        "Geographic Landscape",
        "Study Design Analysis",
        "Phase Transition Funnel",
        "Late-Stage Pipeline (Phase 3)",
        "Phase 3 Endpoint Comparison",
        "Combination Therapy Landscape",
        "Upcoming Readouts",
        "Drug-Level Pipeline",
    ]
    # Dynamic highlight sections from config (mechanisms then sponsors)
    for hl in highlight_mechanisms:
        toc_entries.append(hl["section_title"])
    for hl in highlight_sponsors:
        sponsor_title = hl["section_title"]
        if disease_short and disease_short not in sponsor_title:
            toc_entries.append(f"{sponsor_title}")
        else:
            toc_entries.append(sponsor_title)
    # Remaining fixed sections
    toc_entries.extend([
        "Sponsor Competitive Landscape",
        "Indication Breakdown",
        "Patient Population Analysis",
        "Trial Arms & Comparator Analysis",
        "Enrollment & Investment Signals",
        "Biosimilar Landscape",
        "Whitespace & Unmet Needs",
        "Collaborator Network",
        "Regulatory Signals",
        "Data Notes",
    ])
    for i, title in enumerate(toc_entries, 1):
        anchor = re.sub(r'[^a-z0-9\s-]', '', title.lower()).strip().replace(' ', '-')
        anchor = re.sub(r'-+', '-', anchor)
        sections.append(f"{i}. [{title}](#{anchor})")
    sections.append("")

    # ==========================================
    # 1. EXECUTIVE SUMMARY
    # ==========================================
    sections.append("---\n")
    sections.append("## Executive Summary\n")

    n_total = len(trials_df)
    n_mechanisms = trials_df["mechanism"].nunique()
    n_sponsors = trials_df["sponsor_normalized"].nunique()
    n_industry = int(trials_df["is_industry"].sum())
    n_academic = n_total - n_industry

    # Pharmacological mechanism counts (exclude non-pharma and unclassified)
    non_pharma = ["Non-pharmacological", "Unclassified", "Other Biologic", "Small Molecule (Other)"]
    pharma_df = trials_df[~trials_df["mechanism"].isin(non_pharma)]
    n_pharma_mechanisms = pharma_df["mechanism"].nunique()

    top_mech = trials_df["mechanism"].value_counts()
    pharma_mechs = top_mech[~top_mech.index.isin(non_pharma)]
    top_sponsor = trials_df["sponsor_normalized"].value_counts()

    # Phase counts
    phase3_count = len(trials_df[trials_df["phase_normalized"] == "Phase 3"])
    phase2_count = len(trials_df[trials_df["phase_normalized"].isin(["Phase 2", "Phase 2/3"])])
    phase1_count = len(trials_df[trials_df["phase_normalized"].isin(["Phase 1", "Phase 1/2"])])

    # Recruiting stats
    n_recruiting = len(trials_df[trials_df["overall_status"] == "RECRUITING"])
    n_not_yet = len(trials_df[trials_df["overall_status"] == "NOT_YET_RECRUITING"])

    sections.append("### Key Figures\n")
    sections.append(f"| Metric | Value |")
    sections.append(f"|--------|-------|")
    sections.append(f"| Total active clinical trials | **{n_total}** |")
    sections.append(f"| Pharmacological mechanism classes | **{n_pharma_mechanisms}** |")
    sections.append(f"| Unique sponsors | **{n_sponsors}** |")
    sections.append(f"| Industry-sponsored | **{n_industry}** ({n_industry/n_total*100:.0f}%) |")
    sections.append(f"| Academic / Other | **{n_academic}** ({n_academic/n_total*100:.0f}%) |")
    sections.append(f"| Phase 3 trials | **{phase3_count}** |")
    sections.append(f"| Phase 2 / 2-3 trials | **{phase2_count}** |")
    sections.append(f"| Phase 1 / 1-2 trials | **{phase1_count}** |")
    sections.append(f"| Currently recruiting | **{n_recruiting}** |")
    sections.append(f"| Not yet recruiting | **{n_not_yet}** |")
    sections.append("")

    sections.append("### Strategic Highlights\n")
    if len(pharma_mechs) > 0:
        sections.append(f"- **Most active mechanism class:** {pharma_mechs.index[0]} ({pharma_mechs.iloc[0]} trials)")
    if len(top_sponsor) > 0:
        sections.append(f"- **Most active sponsor:** {top_sponsor.index[0]} ({top_sponsor.iloc[0]} trials)")

    # Config-driven executive highlights (mechanisms)
    exec_mechs = exec_highlights.get("mechanisms", []) if exec_highlights else []
    exec_spons = exec_highlights.get("sponsors", []) if exec_highlights else []

    for mech_name in exec_mechs:
        mech_trials = trials_df[trials_df["mechanism"] == mech_name]
        if len(mech_trials) > 0:
            mech_p3 = len(mech_trials[mech_trials["phase_normalized"] == "Phase 3"])
            p3_note = f" ({mech_p3} in Phase 3)" if mech_p3 > 0 else ""
            sections.append(f"- **{mech_name}:** {len(mech_trials)} trials{p3_note}")

    # Config-driven executive highlights (sponsors)
    for sponsor_name in exec_spons:
        spons_trials = trials_df[trials_df["sponsor_normalized"] == sponsor_name]
        if len(spons_trials) > 0:
            spons_mechs = spons_trials["mechanism"].nunique()
            sections.append(f"- **{sponsor_name} portfolio:** {len(spons_trials)} active trials across {spons_mechs} mechanism(s)")

    # Upcoming readouts
    upcoming = _get_upcoming_readouts(trials_df, months=18)
    if len(upcoming) > 0:
        sections.append(f"- **Upcoming readouts (next 18 months):** {len(upcoming)} trials expected to report")

    # Total enrollment (prefer enrollment_clean, fallback to enrollment)
    enroll_col = "enrollment_clean" if "enrollment_clean" in trials_df.columns else "enrollment"
    total_enrollment = trials_df[enroll_col].sum()
    if total_enrollment > 0:
        sections.append(f"- **Total enrolled/planned participants:** ~{int(total_enrollment):,}")

    # --- NEW: Geographic summary ---
    n_countries_col = _safe_col(trials_df, "n_countries", default=np.nan)
    if n_countries_col.notna().any():
        unique_countries = set()
        for val in _safe_col(trials_df, "countries_str", default=""):
            if pd.notna(val) and str(val).strip():
                for c in str(val).split(";"):
                    c = c.strip()
                    if c:
                        unique_countries.add(c)
        if unique_countries:
            sections.append(f"- **Geographic reach:** trials conducted across **{len(unique_countries)} countries**")

    # --- NEW: Study design summary ---
    study_design_col = _safe_col(trials_df, "study_design_category", default="")
    rct_mask = study_design_col.astype(str).str.lower().str.contains("rct|randomized", na=False)
    n_rct = int(rct_mask.sum())
    if n_rct > 0:
        sections.append(f"- **RCTs:** {n_rct} ({n_rct/n_total*100:.0f}%) of trials are randomized controlled trials")

    # --- NEW: Combination therapy summary ---
    combo_col = _safe_col(trials_df, "is_combination", default=False)
    n_combo = int(combo_col.fillna(False).astype(bool).sum())
    if n_combo > 0:
        sections.append(f"- **Combination therapies:** {n_combo} trials testing multi-drug regimens")

    sections.append("")

    # ==========================================
    # 2. MECHANISM x PHASE OVERVIEW
    # ==========================================
    sections.append("---\n")
    sections.append("## Mechanism \u00d7 Phase Overview\n")

    phase_order = ["Phase 1", "Phase 1/2", "Phase 2", "Phase 2/3", "Phase 3", "Phase 4"]
    ct = pd.crosstab(trials_df["mechanism"], trials_df["phase_normalized"])
    ct = ct.reindex(columns=[p for p in phase_order if p in ct.columns], fill_value=0)
    ct["Total"] = ct.sum(axis=1)
    ct = ct.sort_values("Total", ascending=False)

    cols = list(ct.columns)
    header = "| Mechanism | " + " | ".join(cols) + " |"
    sep = "|---|" + "|".join(["---:"] * len(cols)) + "|"
    sections.append(header)
    sections.append(sep)
    for mech, row in ct.iterrows():
        vals = " | ".join(str(int(row[c])) for c in cols)
        sections.append(f"| {mech} | {vals} |")
    sections.append("")

    # ==========================================
    # 3. MECHANISM DEEP DIVES
    # ==========================================
    sections.append("---\n")
    sections.append("## Mechanism Deep Dives\n")

    # Only deep-dive into pharmacological mechanisms with 2+ trials
    mech_order = pharma_mechs[pharma_mechs >= 2].index.tolist()

    for mech in mech_order:
        mech_df = trials_df[trials_df["mechanism"] == mech].copy()
        sections.append(f"### {mech} ({len(mech_df)} trials)\n")

        # Description
        desc = mechanism_descriptions.get(mech, "")
        if desc:
            sections.append(f"{desc}\n")

        # Phase breakdown
        mech_phases = mech_df["phase_normalized"].value_counts()
        sections.append("**Phase distribution:**")
        for phase, count in mech_phases.items():
            sections.append(f"- {phase}: {count} trial{'s' if count > 1 else ''}")
        sections.append("")

        # Status breakdown
        mech_statuses = mech_df["overall_status"].value_counts()
        status_parts = [f"{_format_status(s)}: {c}" for s, c in mech_statuses.items()]
        sections.append(f"**Recruitment status:** {' | '.join(status_parts)}\n")

        # Key sponsors for this mechanism
        mech_sponsors = mech_df["sponsor_normalized"].value_counts()
        if len(mech_sponsors) > 0:
            sections.append("**Key sponsors:**")
            for sponsor, count in mech_sponsors.head(8).items():
                phases = sorted(mech_df[mech_df["sponsor_normalized"] == sponsor]["phase_normalized"].unique())
                sections.append(f"- **{sponsor}**: {count} trial{'s' if count > 1 else ''} ({', '.join(phases)})")
            sections.append("")

        # Drug pipeline table for this mechanism
        drugs = _extract_drug_table(mech_df, indication_cats=indication_cats)
        if len(drugs) > 0:
            sections.append("**Drug pipeline:**\n")
            sections.append("| Drug / Intervention | Sponsor | Phase | Status | Indication | Enrollment | Expected Completion |")
            sections.append("|---|---|---|---|---|---:|---|")
            for _, drug_row in drugs.iterrows():
                sections.append(
                    f"| {drug_row['drug']} | {drug_row['sponsor']} | {drug_row['phase']} | "
                    f"{drug_row['status']} | {drug_row['indication']} | "
                    f"{drug_row['enrollment']} | {drug_row['completion']} |"
                )
            sections.append("")

        # Notable trials (brief list with NCT IDs)
        sections.append("**Trial listing:**\n")
        sections.append("| NCT ID | Title | Sponsor | Phase | Status | Enrollment | Completion |")
        sections.append("|---|---|---|---|---|---:|---|")
        for _, trial in mech_df.head(15).iterrows():
            enrollment_val = _get_enrollment(trial)
            enrollment_str = f"{int(enrollment_val):,}" if pd.notna(enrollment_val) and enrollment_val > 0 else "\u2014"
            completion_str = _format_date(trial.get("completion_date", ""))
            sections.append(
                f"| {trial['nct_id']} | {trial['brief_title'][:65]} | {trial['sponsor_normalized']} | "
                f"{trial['phase_normalized']} | {_format_status(trial['overall_status'])} | "
                f"{enrollment_str} | {completion_str} |"
            )
        if len(mech_df) > 15:
            sections.append(f"\n*... and {len(mech_df) - 15} additional trials*")
        sections.append("")

    # ==========================================
    # 4. GEOGRAPHIC LANDSCAPE
    # ==========================================
    sections.append("---\n")
    sections.append("## Geographic Landscape\n")
    sections.append(
        f"Geographic distribution of {disease_short or disease_name} trials reveals where investment and patient "
        "recruitment are concentrated. Multi-country trials signal global registration "
        "intent; single-country trials may indicate regional strategies or early-phase work.\n"
    )

    countries_str_col = _safe_col(trials_df, "countries_str", default="")
    n_countries_col = _safe_col(trials_df, "n_countries", default=np.nan)
    regions_str_col = _safe_col(trials_df, "regions_str", default="")

    if countries_str_col.astype(str).str.strip().replace("", pd.NA).dropna().shape[0] > 0:
        # Build country-level counts
        country_counts = {}
        for val in countries_str_col:
            if pd.notna(val) and str(val).strip():
                for c in str(val).split(";"):
                    c = c.strip()
                    if c:
                        country_counts[c] = country_counts.get(c, 0) + 1

        if country_counts:
            sorted_countries = sorted(country_counts.items(), key=lambda x: x[1], reverse=True)
            sections.append("### Top 15 Countries by Trial Presence\n")
            sections.append("| Rank | Country | Trials |")
            sections.append("|---:|---|---:|")
            for rank, (country, count) in enumerate(sorted_countries[:15], 1):
                sections.append(f"| {rank} | {country} | {count} |")
            if len(sorted_countries) > 15:
                sections.append(f"\n*{len(sorted_countries) - 15} additional countries with active trials.*")
            sections.append("")

        # Region breakdown
        region_counts = {}
        for val in regions_str_col:
            if pd.notna(val) and str(val).strip():
                for r in str(val).split(";"):
                    r = r.strip()
                    if r:
                        region_counts[r] = region_counts.get(r, 0) + 1

        if region_counts:
            sorted_regions = sorted(region_counts.items(), key=lambda x: x[1], reverse=True)
            sections.append("### Region Breakdown\n")
            sections.append("| Region | Trials |")
            sections.append("|---|---:|")
            for region, count in sorted_regions:
                sections.append(f"| {region} | {count} |")
            sections.append("")

        # Mechanism x region cross-tab
        if region_counts:
            # Build a DataFrame with one row per trial-region pair
            rows_mr = []
            for idx, row in trials_df.iterrows():
                rval = _safe_col_val(row, "regions_str", "")
                if pd.notna(rval) and str(rval).strip():
                    for r in str(rval).split(";"):
                        r = r.strip()
                        if r:
                            rows_mr.append({"mechanism": row["mechanism"], "region": r})
            if rows_mr:
                mr_df = pd.DataFrame(rows_mr)
                mr_ct = pd.crosstab(mr_df["mechanism"], mr_df["region"])
                mr_ct["Total"] = mr_ct.sum(axis=1)
                mr_ct = mr_ct.sort_values("Total", ascending=False)

                sections.append("### Mechanism \u00d7 Region\n")
                mr_cols = [c for c in mr_ct.columns if c != "Total"] + ["Total"]
                mr_ct = mr_ct[mr_cols]
                header = "| Mechanism | " + " | ".join(str(c) for c in mr_cols) + " |"
                sep_line = "|---|" + "|".join(["---:"] * len(mr_cols)) + "|"
                sections.append(header)
                sections.append(sep_line)
                for mech, vals in mr_ct.iterrows():
                    row_str = " | ".join(str(int(vals[c])) for c in mr_cols)
                    sections.append(f"| {mech} | {row_str} |")
                sections.append("")

        # Multi-country trial distribution
        mc = n_countries_col.dropna()
        if len(mc) > 0:
            n_multi = int((mc > 1).sum())
            n_single = int((mc == 1).sum())
            sections.append("### Multi-Country Trial Distribution\n")
            sections.append(f"- Single-country: {n_single} trials")
            sections.append(f"- Multi-country: {n_multi} trials")
            avg_countries = mc[mc > 1].mean()
            if pd.notna(avg_countries):
                sections.append(f"- Average countries per multi-country trial: {avg_countries:.1f}")
            sections.append("")
    else:
        sections.append("*Geographic data not available in current dataset. Re-run compile_trials.py with Phase 2B to populate.*\n")

    # ==========================================
    # 5. STUDY DESIGN ANALYSIS
    # ==========================================
    sections.append("---\n")
    sections.append("## Study Design Analysis\n")
    sections.append(
        "Study design choices impact data quality, regulatory acceptance, and time to "
        "market. A high proportion of double-blind RCTs signals mature, registration-intent "
        "programs.\n"
    )

    design_cat_col = _safe_col(trials_df, "study_design_category", default="")
    allocation_col = _safe_col(trials_df, "allocation", default="")
    masking_col = _safe_col(trials_df, "masking", default="")
    model_col = _safe_col(trials_df, "intervention_model", default="")

    has_design_data = design_cat_col.astype(str).str.strip().replace("", pd.NA).dropna().shape[0] > 0

    if has_design_data:
        # Study design category breakdown
        design_vc = design_cat_col.astype(str).replace("", "Unknown").value_counts()
        sections.append("### Study Design Category Breakdown\n")
        sections.append("| Design Category | Trials | % |")
        sections.append("|---|---:|---:|")
        for cat, cnt in design_vc.items():
            if str(cat).strip() and str(cat) != "nan":
                sections.append(f"| {cat} | {cnt} | {cnt/n_total*100:.0f}% |")
        sections.append("")

        # Allocation breakdown
        alloc_vc = allocation_col.astype(str).replace("", "Not reported").value_counts()
        if len(alloc_vc) > 0:
            sections.append("### Allocation\n")
            sections.append("| Allocation | Trials |")
            sections.append("|---|---:|")
            for a, cnt in alloc_vc.items():
                if str(a) != "nan":
                    sections.append(f"| {a} | {cnt} |")
            sections.append("")

        # Masking breakdown
        masking_vc = masking_col.astype(str).replace("", "Not reported").value_counts()
        if len(masking_vc) > 0:
            sections.append("### Masking / Blinding\n")
            sections.append("| Masking | Trials |")
            sections.append("|---|---:|")
            for m, cnt in masking_vc.items():
                if str(m) != "nan":
                    sections.append(f"| {m} | {cnt} |")
            sections.append("")

        # % double-blind by phase
        db_mask = masking_col.astype(str).str.lower().str.contains("double", na=False)
        if db_mask.any():
            sections.append("### % Double-Blind by Phase\n")
            phase_groups = trials_df.groupby("phase_normalized")
            sections.append("| Phase | Total Trials | Double-Blind | % Double-Blind |")
            sections.append("|---|---:|---:|---:|")
            for phase in phase_order:
                if phase in phase_groups.groups:
                    idx = phase_groups.groups[phase]
                    n_phase = len(idx)
                    n_db = int(db_mask.loc[idx].sum())
                    pct = n_db / n_phase * 100 if n_phase > 0 else 0
                    sections.append(f"| {phase} | {n_phase} | {n_db} | {pct:.0f}% |")
            sections.append("")

        # Intervention model
        model_vc = model_col.astype(str).replace("", "Not reported").value_counts()
        if len(model_vc) > 0:
            sections.append("### Intervention Model\n")
            sections.append("| Model | Trials |")
            sections.append("|---|---:|")
            for m, cnt in model_vc.items():
                if str(m) != "nan":
                    sections.append(f"| {m} | {cnt} |")
            sections.append("")
    else:
        sections.append("*Study design data not available in current dataset. Re-run compile_trials.py with Phase 2B to populate.*\n")

    # ==========================================
    # 6. PHASE TRANSITION FUNNEL
    # ==========================================
    sections.append("---\n")
    sections.append("## Phase Transition Funnel\n")
    sections.append(
        "The phase funnel shows how many trials each mechanism has at each stage, "
        "providing a rough indicator of pipeline depth and implied transition rates. "
        "Higher Phase 2-to-3 ratios suggest stronger conviction by sponsors.\n"
    )

    # Phase counts per mechanism
    funnel_phases = ["Phase 1", "Phase 1/2", "Phase 2", "Phase 2/3", "Phase 3"]
    funnel_mechs = pharma_mechs[pharma_mechs >= 2].index.tolist()

    sections.append("### Trials per Phase by Mechanism\n")
    sections.append("| Mechanism | Ph 1 | Ph 1/2 | Ph 2 | Ph 2/3 | Ph 3 | Total | Ph2\u21923 Ratio |")
    sections.append("|---|---:|---:|---:|---:|---:|---:|---|")
    for mech in funnel_mechs:
        mech_df = trials_df[trials_df["mechanism"] == mech]
        counts = {}
        for p in funnel_phases:
            counts[p] = len(mech_df[mech_df["phase_normalized"] == p])
        total = sum(counts.values())
        # Implied transition ratio: Phase 3 / (Phase 2 + Phase 2/3) if denominator > 0
        denom = counts["Phase 2"] + counts["Phase 2/3"]
        if denom > 0 and counts["Phase 3"] > 0:
            ratio = f"{counts['Phase 3']/denom:.1f}"
        elif counts["Phase 3"] > 0:
            ratio = "\u221e"  # infinity — no Phase 2 trials
        else:
            ratio = "\u2014"
        sections.append(
            f"| {mech} | {counts['Phase 1']} | {counts['Phase 1/2']} | "
            f"{counts['Phase 2']} | {counts['Phase 2/3']} | {counts['Phase 3']} | "
            f"{total} | {ratio} |"
        )
    sections.append("")

    sections.append(
        "*Ph2\u21923 Ratio = Phase 3 count / (Phase 2 + Phase 2/3 count). Higher values imply "
        "strong advancement conviction. \"\u221e\" means Phase 3 trials exist without active Phase 2.*\n"
    )

    # ==========================================
    # 7. LATE-STAGE PIPELINE (Phase 3)
    # ==========================================
    sections.append("---\n")
    sections.append("## Late-Stage Pipeline (Phase 3)\n")

    p3_df = trials_df[trials_df["phase_normalized"].isin(["Phase 3", "Phase 3/4"])].copy()
    if len(p3_df) > 0:
        sections.append(f"**{len(p3_df)} Phase 3 trials** represent the most advanced pipeline with near-term commercial potential.\n")

        # Phase 3 by mechanism
        p3_mechs = p3_df["mechanism"].value_counts()
        sections.append("**Phase 3 by mechanism:**")
        for mech, count in p3_mechs.items():
            sections.append(f"- {mech}: {count}")
        sections.append("")

        # Full Phase 3 table
        sections.append("| NCT ID | Drug(s) | Mechanism | Sponsor | Indication | Enrollment | Status | Expected Completion |")
        sections.append("|---|---|---|---|---|---:|---|---|")
        for _, trial in p3_df.sort_values("completion_date").iterrows():
            drugs = trial.get("drug_names_str", "")
            if not drugs or drugs == "nan":
                drugs = "\u2014"
            elif len(drugs) > 40:
                drugs = drugs[:37] + "..."
            enrollment_val = _get_enrollment(trial)
            enrollment_str = f"{int(enrollment_val):,}" if pd.notna(enrollment_val) and enrollment_val > 0 else "\u2014"
            completion_str = _format_date(trial.get("completion_date", ""))
            indication = _extract_indication(trial.get("conditions_str", ""), indication_cats=indication_cats)
            sections.append(
                f"| {trial['nct_id']} | {drugs} | {trial['mechanism']} | "
                f"{trial['sponsor_normalized']} | {indication} | {enrollment_str} | "
                f"{_format_status(trial['overall_status'])} | {completion_str} |"
            )
        sections.append("")
    else:
        sections.append("*No Phase 3 trials found in the current dataset.*\n")

    # ==========================================
    # 8. PHASE 3 ENDPOINT COMPARISON
    # ==========================================
    sections.append("---\n")
    sections.append("## Phase 3 Endpoint Comparison\n")
    sections.append(
        "Primary endpoints in Phase 3 trials define the regulatory bar each program must clear. "
        "Comparing endpoints across mechanisms reveals whether the field is converging on "
        "standard outcomes (e.g., clinical remission at Week 12/52) or pursuing differentiated strategies.\n"
    )

    endpoint_col = _safe_col(trials_df, "primary_endpoint", default="")
    timeframe_col = _safe_col(trials_df, "endpoint_timeframe", default="")

    p3_with_endpoint = p3_df.copy() if len(p3_df) > 0 else pd.DataFrame()
    if len(p3_with_endpoint) > 0:
        p3_with_endpoint["_endpoint"] = endpoint_col.reindex(p3_with_endpoint.index).fillna("").astype(str)
        p3_with_endpoint["_timeframe"] = timeframe_col.reindex(p3_with_endpoint.index).fillna("").astype(str)
        has_ep = p3_with_endpoint["_endpoint"].str.strip().replace("", pd.NA).dropna()

        if len(has_ep) > 0:
            sections.append("### Primary Endpoints by Mechanism (Phase 3)\n")
            sections.append("| NCT ID | Mechanism | Sponsor | Primary Endpoint | Timeframe |")
            sections.append("|---|---|---|---|---|")
            for mech in p3_with_endpoint["mechanism"].unique():
                mech_ep = p3_with_endpoint[p3_with_endpoint["mechanism"] == mech]
                for _, trial in mech_ep.iterrows():
                    ep_text = str(trial["_endpoint"]).strip()
                    if not ep_text or ep_text == "nan":
                        ep_text = "\u2014"
                    elif len(ep_text) > 80:
                        ep_text = ep_text[:77] + "..."
                    tf_text = str(trial["_timeframe"]).strip()
                    if not tf_text or tf_text == "nan":
                        tf_text = "\u2014"
                    sections.append(
                        f"| {trial['nct_id']} | {mech} | {trial['sponsor_normalized']} | "
                        f"{ep_text} | {tf_text} |"
                    )
            sections.append("")

            # Timeframe comparison summary
            tf_series = p3_with_endpoint["_timeframe"].replace("", pd.NA).dropna()
            if len(tf_series) > 0:
                sections.append("### Timeframe Summary\n")
                tf_counts = tf_series.value_counts().head(10)
                sections.append("| Timeframe | Trials |")
                sections.append("|---|---:|")
                for tf, cnt in tf_counts.items():
                    if str(tf).strip() and str(tf) != "nan":
                        sections.append(f"| {tf} | {cnt} |")
                sections.append("")
        else:
            sections.append("*Endpoint data not populated for Phase 3 trials. Re-run compile_trials.py with Phase 2B.*\n")
    else:
        sections.append("*No Phase 3 trials in dataset.*\n")

    # ==========================================
    # 9. COMBINATION THERAPY LANDSCAPE
    # ==========================================
    sections.append("---\n")
    sections.append("## Combination Therapy Landscape\n")
    sections.append(
        f"Combination trials (2+ active drugs) represent a growing strategy in {disease_short or disease_name}, reflecting "
        "the need for improved efficacy beyond monotherapy. Identifying which mechanism pairs "
        "are being tested reveals emerging therapeutic paradigms.\n"
    )

    combo_col = _safe_col(trials_df, "is_combination", default=False)
    combo_df = trials_df[combo_col.fillna(False).astype(bool)].copy()

    if len(combo_df) > 0:
        sections.append(f"**{len(combo_df)} combination therapy trials** identified.\n")

        # By mechanism
        combo_mechs = combo_df["mechanism"].value_counts()
        sections.append("### Combination Trials by Mechanism\n")
        sections.append("| Mechanism | Combo Trials | % of Mechanism Total |")
        sections.append("|---|---:|---:|")
        for mech, cnt in combo_mechs.items():
            total_mech = len(trials_df[trials_df["mechanism"] == mech])
            pct = cnt / total_mech * 100 if total_mech > 0 else 0
            sections.append(f"| {mech} | {cnt} | {pct:.0f}% |")
        sections.append("")

        # Full combo listing
        sections.append("### Combination Trial Details\n")
        sections.append("| NCT ID | Drug(s) | Mechanism | Sponsor | Phase | Status |")
        sections.append("|---|---|---|---|---|---|")
        for _, trial in combo_df.sort_values(["mechanism", "phase_normalized"]).iterrows():
            drugs = trial.get("drug_names_str", "")
            if not drugs or str(drugs) == "nan":
                drugs = "\u2014"
            elif len(str(drugs)) > 50:
                drugs = str(drugs)[:47] + "..."
            sections.append(
                f"| {trial['nct_id']} | {drugs} | {trial['mechanism']} | "
                f"{trial['sponsor_normalized']} | {trial['phase_normalized']} | "
                f"{_format_status(trial['overall_status'])} |"
            )
        sections.append("")

        # Sponsor activity in combinations
        combo_sponsors = combo_df["sponsor_normalized"].value_counts()
        if len(combo_sponsors) > 0:
            sections.append("### Sponsors Active in Combination Trials\n")
            sections.append("| Sponsor | Combo Trials |")
            sections.append("|---|---:|")
            for sponsor, cnt in combo_sponsors.head(10).items():
                sections.append(f"| {sponsor} | {cnt} |")
            sections.append("")
    else:
        combo_has_data = "is_combination" in trials_df.columns
        if combo_has_data:
            sections.append("*No combination therapy trials identified in the current dataset.*\n")
        else:
            sections.append("*Combination therapy data not available. Re-run compile_trials.py with Phase 2B to populate.*\n")

    # ==========================================
    # 10. UPCOMING READOUTS
    # ==========================================
    sections.append("---\n")
    sections.append("## Upcoming Readouts\n")

    upcoming_12 = _get_upcoming_readouts(trials_df, months=12)
    upcoming_24 = _get_upcoming_readouts(trials_df, months=24)

    if len(upcoming_24) > 0:
        sections.append(
            f"**{len(upcoming_12)} trials** expected to complete within 12 months, "
            f"**{len(upcoming_24)}** within 24 months.\n"
        )
        sections.append("*Sorted by expected primary completion date.*\n")

        sections.append("| NCT ID | Drug(s) | Mechanism | Sponsor | Phase | Enrollment | Expected Completion | Time to Readout |")
        sections.append("|---|---|---|---|---|---:|---|---|")
        for _, trial in upcoming_24.iterrows():
            drugs = trial.get("drug_names_str", "")
            if not drugs or str(drugs) == "nan":
                drugs = "\u2014"
            elif len(str(drugs)) > 35:
                drugs = str(drugs)[:32] + "..."
            enrollment_val = _get_enrollment(trial)
            enrollment_str = f"{int(enrollment_val):,}" if pd.notna(enrollment_val) and enrollment_val > 0 else "\u2014"
            completion_str = _format_date(trial.get("completion_date", ""))
            time_to = _time_to_readout(trial.get("completion_date", ""))
            sections.append(
                f"| {trial['nct_id']} | {drugs} | {trial['mechanism']} | "
                f"{trial['sponsor_normalized']} | {trial['phase_normalized']} | "
                f"{enrollment_str} | {completion_str} | {time_to} |"
            )
        sections.append("")
    else:
        sections.append("*No trials with completion dates within 24 months found.*\n")

    # ==========================================
    # 11. DRUG-LEVEL PIPELINE
    # ==========================================
    sections.append("---\n")
    sections.append("## Drug-Level Pipeline\n")

    drug_table = _extract_drug_table(trials_df, indication_cats=indication_cats)
    if len(drug_table) > 0:
        sections.append(f"**{len(drug_table)} distinct drug/intervention programs** identified across all mechanisms.\n")
        sections.append("| Drug / Intervention | Mechanism | Sponsor | Phase | Status | Indication | Enrollment | Completion |")
        sections.append("|---|---|---|---|---|---|---:|---|")
        for _, row in drug_table.iterrows():
            sections.append(
                f"| {row['drug']} | {row['mechanism']} | {row['sponsor']} | "
                f"{row['phase']} | {row['status']} | {row['indication']} | "
                f"{row['enrollment']} | {row['completion']} |"
            )
        sections.append("")
    else:
        sections.append("*No named drug interventions identified.*\n")

    # ==========================================
    # 12+. CONFIG-DRIVEN HIGHLIGHT SECTIONS (mechanisms)
    # ==========================================
    for hl in highlight_mechanisms:
        hl_mech_name = hl["mechanism"]
        hl_section_title = hl["section_title"]
        hl_narrative = hl.get("narrative", "")
        hl_trials = trials_df[trials_df["mechanism"] == hl_mech_name]
        if len(hl_trials) > 0:
            sections.append("---\n")
            sections.append(f"## {hl_section_title}\n")
            narrative_suffix = f" \u2014 {hl_narrative}" if hl_narrative else ""
            sections.append(f"**{len(hl_trials)} active trials**{narrative_suffix}.\n")

            desc = mechanism_descriptions.get(hl_mech_name, "")
            if desc:
                sections.append(f"> {desc}\n")

            # Phase breakdown
            hl_phases = hl_trials["phase_normalized"].value_counts()
            for phase, count in hl_phases.items():
                sections.append(f"- **{phase}:** {count} trials")
            sections.append("")

            # Key sponsors + their drugs
            sections.append("### Key Sponsors & Drug Programs\n")
            hl_sponsors = hl_trials["sponsor_normalized"].value_counts()
            for sponsor, count in hl_sponsors.items():
                sponsor_trials = hl_trials[hl_trials["sponsor_normalized"] == sponsor]
                drugs = _get_unique_drugs(sponsor_trials)
                phases = sorted(sponsor_trials["phase_normalized"].unique())
                drug_str = f" ({', '.join(drugs)})" if drugs else ""
                enrollments = sponsor_trials["enrollment"].dropna()
                enroll_str = f", ~{int(enrollments.sum()):,} patients" if len(enrollments) > 0 else ""
                sections.append(
                    f"- **{sponsor}**: {count} trial{'s' if count > 1 else ''}{drug_str} "
                    f"\u2014 {', '.join(phases)}{enroll_str}"
                )
            sections.append("")

            # Indication split
            sections.append("### Indication Split\n")
            _add_indication_split(sections, hl_trials, indication_cats=indication_cats)

            # Complete trial listing
            sections.append("### Complete Trial Listing\n")
            sections.append("| NCT ID | Title | Sponsor | Phase | Status | Enrollment | Completion |")
            sections.append("|---|---|---|---|---|---:|---|")
            for _, trial in hl_trials.iterrows():
                enrollment_val = _get_enrollment(trial)
                enrollment_str = f"{int(enrollment_val):,}" if pd.notna(enrollment_val) and enrollment_val > 0 else "\u2014"
                completion_str = _format_date(trial.get("completion_date", ""))
                sections.append(
                    f"| {trial['nct_id']} | {trial['brief_title'][:60]} | "
                    f"{trial['sponsor_normalized']} | {trial['phase_normalized']} | "
                    f"{_format_status(trial['overall_status'])} | {enrollment_str} | {completion_str} |"
                )
            sections.append("")

    # ==========================================
    # CONFIG-DRIVEN HIGHLIGHT SECTIONS (sponsors)
    # ==========================================
    for hl in highlight_sponsors:
        hl_sponsor_name = hl["sponsor"]
        hl_section_title = hl["section_title"]
        hl_trials = trials_df[trials_df["sponsor_normalized"] == hl_sponsor_name]
        if len(hl_trials) > 0:
            sections.append("---\n")
            sections.append(f"## {hl_section_title}\n")
            sections.append(f"**{len(hl_trials)} active trials** from {hl_sponsor_name}.\n")

            # Portfolio by mechanism
            sections.append("### Portfolio by Mechanism\n")
            hl_mechs = hl_trials["mechanism"].value_counts()
            for mech, count in hl_mechs.items():
                mech_trials = hl_trials[hl_trials["mechanism"] == mech]
                drugs = _get_unique_drugs(mech_trials)
                phases = sorted(mech_trials["phase_normalized"].unique())
                drug_str = f": {', '.join(drugs)}" if drugs else ""
                sections.append(f"- **{mech}** ({count} trial{'s' if count > 1 else ''}){drug_str} \u2014 {', '.join(phases)}")
            sections.append("")

            # Indication split
            sections.append("### Indication Coverage\n")
            _add_indication_split(sections, hl_trials, indication_cats=indication_cats)

            # Competitive context
            sections.append("### Competitive Context\n")
            for mech in hl_mechs.index:
                all_mech = trials_df[trials_df["mechanism"] == mech]
                sponsor_mech = hl_trials[hl_trials["mechanism"] == mech]
                other_sponsors = all_mech[all_mech["sponsor_normalized"] != hl_sponsor_name]["sponsor_normalized"].nunique()
                sections.append(
                    f"- **{mech}**: {hl_sponsor_name} has {len(sponsor_mech)} of {len(all_mech)} total trials "
                    f"(vs. {other_sponsors} other sponsors)"
                )
            sections.append("")

            # Full trial listing
            sections.append("### Complete Trial Listing\n")
            sections.append("| NCT ID | Title | Mechanism | Phase | Status | Enrollment | Completion |")
            sections.append("|---|---|---|---|---|---:|---|")
            for _, trial in hl_trials.iterrows():
                enrollment_val = _get_enrollment(trial)
                enrollment_str = f"{int(enrollment_val):,}" if pd.notna(enrollment_val) and enrollment_val > 0 else "\u2014"
                completion_str = _format_date(trial.get("completion_date", ""))
                sections.append(
                    f"| {trial['nct_id']} | {trial['brief_title'][:55]} | "
                    f"{trial['mechanism']} | {trial['phase_normalized']} | "
                    f"{_format_status(trial['overall_status'])} | {enrollment_str} | {completion_str} |"
                )
            sections.append("")

    # ==========================================
    # SPONSOR COMPETITIVE LANDSCAPE
    # ==========================================
    sections.append("---\n")
    sections.append("## Sponsor Competitive Landscape\n")

    # Top sponsors summary table
    enroll_col = "enrollment_clean" if "enrollment_clean" in trials_df.columns else "enrollment"
    sponsor_summary = (
        trials_df.groupby("sponsor_normalized")
        .agg(
            trials=("nct_id", "count"),
            mechanisms=("mechanism", "nunique"),
            top_mechanism=("mechanism", lambda x: x.value_counts().index[0] if len(x) > 0 else ""),
            phases=("phase_normalized", lambda x: ", ".join(sorted(x.unique()))),
            total_enrollment=(enroll_col, "sum"),
            industry=("is_industry", "first"),
        )
        .sort_values("trials", ascending=False)
    )

    top_n = 25
    top_sponsors = sponsor_summary.head(top_n)

    sections.append(f"### Top {min(top_n, len(top_sponsors))} Sponsors\n")
    sections.append("| Rank | Sponsor | Trials | Mechanisms | Primary Focus | Phases | Est. Enrollment | Type |")
    sections.append("|---:|---|---:|---:|---|---|---:|---|")
    for rank, (sponsor, row) in enumerate(top_sponsors.iterrows(), 1):
        enroll = f"{int(row['total_enrollment']):,}" if pd.notna(row["total_enrollment"]) and row["total_enrollment"] > 0 else "\u2014"
        stype = "Industry" if row["industry"] else "Academic"
        sections.append(
            f"| {rank} | **{sponsor}** | {int(row['trials'])} | {int(row['mechanisms'])} | "
            f"{row['top_mechanism']} | {row['phases'][:35]} | {enroll} | {stype} |"
        )
    sections.append("")

    # Company deep-dives for top sponsors
    sections.append("### Company Portfolio Analysis\n")
    for sponsor, row in top_sponsors.head(10).iterrows():
        sponsor_df = trials_df[trials_df["sponsor_normalized"] == sponsor]
        mech_breakdown = sponsor_df["mechanism"].value_counts()
        phase_breakdown = sponsor_df["phase_normalized"].value_counts()

        sections.append(f"**{sponsor}** \u2014 {int(row['trials'])} trials\n")

        # Mechanism focus
        mech_parts = [f"{m} ({c})" for m, c in mech_breakdown.items()]
        sections.append(f"- Mechanisms: {', '.join(mech_parts)}")

        # Phase coverage
        phase_parts = [f"{p}: {c}" for p, c in phase_breakdown.items()]
        sections.append(f"- Phases: {', '.join(phase_parts)}")

        # Key drugs
        drugs = _get_unique_drugs(sponsor_df)
        if drugs:
            sections.append(f"- Key drugs/interventions: {', '.join(drugs[:5])}")

        # Indication focus
        ind_counts = _count_indications(sponsor_df, indication_cats=indication_cats)
        ind_parts = [f"{label} ({cnt})" for label, _full, cnt in ind_counts if cnt > 0]
        if ind_parts:
            sections.append(f"- Indications: {', '.join(ind_parts)}")
        sections.append("")

    # Industry vs academic summary
    sections.append("### Industry vs. Academic Split\n")
    industry_df = trials_df[trials_df["is_industry"]]
    academic_df = trials_df[~trials_df["is_industry"]]
    sections.append(f"| | Industry | Academic/Other |")
    sections.append(f"|---|---:|---:|")
    sections.append(f"| Total trials | {len(industry_df)} | {len(academic_df)} |")
    sections.append(f"| Unique sponsors | {industry_df['sponsor_normalized'].nunique()} | {academic_df['sponsor_normalized'].nunique()} |")
    sections.append(f"| Phase 3 trials | {len(industry_df[industry_df['phase_normalized'] == 'Phase 3'])} | {len(academic_df[academic_df['phase_normalized'] == 'Phase 3'])} |")
    sections.append(f"| Mechanisms covered | {industry_df['mechanism'].nunique()} | {academic_df['mechanism'].nunique()} |")
    ind_enroll = industry_df[enroll_col].sum() if enroll_col in industry_df.columns else industry_df["enrollment"].sum()
    aca_enroll = academic_df[enroll_col].sum() if enroll_col in academic_df.columns else academic_df["enrollment"].sum()
    sections.append(f"| Total enrollment | {int(ind_enroll):,} | {int(aca_enroll):,} |")
    sections.append("")

    # ==========================================
    # 16. INDICATION BREAKDOWN
    # ==========================================
    sections.append("---\n")
    sections.append("## Indication Breakdown\n")

    ind_totals = _count_indications(trials_df, indication_cats=indication_cats)
    sections.append(f"| Indication | Trials |")
    sections.append(f"|---|---:|")
    for label, full_name, cnt in ind_totals:
        display = f"{full_name} ({label})" if label != full_name else label
        sections.append(f"| {display} | {cnt} |")
    sections.append("")

    # Mechanism x indication
    ind_labels = [entry[0] for entry in ind_totals]
    sections.append("### Mechanism \u00d7 Indication\n")
    header = "| Mechanism | " + " | ".join(ind_labels) + " |"
    sep = "|---|" + "|".join(["---:"] * len(ind_labels)) + "|"
    sections.append(header)
    sections.append(sep)
    for mech in ct.index:
        mech_df = trials_df[trials_df["mechanism"] == mech]
        mech_ind = _count_indications(mech_df, indication_cats=indication_cats)
        vals = " | ".join(str(entry[2]) for entry in mech_ind)
        sections.append(f"| {mech} | {vals} |")
    sections.append("")

    # ==========================================
    # 17. PATIENT POPULATION ANALYSIS
    # ==========================================
    sections.append("---\n")
    sections.append("## Patient Population Analysis\n")
    sections.append(
        "Eligibility criteria reveal which patient segments are being targeted. "
        f"Pediatric {disease_short or disease_name} remains underserved relative to adult populations; identifying "
        "pediatric-specific programs is valuable for portfolio gap analysis.\n"
    )

    is_pediatric_col = _safe_col(trials_df, "is_pediatric", default=False)
    min_age_years_col = _safe_col(trials_df, "min_age_years", default=np.nan)
    max_age_years_col = _safe_col(trials_df, "max_age_years", default=np.nan)
    sex_col = _safe_col(trials_df, "sex", default="")

    has_pop_data = is_pediatric_col.astype(bool).any() or min_age_years_col.notna().any()

    if has_pop_data:
        n_ped = int(is_pediatric_col.fillna(False).astype(bool).sum())
        n_adult = n_total - n_ped
        sections.append("### Pediatric vs. Adult\n")
        sections.append(f"| Population | Trials | % |")
        sections.append(f"|---|---:|---:|")
        sections.append(f"| Adult-only | {n_adult} | {n_adult/n_total*100:.0f}% |")
        sections.append(f"| Includes pediatric | {n_ped} | {n_ped/n_total*100:.0f}% |")
        sections.append("")

        # Pediatric by mechanism
        if n_ped > 0:
            ped_df = trials_df[is_pediatric_col.fillna(False).astype(bool)]
            ped_mechs = ped_df["mechanism"].value_counts()
            sections.append("### Pediatric Trials by Mechanism\n")
            sections.append("| Mechanism | Pediatric Trials |")
            sections.append("|---|---:|")
            for mech, cnt in ped_mechs.items():
                sections.append(f"| {mech} | {cnt} |")
            sections.append("")

        # Age range summary
        min_ages = min_age_years_col.dropna()
        max_ages = max_age_years_col.dropna()
        if len(min_ages) > 0 or len(max_ages) > 0:
            sections.append("### Age Eligibility Summary\n")
            if len(min_ages) > 0:
                sections.append(f"- Minimum age range: {min_ages.min():.0f} \u2013 {min_ages.max():.0f} years (median: {min_ages.median():.0f})")
            if len(max_ages) > 0:
                sections.append(f"- Maximum age range: {max_ages.min():.0f} \u2013 {max_ages.max():.0f} years (median: {max_ages.median():.0f})")
            sections.append("")

        # Gender eligibility
        sex_vc = sex_col.astype(str).replace("", "Not reported").value_counts()
        if len(sex_vc) > 0 and not (len(sex_vc) == 1 and "Not reported" in sex_vc.index):
            sections.append("### Gender Eligibility\n")
            sections.append("| Sex | Trials |")
            sections.append("|---|---:|")
            for s, cnt in sex_vc.items():
                if str(s) != "nan":
                    sections.append(f"| {s} | {cnt} |")
            sections.append("")
    else:
        sections.append("*Patient population data not available. Re-run compile_trials.py with Phase 2B to populate.*\n")

    # ==========================================
    # 18. TRIAL ARMS & COMPARATOR ANALYSIS
    # ==========================================
    sections.append("---\n")
    sections.append("## Trial Arms & Comparator Analysis\n")
    sections.append(
        "Understanding comparator strategies is critical for competitive positioning. "
        "Head-to-head trials directly compare therapies and carry outsize strategic "
        "importance for prescriber adoption and market access.\n"
    )

    has_placebo_col = _safe_col(trials_df, "has_placebo_arm", default=False)
    has_active_col = _safe_col(trials_df, "has_active_comparator", default=False)
    is_h2h_col = _safe_col(trials_df, "is_head_to_head", default=False)
    n_arms_col = _safe_col(trials_df, "n_arms", default=np.nan)

    has_arms_data = has_placebo_col.astype(bool).any() or n_arms_col.notna().any()

    if has_arms_data:
        n_placebo = int(has_placebo_col.fillna(False).astype(bool).sum())
        n_active = int(has_active_col.fillna(False).astype(bool).sum())
        n_h2h = int(is_h2h_col.fillna(False).astype(bool).sum())

        sections.append("### Comparator Summary\n")
        sections.append("| Comparator Type | Trials | % |")
        sections.append("|---|---:|---:|")
        sections.append(f"| Has placebo arm | {n_placebo} | {n_placebo/n_total*100:.0f}% |")
        sections.append(f"| Has active comparator | {n_active} | {n_active/n_total*100:.0f}% |")
        sections.append(f"| Head-to-head | {n_h2h} | {n_h2h/n_total*100:.0f}% |")
        sections.append("")

        # Number of arms distribution
        arms_valid = n_arms_col.dropna()
        if len(arms_valid) > 0:
            sections.append("### Number of Arms\n")
            arms_vc = arms_valid.astype(int).value_counts().sort_index()
            sections.append("| Arms | Trials |")
            sections.append("|---:|---:|")
            for n, cnt in arms_vc.items():
                sections.append(f"| {n} | {cnt} |")
            sections.append("")

        # Head-to-head trial details
        if n_h2h > 0:
            h2h_df = trials_df[is_h2h_col.fillna(False).astype(bool)]
            sections.append("### Head-to-Head Trials\n")
            sections.append("| NCT ID | Drug(s) | Mechanism | Sponsor | Phase | Status |")
            sections.append("|---|---|---|---|---|---|")
            for _, trial in h2h_df.iterrows():
                drugs = trial.get("drug_names_str", "")
                if not drugs or str(drugs) == "nan":
                    drugs = "\u2014"
                elif len(str(drugs)) > 50:
                    drugs = str(drugs)[:47] + "..."
                sections.append(
                    f"| {trial['nct_id']} | {drugs} | {trial['mechanism']} | "
                    f"{trial['sponsor_normalized']} | {trial['phase_normalized']} | "
                    f"{_format_status(trial['overall_status'])} |"
                )
            sections.append("")

        # Placebo vs active by phase
        sections.append("### Comparator Strategy by Phase\n")
        sections.append("| Phase | Placebo | Active | Head-to-Head | Neither |")
        sections.append("|---|---:|---:|---:|---:|")
        for phase in phase_order:
            phase_mask = trials_df["phase_normalized"] == phase
            if phase_mask.sum() == 0:
                continue
            n_ph = int(phase_mask.sum())
            n_pl = int((phase_mask & has_placebo_col.fillna(False).astype(bool)).sum())
            n_ac = int((phase_mask & has_active_col.fillna(False).astype(bool)).sum())
            n_hh = int((phase_mask & is_h2h_col.fillna(False).astype(bool)).sum())
            n_neither = n_ph - max(n_pl, n_ac)
            if n_neither < 0:
                n_neither = 0
            sections.append(f"| {phase} | {n_pl} | {n_ac} | {n_hh} | {n_neither} |")
        sections.append("")
    else:
        sections.append("*Trial arm/comparator data not available. Re-run compile_trials.py with Phase 2B to populate.*\n")

    # ==========================================
    # 19. ENROLLMENT & INVESTMENT SIGNALS
    # ==========================================
    sections.append("---\n")
    sections.append("## Enrollment & Investment Signals\n")

    # Use enrollment_clean if available, else fallback to enrollment
    enroll_col = "enrollment_clean" if "enrollment_clean" in trials_df.columns else "enrollment"
    if enroll_col == "enrollment_clean":
        sections.append("*Using cleaned enrollment figures (outliers flagged/removed).*\n")

    # Largest trials
    large_trials = trials_df[trials_df[enroll_col].notna() & (trials_df[enroll_col] > 0)].sort_values(enroll_col, ascending=False)
    if len(large_trials) > 0:
        sections.append("### Largest Trials by Enrollment\n")
        sections.append(f"*Large enrollment signals significant investment and commercial intent.*\n")
        sections.append("| NCT ID | Drug(s) | Mechanism | Sponsor | Phase | Enrollment | Status |")
        sections.append("|---|---|---|---|---|---:|---|")
        for _, trial in large_trials.head(20).iterrows():
            drugs = trial.get("drug_names_str", "")
            if not drugs or str(drugs) == "nan":
                drugs = "\u2014"
            elif len(str(drugs)) > 35:
                drugs = str(drugs)[:32] + "..."
            enrollment_val = trial[enroll_col]
            sections.append(
                f"| {trial['nct_id']} | {drugs} | {trial['mechanism']} | "
                f"{trial['sponsor_normalized']} | {trial['phase_normalized']} | "
                f"{int(enrollment_val):,} | {_format_status(trial['overall_status'])} |"
            )
        sections.append("")

    # Enrollment by mechanism
    sections.append("### Total Enrollment by Mechanism\n")
    mech_enrollment = trials_df.groupby("mechanism")[enroll_col].agg(["sum", "count", "mean"]).sort_values("sum", ascending=False)
    sections.append("| Mechanism | Total Enrollment | Trials | Avg. per Trial |")
    sections.append("|---|---:|---:|---:|")
    for mech, row in mech_enrollment.iterrows():
        total = f"{int(row['sum']):,}" if pd.notna(row["sum"]) else "\u2014"
        avg = f"{int(row['mean']):,}" if pd.notna(row["mean"]) else "\u2014"
        sections.append(f"| {mech} | {total} | {int(row['count'])} | {avg} |")
    sections.append("")

    # New trials (started recently)
    recent_starts = trials_df[trials_df["start_year"].notna()].copy()
    if len(recent_starts) > 0:
        current_year = now.year
        new_trials = recent_starts[recent_starts["start_year"] >= current_year - 1]
        if len(new_trials) > 0:
            sections.append(f"### Recently Initiated Trials ({current_year - 1}\u2013{current_year})\n")
            sections.append(f"**{len(new_trials)} trials** started in {current_year - 1}\u2013{current_year}.\n")
            new_mechs = new_trials["mechanism"].value_counts()
            for mech, count in new_mechs.items():
                sections.append(f"- {mech}: {count}")
            sections.append("")

    # ==========================================
    # 20. BIOSIMILAR LANDSCAPE
    # ==========================================
    sections.append("---\n")
    sections.append("## Biosimilar Landscape\n")
    sections.append(
        "Biosimilar trials erode originator revenue and reshape competitive dynamics. "
        "Mechanisms with heavy biosimilar activity (e.g., Anti-TNF) face price compression, "
        "while mechanisms with no biosimilars retain pricing power.\n"
    )

    biosim_col = _safe_col(trials_df, "is_biosimilar", default=False)
    has_biosim_data = "is_biosimilar" in trials_df.columns

    if has_biosim_data:
        n_biosim = int(biosim_col.fillna(False).astype(bool).sum())
        n_originator = n_total - n_biosim

        sections.append(f"**{n_biosim} biosimilar trials** vs. **{n_originator} originator/novel** trials.\n")

        if n_biosim > 0:
            biosim_df = trials_df[biosim_col.fillna(False).astype(bool)]

            # Biosimilar by mechanism
            biosim_mechs = biosim_df["mechanism"].value_counts()
            sections.append("### Biosimilar Trials by Mechanism\n")
            sections.append("| Mechanism | Biosimilar Trials | Originator Trials | Biosimilar % |")
            sections.append("|---|---:|---:|---:|")
            for mech in ct.index:
                mech_total = len(trials_df[trials_df["mechanism"] == mech])
                mech_biosim = int(biosim_mechs.get(mech, 0))
                mech_orig = mech_total - mech_biosim
                pct = mech_biosim / mech_total * 100 if mech_total > 0 else 0
                if mech_biosim > 0 or mech_total >= 3:  # Only show mechanisms with biosimilars or enough trials
                    sections.append(f"| {mech} | {mech_biosim} | {mech_orig} | {pct:.0f}% |")
            sections.append("")

            # Biosimilar sponsors
            biosim_sponsors = biosim_df["sponsor_normalized"].value_counts()
            sections.append("### Top Biosimilar Sponsors\n")
            sections.append("| Sponsor | Biosimilar Trials |")
            sections.append("|---|---:|")
            for sponsor, cnt in biosim_sponsors.head(10).items():
                sections.append(f"| {sponsor} | {cnt} |")
            sections.append("")
        else:
            sections.append("*No biosimilar trials identified in current dataset.*\n")
    else:
        sections.append("*Biosimilar classification not available. Re-run compile_trials.py with Phase 2B to populate.*\n")

    # ==========================================
    # 21. WHITESPACE & UNMET NEEDS
    # ==========================================
    sections.append("---\n")
    sections.append("## Whitespace & Unmet Needs\n")
    sections.append(
        "Identifying gaps in the current pipeline highlights opportunities for BD and "
        "portfolio strategy. Mechanisms without Phase 3 programs, indications with thin "
        "coverage, and under-tested patient segments represent potential whitespace.\n"
    )

    # Mechanisms with no Phase 3
    sections.append("### Mechanisms Without Phase 3 Trials\n")
    mechs_no_p3 = []
    for mech in pharma_mechs.index:
        mech_p3 = len(trials_df[(trials_df["mechanism"] == mech) &
                                 (trials_df["phase_normalized"].isin(["Phase 3", "Phase 3/4"]))])
        if mech_p3 == 0:
            total_for_mech = int(pharma_mechs[mech])
            mechs_no_p3.append((mech, total_for_mech))

    if mechs_no_p3:
        sections.append("| Mechanism | Total Trials | Highest Phase |")
        sections.append("|---|---:|---|")
        for mech, total in mechs_no_p3:
            mech_df_ws = trials_df[trials_df["mechanism"] == mech]
            highest = mech_df_ws["phase_normalized"].value_counts().index[0] if len(mech_df_ws) > 0 else "\u2014"
            sections.append(f"| {mech} | {total} | {highest} |")
        sections.append("")
    else:
        sections.append("*All pharmacological mechanisms have at least one Phase 3 trial.*\n")

    # Indication gaps — mechanisms x indication with 0 trials
    sections.append("### Underserved Mechanism \u00d7 Indication Combinations\n")
    sections.append(
        "*Mechanism-indication pairs where no active trials exist represent potential "
        "first-mover opportunities.*\n"
    )
    gaps = []
    for mech in pharma_mechs.index[:10]:  # Top 10 mechanisms
        mech_df_gap = trials_df[trials_df["mechanism"] == mech]
        mech_ind_counts = _count_indications(mech_df_gap, indication_cats=indication_cats)
        for label, _full, cnt in mech_ind_counts:
            # Skip default/catch-all categories for gap analysis
            is_default = False
            if indication_cats:
                for cat in indication_cats:
                    if cat.get("label") == label and cat.get("is_default"):
                        is_default = True
                        break
            if not is_default and cnt == 0:
                gaps.append((mech, label))

    if gaps:
        sections.append("| Mechanism | Missing Indication |")
        sections.append("|---|---|")
        for mech, ind in gaps:
            sections.append(f"| {mech} | {ind} |")
        sections.append("")
    else:
        sections.append("*No obvious mechanism \u00d7 indication gaps among top mechanisms.*\n")

    # Pediatric gaps
    if has_pop_data and n_ped > 0:
        sections.append("### Pediatric Coverage Gaps\n")
        ped_mechs_set = set(trials_df[is_pediatric_col.fillna(False).astype(bool)]["mechanism"].unique())
        all_pharma_mechs = set(pharma_mechs.index)
        no_ped = all_pharma_mechs - ped_mechs_set
        if no_ped:
            sections.append("*Mechanisms with NO pediatric trials:*\n")
            for mech in sorted(no_ped):
                sections.append(f"- {mech}")
            sections.append("")
        else:
            sections.append("*All pharmacological mechanisms have at least one pediatric trial.*\n")

    # ==========================================
    # 22. COLLABORATOR NETWORK
    # ==========================================
    sections.append("---\n")
    sections.append("## Collaborator Network\n")
    sections.append(
        "Collaborating institutions (listed as collaborators on ClinicalTrials.gov) "
        f"reveal partnership density and key academic centers driving {disease_short or disease_name} research.\n"
    )

    collab_col = _safe_col(trials_df, "collaborators_str", default="")
    has_collab = collab_col.astype(str).str.strip().replace("", pd.NA).dropna().shape[0] > 0

    if has_collab:
        # Count collaborator appearances
        collab_counts = {}
        for val in collab_col:
            if pd.notna(val) and str(val).strip():
                for c in str(val).split(";"):
                    c = c.strip()
                    if c:
                        collab_counts[c] = collab_counts.get(c, 0) + 1

        if collab_counts:
            sorted_collabs = sorted(collab_counts.items(), key=lambda x: x[1], reverse=True)
            sections.append(f"**{len(sorted_collabs)} unique collaborating institutions** identified.\n")

            sections.append("### Top 20 Collaborators\n")
            sections.append("| Rank | Collaborator | Trials |")
            sections.append("|---:|---|---:|")
            for rank, (collab, cnt) in enumerate(sorted_collabs[:20], 1):
                sections.append(f"| {rank} | {collab} | {cnt} |")
            sections.append("")

            # Trials with collaborators vs. without
            n_with_collab = int(collab_col.astype(str).str.strip().replace("", pd.NA).dropna().shape[0])
            sections.append(f"- Trials with listed collaborators: {n_with_collab} ({n_with_collab/n_total*100:.0f}%)")
            sections.append(f"- Trials without collaborators: {n_total - n_with_collab} ({(n_total - n_with_collab)/n_total*100:.0f}%)")
            sections.append("")
        else:
            sections.append("*No collaborator data found.*\n")
    else:
        sections.append("*Collaborator data not available. Re-run compile_trials.py with Phase 2B to populate.*\n")

    # ==========================================
    # 23. REGULATORY SIGNALS
    # ==========================================
    sections.append("---\n")
    sections.append("## Regulatory Signals\n")
    sections.append(
        "FDA-regulated status and Data Safety Monitoring Board (DSMB) presence are "
        "proxies for regulatory seriousness and risk management maturity.\n"
    )

    fda_col = _safe_col(trials_df, "is_fda_regulated_drug", default=False)
    dmc_col = _safe_col(trials_df, "has_dmc", default=False)
    has_reg_data = "is_fda_regulated_drug" in trials_df.columns or "has_dmc" in trials_df.columns

    if has_reg_data:
        # FDA-regulated breakdown
        if "is_fda_regulated_drug" in trials_df.columns:
            n_fda = int(fda_col.fillna(False).astype(bool).sum())
            n_non_fda = n_total - n_fda
            sections.append("### FDA-Regulated Drug Trials\n")
            sections.append(f"| | Trials | % |")
            sections.append(f"|---|---:|---:|")
            sections.append(f"| FDA-regulated | {n_fda} | {n_fda/n_total*100:.0f}% |")
            sections.append(f"| Non-FDA-regulated | {n_non_fda} | {n_non_fda/n_total*100:.0f}% |")
            sections.append("")

            # FDA by mechanism
            sections.append("### FDA-Regulated by Mechanism\n")
            sections.append("| Mechanism | FDA-Regulated | Non-FDA | % FDA |")
            sections.append("|---|---:|---:|---:|")
            for mech in ct.index:
                mech_mask = trials_df["mechanism"] == mech
                mech_n = int(mech_mask.sum())
                mech_fda = int((mech_mask & fda_col.fillna(False).astype(bool)).sum())
                pct = mech_fda / mech_n * 100 if mech_n > 0 else 0
                sections.append(f"| {mech} | {mech_fda} | {mech_n - mech_fda} | {pct:.0f}% |")
            sections.append("")

        # DSMB breakdown
        if "has_dmc" in trials_df.columns:
            n_dmc = int(dmc_col.fillna(False).astype(bool).sum())
            sections.append("### Data Safety Monitoring Board (DSMB)\n")
            sections.append(f"| | Trials | % |")
            sections.append(f"|---|---:|---:|")
            sections.append(f"| Has DSMB | {n_dmc} | {n_dmc/n_total*100:.0f}% |")
            sections.append(f"| No DSMB | {n_total - n_dmc} | {(n_total - n_dmc)/n_total*100:.0f}% |")
            sections.append("")

            # DSMB rate by phase
            sections.append("### DSMB Rate by Phase\n")
            sections.append("| Phase | Has DSMB | Total | % DSMB |")
            sections.append("|---|---:|---:|---:|")
            for phase in phase_order:
                phase_mask = trials_df["phase_normalized"] == phase
                if phase_mask.sum() == 0:
                    continue
                n_ph = int(phase_mask.sum())
                n_dmc_ph = int((phase_mask & dmc_col.fillna(False).astype(bool)).sum())
                pct = n_dmc_ph / n_ph * 100 if n_ph > 0 else 0
                sections.append(f"| {phase} | {n_dmc_ph} | {n_ph} | {pct:.0f}% |")
            sections.append("")
    else:
        sections.append("*Regulatory signal data not available. Re-run compile_trials.py with Phase 2B to populate.*\n")

    # ==========================================
    # 24. DATA NOTES
    # ==========================================
    sections.append("---\n")
    sections.append("## Data Notes\n")

    sections.append(f"- **Source:** ClinicalTrials.gov API v2 (free, no authentication)")
    sections.append(f"- **Query date:** {now.strftime('%Y-%m-%d')}")

    if parameters:
        conditions = parameters.get("conditions", [])
        if conditions:
            sections.append(f"- **Conditions searched:** {', '.join(conditions)}")
        statuses = parameters.get("statuses", [])
        if statuses:
            sections.append(f"- **Status filter:** {', '.join(_format_status(s) for s in statuses)}")
        highlight_mech = parameters.get("highlight_mechanism")
        if highlight_mech:
            sections.append(f"- **Mechanism focus:** {highlight_mech}")
        highlight_sponsor = parameters.get("highlight_sponsor")
        if highlight_sponsor:
            sections.append(f"- **Sponsor focus:** {highlight_sponsor}")

    unclassified = trials_df[trials_df["mechanism"].isin(["Unclassified", "Other Biologic", "Small Molecule (Other)"])]
    if len(unclassified) > 0:
        sections.append(
            f"- **Unclassified trials:** {len(unclassified)} ({len(unclassified)/n_total*100:.0f}% of total) "
            f"\u2014 trials with generic or unrecognized interventions"
        )
    sections.append(f"- **Classification method:** Pattern matching on intervention names, descriptions, and trial titles")
    sections.append(f"- **Limitations:** Mechanism classification is automated and may misclassify novel or ambiguous interventions. "
                    f"Completion dates are sponsor-reported estimates and may change.")
    if "enrollment_clean" in trials_df.columns:
        n_outliers = int(_safe_col(trials_df, "enrollment_outlier", default=False).fillna(False).astype(bool).sum())
        if n_outliers > 0:
            sections.append(f"- **Enrollment cleaning:** {n_outliers} enrollment outlier(s) flagged and excluded from summary statistics")
    sections.append("")

    # ==========================================
    # BUILD AND WRITE
    # ==========================================
    report = "\n".join(sections)

    with open(output_file, "w") as f:
        f.write(report)

    print(f"\u2713 Markdown report generated: {output_file}")
    return report


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def _safe_col_val(row, col, default=""):
    """Safely get a value from a row (Series), returning default if key missing."""
    try:
        val = row[col]
        if pd.isna(val):
            return default
        return val
    except (KeyError, IndexError):
        return default


def _get_enrollment(trial):
    """
    Get enrollment from a trial row, preferring enrollment_clean over enrollment.

    Returns the numeric value or NaN.
    """
    for col in ("enrollment_clean", "enrollment"):
        try:
            val = trial[col]
            if pd.notna(val) and val > 0:
                return val
        except (KeyError, IndexError):
            continue
    return np.nan


def _format_status(status):
    """Convert API status to readable format."""
    status_map = {
        "RECRUITING": "Recruiting",
        "ACTIVE_NOT_RECRUITING": "Active, not recruiting",
        "NOT_YET_RECRUITING": "Not yet recruiting",
        "ENROLLING_BY_INVITATION": "Enrolling by invitation",
        "COMPLETED": "Completed",
        "SUSPENDED": "Suspended",
        "TERMINATED": "Terminated",
        "WITHDRAWN": "Withdrawn",
    }
    return status_map.get(status, status)


def _format_date(date_str):
    """Format date string to readable format, return dash if empty."""
    if not date_str or str(date_str) == "nan":
        return "\u2014"
    # Clean up: just return the date as-is but shorter
    date_str = str(date_str).strip()
    if len(date_str) > 10:
        date_str = date_str[:10]
    return date_str if date_str else "\u2014"


def _time_to_readout(completion_date):
    """Calculate time from now to expected completion."""
    if not completion_date or str(completion_date) == "nan":
        return "\u2014"
    try:
        date_str = str(completion_date).strip()
        # Parse various date formats
        for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
            try:
                dt = datetime.strptime(date_str[:len(fmt.replace("%", "").replace("-", "") + date_str[:4])], fmt)
                break
            except ValueError:
                continue
        else:
            # Try simple parse
            if len(date_str) >= 7:
                dt = datetime.strptime(date_str[:7], "%Y-%m")
            elif len(date_str) >= 4:
                dt = datetime.strptime(date_str[:4], "%Y")
            else:
                return "\u2014"

        delta = dt - datetime.now()
        months = delta.days / 30.44
        if months < 0:
            return "Overdue"
        elif months < 1:
            return "<1 month"
        elif months < 12:
            return f"~{int(months)} months"
        else:
            years = months / 12
            return f"~{years:.1f} years"
    except (ValueError, TypeError):
        return "\u2014"


def _get_upcoming_readouts(trials_df, months=18):
    """Get trials with completion dates within the next N months."""
    now = datetime.now()
    cutoff = now + timedelta(days=months * 30.44)
    upcoming = []

    for _, trial in trials_df.iterrows():
        cd = trial.get("completion_date", "")
        if not cd or str(cd) == "nan":
            continue
        try:
            date_str = str(cd).strip()
            if len(date_str) >= 10:
                dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
            elif len(date_str) >= 7:
                dt = datetime.strptime(date_str[:7], "%Y-%m")
            elif len(date_str) >= 4:
                dt = datetime.strptime(date_str[:4], "%Y")
            else:
                continue

            if now <= dt <= cutoff:
                upcoming.append(trial)
        except (ValueError, TypeError):
            continue

    if not upcoming:
        return pd.DataFrame()

    result = pd.DataFrame(upcoming)
    # Sort by completion date
    result = result.sort_values("completion_date")
    return result


def _extract_drug_table(df, indication_cats=None):
    """Extract a drug-level pipeline table from trials DataFrame."""
    records = []
    seen_drugs = set()

    for _, trial in df.iterrows():
        drugs_str = trial.get("drug_names_str", "")
        if not drugs_str or str(drugs_str) == "nan":
            continue

        drugs = [d.strip() for d in str(drugs_str).split(";") if d.strip()]

        for drug in drugs:
            # Skip placebo, generic names
            drug_lower = drug.lower()
            if any(skip in drug_lower for skip in ["placebo", "saline", "sodium chloride", "standard of care",
                                                     "standard care", "usual care", "sham", "no intervention"]):
                continue

            # Deduplicate by drug + sponsor
            key = (drug_lower, trial.get("sponsor_normalized", ""))
            if key in seen_drugs:
                continue
            seen_drugs.add(key)

            enrollment_val = _get_enrollment(trial)
            enrollment_str = f"{int(enrollment_val):,}" if pd.notna(enrollment_val) and enrollment_val > 0 else "\u2014"
            indication = _extract_indication(trial.get("conditions_str", ""), indication_cats=indication_cats)
            completion_str = _format_date(trial.get("completion_date", ""))

            records.append({
                "drug": drug[:40],
                "mechanism": trial.get("mechanism", ""),
                "sponsor": trial.get("sponsor_normalized", ""),
                "phase": trial.get("phase_normalized", ""),
                "status": _format_status(trial.get("overall_status", "")),
                "indication": indication,
                "enrollment": enrollment_str,
                "completion": completion_str,
                "phase_numeric": trial.get("phase_numeric", 0),
            })

    if not records:
        return pd.DataFrame()

    result = pd.DataFrame(records)
    result = result.sort_values(["phase_numeric", "drug"], ascending=[False, True])
    return result.drop(columns=["phase_numeric"])


def _get_unique_drugs(df):
    """Extract unique meaningful drug names from a trials DataFrame."""
    drugs = set()
    skip_terms = {"placebo", "saline", "sodium chloride", "standard of care", "standard care",
                  "usual care", "sham", "no intervention", "data collection"}
    for _, trial in df.iterrows():
        drugs_str = trial.get("drug_names_str", "")
        if not drugs_str or str(drugs_str) == "nan":
            continue
        for d in str(drugs_str).split(";"):
            d = d.strip()
            if d and not any(skip in d.lower() for skip in skip_terms):
                drugs.add(d)
    return sorted(drugs)


def _extract_indication(conditions_str, indication_cats=None):
    """
    Extract simplified indication from conditions string.

    Parameters
    ----------
    conditions_str : str
        The trial's conditions string.
    indication_cats : list of dict, optional
        Config-driven indication categories. Each dict has 'label',
        'pattern' (substring match), and optionally 'is_default'.
        When None, falls back to returning the raw conditions (truncated).
    """
    if not conditions_str or str(conditions_str) == "nan":
        return "\u2014"
    conditions_lower = str(conditions_str).lower()

    if indication_cats:
        matched = []
        for cat in indication_cats:
            if cat.get("is_default"):
                continue
            if cat.get("pattern") and cat["pattern"].lower() in conditions_lower:
                matched.append(cat["label"])
        if matched:
            return " + ".join(matched)
        # Check for default category
        for cat in indication_cats:
            if cat.get("is_default"):
                return cat["label"]
        return "Other"
    else:
        # No config: return truncated conditions
        raw = str(conditions_str).strip()
        return raw[:40] if len(raw) > 40 else raw if raw else "Other"


def _count_indications(df, indication_cats=None):
    """
    Count trials per indication category.

    Parameters
    ----------
    df : pd.DataFrame
        Trials DataFrame.
    indication_cats : list of dict, optional
        Config-driven indication categories. When None, falls back to
        counting top conditions from the data.

    Returns
    -------
    list of (label, full_name, count) tuples if indication_cats provided,
    or (uc_count, cd_count, other_count) tuple for backward compatibility.
    """
    if indication_cats:
        counts = []
        matched_indices = set()
        for cat in indication_cats:
            if cat.get("is_default"):
                continue
            label = cat["label"]
            full_name = cat.get("full_name", label)
            pattern = cat.get("pattern", "").lower()
            cat_count = 0
            for idx, trial in df.iterrows():
                cond = str(trial.get("conditions_str", "")).lower()
                if pattern and pattern in cond:
                    cat_count += 1
                    matched_indices.add(idx)
            counts.append((label, full_name, cat_count))
        # Handle default category (remaining unmatched)
        for cat in indication_cats:
            if cat.get("is_default"):
                label = cat["label"]
                full_name = cat.get("full_name", label)
                default_count = len(df) - len(matched_indices)
                counts.append((label, full_name, default_count))
                break
        return counts
    else:
        # Fallback: no config, return top conditions from data
        cond_counts = {}
        for _, trial in df.iterrows():
            cond = str(trial.get("conditions_str", "")).strip()
            if cond and cond != "nan":
                # Split semicolon-separated conditions
                for c in cond.split(";"):
                    c = c.strip()
                    if c:
                        cond_counts[c] = cond_counts.get(c, 0) + 1
        # Return as list of (label, full_name, count) tuples
        sorted_conds = sorted(cond_counts.items(), key=lambda x: x[1], reverse=True)
        return [(c, c, n) for c, n in sorted_conds[:10]]


def _add_indication_split(sections, df, indication_cats=None):
    """Add indication split analysis to sections."""
    counts = _count_indications(df, indication_cats=indication_cats)
    total = len(df)
    for entry in counts:
        label, full_name, cnt = entry
        display = f"{full_name} ({label})" if label != full_name else label
        if total > 0:
            sections.append(f"- {display}: {cnt} ({cnt/total*100:.0f}%)")
        else:
            sections.append(f"- {display}: 0")
    sections.append("")

