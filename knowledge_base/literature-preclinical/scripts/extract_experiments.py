"""
Preclinical Experiment Extraction Module

Parse abstracts to extract structured in vitro and in vivo experiment details.
Uses keyword-based extraction to identify cell lines, assays, animal models,
endpoints, and key findings from each paper.
"""

import re
import os
from typing import List, Dict, Tuple
import pandas as pd


# ---------------------------------------------------------------------------
# Keyword dictionaries
# ---------------------------------------------------------------------------

# In vitro indicators
IN_VITRO_KEYWORDS = [
    "cell line", "cell lines", "cell culture", "in vitro", "cultured cells",
    "transfect", "transduct", "knockdown", "overexpress", "overexpression",
    "siRNA", "shRNA", "CRISPR", "sgRNA",
    "co-culture", "monolayer", "spheroid", "organoid",
]

# Common cell line names (case-insensitive matching handled separately)
CELL_LINE_NAMES = [
    "MCF-7", "MCF7", "MDA-MB-231", "MDA-MB-468", "T47D", "BT-474", "BT474",
    "BT-549", "BT549", "MDA-MB-453", "CAL-51", "HCC1937", "HCC1806",
    "SK-BR-3", "SKBR3", "ZR-75", "4T1", "EMT6",
    "HeLa", "HEK293", "HEK-293", "293T", "HEK293T",
    "A549", "H1299", "H460", "H1975", "PC9", "HCC827",
    "HCT116", "HT29", "SW480", "SW620", "LoVo", "Caco-2",
    "U87", "U251", "T98G", "LN229",
    "PC3", "PC-3", "LNCaP", "DU145", "22Rv1", "VCaP",
    "K562", "HL60", "HL-60", "Jurkat", "THP-1", "U937",
    "HepG2", "Hep3B", "Huh7", "SMMC-7721",
    "PANC-1", "MiaPaCa-2", "BxPC-3", "AsPC-1",
    "A375", "SK-MEL-28", "B16", "B16F10",
    "OVCAR3", "SKOV3", "A2780",
    "CHO", "NIH3T3", "3T3", "COS-7",
    "Raji", "Ramos", "Daudi",
    "SH-SY5Y", "Neuro-2a", "N2a",
    "RAW264.7", "RAW 264.7", "J774",
]

# Assay keyword categories
ASSAY_KEYWORDS = {
    "viability": [
        "viability", "MTT", "CCK-8", "CCK8", "WST", "cell counting",
        "CellTiter", "MTS", "XTT", "alamarBlue", "resazurin",
        "cytotoxicity", "IC50", "EC50", "dose-response",
    ],
    "proliferation": [
        "proliferation", "colony formation", "clonogenic", "BrdU", "EdU",
        "Ki-67", "Ki67", "cell growth", "growth curve", "doubling time",
    ],
    "apoptosis": [
        "apoptosis", "annexin", "caspase", "TUNEL", "cell death",
        "sub-G1", "programmed cell death", "Bcl-2", "BAX",
        "cleaved PARP", "cytochrome c release",
    ],
    "migration_invasion": [
        "migration", "invasion", "wound healing", "transwell", "Boyden",
        "scratch assay", "chemotaxis", "Matrigel",
    ],
    "gene_expression": [
        "qPCR", "RT-PCR", "real-time PCR", "qRT-PCR",
        "mRNA expression", "RNA-seq", "RNAseq", "transcriptom",
        "gene expression", "Northern blot",
    ],
    "protein_analysis": [
        "Western blot", "immunoblot", "ELISA", "immunoprecipitation",
        "phosphorylation", "Co-IP", "pull-down", "mass spectrometry",
        "proteomics", "immunofluorescence",
    ],
    "flow_cytometry": [
        "flow cytometry", "FACS", "cell cycle", "cell sorting",
        "intracellular staining", "surface marker",
    ],
    "reporter": [
        "luciferase", "reporter assay", "GFP", "fluorescent reporter",
        "dual-luciferase", "beta-galactosidase",
    ],
    "cell_signaling": [
        "signaling assay", "signaling pathway analysis",
        "phospho-", "kinase activity", "kinase assay",
        "pathway activation assay", "phosphoproteomics",
    ],
}

# In vivo indicators
IN_VIVO_KEYWORDS = [
    "in vivo", "mouse", "mice", "murine", "rat", "rats",
    "xenograft", "allograft", "PDX", "patient-derived xenograft",
    "orthotopic", "subcutaneous", "tumor-bearing",
    "nude mice", "BALB/c", "C57BL/6", "SCID", "NSG", "NOD",
    "transgenic", "knockout mice", "knock-in",
    "animal model", "animal experiment", "preclinical model",
]

# Animal model categories
ANIMAL_MODEL_KEYWORDS = {
    "xenograft": [
        "xenograft", "subcutaneous tumor", "subcutaneous implant",
        "orthotopic implant", "orthotopic model",
        "human tumor", "nude mice xenograft",
    ],
    "pdx": [
        "PDX", "patient-derived xenograft", "patient-derived model",
    ],
    "syngeneic": [
        "syngeneic", "allograft", "immunocompetent",
        "4T1", "CT26", "B16", "MC38", "LLC", "EMT6",
    ],
    "transgenic": [
        "transgenic", "knockout", "knock-in", "conditional knockout",
        "Cre-lox", "GEMM", "genetically engineered",
    ],
    "metastasis": [
        "metastasis model", "tail vein injection", "intracardiac",
        "metastatic", "lung metastasis", "liver metastasis",
        "spontaneous metastasis",
    ],
}

# In vivo endpoint categories
ENDPOINT_KEYWORDS = {
    "tumor_growth": [
        "tumor volume", "tumor growth", "tumor weight", "tumor size",
        "tumor regression", "tumor inhibition", "anti-tumor",
        "tumor growth inhibition", "TGI",
    ],
    "survival": [
        "survival", "overall survival", "Kaplan-Meier",
        "median survival", "survival rate", "lifespan",
    ],
    "biomarker": [
        "biomarker", "serum level", "plasma level", "circulating",
        "pharmacodynamic", "PD marker",
    ],
    "imaging": [
        "bioluminescence", "in vivo imaging", "PET", "MRI", "CT scan",
        "IVIS", "fluorescence imaging", "ultrasound",
    ],
    "histology": [
        "histology", "immunohistochemistry", "IHC", "H&E",
        "histopathology", "tissue staining", "TUNEL staining",
    ],
    "pharmacokinetics": [
        "pharmacokinetic", "PK", "half-life", "bioavailability",
        "AUC", "Cmax", "clearance", "distribution",
    ],
    "toxicity": [
        "toxicity", "body weight", "adverse", "tolerability",
        "maximum tolerated dose", "MTD", "safety", "organ toxicity",
    ],
}

# Finding / result keywords
FINDING_KEYWORDS = [
    "significantly", "inhibited", "reduced", "suppressed", "attenuated",
    "enhanced", "increased", "promoted", "induced", "abolished",
    "demonstrated", "showed", "revealed", "observed",
    "decreased", "elevated", "impaired", "restored", "abrogated",
    "potentiated", "synergistic", "additive", "antagonistic",
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_all_experiments(
    results: List[Dict],
    output_dir: str = "preclinical_results"
) -> List[Dict]:
    """
    Extract in vitro and in vivo experiment details from all paper abstracts.

    Parameters
    ----------
    results : List[Dict]
        Search results from preclinical_search
    output_dir : str
        Output directory for experiment_extraction.csv

    Returns
    -------
    List[Dict]
        List of experiment extraction dicts, one per paper

    Verification
    ------------
    Prints "✓ Experiment extraction completed successfully!"
    """
    print("\n" + "=" * 70)
    print("EXTRACTING EXPERIMENTS FROM ABSTRACTS")
    print("=" * 70)

    experiments = []
    in_vitro_count = 0
    in_vivo_count = 0
    both_count = 0

    for i, paper in enumerate(results):
        abstract = paper.get("abstract", "")
        title = paper.get("title", "")
        text = f"{title} {abstract}"

        # Classify experiment type
        exp_type = _classify_experiment_type(text)

        # Extract details
        in_vitro = _extract_in_vitro(text)
        in_vivo = _extract_in_vivo(text)
        findings = _extract_findings(text)

        experiment = {
            "pmid": paper.get("pmid", ""),
            "doi": paper.get("doi", ""),
            "title": paper.get("title", ""),
            "authors": paper.get("authors", ""),
            "publication_date": paper.get("publication_date", ""),
            "experiment_type": exp_type,
            # In vitro details
            "cell_lines": "; ".join(in_vitro["cell_lines"]) if in_vitro["cell_lines"] else "",
            "assays": "; ".join(in_vitro["assays"]) if in_vitro["assays"] else "",
            "in_vitro_findings": " | ".join(in_vitro["findings"][:3]) if in_vitro["findings"] else "",
            # In vivo details
            "animal_models": "; ".join(in_vivo["animal_models"]) if in_vivo["animal_models"] else "",
            "endpoints": "; ".join(in_vivo["endpoints"]) if in_vivo["endpoints"] else "",
            "in_vivo_findings": " | ".join(in_vivo["findings"][:3]) if in_vivo["findings"] else "",
            # General findings
            "key_findings": " | ".join(findings[:3]) if findings else "",
        }

        experiments.append(experiment)

        if exp_type == "in_vitro":
            in_vitro_count += 1
        elif exp_type == "in_vivo":
            in_vivo_count += 1
        elif exp_type == "both":
            both_count += 1

    # Summary
    unclassified = len(experiments) - in_vitro_count - in_vivo_count - both_count
    print(f"\n  Processed {len(experiments)} papers:")
    print(f"    In vitro only:  {in_vitro_count}")
    print(f"    In vivo only:   {in_vivo_count}")
    print(f"    Both:           {both_count}")
    print(f"    Unclassified:   {unclassified}")

    # Save CSV
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, "experiment_extraction.csv")
    df = pd.DataFrame(experiments)
    df.to_csv(output_file, index=False, encoding="utf-8")
    print(f"\n  Saved extraction results to {output_file}")

    print(f"\n✓ Experiment extraction completed successfully!")
    return experiments


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _keyword_match(text: str, keywords: list, case_sensitive: bool = False) -> bool:
    """Check if any keyword matches as a whole word in text."""
    for kw in keywords:
        if case_sensitive:
            pattern = r'\b' + re.escape(kw) + r'\b'
            if re.search(pattern, text):
                return True
        else:
            pattern = r'\b' + re.escape(kw.lower()) + r'\b'
            if re.search(pattern, text.lower()):
                return True
    return False


def _classify_experiment_type(text: str) -> str:
    """Classify whether a paper describes in vitro, in vivo, or both experiments."""
    has_in_vitro = _keyword_match(text, IN_VITRO_KEYWORDS)
    has_in_vivo = _keyword_match(text, IN_VIVO_KEYWORDS)

    # Also check for cell line names (case-sensitive for some)
    if not has_in_vitro:
        has_in_vitro = any(re.search(r'\b' + re.escape(cl) + r'\b', text) for cl in CELL_LINE_NAMES)

    if has_in_vitro and has_in_vivo:
        return "both"
    elif has_in_vitro:
        return "in_vitro"
    elif has_in_vivo:
        return "in_vivo"
    else:
        return "unclassified"


def _extract_in_vitro(text: str) -> Dict:
    """Extract in vitro experiment details from text."""
    result = {
        "cell_lines": [],
        "assays": [],
        "findings": [],
    }

    # Detect cell lines (word boundary matching to avoid partial matches)
    found_cell_lines = set()
    for cl_name in CELL_LINE_NAMES:
        pattern = r'\b' + re.escape(cl_name) + r'\b'
        if re.search(pattern, text):
            found_cell_lines.add(cl_name)

    result["cell_lines"] = sorted(found_cell_lines)

    # Detect assay types
    found_assays = set()
    for assay_category, keywords in ASSAY_KEYWORDS.items():
        if _keyword_match(text, keywords):
            found_assays.add(assay_category)

    result["assays"] = sorted(found_assays)

    # Extract in vitro finding sentences
    result["findings"] = _extract_finding_sentences(text, IN_VITRO_KEYWORDS)

    return result


def _extract_in_vivo(text: str) -> Dict:
    """Extract in vivo experiment details from text."""
    result = {
        "animal_models": [],
        "endpoints": [],
        "findings": [],
    }

    # Detect animal model types
    found_models = set()
    for model_category, keywords in ANIMAL_MODEL_KEYWORDS.items():
        if _keyword_match(text, keywords):
            found_models.add(model_category)

    result["animal_models"] = sorted(found_models)

    # Detect endpoints
    found_endpoints = set()
    for endpoint_category, keywords in ENDPOINT_KEYWORDS.items():
        if _keyword_match(text, keywords):
            found_endpoints.add(endpoint_category)

    result["endpoints"] = sorted(found_endpoints)

    # Extract in vivo finding sentences
    result["findings"] = _extract_finding_sentences(text, IN_VIVO_KEYWORDS)

    return result


def _extract_findings(text: str) -> List[str]:
    """Extract general key finding sentences from text."""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    findings = []

    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence.split()) < 8:
            continue

        if _keyword_match(sentence, FINDING_KEYWORDS):
            if len(sentence) > 300:
                sentence = sentence[:297] + "..."
            findings.append(sentence)

    return findings[:5]


def _extract_finding_sentences(text: str, context_keywords: List[str]) -> List[str]:
    """Extract finding sentences that also mention context keywords."""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    findings = []

    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence.split()) < 8:
            continue

        has_finding = _keyword_match(sentence, FINDING_KEYWORDS)
        has_context = _keyword_match(sentence, context_keywords)

        if has_finding and has_context:
            if len(sentence) > 300:
                sentence = sentence[:297] + "..."
            findings.append(sentence)

    return findings[:3]

