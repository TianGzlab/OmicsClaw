"""
Main diff analysis workflow orchestrator for ChIP-Atlas.

Uses the official ChIP-Atlas Diff Analysis API to compare two sets of
experiments and identify differential peak regions (DPR via edgeR) or
differentially methylated regions (DMR via metilene).

API: POST https://dtn1.ddbj.nig.ac.jp/wabi/chipatlas/
Reference: Zou et al. 2024 (NAR), https://chip-atlas.org
"""

import os

try:
    from scripts.query_chipatlas_api import (
        submit_diff_job,
        poll_job_status,
        retrieve_zip_results,
        VALID_ANALYSIS_TYPES,
    )
    from scripts.parse_bed_results import parse_bed_results, summarize_regions
    from scripts.filter_regions import (
        filter_regions,
        filter_standard_chromosomes,
        filter_min_region_size,
    )
    from scripts.qc_checks import run_qc_checks
except ImportError:
    from query_chipatlas_api import (
        submit_diff_job,
        poll_job_status,
        retrieve_zip_results,
        VALID_ANALYSIS_TYPES,
    )
    from parse_bed_results import parse_bed_results, summarize_regions
    from filter_regions import (
        filter_regions,
        filter_standard_chromosomes,
        filter_min_region_size,
    )
    from qc_checks import run_qc_checks


def run_diff_workflow(
    experiments_a,
    experiments_b,
    genome="hg38",
    analysis_type="diffbind",
    title="diff_analysis",
    description_a="group_A",
    description_b="group_B",
    min_score=0,
    min_region_size=0,
    direction_filter=None,
    design_caveats=None,
    output_dir="diff_analysis_results",
):
    """
    Run complete ChIP-Atlas differential analysis workflow.

    Parameters
    ----------
    experiments_a : list of str
        Experiment IDs for group A (minimum 2)
    experiments_b : list of str
        Experiment IDs for group B (minimum 2)
    genome : str
        Genome assembly (hg38, hg19, mm10, mm9, rn6, dm6, dm3, ce11, ce10, sacCer3)
    analysis_type : str
        'diffbind' for DPR (ChIP/ATAC/DNase-seq) or 'dmr' for DMR (Bisulfite-seq)
    title : str
        Analysis title
    description_a : str
        Label for dataset A
    description_b : str
        Label for dataset B
    min_score : int
        Post-filter: minimum BED score (0-1000)
    min_region_size : int
        Post-filter: minimum region size in bp
    direction_filter : str or None
        Post-filter: 'A_enriched' or 'B_enriched'
    output_dir : str
        Output directory for results

    Returns
    -------
    dict
        {
            'diff_regions': pd.DataFrame,
            'experiments_a': list,
            'experiments_b': list,
            'raw_files': dict,
            'log_content': str,
            'parameters': dict,
        }

    Verification
    ------------
    Prints "✓ Diff analysis completed successfully!" when done
    """
    # Validate inputs
    if not experiments_a or len(experiments_a) < 2:
        raise ValueError("Group A requires at least 2 experiment IDs")
    if not experiments_b or len(experiments_b) < 2:
        raise ValueError("Group B requires at least 2 experiment IDs")

    os.makedirs(output_dir, exist_ok=True)

    analysis_label = VALID_ANALYSIS_TYPES.get(analysis_type, analysis_type)

    print("\n" + "=" * 70)
    print("CHIP-ATLAS DIFF ANALYSIS WORKFLOW")
    print("=" * 70 + "\n")

    # Step 1: Submit to ChIP-Atlas API
    print("Step 1: Submitting experiment sets to ChIP-Atlas Diff Analysis API...")
    print(f"   Analysis type: {analysis_label}")
    print(f"   Genome: {genome}")
    print(f"   Group A ({description_a}): {len(experiments_a)} experiments")
    for exp_id in experiments_a:
        print(f"      - {exp_id}")
    print(f"   Group B ({description_b}): {len(experiments_b)} experiments")
    for exp_id in experiments_b:
        print(f"      - {exp_id}")

    request_id = submit_diff_job(
        experiments_a=experiments_a,
        experiments_b=experiments_b,
        genome=genome,
        analysis_type=analysis_type,
        title=title,
        description_a=description_a,
        description_b=description_b,
    )

    print(f"   Request ID: {request_id}")
    print("✓ Job submitted successfully")

    # Step 2: Poll for completion
    print("\nStep 2: Waiting for analysis to complete...")
    print("   (Diff analysis typically takes 2-10 minutes depending on dataset size)")

    status = poll_job_status(request_id, timeout=900, poll_interval=15)
    print(f"✓ Job completed (status: {status})")

    # Step 3: Retrieve and parse results
    print("\nStep 3: Retrieving results...")

    extracted = retrieve_zip_results(request_id, output_dir)
    print(f"   Extracted {len(extracted)} files from ZIP archive:")
    for key, path in extracted.items():
        size = os.path.getsize(path)
        print(f"      {key}: {os.path.basename(path)} ({size:,} bytes)")

    # Read log content if available
    log_content = ""
    if "log" in extracted:
        with open(extracted["log"], "r") as f:
            log_content = f.read()

    # Parse BED results
    print("\n   Parsing BED results...")
    results_df = parse_bed_results(extracted["bed"])
    n_total_raw = len(results_df)
    n_sig_raw = int(results_df["significant"].sum()) if "significant" in results_df.columns else 0
    print(f"✓ Parsed {n_total_raw} differential regions ({n_sig_raw} significant at FDR < 0.05)")

    # QC checks on unfiltered data
    qc_warnings = run_qc_checks(
        results_df,
        n_samples_a=len(experiments_a),
        n_samples_b=len(experiments_b),
        analysis_type=analysis_type,
        genome=genome,
    )

    # Preserve unfiltered data for reference
    unfiltered_df = results_df.copy()
    n_before_qc = len(results_df)

    # Default QC filtering: remove non-standard contigs and tiny regions
    print("\n   Applying default QC filters...")
    results_df = filter_standard_chromosomes(results_df, genome=genome)
    results_df = filter_min_region_size(results_df, min_size=10)
    n_after_qc = len(results_df)

    if n_before_qc != n_after_qc:
        n_sig_after_qc = int(results_df["significant"].sum()) if "significant" in results_df.columns else 0
        n_sig_removed = n_sig_raw - n_sig_after_qc
        msg = f"   QC filtering: {n_before_qc} → {n_after_qc} regions"
        if n_sig_removed > 0:
            msg += f" ({n_sig_removed} significant regions removed)"
        print(msg)

    # Step 4: Apply user-requested post-filters
    if min_score > 0 or min_region_size > 0 or direction_filter:
        print("\nStep 4: Applying additional filters...")
        results_df = filter_regions(
            results_df,
            min_score=min_score,
            min_region_size=min_region_size,
            direction_filter=direction_filter,
        )
        print(f"✓ Filtered to {len(results_df)} regions")
    else:
        print("\nStep 4: No additional user filters applied")

    # Post-QC detailed summary
    summarize_regions(results_df)

    # Summary
    n_a_enriched = (results_df["direction"] == "A_enriched").sum() if len(results_df) > 0 else 0
    n_b_enriched = (results_df["direction"] == "B_enriched").sum() if len(results_df) > 0 else 0
    n_sig_final = int(results_df["significant"].sum()) if len(results_df) > 0 and "significant" in results_df.columns else 0

    print(f"\n   === Results Summary (post-QC) ===")
    print(f"   Total differential regions: {len(results_df)}")
    print(f"   Significant (FDR < 0.05): {n_sig_final}")
    print(f"   Enriched in {description_a}: {n_a_enriched}")
    print(f"   Enriched in {description_b}: {n_b_enriched}")

    if n_sig_final > 0 and "direction" in results_df.columns:
        sig_df = results_df[results_df["significant"]]
        n_sig_a = int((sig_df["direction"] == "A_enriched").sum())
        n_sig_b = int((sig_df["direction"] == "B_enriched").sum())
        print(f"   Significant in {description_a}: {n_sig_a}")
        print(f"   Significant in {description_b}: {n_sig_b}")

    if len(results_df) > 0 and "region_size" in results_df.columns:
        median_size = results_df["region_size"].median()
        print(f"   Median region size: {median_size:.0f} bp")

    print("\n✓ Diff analysis completed successfully!")
    print("=" * 70 + "\n")

    return {
        "diff_regions": results_df,
        "diff_regions_unfiltered": unfiltered_df,
        "qc_warnings": qc_warnings,
        "experiments_a": experiments_a,
        "experiments_b": experiments_b,
        "raw_files": extracted,
        "log_content": log_content,
        "parameters": {
            "genome": genome,
            "analysis_type": analysis_type,
            "title": title,
            "description_a": description_a,
            "description_b": description_b,
            "min_score": min_score,
            "min_region_size": min_region_size,
            "direction_filter": direction_filter,
            "design_caveats": design_caveats or [],
        },
    }

