"""Parse different input types (URL, PDF, DOI) to extract text."""

import re
import tempfile
from pathlib import Path
from typing import Tuple
import requests


def parse_input(input_value: str, input_type: str = "auto") -> Tuple[str, str]:
    """Parse input and return (text_content, detected_type).

    Args:
        input_value: URL, DOI, file path, or text
        input_type: "auto", "url", "doi", "pubmed", "file", "text"

    Returns:
        Tuple of (extracted_text, actual_input_type)
    """
    if input_type == "auto":
        input_type = detect_input_type(input_value)

    if input_type == "url":
        return parse_url(input_value), "url"
    elif input_type == "doi":
        return parse_doi(input_value), "doi"
    elif input_type == "pubmed":
        return parse_pubmed(input_value), "pubmed"
    elif input_type == "file":
        return parse_file(input_value), "file"
    else:
        return input_value, "text"


def detect_input_type(value: str) -> str:
    """Auto-detect input type."""
    value = value.strip()

    # DOI pattern
    if re.match(r'^10\.\d{4,}/\S+', value):
        return "doi"

    # PubMed ID
    if re.match(r'^\d{7,8}$', value):
        return "pubmed"

    # URL
    if value.startswith(('http://', 'https://')):
        return "url"

    # File path
    if Path(value).exists() and Path(value).suffix == '.pdf':
        return "file"

    return "text"


def parse_url(url: str) -> str:
    """Fetch and extract text from URL."""
    try:
        # Handle PubMed URLs
        if 'pubmed.ncbi.nlm.nih.gov' in url:
            pmid = re.search(r'/(\d+)', url)
            if pmid:
                return parse_pubmed(pmid.group(1))

        # Fetch HTML
        headers = {'User-Agent': 'Mozilla/5.0 (OmicsClaw Literature Parser)'}
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        # Simple text extraction (remove HTML tags)
        text = re.sub(r'<[^>]+>', ' ', response.text)
        text = re.sub(r'\s+', ' ', text)
        return text

    except Exception as e:
        return f"Error fetching URL: {e}"


def parse_doi(doi: str) -> str:
    """Fetch article via DOI."""
    # Normalize DOI
    doi = doi.strip()
    if not doi.startswith('10.'):
        doi = '10.' + doi.lstrip('10.')

    # Try dx.doi.org redirect
    url = f"https://doi.org/{doi}"
    return parse_url(url)


def parse_pubmed(pmid: str) -> str:
    """Fetch article from PubMed."""
    pmid = pmid.strip()

    # Use PubMed E-utilities API
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    try:
        # Fetch abstract
        fetch_url = f"{base_url}/efetch.fcgi?db=pubmed&id={pmid}&retmode=xml"
        response = requests.get(fetch_url, timeout=30)
        response.raise_for_status()

        # Extract text from XML (simple approach)
        text = re.sub(r'<[^>]+>', ' ', response.text)
        text = re.sub(r'\s+', ' ', text)
        return text

    except Exception as e:
        return f"Error fetching PubMed {pmid}: {e}"


def parse_file(filepath: str) -> str:
    """Extract text from PDF file."""
    try:
        from pypdf import PdfReader

        reader = PdfReader(filepath)
        text_parts = []

        for page in reader.pages:
            text_parts.append(page.extract_text())

        return ' '.join(text_parts)

    except ImportError:
        return "Error: pypdf not installed. Run: pip install pypdf"
    except Exception as e:
        return f"Error parsing PDF: {e}"
