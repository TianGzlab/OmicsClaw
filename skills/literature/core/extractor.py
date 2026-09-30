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
    """Extract sequencing / assay technology from text.

    Detection is first-match-wins by dict order, so the MORE SPECIFIC spatial &
    single-cell platforms are checked BEFORE the broader families (a paper that
    says "10x" or "single-cell RNA-seq" must not be read as bulk RNA-seq). The
    bulk/genomics/proteomics/metabolomics families use deliberately specific
    aliases (e.g. "bulk rna-seq", not a bare "rna-seq") to avoid mis-routing.
    """
    technologies = {
        # Spatial (most specific first)
        'Visium': ['visium', 'spatial transcriptomics'],
        'Xenium': ['xenium'],
        'MERFISH': ['merfish'],
        'seqFISH': ['seqfish'],
        'Slide-seq': ['slide-seq', 'slideseq'],
        # Single-cell platforms + generic single-cell (before bulk)
        '10x Genomics': ['10x', '10x genomics', 'chromium'],
        'Smart-seq': ['smart-seq', 'smartseq'],
        'Drop-seq': ['drop-seq', 'dropseq'],
        'single-cell RNA-seq': ['single-cell rna', 'single cell rna', 'scrna-seq', 'scrna seq',
                                'snrna-seq', 'single-nucleus rna', 'single nucleus rna'],
        # Bulk RNA-seq — require an explicit "bulk" so scRNA papers aren't captured
        'Bulk RNA-seq': ['bulk rna-seq', 'bulk rna seq', 'bulk rna sequencing', 'bulk transcriptom'],
        # Genomics / DNA — short aliases (wgs/wes) rely on WORD-BOUNDARY matching below
        # so they don't substring-hit ordinary words ("western", "we").
        'WGS/WES': ['whole-genome sequencing', 'whole genome sequencing', 'whole-exome',
                    'whole exome', 'wgs', 'wes', 'dna-seq', 'dna sequencing'],
        'ATAC-seq': ['atac-seq', 'atacseq', 'atac sequencing'],
        'ChIP-seq': ['chip-seq', 'chipseq', 'chip sequencing'],
        # Metabolomics BEFORE proteomics: LC-MS is used by BOTH, so a metabolomics
        # anchor must win first ("LC-MS/MS-based metabolomics" is metabolomics, not
        # proteomics). Anchor on metabolomics-specific terms only.
        'Metabolomics': ['metabolomic', 'metabolome', 'metabolite', 'lipidomic', 'xcms', 'gc-ms'],
        # Proteomics (mass-spec) — proteomics-specific anchors (drop bare LC-MS, which
        # is ambiguous). 'mass spectrometry' is reached only after metabolomics anchors.
        'Mass spectrometry': ['proteomic', 'peptide', 'tmt', 'label-free quantification',
                              'tandem mass spectrom', 'dia-ms', 'shotgun proteom', 'mass spectrometry'],
    }

    text_lower = text.lower()
    for tech, aliases in technologies.items():
        for alias in aliases:
            # Word-boundary match with an optional trailing plural ``s``: matches
            # stems ("metabolomic" → "metabolomics", "proteomic" → "proteomics")
            # while still rejecting substring false-positives ("wes" ∉ "western",
            # "10x" ∉ "210x"). re.escape handles hyphens/slashes in aliases.
            if re.search(rf"\b{re.escape(alias)}s?\b", text_lower):
                return tech

    return 'unknown'


# Candidate methodology parameters extract_methodology() recognizes, keyed by the
# canonical param name used downstream. Aliases are matched
# case-insensitively, longest-first within each param, against a "KEY (op) NUMBER"
# pattern (e.g. "resolution=0.8", "FDR < 0.1") — see extract_methodology below.
_PARAM_ALIASES: Dict[str, List[str]] = {
    'resolution': ['leiden resolution', 'clustering resolution', 'leiden_resolution', 'resolution'],
    'n_pcs': ['number of pcs', 'principal components', 'n_pcs', 'npcs'],
    'n_neighbors': ['nearest neighbors', 'k neighbors', 'n_neighbors'],
    'min_genes': ['minimum genes', 'min genes', 'min_genes'],
    'min_cells': ['minimum cells', 'min cells', 'min_cells'],
    'max_mt_pct': ['mitochondrial percentage', 'pct_counts_mt', 'percent.mt', 'max_mt_pct'],
    'n_top_hvg': ['highly variable genes', 'n_top_hvg', 'hvg'],
    'p_value': ['p-value', 'p value', 'pvalue'],
    'fdr': ['false discovery rate', 'q-value', 'qvalue', 'padj', 'fdr'],
    'log2fc': ['log2 fold change', 'log2fc', 'logfc'],
}
_OP_RE = r'==|<=|>=|=|<|>|:'
# Atomic group ((?>...), Python 3.11+): without it, a trailing-boundary check
# failing on the full greedy match (e.g. "0.8" in "0.8abc") lets the engine
# backtrack to a SHORTER, wrong match ("0", dropping ".8abc" silently) instead
# of failing outright — worse than not extracting at all. Atomic grouping
# forbids that backtrack, so a boundary failure rejects the whole candidate.
_NUM_RE = r'(?>-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)'
# A number match must not be immediately followed by another alnum/underscore
# char — otherwise a value embedded in a larger token (e.g. "0.8abc",
# "30cells", or a truncated "1e-" with no exponent digits) would be silently
# reported as a clean, complete value instead of being rejected outright.
# Deliberately does NOT forbid a following '.' — a sentence-ending period
# ("resolution=0.8.") is common prose and must not suppress a real match.
_NUM_BOUNDARY_RE = r'(?![A-Za-z0-9_])'


def extract_methodology(text: str) -> List[Dict]:
    """Extract candidate methodology parameters, each backed by a verifiable
    (quote, char_span) slice into `text` — never a paraphrase or a guessed
    value. Vocabulary-limited, regex-only, mirroring extract_technology's
    alias-dict style: this is deliberately NOT an NLP/LLM pass, so that every
    candidate returned is sourced by construction (P5 iron rule: never emit a
    numeric default without a real, re-verifiable span into the source text).

    Only recognizes a fixed "KEY (operator) NUMBER" phrasing (e.g.
    "resolution=0.8", "FDR < 0.1", "n_pcs: 30"). A param mentioned without an
    adjacent parseable number is simply not returned — this function never
    guesses, and never emits a TODO placeholder itself (that policy choice
    belongs to the caller, if ever needed).

    Returns:
        One dict per recognized param (first match in `text` wins, same
        first-match-wins policy as extract_technology): {'param', 'operator',
        'value' (int|float), 'quote', 'char_span': [start, end], 'todo': False}.
    """
    found: Dict[str, Dict] = {}
    for param, aliases in _PARAM_ALIASES.items():
        alias_pattern = '|'.join(re.escape(a) for a in sorted(aliases, key=len, reverse=True))
        pattern = re.compile(
            rf'\b(?:{alias_pattern})\b\s*({_OP_RE})\s*({_NUM_RE}){_NUM_BOUNDARY_RE}',
            re.IGNORECASE,
        )
        m = pattern.search(text)
        if not m:
            continue
        start, end = m.span()
        quote = text[start:end]
        assert text[start:end] == quote  # self-consistent by construction (re.Match.span())
        raw_num = m.group(2)
        value = float(raw_num) if ('.' in raw_num or 'e' in raw_num.lower()) else int(raw_num)
        found[param] = {
            'param': param,
            'operator': m.group(1),
            'value': value,
            'quote': quote,
            'char_span': [start, end],
            'todo': False,
        }
    return list(found.values())


# Detected-technology → omics domain. The report's "Next Steps" maps each domain
# to its entry skill (DOMAIN_ENTRY below) so all 6 domains route correctly.
_TECH_TO_DOMAIN = {
    'Visium': 'spatial', 'Xenium': 'spatial', 'MERFISH': 'spatial',
    'seqFISH': 'spatial', 'Slide-seq': 'spatial',
    '10x Genomics': 'singlecell', 'Smart-seq': 'singlecell', 'Drop-seq': 'singlecell',
    'single-cell RNA-seq': 'singlecell',
    'Bulk RNA-seq': 'bulkrna',
    'WGS/WES': 'genomics', 'ATAC-seq': 'genomics', 'ChIP-seq': 'genomics',
    'Mass spectrometry': 'proteomics',
    'Metabolomics': 'metabolomics',
}

# domain → (entry skill, human label). Skill names verified against skills/<domain>/.
DOMAIN_ENTRY = {
    'spatial': ('spatial-preprocess', 'spatial transcriptomics'),
    'singlecell': ('sc-preprocessing', 'single-cell'),
    'bulkrna': ('bulkrna-qc', 'bulk RNA-seq'),
    'genomics': ('genomics-alignment', 'genomics / DNA-seq'),
    'proteomics': ('proteomics-identification', 'mass-spec proteomics'),
    'metabolomics': ('metabolomics-peak-detection', 'LC-MS metabolomics'),
}


def infer_domain(technology: str) -> str | None:
    """Map a detected technology to its omics domain, or None if unrecognized."""
    return _TECH_TO_DOMAIN.get(technology)


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
