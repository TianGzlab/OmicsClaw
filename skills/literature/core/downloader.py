"""Download datasets from GEO."""

import json
import re
import time
from pathlib import Path
from typing import Dict, List
import requests


def download_geo_dataset(gse_id: str, output_dir: Path, max_retries: int = 3) -> Dict:
    """Download GEO dataset by GSE ID.

    Args:
        gse_id: GEO Series accession (e.g., GSE123456)
        output_dir: Directory to save files
        max_retries: Number of retry attempts

    Returns:
        Dict with download status and file paths
    """
    gse_id = gse_id.upper().strip()
    gse_dir = output_dir / gse_id
    gse_dir.mkdir(parents=True, exist_ok=True)

    result = {
        'gse_id': gse_id,
        'status': 'pending',
        'files': [],
        'errors': [],
    }

    try:
        # Get GSE metadata
        metadata = fetch_geo_metadata(gse_id)
        if not metadata:
            result['status'] = 'failed'
            result['errors'].append(f"Could not fetch metadata for {gse_id}")
            return result

        # Save metadata
        metadata_file = gse_dir / 'metadata.json'
        metadata_file.write_text(json.dumps(metadata, indent=2))
        result['files'].append(str(metadata_file))

        # Try to download supplementary files
        supp_files = download_supplementary_files(gse_id, gse_dir, max_retries)
        result['files'].extend(supp_files)

        result['status'] = 'success' if result['files'] else 'partial'

    except Exception as e:
        result['status'] = 'failed'
        result['errors'].append(str(e))

    return result


def fetch_geo_metadata(gse_id: str) -> Dict:
    """Fetch GEO metadata via NCBI E-utilities."""
    try:
        # Use GEO API
        url = f"https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={gse_id}&targ=self&form=text&view=quick"
        response = requests.get(url, timeout=30)
        response.raise_for_status()

        text = response.text
        metadata = {
            'gse_id': gse_id,
            'title': extract_field(text, r'\!Series_title\s*=\s*(.+)'),
            'summary': extract_field(text, r'\!Series_summary\s*=\s*(.+)'),
            'organism': extract_field(text, r'\!Series_sample_organism\s*=\s*(.+)'),
            'platform': extract_field(text, r'\!Series_platform_id\s*=\s*(.+)'),
            'samples': extract_samples(text),
        }

        return metadata

    except Exception as e:
        print(f"Error fetching metadata for {gse_id}: {e}")
        return {}


def extract_field(text: str, pattern: str) -> str:
    """Extract field from GEO text format."""
    match = re.search(pattern, text, re.MULTILINE)
    return match.group(1).strip() if match else ''


def extract_samples(text: str) -> List[str]:
    """Extract GSM sample IDs from GEO metadata."""
    pattern = r'\!Series_sample_id\s*=\s*(GSM\d+)'
    return re.findall(pattern, text)


def download_supplementary_files(gse_id: str, output_dir: Path, max_retries: int = 3) -> List[str]:
    """Download supplementary files from GEO FTP."""
    downloaded = []

    try:
        # GEO FTP structure: ftp://ftp.ncbi.nlm.nih.gov/geo/series/GSEnnn/GSE123456/suppl/
        gse_prefix = gse_id[:-3] + 'nnn'  # GSE123456 -> GSE123nnn
        ftp_base = f"https://ftp.ncbi.nlm.nih.gov/geo/series/{gse_prefix}/{gse_id}/suppl/"

        # Try to list files
        response = requests.get(ftp_base, timeout=30)
        if response.status_code != 200:
            return downloaded

        # Parse HTML directory listing
        file_links = re.findall(r'href="([^"]+\.(h5ad|mtx|csv|tsv|txt|gz|tar))"', response.text, re.IGNORECASE)

        for filename in file_links[:10]:  # Limit to 10 files
            file_url = ftp_base + filename
            output_file = output_dir / filename

            # Download with retry
            for attempt in range(max_retries):
                try:
                    print(f"Downloading {filename} (attempt {attempt + 1}/{max_retries})...")
                    file_response = requests.get(file_url, timeout=120, stream=True)
                    file_response.raise_for_status()

                    with open(output_file, 'wb') as f:
                        for chunk in file_response.iter_content(chunk_size=8192):
                            f.write(chunk)

                    downloaded.append(str(output_file))
                    print(f"Downloaded: {output_file}")
                    break

                except Exception as e:
                    if attempt == max_retries - 1:
                        print(f"Failed to download {filename}: {e}")
                    else:
                        time.sleep(2 ** attempt)  # Exponential backoff

    except Exception as e:
        print(f"Error downloading supplementary files: {e}")

    return downloaded
