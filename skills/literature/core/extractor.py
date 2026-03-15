"""Extract GEO accessions and metadata from text."""

import re
from typing import Dict, List, Set


def extract_geo_accessions(text: str) -> Dict[str, List[str]]:
    """Extract GEO accessions (GSE, GSM, GPL) from text.

    Returns:
        Dict with keys 'gse', 'gsm', 'gpl' containing lists of accessions
    """
    # GEO accession patterns
    gse_pattern = r'\b(GSE\d{3,})\b'
    gsm_pattern = r'\b(GSM\d{3,})\b'
    gpl_pattern = r'\b(GPL\d{3,})\b'

    gse_ids = list(set(re.findall(gse_pattern, text, re.IGNORECASE)))
    gsm_ids = list(set(re.findall(gsm_pattern, text, re.IGNORECASE)))
    gpl_ids = list(set(re.findall(gpl_pattern, text, re.IGNORECASE)))

    # Normalize to uppercase
    return {
        'gse': [x.upper() for x in gse_ids],
        'gsm': [x.upper() for x in gsm_ids],
        'gpl': [x.upper() for x in gpl_ids],
    }


def extract_organism(text: str) -> str:
    """Extract organism/species from text."""
    organisms = {
        'homo sapiens': ['human', 'homo sapiens', 'h. sapiens'],
        'mus musculus': ['mouse', 'mus musculus', 'm. musculus', 'mice'],
        'rattus norvegicus': ['rat', 'rattus norvegicus', 'r. norvegicus'],
        'danio rerio': ['zebrafish', 'danio rerio', 'd. rerio'],
        'drosophila melanogaster': ['fly', 'drosophila', 'd. melanogaster'],
    }

    text_lower = text.lower()
    for canonical, aliases in organisms.items():
        for alias in aliases:
            if alias in text_lower:
                return canonical

    return 'unknown'


def extract_tissue(text: str) -> str:
    """Extract tissue type from text."""
    tissues = [
        'brain', 'heart', 'liver', 'kidney', 'lung', 'spleen',
        'muscle', 'skin', 'blood', 'bone', 'pancreas', 'intestine',
        'stomach', 'colon', 'breast', 'prostate', 'ovary', 'testis',
        'thyroid', 'adrenal', 'pituitary', 'retina', 'cornea',
        'tumor', 'cancer', 'carcinoma', 'lymphoma', 'leukemia',
    ]

    text_lower = text.lower()
    for tissue in tissues:
        if tissue in text_lower:
            return tissue

    return 'unknown'


def extract_technology(text: str) -> str:
    """Extract sequencing technology from text."""
    technologies = {
        '10x Genomics': ['10x', '10x genomics', 'chromium'],
        'Visium': ['visium', 'spatial transcriptomics'],
        'Smart-seq': ['smart-seq', 'smartseq'],
        'Drop-seq': ['drop-seq', 'dropseq'],
        'MERFISH': ['merfish'],
        'seqFISH': ['seqfish'],
        'Slide-seq': ['slide-seq', 'slideseq'],
        'Xenium': ['xenium'],
    }

    text_lower = text.lower()
    for tech, aliases in technologies.items():
        for alias in aliases:
            if alias in text_lower:
                return tech

    return 'unknown'


def extract_metadata(text: str) -> Dict[str, any]:
    """Extract all metadata from text.

    Returns:
        Dict containing geo_accessions, organism, tissue, technology
    """
    return {
        'geo_accessions': extract_geo_accessions(text),
        'organism': extract_organism(text),
        'tissue': extract_tissue(text),
        'technology': extract_technology(text),
    }
