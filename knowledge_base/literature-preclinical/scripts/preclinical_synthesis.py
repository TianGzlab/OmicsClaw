"""
Preclinical Synthesis and Export Module

Aggregate experiment extraction results across papers and export all outputs.

Sub-modules:
    narrative_synthesis — direction analysis, agreements/disagreements, gaps
    report_generation   — markdown report, PDF conversion, URL helpers
"""

import os
import pickle
from collections import Counter
from datetime import datetime
from typing import List, Dict
import pandas as pd

# Import from sub-modules
from narrative_synthesis import generate_narrative
from report_generation import generate_markdown_report, generate_pdf_report


def synthesize_preclinical(
    results: List[Dict],
    experiments: List[Dict],
    target: str = "",
) -> Dict:
    """
    Synthesize experiment extraction results across all papers.

    Parameters
    ----------
    results : List[Dict]
        Original search results (with abstracts for modality detection)
    experiments : List[Dict]
        Experiment extraction dicts from extract_all_experiments()
    target : str
        Target name for therapeutic direction inference

    Returns
    -------
    Dict
        Synthesis summary with frequency counts and breakdowns
    """
    print("\n" + "=" * 70)
    print("SYNTHESIZING PRECLINICAL FINDINGS")
    print("=" * 70)

    # Experiment type breakdown
    type_counter = Counter(e["experiment_type"] for e in experiments)
    print(f"\n  Experiment type breakdown:")
    for etype, count in type_counter.most_common():
        print(f"    {etype}: {count}")

    # Cell line frequency
    cell_line_counter = Counter()
    for e in experiments:
        if e["cell_lines"]:
            for cl in e["cell_lines"].split("; "):
                cl = cl.strip()
                if cl:
                    cell_line_counter[cl] += 1

    print(f"\n  Top cell lines ({len(cell_line_counter)} unique):")
    for cl, count in cell_line_counter.most_common(10):
        print(f"    {cl}: {count} papers")

    # Assay frequency
    assay_counter = Counter()
    for e in experiments:
        if e["assays"]:
            for assay in e["assays"].split("; "):
                assay = assay.strip()
                if assay:
                    assay_counter[assay] += 1

    print(f"\n  Top assay types ({len(assay_counter)} unique):")
    for assay, count in assay_counter.most_common(10):
        print(f"    {assay}: {count} papers")

    # Animal model frequency
    model_counter = Counter()
    for e in experiments:
        if e["animal_models"]:
            for model in e["animal_models"].split("; "):
                model = model.strip()
                if model:
                    model_counter[model] += 1

    print(f"\n  Top animal models ({len(model_counter)} unique):")
    for model, count in model_counter.most_common(10):
        print(f"    {model}: {count} papers")

    # Endpoint frequency
    endpoint_counter = Counter()
    for e in experiments:
        if e["endpoints"]:
            for ep in e["endpoints"].split("; "):
                ep = ep.strip()
                if ep:
                    endpoint_counter[ep] += 1

    print(f"\n  Top endpoints ({len(endpoint_counter)} unique):")
    for ep, count in endpoint_counter.most_common(10):
        print(f"    {ep}: {count} papers")

    # Papers with both in vitro and in vivo
    both_papers = [e for e in experiments if e["experiment_type"] == "both"]
    print(f"\n  Papers with both in vitro + in vivo: {len(both_papers)}")

    # Publication year distribution
    year_counter = Counter()
    for e in experiments:
        year = e.get("publication_date", "")[:4]
        if year.isdigit():
            year_counter[year] += 1

    synthesis = {
        "total_papers": len(experiments),
        "experiment_type_breakdown": dict(type_counter),
        "cell_line_frequency": dict(cell_line_counter.most_common(30)),
        "assay_frequency": dict(assay_counter.most_common(20)),
        "animal_model_frequency": dict(model_counter.most_common(15)),
        "endpoint_frequency": dict(endpoint_counter.most_common(15)),
        "year_distribution": dict(sorted(year_counter.items())),
        "papers_with_both": len(both_papers),
    }

    # Generate narrative synthesis (delegated to narrative_synthesis module)
    narrative = generate_narrative(synthesis, experiments, results, target)
    synthesis["narrative"] = narrative

    print(f"\n  Narrative synthesis:")
    print(f"    Agreements:    {len(narrative['agreements'])} point(s)")
    print(f"    Disagreements: {len(narrative['disagreements'])} point(s)")
    print(f"    Gaps:          {len(narrative['gaps'])} point(s)")
    td = narrative.get("therapeutic_direction", [])
    if td:
        print(f"    Therapeutic:   {td[0][:80]}...")

    print(f"\n\u2713 Synthesis completed successfully!")
    return synthesis


def export_all(
    results: List[Dict],
    experiments: List[Dict],
    synthesis: Dict,
    target: str = "",
    disease: str = "",
    output_dir: str = "preclinical_results"
) -> None:
    """
    Export all preclinical analysis results.

    Saves:
    1. preclinical_search_results.csv - All papers with metadata
    2. experiment_extraction.csv - Per-paper experiment details
    3. preclinical_synthesis_report.md - Structured markdown report
    3b. preclinical_synthesis_report.pdf - PDF version (if deps available)
    4. analysis_object.pkl - Pickle of all objects for downstream use

    Parameters
    ----------
    results : List[Dict]
        Original search results
    experiments : List[Dict]
        Experiment extraction results
    synthesis : Dict
        Synthesis summary
    target : str
        Target name for report header
    disease : str
        Disease name for report header
    output_dir : str
        Output directory

    Verification
    ------------
    Prints "=== Export Complete ==="
    """
    os.makedirs(output_dir, exist_ok=True)

    print("\n" + "=" * 70)
    print("EXPORTING RESULTS")
    print("=" * 70)

    # 1. Search results CSV (may already exist from Step 1, re-save for completeness)
    search_csv = os.path.join(output_dir, "preclinical_search_results.csv")
    if results:
        df_results = pd.DataFrame(results)
        column_order = [
            "source", "pmid", "doi", "title", "authors", "journal",
            "publication_date", "keywords", "abstract", "url"
        ]
        df_results = df_results[[c for c in column_order if c in df_results.columns]]
        df_results.to_csv(search_csv, index=False, encoding="utf-8")
        print(f"  1. Saved: {search_csv} ({len(df_results)} papers)")

    # 2. Experiment extraction CSV
    extract_csv = os.path.join(output_dir, "experiment_extraction.csv")
    if experiments:
        df_exp = pd.DataFrame(experiments)
        df_exp.to_csv(extract_csv, index=False, encoding="utf-8")
        print(f"  2. Saved: {extract_csv} ({len(df_exp)} rows)")

    # 3. Markdown synthesis report (delegated to report_generation module)
    report_path = os.path.join(output_dir, "preclinical_synthesis_report.md")
    generate_markdown_report(results, experiments, synthesis, target, disease, report_path)
    print(f"  3. Saved: {report_path}")

    # 3b. PDF report (reportlab — structured with Title, Intro, Methods, Results, Conclusions)
    try:
        from generate_report import generate_report
        pdf_result = generate_report(
            results, experiments, synthesis,
            target=target, disease=disease,
            output_dir=output_dir,
            output_file=os.path.join(output_dir, "preclinical_synthesis_report.pdf"),
        )
        if pdf_result:
            print(f"  3b. PDF report generated (reportlab)")
        else:
            # reportlab not installed — try weasyprint fallback
            pdf_path = os.path.join(output_dir, "preclinical_synthesis_report.pdf")
            if generate_pdf_report(report_path, pdf_path):
                print(f"  3b. Saved: {pdf_path} (weasyprint fallback)")
            else:
                print(f"  3b. PDF skipped (install: pip install reportlab)")
    except Exception as e:
        print(f"  3b. PDF generation skipped: {e}")
        print(f"      (Markdown report still available)")

    # 4. Analysis object (pickle)
    pkl_path = os.path.join(output_dir, "analysis_object.pkl")
    analysis_object = {
        "search_results": results,
        "experiments": experiments,
        "synthesis": synthesis,
        "parameters": {
            "target": target,
            "disease": disease,
            "n_papers": len(results),
            "export_date": datetime.now().isoformat(),
        }
    }
    with open(pkl_path, "wb") as f:
        pickle.dump(analysis_object, f)
    print(f"  4. Saved: {pkl_path}")
    print(f"     (Load with: import pickle; obj = pickle.load(open('{pkl_path}', 'rb')))")

    print(f"\n=== Export Complete ===")

