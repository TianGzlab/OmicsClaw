"""
Query the ChIP-Atlas Enrichment Analysis API.

Submits gene lists to the official ChIP-Atlas WABI API, which performs
Fisher's exact test enrichment analysis against all public ChIP-seq experiments.
Results include Benjamini-Hochberg corrected Q-values.

API endpoint: POST https://dtn1.ddbj.nig.ac.jp/wabi/chipatlas/
Reference: Zou et al. 2024 (NAR), https://chip-atlas.org
"""

import time
import requests
import pandas as pd


# Valid antigen classes from ChIP-Atlas
VALID_ANTIGEN_CLASSES = [
    "Histone",
    "RNA polymerase",
    "TFs and others",
    "Input control",
    "ATAC-Seq",
    "DNase-seq",
    "Bisulfite-Seq",
    "Annotation tracks",
]

# API endpoint
WABI_API_URL = "https://dtn1.ddbj.nig.ac.jp/wabi/chipatlas/"

# TSV column names (no header in API response)
TSV_COLUMNS = [
    "experiment_id",
    "antigen_class",
    "antigen",
    "cell_type_class",
    "cell_type",
    "num_peaks",
    "overlap_a",
    "overlap_b",
    "log10_pvalue",
    "log10_qvalue",
    "fold_enrichment",
]


def submit_enrichment_job(
    gene_list,
    genome="hg38",
    antigen_class="TFs and others",
    cell_class="All cell types",
    threshold=50,
    distance_up=5000,
    distance_down=5000,
):
    """
    Submit enrichment analysis job to ChIP-Atlas API.

    Parameters:
    -----------
    gene_list : list of str
        Gene symbols (e.g., ['TP53', 'CDKN1A', 'BAX'])
    genome : str
        Genome assembly (hg38, hg19, mm10, mm9, rn6, dm6, dm3, ce11, ce10, sacCer3)
    antigen_class : str
        Experiment type filter (e.g., "TFs and others", "Histone")
    cell_class : str
        Cell type class filter (e.g., "Blood", "All cell types")
    threshold : int
        MACS2 peak significance: 50 (1e-5), 100 (1e-10), 200 (1e-20), 500 (1e-50)
    distance_up : int
        Bases upstream of TSS
    distance_down : int
        Bases downstream of TSS

    Returns:
    --------
    str: Request ID for polling

    Raises:
    -------
    RuntimeError: If API submission fails
    """

    # Sanitize gene names (API only accepts alphanumeric + tab + underscore + newline)
    sanitized_genes = []
    for gene in gene_list:
        sanitized = "".join(c if c.isalnum() or c == "_" else "_" for c in gene)
        sanitized_genes.append(sanitized)

    bed_a_content = "\n".join(sanitized_genes)

    data = {
        "address": "",
        "format": "json",
        "result": "www",
        "genome": genome,
        "antigenClass": antigen_class,
        "cellClass": cell_class,
        "threshold": str(threshold),
        "typeA": "gene",
        "bedAFile": bed_a_content,
        "typeB": "refseq",
        "bedBFile": "empty",
        "permTime": "1",
        "title": "chipatlas_enrichment",
        "descriptionA": "query_genes",
        "descriptionB": "RefSeq_genes",
        "distanceUp": str(distance_up),
        "distanceDown": str(distance_down),
    }

    try:
        response = requests.post(WABI_API_URL, data=data, timeout=60)
        response.raise_for_status()
        result = response.json()

        if "requestId" in result:
            return result["requestId"]
        else:
            error_msg = result.get("error-message", result.get("Message", "Unknown error"))
            raise RuntimeError(f"API submission failed: {error_msg}")

    except requests.exceptions.RequestException as e:
        raise RuntimeError(
            f"Failed to connect to ChIP-Atlas API: {e}. "
            f"Check internet connection and https://chip-atlas.org availability."
        )


def poll_job_status(request_id, timeout=600, poll_interval=15):
    """
    Poll job until finished or timeout.

    Parameters:
    -----------
    request_id : str
        Request ID from submit_enrichment_job()
    timeout : int
        Maximum seconds to wait (default: 600 = 10 min)
    poll_interval : int
        Seconds between polls (default: 15)

    Returns:
    --------
    str: Final status ("finished")

    Raises:
    -------
    RuntimeError: If job fails or times out
    """

    url = f"{WABI_API_URL}{request_id}?info=status"
    start_time = time.time()

    while True:
        elapsed = time.time() - start_time
        if elapsed > timeout:
            raise RuntimeError(
                f"ChIP-Atlas job timed out after {timeout}s. "
                f"Request ID: {request_id}. Try again or increase timeout."
            )

        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            text = response.text

            # Parse status from text response
            status = None
            for line in text.strip().split("\n"):
                if line.startswith("status:"):
                    status = line.split(":", 1)[1].strip()
                    break

            if status == "finished":
                return "finished"
            elif status in ("error", "failed"):
                raise RuntimeError(
                    f"ChIP-Atlas job failed. Request ID: {request_id}. "
                    f"Response: {text}"
                )

            # Still running
            minutes_elapsed = elapsed / 60
            print(f"   Job running... ({minutes_elapsed:.1f} min elapsed)")

        except requests.exceptions.RequestException as e:
            print(f"   Warning: Poll request failed ({e}), retrying...")

        time.sleep(poll_interval)


def retrieve_results(request_id):
    """
    Retrieve TSV results from completed job.

    Parameters:
    -----------
    request_id : str
        Request ID from submit_enrichment_job()

    Returns:
    --------
    pd.DataFrame: Raw API results with columns:
        experiment_id, antigen_class, antigen, cell_type_class, cell_type,
        num_peaks, overlap_a, overlap_b, log10_pvalue, log10_qvalue,
        fold_enrichment

    Raises:
    -------
    RuntimeError: If retrieval fails
    """

    url = f"{WABI_API_URL}{request_id}?info=result&format=tsv"

    try:
        response = requests.get(url, timeout=120)
        response.raise_for_status()

        if not response.text.strip():
            raise RuntimeError("API returned empty results")

        # Parse TSV (no header)
        from io import StringIO

        df = pd.read_csv(
            StringIO(response.text),
            sep="\t",
            header=None,
            names=TSV_COLUMNS,
        )

        return df

    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Failed to retrieve results: {e}")


def parse_api_results(api_df, total_input_genes):
    """
    Map API results to the enrichment results contract.

    Converts API-specific columns (log10 p-values, fraction strings)
    to the format expected by generate_all_plots.py and export_all.py.

    Parameters:
    -----------
    api_df : pd.DataFrame
        Raw API results from retrieve_results()
    total_input_genes : int
        Number of input genes (for validation)

    Returns:
    --------
    pd.DataFrame: Contract-compliant DataFrame with columns:
        experiment_id, antigen, cell_type, fold_enrichment, p_value,
        q_value, significant, overlap_rate, regions_with_overlaps,
        total_regions, total_peaks
    """

    result = pd.DataFrame()

    result["experiment_id"] = api_df["experiment_id"]
    result["antigen"] = api_df["antigen"]
    result["cell_type"] = api_df["cell_type"]
    result["fold_enrichment"] = api_df["fold_enrichment"].astype(float)

    # Convert log10(p-value) to raw p-value
    # API returns negative values for significant results, 0 for p=1
    log10_p = api_df["log10_pvalue"].astype(float)
    result["p_value"] = _log10_to_raw(log10_p)

    # Convert log10(q-value) to raw q-value
    log10_q = api_df["log10_qvalue"].astype(float)
    result["q_value"] = _log10_to_raw(log10_q)

    result["significant"] = result["q_value"] < 0.05

    # Parse overlap fractions (e.g., "4/5" → regions_with_overlaps=4, total_regions=5)
    overlap_a_parsed = api_df["overlap_a"].apply(_parse_fraction)
    result["regions_with_overlaps"] = overlap_a_parsed.apply(lambda x: x[0])
    result["total_regions"] = overlap_a_parsed.apply(lambda x: x[1])
    result["overlap_rate"] = result["regions_with_overlaps"] / result["total_regions"].replace(0, 1)

    result["total_peaks"] = api_df["num_peaks"].astype(int)

    # Sort by q-value ascending (most significant first)
    result = result.sort_values("q_value", ascending=True).reset_index(drop=True)

    return result


def _log10_to_raw(log10_values):
    """Convert log10(value) to raw value, handling 0 → 1.0."""
    import numpy as np

    raw = np.where(
        log10_values < 0,
        10.0 ** log10_values,
        1.0,
    )
    return raw


def _parse_fraction(fraction_str):
    """Parse 'N/M' string to (N, M) tuple."""
    try:
        parts = str(fraction_str).split("/")
        return (int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        return (0, 0)


if __name__ == "__main__":
    print("Testing query_chipatlas_api module...")
    print("Note: This requires internet connection.\n")

    # Test with a small gene set
    test_genes = ["TP53", "CDKN1A", "BAX", "MDM2", "BBC3"]

    print(f"Submitting {len(test_genes)} genes to ChIP-Atlas API...")
    request_id = submit_enrichment_job(
        gene_list=test_genes,
        genome="hg38",
        antigen_class="TFs and others",
        cell_class="Blood",
        threshold=50,
    )
    print(f"   Request ID: {request_id}")

    print("Polling for completion...")
    status = poll_job_status(request_id, timeout=300)
    print(f"   Status: {status}")

    print("Retrieving results...")
    raw_df = retrieve_results(request_id)
    print(f"   Raw results: {len(raw_df)} rows, {len(raw_df.columns)} columns")
    print(f"   Columns: {list(raw_df.columns)}")

    print("Parsing to contract format...")
    results_df = parse_api_results(raw_df, len(test_genes))
    print(f"   Parsed results: {len(results_df)} rows")
    print(f"   Significant (q<0.05): {results_df['significant'].sum()}")
    print(f"\n   Top 5 results:")
    print(results_df[["experiment_id", "antigen", "cell_type", "fold_enrichment", "q_value"]].head())

    print("\nTest completed successfully!")

