"""Text extraction and explicit acquisition for scientific literature."""
from copy import deepcopy
from pathlib import Path
import re
import pandas as pd
from skills.literature._lib.extractor import extract_metadata, extract_methodology

__all__ = ['extract', 'methodology', 'read_document', 'fetch_text', 'run_info', 'accession_figure']


def extract(data):
    """Extract GEO accessions and heuristic study metadata from text.

    :param data: Local paper text; URLs and paths are treated as text, never fetched.
    :returns: A DataFrame of kind/accession pairs, with metadata in attrs['run_info'].
    :raises ValueError: data is empty or not a string.
    """
    if not isinstance(data, str) or not data.strip():
        raise ValueError('Provide nonempty paper text')
    metadata = extract_metadata(data)
    records = [{'kind': kind, 'accession': value} for kind, values in metadata['geo_accessions'].items() for value in values]
    result = pd.DataFrame(records, columns=['kind', 'accession'])
    result.attrs['run_info'] = metadata
    return result


def methodology(data):
    """Extract stated numeric method parameters with exact source spans.

    :param data: Paper text containing supported parameter names and numeric values.
    :returns: A DataFrame with param, operator, value, quote, start and end columns.
    :raises TypeError: data is not text.
    """
    records = [{k: value for k, value in record.items() if k not in ('char_span', 'todo')} |
               {'start': record['char_span'][0], 'end': record['char_span'][1]}
               for record in extract_methodology(data)]
    return pd.DataFrame(records, columns=['param', 'operator', 'value', 'quote', 'start', 'end'])


def read_document(data):
    """Read a local PDF or UTF-8 text file; use as reader= in read_input.

    :param data: Local Path or path string; no network requests are made.
    :returns: Extracted text with empty PDF pages omitted.
    :raises ImportError: Install pypdf with install_skill_deps for PDFs.
    :raises OSError: The file cannot be read.
    """
    path = Path(data)
    if path.suffix.lower() != '.pdf':
        return path.read_text(encoding='utf-8')
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ImportError('Install pypdf with install_skill_deps to read PDF documents') from exc
    reader = PdfReader(path)
    return ' '.join(page.extract_text() or '' for page in reader.pages)


def fetch_text(data, *, input_type='url'):
    """Fetch article text explicitly from a URL, DOI or PubMed reference.

    :param data: Reference sent to the remote service; results may change between requests.
    :param input_type: Default url; doi and pubmed resolve their respective endpoints.
    :returns: HTML/XML with tags removed and whitespace collapsed, as in the CLI.
    :raises ImportError: Install requests with install_skill_deps if unavailable.
    :raises ValueError: The reference type or URL scheme is unsupported.
    :raises Exception: HTTP and network errors propagate instead of becoming article text.
    """
    from urllib.parse import urlsplit
    if input_type == 'doi':
        url = 'https://doi.org/' + str(data).strip()
    elif input_type == 'pubmed':
        if not str(data).strip().isdigit():
            raise ValueError('PubMed ID must be numeric')
        url = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id=' + str(data).strip() + '&retmode=xml'
    elif input_type == 'url':
        url = str(data)
        parts = urlsplit(url)
        pubmed = re.match(r'/([0-9]+)(?:/|$)', parts.path)
        if parts.hostname == 'pubmed.ncbi.nlm.nih.gov' and pubmed:
            return fetch_text(pubmed.group(1), input_type='pubmed')
    else:
        raise ValueError('input_type must be url, doi or pubmed')
    if urlsplit(url).scheme not in ('https', 'http'):
        raise ValueError('Only HTTP(S) literature URLs are supported')
    try:
        import requests
    except ImportError as exc:
        raise ImportError('Install requests with install_skill_deps to fetch literature') from exc
    response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0 (OmicsClaw Literature Parser)'}, timeout=30)
    response.raise_for_status()
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', response.text))


def run_info(data, *, keep=True):
    """Read heuristic metadata and the accession lists extracted from text.

    :param data: Accession table returned by extract.
    :param keep: Default True; use False to remove metadata from the table.
    :returns: An independent metadata dictionary.
    :raises KeyError: The table has no extraction diagnostics.
    """
    return deepcopy(data.attrs['run_info'] if keep else data.attrs.pop('run_info'))


def accession_figure(data):
    """Plot accession counts by GEO accession kind.

    :param data: Accession table returned by extract.
    :returns: A matplotlib Figure, including zero counts for missing kinds.
    :raises KeyError: kind is absent.
    """
    from matplotlib.figure import Figure
    counts = data['kind'].value_counts().reindex(['gse', 'gsm', 'gpl'], fill_value=0)
    fig = Figure(figsize=(5, 3))
    ax = fig.subplots()
    ax.bar(counts.index, counts.values)
    ax.set_ylabel('Unique accessions')
    return fig
