"""
Query the ChIP-Atlas Diff Analysis API.

Submits two sets of experiment IDs to the official ChIP-Atlas WABI API,
which performs differential peak (DPR via edgeR) or differentially methylated
region (DMR via metilene) analysis between the two groups.
Results are returned as a ZIP archive containing BED and IGV files.

API endpoint: POST https://dtn1.ddbj.nig.ac.jp/wabi/chipatlas/
Reference: Zou et al. 2024 (NAR), https://chip-atlas.org
"""

import io
import os
import re
import time
import zipfile

import requests

# API endpoint (shared with enrichment analysis)
WABI_API_URL = "https://dtn1.ddbj.nig.ac.jp/wabi/chipatlas/"

# Valid analysis types
VALID_ANALYSIS_TYPES = {
    "diffbind": "Differential Peak Regions (ChIP/ATAC/DNase-seq)",
    "dmr": "Differentially Methylated Regions (Bisulfite-seq)",
}

# Valid genomes (same as enrichment)
VALID_GENOMES = [
    "hg38", "hg19", "mm10", "mm9", "rn6",
    "dm6", "dm3", "ce11", "ce10", "sacCer3",
]

# Experiment ID pattern
EXPERIMENT_ID_PATTERN = re.compile(r"^(SRX|ERX|DRX|GSM)\d+$")


def submit_diff_job(
    experiments_a,
    experiments_b,
    genome="hg38",
    analysis_type="diffbind",
    title="diff_analysis",
    description_a="group_A",
    description_b="group_B",
):
    """
    Submit differential analysis job to ChIP-Atlas API.

    Parameters
    ----------
    experiments_a : list of str
        Experiment IDs for group A (e.g., ['SRX123456', 'SRX123457'])
    experiments_b : list of str
        Experiment IDs for group B
    genome : str
        Genome assembly (hg38, hg19, mm10, etc.)
    analysis_type : str
        'diffbind' for DPR (ChIP/ATAC/DNase-seq) or 'dmr' for DMR (Bisulfite-seq)
    title : str
        Analysis title
    description_a : str
        Label for dataset A
    description_b : str
        Label for dataset B

    Returns
    -------
    str
        Request ID for polling

    Raises
    ------
    ValueError
        If inputs are invalid
    RuntimeError
        If API submission fails
    """
    # Validate inputs
    if not experiments_a or len(experiments_a) < 2:
        raise ValueError("Group A requires at least 2 experiment IDs")
    if not experiments_b or len(experiments_b) < 2:
        raise ValueError("Group B requires at least 2 experiment IDs")
    if genome not in VALID_GENOMES:
        raise ValueError(f"Invalid genome '{genome}'. Valid: {VALID_GENOMES}")
    if analysis_type not in VALID_ANALYSIS_TYPES:
        raise ValueError(
            f"Invalid analysis_type '{analysis_type}'. "
            f"Valid: {list(VALID_ANALYSIS_TYPES.keys())}"
        )

    # Validate experiment IDs
    for group_name, ids in [("A", experiments_a), ("B", experiments_b)]:
        for exp_id in ids:
            if not EXPERIMENT_ID_PATTERN.match(exp_id):
                print(f"   Warning: ID '{exp_id}' in group {group_name} "
                      f"doesn't match expected format (SRX/ERX/DRX/GSM)")

    bed_a_content = "\n".join(experiments_a)
    bed_b_content = "\n".join(experiments_b)

    data = {
        "address": "",          # Hidden but required (from enrichment debugging)
        "format": "text",       # Diff analysis uses text, not json
        "result": "www",        # Hidden but required
        "genome": genome,
        "antigenClass": analysis_type,
        "cellClass": "empty",   # Fixed for diff analysis
        "threshold": "50",      # Fixed for diff analysis
        "typeA": "srx",
        "bedAFile": bed_a_content,
        "typeB": "srx",
        "bedBFile": bed_b_content,
        "permTime": "1",
        "title": title,
        "descriptionA": description_a,
        "descriptionB": description_b,
    }

    try:
        response = requests.post(WABI_API_URL, data=data, timeout=60)
        response.raise_for_status()

        # Try JSON parsing first (in case API accepts format=text but returns JSON)
        try:
            result = response.json()
            if "requestId" in result:
                return result["requestId"]
            error_msg = result.get("error-message", result.get("Message", ""))
            if error_msg:
                raise RuntimeError(f"API submission failed: {error_msg}")
        except (ValueError, KeyError):
            pass

        # Parse text response: look for "requestId: ..." line
        text = response.text.strip()
        for line in text.split("\n"):
            line = line.strip()
            if line.startswith("requestId"):
                # Handle both "requestId: value" and "requestId\tvalue"
                request_id = re.split(r"[:\t]\s*", line, maxsplit=1)
                if len(request_id) > 1 and request_id[1].strip():
                    return request_id[1].strip()

        raise RuntimeError(
            f"Could not parse request ID from API response:\n{text[:500]}"
        )

    except requests.exceptions.RequestException as e:
        raise RuntimeError(
            f"Failed to connect to ChIP-Atlas API: {e}. "
            f"Check internet connection and https://chip-atlas.org availability."
        )


def poll_job_status(request_id, timeout=900, poll_interval=15):
    """
    Poll job until finished or timeout.

    Parameters
    ----------
    request_id : str
        Request ID from submit_diff_job()
    timeout : int
        Maximum seconds to wait (default: 900 = 15 min)
    poll_interval : int
        Seconds between polls (default: 15)

    Returns
    -------
    str
        Final status ("finished")

    Raises
    ------
    RuntimeError
        If job fails or times out
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
                if line.startswith("status"):
                    status = re.split(r"[:\t]\s*", line, maxsplit=1)
                    status = status[1].strip() if len(status) > 1 else None
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


def retrieve_zip_results(request_id, output_dir):
    """
    Retrieve ZIP results from completed job and extract to output directory.

    Parameters
    ----------
    request_id : str
        Request ID from submit_diff_job()
    output_dir : str
        Directory to extract results into

    Returns
    -------
    dict
        Paths to extracted files: {'bed': path, 'igv_bed': path,
        'log': path, 'igv_xml': path}. Keys may be absent if file
        not found in ZIP.

    Raises
    ------
    RuntimeError
        If retrieval or extraction fails
    """
    url = f"{WABI_API_URL}{request_id}?info=result&format=zip"

    try:
        response = requests.get(url, timeout=300)
        response.raise_for_status()

        if not response.content:
            raise RuntimeError("API returned empty ZIP response")

        raw_dir = os.path.join(output_dir, "raw_results")
        os.makedirs(raw_dir, exist_ok=True)

        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            zf.extractall(raw_dir)

        # Identify extracted files by extension
        extracted = {}
        for root, _dirs, files in os.walk(raw_dir):
            for f in files:
                full_path = os.path.join(root, f)
                if f.endswith(".igv.bed"):
                    extracted["igv_bed"] = full_path
                elif f.endswith(".bed") and "igv" not in f:
                    extracted["bed"] = full_path
                elif f.endswith(".log"):
                    extracted["log"] = full_path
                elif f.endswith(".xml"):
                    extracted["igv_xml"] = full_path

        if "bed" not in extracted:
            # List what was actually extracted for debugging
            all_files = []
            for root, _dirs, files in os.walk(raw_dir):
                all_files.extend(files)
            raise RuntimeError(
                f"No BED file found in ZIP results. "
                f"Extracted files: {all_files}"
            )

        return extracted

    except zipfile.BadZipFile:
        raise RuntimeError(
            "API returned invalid ZIP data. The job may still be processing. "
            f"Request ID: {request_id}"
        )
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Failed to retrieve results: {e}")


if __name__ == "__main__":
    print("Testing query_chipatlas_api module (diff analysis)...")
    print("Note: This requires internet connection.\n")

    # Test with a small example
    test_a = ["SRX8347024", "SRX8347025"]
    test_b = ["SRX8347026", "SRX8347027"]

    print(f"Submitting diff analysis: {len(test_a)} vs {len(test_b)} experiments...")
    request_id = submit_diff_job(
        experiments_a=test_a,
        experiments_b=test_b,
        genome="mm10",
        analysis_type="diffbind",
        title="test_diff",
        description_a="group_A",
        description_b="group_B",
    )
    print(f"   Request ID: {request_id}")

    print("Polling for completion...")
    status = poll_job_status(request_id, timeout=900)
    print(f"   Status: {status}")

    print("Retrieving ZIP results...")
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        extracted = retrieve_zip_results(request_id, tmpdir)
        print(f"   Extracted files: {list(extracted.keys())}")
        for key, path in extracted.items():
            size = os.path.getsize(path)
            print(f"   {key}: {os.path.basename(path)} ({size} bytes)")

    print("\nTest completed successfully!")

