"""
Report Generation Module

URL mapping helpers, markdown report generation, and PDF conversion
for preclinical synthesis reports.
"""

import os
import re
from datetime import datetime
from typing import List, Dict


# ---------------------------------------------------------------------------
# URL mapping helpers for hyperlinked reports
# ---------------------------------------------------------------------------

def build_url_maps(results: List[Dict]):
    """Build PMID->URL and DOI->URL lookup maps from search results."""
    pmid_url = {}
    doi_url = {}
    for r in results:
        pmid = str(r.get("pmid", "")).strip()
        doi = str(r.get("doi", "")).strip()
        url = str(r.get("url", "")).strip()
        if pmid and url:
            pmid_url[pmid] = url
        if doi and url:
            doi_url[doi] = url
    return pmid_url, doi_url


def hyperlink_pmid(pmid: str, pmid_url_map: dict) -> str:
    """Return markdown hyperlink for a PMID."""
    pmid = str(pmid).strip()
    if not pmid:
        return ""
    url = pmid_url_map.get(pmid, "")
    if not url and pmid.isdigit():
        url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
    if url:
        return f"[PMID: {pmid}]({url})"
    return f"PMID: {pmid}"


def hyperlink_pmids_in_text(text: str, pmid_url_map: dict) -> str:
    """Replace bare [PMID] patterns in text with hyperlinked markdown."""
    def _replace_match(match):
        pmid = match.group(1)
        url = pmid_url_map.get(pmid, "")
        if not url and pmid.isdigit():
            url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
        if url:
            return f"[PMID: {pmid}]({url})"
        return match.group(0)
    return re.sub(r'\[(\d{5,})\]', _replace_match, text)


# ---------------------------------------------------------------------------
# Markdown report generation
# ---------------------------------------------------------------------------

def generate_markdown_report(
    results: List[Dict],
    experiments: List[Dict],
    synthesis: Dict,
    target: str,
    disease: str,
    output_file: str
) -> None:
    """Generate structured markdown synthesis report."""
    n_papers = synthesis["total_papers"]
    type_bd = synthesis["experiment_type_breakdown"]

    # Year range
    years = [e.get("publication_date", "")[:4] for e in experiments]
    years = [y for y in years if y.isdigit()]
    year_range = f"{min(years)}-{max(years)}" if years else "N/A"

    md = f"""# Preclinical Literature Extraction Report

| | |
|---|---|
| **Target** | {target} |
| **Disease** | {disease} |
| **Date Generated** | {datetime.now().strftime('%Y-%m-%d')} |
| **Total Papers** | {n_papers} |
| **Date Range** | {year_range} |

---

## Summary

This report extracts and synthesizes preclinical experiment details from {n_papers} papers studying **{target}** in **{disease}**.

### Experiment Type Breakdown

| Type | Count | Percentage |
|------|-------|------------|
| In vitro only | {type_bd.get('in_vitro', 0)} | {type_bd.get('in_vitro', 0)/max(n_papers,1)*100:.1f}% |
| In vivo only | {type_bd.get('in_vivo', 0)} | {type_bd.get('in_vivo', 0)/max(n_papers,1)*100:.1f}% |
| Both | {type_bd.get('both', 0)} | {type_bd.get('both', 0)/max(n_papers,1)*100:.1f}% |
| Unclassified | {type_bd.get('unclassified', 0)} | {type_bd.get('unclassified', 0)/max(n_papers,1)*100:.1f}% |

"""

    # Build URL maps for hyperlinking papers
    pmid_url_map, doi_url_map = build_url_maps(results)

    # Insert narrative synthesis section if available
    narrative = synthesis.get("narrative", {})
    narrative_md = narrative.get("narrative_markdown", "")
    if narrative_md:
        # Hyperlink bare PMID references in narrative text
        narrative_md = hyperlink_pmids_in_text(narrative_md, pmid_url_map)
        md += "\n---\n\n"
        md += narrative_md

    md += """---

## In Vitro Experiments

### Most Common Cell Lines

"""
    cell_lines = synthesis.get("cell_line_frequency", {})
    if cell_lines:
        md += "| Rank | Cell Line | Papers |\n|------|-----------|--------|\n"
        for i, (cl, count) in enumerate(list(cell_lines.items())[:15], 1):
            md += f"| {i} | {cl} | {count} |\n"
    else:
        md += "_No cell lines detected._\n"

    md += "\n### Most Common Assay Types\n\n"
    assays = synthesis.get("assay_frequency", {})
    if assays:
        md += "| Rank | Assay Type | Papers |\n|------|-----------|--------|\n"
        for i, (assay, count) in enumerate(list(assays.items())[:15], 1):
            md += f"| {i} | {assay} | {count} |\n"
    else:
        md += "_No assays detected._\n"

    md += "\n---\n\n## In Vivo Experiments\n\n### Animal Model Types\n\n"
    models = synthesis.get("animal_model_frequency", {})
    if models:
        md += "| Rank | Model Type | Papers |\n|------|-----------|--------|\n"
        for i, (model, count) in enumerate(list(models.items())[:10], 1):
            md += f"| {i} | {model} | {count} |\n"
    else:
        md += "_No animal models detected._\n"

    md += "\n### Endpoints Measured\n\n"
    endpoints = synthesis.get("endpoint_frequency", {})
    if endpoints:
        md += "| Rank | Endpoint | Papers |\n|------|----------|--------|\n"
        for i, (ep, count) in enumerate(list(endpoints.items())[:10], 1):
            md += f"| {i} | {ep} | {count} |\n"
    else:
        md += "_No endpoints detected._\n"

    md += "\n---\n\n## Papers with Both In Vitro and In Vivo Data\n\n"
    both_papers = [e for e in experiments if e["experiment_type"] == "both"]
    if both_papers:
        n_both = len(both_papers)
        verb = "reports" if n_both == 1 else "report"
        noun = "paper" if n_both == 1 else "papers"
        md += f"{n_both} {noun} {verb} both in vitro and in vivo experiments:\n\n"
        for i, e in enumerate(both_papers[:20], 1):
            pmid = str(e.get('pmid', '')).strip()
            paper_url = pmid_url_map.get(pmid, '')
            if not paper_url:
                doi = str(e.get('doi', '')).strip()
                paper_url = doi_url_map.get(doi, '')
            if paper_url:
                md += f"{i}. **[{e['title']}]({paper_url})**\n"
            else:
                md += f"{i}. **{e['title']}**\n"
            author_line = f"   - {e['authors'][:60]}... ({e['publication_date'][:4]})"
            if pmid:
                author_line += f" \u2014 {hyperlink_pmid(pmid, pmid_url_map)}"
            md += f"{author_line}\n"
            if e["cell_lines"]:
                md += f"   - Cell lines: {e['cell_lines']}\n"
            if e["assays"]:
                md += f"   - Assays: {e['assays']}\n"
            if e["animal_models"]:
                md += f"   - Models: {e['animal_models']}\n"
            if e["endpoints"]:
                md += f"   - Endpoints: {e['endpoints']}\n"
            md += "\n"
    else:
        md += "_No papers with both experiment types found._\n"

    md += "\n---\n\n## Publication Timeline\n\n"
    year_dist = synthesis.get("year_distribution", {})
    if year_dist:
        md += "| Year | Papers |\n|------|--------|\n"
        for year, count in sorted(year_dist.items()):
            md += f"| {year} | {count} |\n"

    md += "\n---\n\n## Per-Paper Extraction Details\n\n"
    md += "See `experiment_extraction.csv` for full per-paper details.\n\n"

    md += "---\n\n"
    md += "## Full-Text Insights\n\n"
    md += "_Pending: Read full text for top papers and replace this section "
    md += "with per-paper findings. See references/full-text-enrichment-guide.md._\n\n"

    # References section with all papers hyperlinked
    md += "---\n\n## References\n\n"
    for i, r in enumerate(results, 1):
        pmid = str(r.get('pmid', '')).strip()
        doi = str(r.get('doi', '')).strip()
        url = str(r.get('url', '')).strip()
        title = r.get('title', 'Untitled')
        authors = r.get('authors', 'Unknown')
        journal = r.get('journal', '')

        ref = f"{i}. {authors}. "
        if url:
            ref += f"[{title}]({url})"
        else:
            ref += title
        if journal:
            ref += f". *{journal}*"
        ref += "."

        identifiers = []
        if pmid:
            identifiers.append(hyperlink_pmid(pmid, pmid_url_map))
        if doi:
            identifiers.append(f"[DOI: {doi}](https://doi.org/{doi})")
        if identifiers:
            ref += " " + " | ".join(identifiers)

        md += f"{ref}\n\n"

    md += "---\n\n"
    md += "_Report generated by literature-preclinical skill._\n"

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(md)


# ---------------------------------------------------------------------------
# PDF generation
# ---------------------------------------------------------------------------

def generate_pdf_report(md_path: str, pdf_path: str) -> bool:
    """Convert markdown report to PDF.

    Tries weasyprint first (best quality), falls back to pandoc.
    Returns True if PDF was generated successfully.
    """
    # Strategy 1: markdown + weasyprint (pip install markdown weasyprint)
    try:
        import markdown as md_lib
        from weasyprint import HTML

        with open(md_path, "r", encoding="utf-8") as f:
            md_content = f.read()

        html_body = md_lib.markdown(
            md_content,
            extensions=["tables", "fenced_code"],
        )

        # Make all links open in a new window/tab
        html_body = re.sub(r'<a ', '<a target="_blank" ', html_body)

        styled_html = (
            "<!DOCTYPE html>\n<html>\n<head><meta charset='utf-8'><style>\n"
            "body { font-family: 'Helvetica Neue', Arial, sans-serif; "
            "margin: 40px; line-height: 1.6; color: #333; max-width: 900px; }\n"
            "h1 { color: #1a1a1a; border-bottom: 2px solid #333; padding-bottom: 10px; }\n"
            "h2 { color: #2c3e50; border-bottom: 1px solid #ddd; padding-bottom: 5px; "
            "margin-top: 30px; }\n"
            "h3 { color: #34495e; margin-top: 20px; }\n"
            "table { border-collapse: collapse; width: 100%; margin: 15px 0; "
            "font-size: 0.9em; }\n"
            "th, td { border: 1px solid #ddd; padding: 8px 12px; text-align: left; }\n"
            "th { background-color: #f5f5f5; font-weight: bold; }\n"
            "tr:nth-child(even) { background-color: #fafafa; }\n"
            "a { color: #2980b9; text-decoration: none; }\n"
            "a:hover { text-decoration: underline; }\n"
            "hr { border: none; border-top: 1px solid #ddd; margin: 20px 0; }\n"
            "ul, ol { padding-left: 20px; }\n"
            "li { margin-bottom: 5px; }\n"
            "strong { color: #1a1a1a; }\n"
            "em { color: #555; }\n"
            "@page { margin: 2cm; size: A4; "
            "@bottom-center { content: counter(page); font-size: 9pt; color: #999; } }\n"
            "</style>\n</head>\n<body>\n"
            f"{html_body}\n"
            "</body>\n</html>"
        )

        HTML(string=styled_html).write_pdf(pdf_path)
        return True
    except ImportError:
        pass
    except Exception as e:
        print(f"    weasyprint error: {e}")

    # Strategy 2: pandoc (system tool)
    try:
        import shutil
        import subprocess
        if shutil.which("pandoc"):
            # Use xelatex for Unicode support (alpha, beta, etc. in abstracts)
            pdf_engine = "xelatex" if shutil.which("xelatex") else "pdflatex"
            result = subprocess.run(
                ["pandoc", md_path, "-o", pdf_path,
                 f"--pdf-engine={pdf_engine}",
                 "-V", "geometry:margin=2.5cm",
                 "-V", "colorlinks=true",
                 "-V", "linkcolor=blue"],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0:
                return True
            print(f"    pandoc error: {result.stderr[:200]}")
    except Exception as e:
        print(f"    pandoc error: {e}")

    return False

