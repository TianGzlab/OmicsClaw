"""
Export all landscape results (Step 4).

Exports:
1. analysis_object.pkl - Complete results for downstream use
2. trials_all.csv - All trials with mechanism classification
3. trials_by_mechanism.csv - Mechanism x phase cross-tabulation
4. trials_by_sponsor.csv - Sponsor summary
5. trials_filtered.csv - Filtered subset (if applicable)
6. landscape_report.md - Human-readable summary (24 sections)
7. landscape_report.pdf - Publication-quality PDF report
8. landscape_supplementary.png - Supplementary 4-panel visualization
"""

import os
import pickle
from datetime import datetime

from scripts.generate_report import generate_report
from scripts.generate_pdf_report import generate_pdf_report


def export_all(trials_df, parameters=None, output_dir="landscape_results", config=None):
    """
    Export all landscape results with pickle object.

    Parameters
    ----------
    trials_df : pd.DataFrame
        Compiled trials from compile_trials().
    parameters : dict, optional
        Query parameters and metadata.
    output_dir : str
        Output directory.
    config : dict or None
        Disease config for report generation.

    Returns
    -------
    None

    Verification
    ------------
    Prints "=== Export Complete ===" when done.
    """
    if parameters is None:
        parameters = {}

    os.makedirs(output_dir, exist_ok=True)

    print("\n" + "=" * 70)
    print("EXPORTING RESULTS")
    print("=" * 70 + "\n")

    # 1. Save analysis object as pickle (CRITICAL for downstream skills)
    print("1. Saving analysis objects for downstream use...")

    # Build enriched analysis object with new Phase 2 fields
    analysis_object = {
        "trials_df": trials_df,
        "parameters": parameters,
        "n_total": len(trials_df),
        "n_by_mechanism": trials_df["mechanism"].value_counts().to_dict(),
        "n_by_phase": trials_df["phase_normalized"].value_counts().to_dict(),
        "n_by_sponsor": trials_df["sponsor_normalized"].value_counts().to_dict(),
        "n_industry": int(trials_df["is_industry"].sum()),
        "unique_mechanisms": int(trials_df["mechanism"].nunique()),
        "unique_sponsors": int(trials_df["sponsor_normalized"].nunique()),
        "mechanism_phase_matrix": _build_mechanism_phase_matrix(trials_df),
        "timestamp": datetime.now().isoformat(),
    }

    # Add Phase 2B enrichment stats if available
    if "n_countries" in trials_df.columns:
        analysis_object["n_with_geographic_data"] = int((trials_df["n_countries"] > 0).sum())
    if "study_design_category" in trials_df.columns:
        analysis_object["n_by_design"] = trials_df["study_design_category"].value_counts().to_dict()
    if "is_combination" in trials_df.columns:
        analysis_object["n_combination"] = int(trials_df["is_combination"].sum())
    if "is_pediatric" in trials_df.columns:
        analysis_object["n_pediatric"] = int(trials_df["is_pediatric"].sum())
    if "is_biosimilar" in trials_df.columns:
        analysis_object["n_biosimilar"] = int(trials_df["is_biosimilar"].sum())
    if "enrollment_clean" in trials_df.columns:
        analysis_object["enrollment_outliers"] = int(trials_df["enrollment_outlier"].sum())

    pickle_path = os.path.join(output_dir, "analysis_object.pkl")
    with open(pickle_path, "wb") as f:
        pickle.dump(analysis_object, f)

    print(f"   Saved: {pickle_path}")
    print("   (Load with: import pickle; obj = pickle.load(open('analysis_object.pkl', 'rb')))")

    # 2. Export all trials to CSV
    print("\n2. Exporting trial data...")

    all_path = os.path.join(output_dir, "trials_all.csv")
    trials_df.to_csv(all_path, index=False)
    print(f"   Saved: {all_path} ({len(trials_df)} trials)")

    # 3. Export mechanism x phase cross-tabulation
    print("\n3. Exporting mechanism summary...")

    ct = _build_mechanism_phase_matrix(trials_df, as_df=True)
    mech_path = os.path.join(output_dir, "trials_by_mechanism.csv")
    ct.to_csv(mech_path)
    print(f"   Saved: {mech_path}")

    # 4. Export sponsor summary
    print("\n4. Exporting sponsor summary...")

    sponsor_summary = (
        trials_df.groupby("sponsor_normalized")
        .agg(
            trials=("nct_id", "count"),
            mechanisms=("mechanism", "nunique"),
            industry=("is_industry", "first"),
        )
        .sort_values("trials", ascending=False)
    )
    sponsor_path = os.path.join(output_dir, "trials_by_sponsor.csv")
    sponsor_summary.to_csv(sponsor_path)
    print(f"   Saved: {sponsor_path}")

    # 5. Export filtered subset if mechanism or sponsor filter was used
    mechanism_filter = parameters.get("highlight_mechanism")
    sponsor_filter = parameters.get("highlight_sponsor")

    if mechanism_filter:
        filtered = trials_df[trials_df["mechanism"] == mechanism_filter]
        if len(filtered) > 0:
            filtered_path = os.path.join(output_dir, "trials_filtered.csv")
            filtered.to_csv(filtered_path, index=False)
            print(f"\n5. Saved filtered subset: {filtered_path} ({len(filtered)} trials for {mechanism_filter})")

    if sponsor_filter:
        filtered = trials_df[
            trials_df["sponsor_normalized"].str.lower().str.contains(sponsor_filter.lower(), na=False)
        ]
        if len(filtered) > 0:
            sponsor_filtered_path = os.path.join(output_dir, "trials_sponsor_filtered.csv")
            filtered.to_csv(sponsor_filtered_path, index=False)
            print(f"   Saved sponsor filter: {sponsor_filtered_path} ({len(filtered)} trials for {sponsor_filter})")

    # 6. Generate summary reports (Markdown + PDF)
    step_num = 5 if not mechanism_filter else 6
    print(f"\n{step_num}. Generating summary reports...")

    report_path = os.path.join(output_dir, "landscape_report.md")
    generate_report(trials_df, parameters=parameters, output_file=report_path, config=config)
    print(f"   Saved: {report_path}")

    # 7. Generate PDF report with embedded visualization
    print(f"\n{step_num + 1}. Generating PDF report...")
    pdf_path = os.path.join(output_dir, "landscape_report.pdf")
    plot_image_path = os.path.join(output_dir, "landscape_overview.png")
    if not os.path.exists(plot_image_path):
        plot_image_path = None

    try:
        generate_pdf_report(
            trials_df,
            parameters=parameters,
            output_file=pdf_path,
            plot_image_path=plot_image_path,
            config=config,
        )
        print(f"   Saved: {pdf_path}")
    except Exception as e:
        print(f"   PDF generation failed: {e}")
        print("   (Markdown report still available)")

    # 8. Generate supplementary visualizations (Phase 2I)
    print(f"\n{step_num + 2}. Generating supplementary visualizations...")
    supp_png_path = None
    try:
        from scripts.generate_landscape_plots import generate_supplementary_plots
        supp_png_path = generate_supplementary_plots(trials_df, output_dir=output_dir, config=config)
    except Exception as e:
        print(f"   Supplementary plots failed: {e}")
        print("   (Main plots and reports still available)")

    # Final verification
    print("\n" + "=" * 70)
    print("=== Export Complete ===")
    print("=" * 70)
    print(f"\nAll results saved to: {output_dir}/")
    print(f"  - analysis_object.pkl (for downstream analysis)")
    print(f"  - trials_all.csv ({len(trials_df)} trials)")
    print(f"  - trials_by_mechanism.csv (mechanism x phase)")
    print(f"  - trials_by_sponsor.csv (sponsor summary)")
    if mechanism_filter:
        print(f"  - trials_filtered.csv ({mechanism_filter} subset)")
    print(f"  - landscape_report.md (human-readable summary)")
    if os.path.exists(pdf_path):
        print(f"  - landscape_report.pdf (publication-quality PDF)")
    if supp_png_path and os.path.exists(supp_png_path):
        print(f"  - landscape_supplementary.png (supplementary 4-panel)")
    print()


def _build_mechanism_phase_matrix(trials_df, as_df=False):
    """Build mechanism x phase cross-tabulation."""
    import pandas as pd

    phase_order = ["Phase 1", "Phase 1/2", "Phase 2", "Phase 2/3", "Phase 3", "Phase 4"]
    ct = pd.crosstab(trials_df["mechanism"], trials_df["phase_normalized"])
    ct = ct.reindex(columns=[p for p in phase_order if p in ct.columns], fill_value=0)
    ct["Total"] = ct.sum(axis=1)
    ct = ct.sort_values("Total", ascending=False)

    if as_df:
        return ct
    return ct.to_dict()


if __name__ == "__main__":
    import pandas as pd

    # Quick test with mock data
    mock_df = pd.DataFrame({
        "nct_id": ["NCT001", "NCT002", "NCT003"],
        "brief_title": ["Vedolizumab in UC", "Risankizumab in CD", "TEV-48574 in UC"],
        "official_title": ["", "", ""],
        "lead_sponsor": ["Takeda", "AbbVie", "Takeda"],
        "sponsor_normalized": ["Takeda", "AbbVie", "Takeda"],
        "sponsor_class": ["INDUSTRY", "INDUSTRY", "INDUSTRY"],
        "is_industry": [True, True, True],
        "mechanism": ["Anti-Integrin", "Anti-IL-23 (p19)", "Anti-TL1A"],
        "drug_names_str": ["Vedolizumab", "Risankizumab", "TEV-48574"],
        "phase_normalized": ["Phase 3", "Phase 3", "Phase 2"],
        "phase_numeric": [3, 3, 2],
        "overall_status": ["RECRUITING", "RECRUITING", "RECRUITING"],
        "conditions_str": ["Ulcerative Colitis", "Crohn's Disease", "Ulcerative Colitis"],
        "enrollment": [500, 400, 200],
        "start_date": ["2022-01", "2023-03", "2024-01"],
        "start_year": [2022, 2023, 2024],
        "completion_date": ["", "", ""],
        "study_type": ["INTERVENTIONAL", "INTERVENTIONAL", "INTERVENTIONAL"],
    })

    export_all(mock_df, output_dir="/tmp/test_export")

