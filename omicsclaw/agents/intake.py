"""Input preprocessing and PDF→Markdown conversion.

Handles three input modes:
- Mode A: PDF + idea (data obtainable from paper / GEO)
- Mode B: PDF + idea + h5ad (user-provided data)
- Mode C: idea only (no PDF, no data — pure research from scratch)

Converts PDF to structured Markdown for agent consumption.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class IntakeResult:
    """Structured output from the intake stage."""

    # Paper content (present in Mode A/B, empty in Mode C)
    paper_markdown: str = ""
    paper_title: str = ""

    # User input (always present)
    idea: str = ""

    # Extracted metadata (from PDF; empty in Mode C)
    geo_accessions: list[str] = field(default_factory=list)
    organism: str = ""
    tissue: str = ""
    technology: str = ""

    # Data description (Mode B — user-provided h5ad)
    h5ad_metadata: dict[str, Any] | None = None
    input_mode: str = "A"  # "A", "B", or "C"

    # File paths
    paper_md_path: str = ""
    h5ad_path: str = ""

    @classmethod
    def from_workspace(
        cls,
        workspace_dir: str,
        idea: str = "",
        pdf_path: str | None = None,
        h5ad_path: str | None = None,
    ) -> "IntakeResult":
        """Reconstruct an IntakeResult from an existing workspace.

        Used during pipeline resume to skip re-running the intake stage.
        Reads metadata and file paths from the workspace directory.
        """
        ws = Path(workspace_dir)

        # Determine input mode from existing files
        paper_dir = ws / "paper"
        has_paper = paper_dir.exists() and any(paper_dir.iterdir())
        if not has_paper:
            input_mode = "C"
        elif h5ad_path:
            input_mode = "B"
        else:
            input_mode = "A"

        # Read paper title from abstract file
        paper_title = ""
        abstract_path = paper_dir / "01_abstract_conclusion.md"
        if abstract_path.exists():
            # Title is typically the first non-empty line
            for line in abstract_path.read_text(encoding="utf-8").splitlines():
                line = line.strip().lstrip("#").strip()
                if line:
                    paper_title = line[:200]
                    break

        # Check for methodology
        meth_path = paper_dir / "02_methodology.md"

        # Read metadata JSON if it exists
        geo_accessions: list[str] = []
        organism = tissue = technology = ""
        meta_path = ws / "paper" / "metadata.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                geo_accessions = meta.get("geo_accessions", [])
                organism = meta.get("organism", "")
                tissue = meta.get("tissue", "")
                technology = meta.get("technology", "")
            except (json.JSONDecodeError, KeyError):
                pass

        return cls(
            paper_markdown="",  # Not needed for resume
            paper_title=paper_title,
            idea=idea,
            geo_accessions=geo_accessions,
            organism=organism,
            tissue=tissue,
            technology=technology,
            h5ad_metadata=None,
            input_mode=input_mode,
            paper_md_path=str(meth_path) if meth_path.exists() else "",
            h5ad_path=h5ad_path or "",
        )


# =========================================================================
# PDF → Markdown conversion
# =========================================================================


def _convert_pdf_opendataloader(pdf_path: str, output_dir: str) -> str | None:
    """Convert PDF to Markdown using opendataloader-pdf (preferred engine).

    Returns the **post-processed** Markdown content string on success,
    or ``None`` if opendataloader-pdf is not installed or conversion fails.

    All warnings from the Java/ODL runtime (which write directly to the
    OS-level stderr via ``java.util.logging``) are suppressed by
    temporarily redirecting file-descriptor 2 to ``/dev/null``.

    Requires:
        pip install opendataloader-pdf   # + Java 11+
    """
    try:
        import opendataloader_pdf
    except ImportError:
        logger.debug("opendataloader-pdf not installed — skipping")
        return None

    import logging as _logging
    import os
    import sys
    import tempfile
    import warnings

    # ── 1. Suppress Python-level loggers ──────────────────────────
    _odl_loggers = [
        "opendataloader_pdf",
        "opendataloader",
        "jpype",
        "java",
    ]
    saved_levels: dict[str, int] = {}
    for name in _odl_loggers:
        lg = _logging.getLogger(name)
        saved_levels[name] = lg.level
        lg.setLevel(_logging.ERROR)

    # ── 2. Redirect OS-level stdout (fd 1) and stderr (fd 2) ───────────
    # Java's java.util.logging or sub-processes might write to native 
    # file descriptors (fd 1 or 2) directly. Python's logging/warnings 
    # cannot intercept this. We point fd 1 and 2 to /dev/null temporarily.
    saved_stdout_fd = os.dup(1)          # save original fd 1
    saved_stderr_fd = os.dup(2)          # save original fd 2
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    
    # Also redirect Python's sys.stdout and sys.stderr
    saved_sys_stdout = sys.stdout
    saved_sys_stderr = sys.stderr

    try:
        os.dup2(devnull_fd, 1)           # stdout → /dev/null
        os.dup2(devnull_fd, 2)           # stderr → /dev/null
        sys.stdout = open(os.devnull, "w")  # noqa: SIM115
        sys.stderr = open(os.devnull, "w")  # noqa: SIM115

        with tempfile.TemporaryDirectory(prefix="oc_odl_") as tmp_dir:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                opendataloader_pdf.convert(
                    input_path=[pdf_path],
                    output_dir=tmp_dir,
                    format="markdown",
                )
            # Find the generated markdown file
            md_files = list(Path(tmp_dir).glob("**/*.md"))
            if not md_files:
                logger.warning("opendataloader-pdf produced no .md output")
                return None
            md_content = md_files[0].read_text(encoding="utf-8")
            
            # Since we have logging redirected, we must restore before logging
            sys.stdout.close()
            sys.stderr.close()
            sys.stdout = saved_sys_stdout
            sys.stderr = saved_sys_stderr
            os.dup2(saved_stdout_fd, 1)
            os.dup2(saved_stderr_fd, 2)

            if md_content.strip():
                logger.info(
                    "opendataloader-pdf converted %s (%d chars → post-process)",
                    pdf_path, len(md_content),
                )
                md_content = _postprocess_odl_markdown(md_content)
                logger.info(
                    "Post-processed to %d chars",
                    len(md_content),
                )
                return md_content
            
            logger.warning("opendataloader-pdf output was empty")
            return None
    except Exception as e:
        # Restore before logging
        try:
            sys.stdout = saved_sys_stdout
            sys.stderr = saved_sys_stderr
            os.dup2(saved_stdout_fd, 1)
            os.dup2(saved_stderr_fd, 2)
        except Exception:
            pass
        logger.warning("opendataloader-pdf failed for %s: %s", pdf_path, e)
        return None
    finally:
        # ── Restore stdout & stderr ────────────────────────────────────────
        try:
            sys.stdout = saved_sys_stdout
            sys.stderr = saved_sys_stderr
            os.dup2(saved_stdout_fd, 1)
            os.dup2(saved_stderr_fd, 2)
            os.close(saved_stdout_fd)
            os.close(saved_stderr_fd)
            os.close(devnull_fd)
        except Exception:
            pass
            
        # Restore Python logger levels
        for name, level in saved_levels.items():
            _logging.getLogger(name).setLevel(level)


# ── ODL Markdown post-processing ──────────────────────────────────────────


# Sections that are typically not useful for downstream research analysis.
# We match on heading text (case-insensitive) and remove everything from
# that heading until the next same-or-higher-level heading.
_STRIP_SECTIONS = {
    # Exact heading matches (lowercased)
    "references",
    "bibliography",
    "acknowledgements",
    "acknowledgments",
    "author contributions",
    "competing interests",
    "additional information",
    "supplementary information",
    "supplementary materials",
    "supplementary figures",
    "supplementary tables",
    "code availability",
    "data availability",
    "reporting summary",
    "extended data",
    "extended data figures",
    "extended data tables",
    # NOTE: "online methods" was previously stripped here, but Nature papers
    # put their *entire* methodology in this section.  We now keep it so that
    # it flows into 02_methodology.md during the Macro Agentic FS split.
    "ethics oversight",
    "peer review information",
    "reprints and permissions",
    "nature portfolio",     # reporting checklist header
}

# Patterns for lines to remove individually (not section-based)
_STRIP_LINE_PATTERNS = [
    re.compile(r"^!\[image\s+\d+\]", re.IGNORECASE),          # ![image 1](...)
    re.compile(r"^!\[.*?\]\(.*?imageFile.*?\)", re.IGNORECASE), # ODL image refs
    re.compile(r"^\|\s*\|\s*$"),                                # empty table rows |  |
    re.compile(r"^\|---\|$"),                                   # minimal table separators
    re.compile(r"^Check for updates\s*$", re.IGNORECASE),
    re.compile(r"^nature portfolio.*reporting summary", re.IGNORECASE),
    re.compile(r"^Tick this box to confirm", re.IGNORECASE),
]


def _postprocess_odl_markdown(md: str) -> str:
    """Clean opendataloader-pdf Markdown output for research use.

    Removes:
    - Image embed lines ``![image N](...)``
    - Entire sections: References, Acknowledgements, Extended Data, etc.
    - Reporting summary / checklist boilerplate
    - Empty / decorative table rows
    - Redundant whitespace runs

    Keeps:
    - Title, authors, abstract
    - Main body sections (Introduction, Results, Discussion, Methods)
    - Inline citations (superscript numbers)
    """
    lines = md.split("\n")
    result: list[str] = []
    skip_until_level: int | None = None  # heading level to stop skipping at

    for line in lines:
        stripped = line.strip()

        # ── Check if we enter a section to skip ──────────────────
        heading_match = re.match(r"^(#{1,6})\s+(.*)", stripped)
        if heading_match:
            level = len(heading_match.group(1))
            heading_text = heading_match.group(2).strip()
            heading_lower = heading_text.lower().rstrip(".")

            # Are we currently skipping? Check if we should stop.
            if skip_until_level is not None:
                if level <= skip_until_level:
                    # Same or higher level heading → stop skipping
                    skip_until_level = None
                else:
                    continue  # still inside a skipped section

            # Should we start skipping this heading?
            if heading_lower in _STRIP_SECTIONS or any(
                heading_lower.startswith(s) for s in _STRIP_SECTIONS
            ):
                skip_until_level = level
                continue

            # Also skip generic figure legend headings like
            # "Fig. 1 | Description" or "Extended Data Fig. X"
            if re.match(
                r"^(extended\s+data\s+)?fig(\.|ure)\s*\d",
                heading_lower,
            ):
                skip_until_level = level
                continue

        # If we're in a skipped section, drop the line
        if skip_until_level is not None:
            continue

        # ── Drop individual noisy lines ──────────────────────────
        if any(pat.match(stripped) for pat in _STRIP_LINE_PATTERNS):
            continue

        # ── Drop lines that are only affiliation / footnote markers ──
        # e.g. "1School of Biological Sciences, Department of..."
        if re.match(r"^\d+[A-Z][a-z]+.*(University|Institute|Department)", stripped):
            continue

        result.append(line)

    # ── Collapse excessive blank lines ────────────────────────────
    cleaned = "\n".join(result)
    cleaned = re.sub(r"\n{4,}", "\n\n\n", cleaned)

    return cleaned.strip()


def _extract_pdf_text(pdf_path: str) -> str:
    """Extract raw text from PDF using pypdf (fallback engine)."""
    try:
        from pypdf import PdfReader
    except ImportError:
        try:
            from PyPDF2 import PdfReader
        except ImportError:
            logger.warning("No PDF library found (pypdf/PyPDF2), using fallback")
            return _fallback_pdf_text(pdf_path)

    try:
        reader = PdfReader(pdf_path)
        pages = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            if text.strip():
                pages.append(f"<!-- Page {i + 1} -->\n{text}")
        if pages:
            return "\n\n".join(pages)
    except Exception as e:
        logger.warning("pypdf failed to read %s: %s — trying fallback", pdf_path, e)

    return _fallback_pdf_text(pdf_path)


def _fallback_pdf_text(pdf_path: str) -> str:
    """Last resort: use pdftotext CLI if available."""
    import subprocess

    try:
        result = subprocess.run(
            ["pdftotext", "-layout", pdf_path, "-"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            return result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return f"[Unable to extract text from PDF: {pdf_path}]"


def _extract_geo_accessions(text: str) -> list[str]:
    """Extract GEO accession numbers from text."""
    gse = re.findall(r"\b(GSE\d{4,8})\b", text, re.IGNORECASE)
    gsm = re.findall(r"\b(GSM\d{4,8})\b", text, re.IGNORECASE)
    # Deduplicate preserving order
    seen = set()
    result = []
    for acc in gse + gsm:
        acc_upper = acc.upper()
        if acc_upper not in seen:
            seen.add(acc_upper)
            result.append(acc_upper)
    return result


def _extract_organism(text: str) -> str:
    """Extract organism(s) from text.  Returns all detected organisms."""
    lower = text.lower()
    organisms: list[str] = []
    if any(w in lower for w in ["homo sapiens", "human patient", "human sample",
                                 "human tissue"]):
        organisms.append("Homo sapiens")
    if any(w in lower for w in ["mus musculus", "mouse", "murine"]):
        organisms.append("Mus musculus")
    if not organisms:
        # Broad fallback — only if nothing specific was found
        if "human" in lower:
            organisms.append("Homo sapiens (inferred)")
    return ", ".join(organisms) if organisms else "Unknown"


def _extract_technology(text: str) -> str:
    """Extract sequencing technology(ies) from text.  Returns all matches."""
    lower = text.lower()
    tech_patterns = [
        ("Visium HD", ["visium hd", "visiumhd"]),
        ("10x Visium", ["visium", "10x visium"]),
        ("Xenium", ["xenium"]),
        ("MERSCOPE", ["merscope"]),
        ("MERFISH", ["merfish"]),
        ("seqFISH", ["seqfish"]),
        ("Slide-seq", ["slide-seq", "slideseq"]),
        ("STORM-seq", ["storm-seq"]),
        ("10x Chromium", ["10x chromium", "10x genomics", "chromium"]),
        ("Smart-seq2", ["smart-seq2", "smartseq2"]),
        ("Drop-seq", ["drop-seq", "dropseq"]),
        ("snRNA-seq", ["snrna-seq", "single-nucleus rna"]),
        ("scRNA-seq", ["scrna-seq", "single-cell rna"]),
        ("Bulk RNA-seq", ["bulk rna-seq", "bulk rna seq"]),
    ]
    found: list[str] = []
    for name, patterns in tech_patterns:
        if any(p in lower for p in patterns):
            # Avoid duplicates (e.g. "Visium HD" already covers "visium")
            if not any(name in f or f in name for f in found):
                found.append(name)
    return ", ".join(found) if found else "Unknown"


def _extract_tissue(text: str) -> str:
    """Extract tissue type from text."""
    lower = text.lower()
    tissues = [
        "small intestine", "intestine", "colon",
        "brain", "liver", "lung", "kidney", "heart", "skin",
        "breast", "pancreas", "ovary", "prostate",
        "muscle", "bone marrow", "lymph node", "spleen",
        "tumor", "cancer",
    ]
    found = [t for t in tissues if t in lower]
    # Deduplicate substrings (e.g. "small intestine" includes "intestine")
    deduped: list[str] = []
    for t in found:
        if not any(t != other and t in other for other in found):
            deduped.append(t)
    return ", ".join(deduped[:3]) if deduped else "Unknown"


# ── Noise filtering helpers ────────────────────────────────────────────────


def _is_noise_line(line: str) -> bool:
    """Detect lines that are figure/table axis labels or other PDF noise."""
    stripped = line.strip()
    if not stripped:
        return False
    # Pure numbers, number sequences, or very short non-word fragments
    if re.fullmatch(r"[\d\s.,;:–−\-/]+", stripped):
        return True
    # Very short fragments that are likely axis ticks or legend labels
    if len(stripped) <= 3 and not re.search(r"[a-zA-Z]{2,}", stripped):
        return True
    # Single letter sub-panel labels (e.g. "a", "b", "c", "d", "e", "f", "g")
    if re.fullmatch(r"[a-zA-Z]", stripped):
        return True
    # Concatenated axis-tick strings like "0.150.30.610.156" or "0.150.3 0.6160.150.3"
    if re.fullmatch(r"[\d.\s]{8,}", stripped):
        return True
    # Axis tick ranges like "0 1 0 1 0 1 0 1" or "10 30 50 70 90"
    if re.fullmatch(r"(\d+\s+){2,}\d+", stripped):
        return True
    # Journal page-number lines: "484 | Nature | Vol 639 | 13 March 2025"
    if re.search(r"^\d+\s*\|\s*Nature\s*\|", stripped):
        return True
    # Short axis/legend labels: "Min.", "Max.", "Expression", "Bottom Top" etc.
    if len(stripped) < 15 and not re.search(r"[a-zA-Z]{4,}\s+[a-zA-Z]{4,}", stripped):
        # But keep short headings that start with # (Markdown headings)
        if not stripped.startswith("#"):
            # Keep lines that are clearly sentences (contain a period + letter after)
            if not re.search(r"\.\s*[A-Z]", stripped):
                return True
    return False


def _clean_body_text(text: str) -> str:
    """Remove figure/table noise from extracted PDF text.

    Handles the full spectrum of opendataloader-pdf conversion artifacts:
    - Empty Markdown tables (``| | |\\n|---|---|``)
    - Image tag runs (``![image 1234](...)<br><br>``)
    - Axis tick fragments and concatenated numeric strings
    - Figure sub-panel labels (isolated ``a``, ``b``, ``c``)
    - Journal page-number lines
    - Excessive blank lines
    """
    # ── Phase 1: Regex-based bulk removal ─────────────────────────
    # Remove empty Markdown tables  | | |\n|---|---|\n| | |\n...
    text = re.sub(
        r"(?:\|\s*(?:<br>)?\s*\|[\s|]*\n?)+(?:\|[-|–]+\|[\s|]*\n?)+(?:\|\s*(?:<br>[^|]*)?\s*\|[\s|]*\n?)*",
        "\n", text,
    )
    # Remove image reference runs: ![image 1234](path)<br><br>...
    text = re.sub(
        r"(?:\|?\s*!\[image\s+\d+\]\([^)]+\)\s*(?:<br>)*\s*)+",
        "\n", text,
    )
    # Remove standalone <br> tags
    text = re.sub(r"<br>\s*", " ", text)
    # Remove journal page lines: "484 | Nature | Vol 639 | 13 March 2025"
    text = re.sub(r"^\d+\s*\|\s*Nature\s*\|[^\n]*$", "", text, flags=re.MULTILINE)

    # ── Phase 2: Line-by-line noise filtering ─────────────────────
    lines = text.split("\n")
    cleaned: list[str] = []
    noise_run = 0
    for line in lines:
        if _is_noise_line(line):
            noise_run += 1
            # Allow up to 1 isolated noise line (may be inside a list)
            if noise_run <= 1:
                # Only keep it if surrounded by real content
                cleaned.append(line)
            continue
        noise_run = 0
        cleaned.append(line)

    # ── Phase 3: Collapse excessive blank lines (max 2) ──────────
    result = "\n".join(cleaned)
    result = re.sub(r"\n{4,}", "\n\n\n", result)
    # Remove leading/trailing whitespace per line but preserve structure
    lines_final = []
    for line in result.split("\n"):
        lines_final.append(line.rstrip())
    return "\n".join(lines_final)


def _extract_title(raw_text: str, pdf_path: str) -> str:
    """Extract paper title from raw PDF text.

    Strategy:
    1. Skip HTML page comments, journal headers and short noise lines.
    2. Pick the first 'substantial' line (>=20 chars, mostly letters).
    3. If it spans multiple lines before a blank line, join them.
    """
    lines = raw_text.split("\n")
    candidate_lines: list[str] = []
    collecting = False

    for line in lines:
        stripped = line.strip()
        # Skip empty / page markers / journal header lines
        if not stripped:
            if collecting:
                break  # end of title block
            continue
        if stripped.startswith("<!--"):
            continue
        # Skip typical journal header patterns
        if re.match(r"^(Nature|Science|Cell|Article|Letter)\s*\|", stripped):
            continue
        if re.match(r"^(Nature|Science|Cell)\s*$", stripped, re.IGNORECASE):
            continue
        # Skip short numeric / noise lines
        if _is_noise_line(stripped):
            continue
        # Must contain enough letters to be a title
        alpha_ratio = sum(c.isalpha() for c in stripped) / max(len(stripped), 1)
        if alpha_ratio < 0.4:
            continue
        if len(stripped) < 15 and not collecting:
            continue

        collecting = True
        candidate_lines.append(stripped)

        # Title usually doesn't exceed 3 lines
        if len(candidate_lines) >= 3:
            break

    if candidate_lines:
        return " ".join(candidate_lines)
    return Path(pdf_path).stem


def _extract_abstract(raw_text: str) -> str:
    """Extract abstract from raw PDF text using multiple strategies."""
    # Strategy 1: explicit "Abstract" header
    for pattern in [
        # "Abstract" followed by text, ending at Introduction/Keywords/etc.
        r"(?:^|\n)\s*(?:Abstract|ABSTRACT)\s*\n+(.*?)(?:\n\s*(?:Introduction|INTRODUCTION|Keywords|KEYWORDS|Main|Background|BACKGROUND|1[\s.]+\w))",
        # Abstract followed by text ending at a double newline + section header
        r"(?:^|\n)\s*(?:Abstract|ABSTRACT)\s*\n+(.*?)(?:\n\n+\s*[A-Z][A-Za-z\s]{5,}\n)",
    ]:
        m = re.search(pattern, raw_text, re.IGNORECASE | re.DOTALL)
        if m:
            text = m.group(1).strip()
            # Validate: real abstracts are >50 chars and have sentences
            if len(text) > 50 and "." in text:
                # Clean up page markers inside abstract
                text = re.sub(r"<!--.*?-->", "", text).strip()
                return text

    # Strategy 2: Nature-style inline abstract (no explicit header)
    # Look for a substantial paragraph early in the text that contains
    # typical abstract vocabulary
    paragraphs = re.split(r"\n\s*\n", raw_text[:8000])
    for para in paragraphs[:10]:
        para_clean = para.strip()
        # Skip short paragraphs and page markers
        if len(para_clean) < 200:
            continue
        if para_clean.startswith("<!--"):
            continue
        # Look for hallmarks of an abstract: "Here we", "we show", "our study",
        # "we demonstrate", "we developed", etc.
        abstract_signals = [
            "here we", "we show", "our study", "we demonstrate",
            "we developed", "we propose", "we report", "this study",
            "we present", "we found", "our results", "we identify",
            "we reveal", "our framework",
        ]
        lower_para = para_clean.lower()
        if any(sig in lower_para for sig in abstract_signals):
            # Clean up
            para_clean = re.sub(r"<!--.*?-->", "", para_clean).strip()
            return para_clean

    return ""


def _extract_sections(raw_text: str) -> list[tuple[str, str]]:
    """Extract major sections from paper body text.

    Returns list of (heading, content) tuples.
    Skips reference lists and acknowledgements.

    Supports **both** Markdown heading syntax (``#+ Title``) and bare
    title-case headings that appear on their own line.

    For Nature-style papers where a top-level region marker like ``Methods``
    is followed by multiple sub-sections (``Mice``, ``Adoptive cell transfer``,
    etc.), the sub-sections are automatically merged into the parent region so
    that ``02_methodology.md`` captures all of them as a single block.
    """
    # Remove page markers for cleaner section detection
    text = re.sub(r"<!--\s*Page\s*\d+\s*-->", "", raw_text)

    # ── Dual-format heading extraction ────────────────────────────
    # Pattern A: Markdown headings  (##+ Title)
    md_heading_pat = re.compile(
        r"^(#{1,6})\s+(.+)$", re.MULTILINE,
    )
    # Pattern B: Bare title-case headings (existing logic)
    bare_heading_pat = re.compile(
        r"\n\s*((?:[A-Z][a-z]+(?:\s+[a-zA-Z]+){1,10}|[A-Z\s]{10,50}))\s*\n",
    )

    # Collect all heading candidates (position, heading_text)
    candidates: list[tuple[int, int, str]] = []  # (start_of_heading, end_of_heading, heading_text)

    for m in md_heading_pat.finditer(text):
        heading_text = m.group(2).strip()
        # Skip if it looks like a figure/table sub-label (single letter, e.g. "a", "b c")
        if len(heading_text) <= 3 and not heading_text[0].isupper():
            continue
        candidates.append((m.start(), m.end(), heading_text))

    # Only use bare headings if Markdown headings didn't find enough
    if len(candidates) < 3:
        for m in bare_heading_pat.finditer(text):
            heading_text = m.group(1).strip()
            candidates.append((m.start(), m.end(), heading_text))
        # Deduplicate and sort by position
        candidates.sort(key=lambda x: x[0])

    if not candidates:
        return []

    # ── Sections to skip ──────────────────────────────────────────
    skip_headings = {
        "references", "bibliography", "acknowledgements", "acknowledgments",
        "author contributions", "competing interests", "additional information",
        "supplementary information", "code availability", "data availability",
        "extended data", "reporting summary", "online content",
    }

    # ── Top-level region markers for merging sub-sections ─────────
    # When we encounter these, all following sub-sections are merged
    # into a single logical block until the next region marker.
    _REGION_MARKERS = {
        "methods": "methodology",
        "online methods": "methodology",
        "experimental procedures": "methodology",
        "materials and methods": "methodology",
        "star methods": "methodology",
        "discussion": "results_figs",
    }

    sections: list[tuple[str, str]] = []
    active_region: str | None = None  # Current merging region
    region_heading: str | None = None   # Heading of the active region marker

    for idx, (h_start, h_end, heading) in enumerate(candidates):
        h_lower = heading.lower().strip()

        # Skip unwanted sections
        if h_lower in skip_headings:
            active_region = None  # Stop merging if we hit references etc.
            continue

        # Determine content span: from heading end to next heading start
        if idx + 1 < len(candidates):
            content_end = candidates[idx + 1][0]
        else:
            content_end = len(text)
        content = text[h_end:content_end].strip()

        # Check if this is a region marker
        if h_lower in _REGION_MARKERS:
            active_region = _REGION_MARKERS[h_lower]
            region_heading = heading
            # If the marker itself has substantial content, include it
            if len(content) >= 100:
                sections.append((heading, content))
            continue

        # If we're inside a region (e.g. under "Methods"), tag the heading
        # with the region prefix so _classify_section can route it properly.
        if active_region == "methodology":
            # Prefix with "Methods: " so _classify_section recognizes it
            tagged_heading = f"Methods: {heading}"
        else:
            tagged_heading = heading

        # Skip very short content (likely figure labels, axis labels, etc.)
        if len(content) < 80:
            continue

        sections.append((tagged_heading, content))

    return sections[:40]  # Allow more sections for Nature-style papers


# =========================================================================
# Macro Agentic FS — modular paper file builders
# =========================================================================

# Heading keywords used to classify sections into the three modular files.
_ABSTRACT_CONCLUSION_KEYWORDS = [
    "abstract", "introduction", "background", "conclusion", "conclusions",
    "summary",
]
_METHODOLOGY_KEYWORDS = [
    "method", "online method", "experimental", "data processing",
    "data analysis", "computational", "statistical analysis",
    "bioinformatics", "pipeline", "preprocessing", "pre-processing",
    "implementation", "algorithm", "workflow",
]
_RESULTS_KEYWORDS = [
    "result", "discussion", "finding", "observation", "analysis",
    "comparison", "evaluation", "performance", "validation",
]


def _classify_section(heading: str) -> str:
    """Return the bucket name for a section heading.

    Returns one of ``"abstract_conclusion"``, ``"methodology"``,
    ``"results_figs"``, or ``"other"``.
    """
    h = heading.lower().strip()
    # Check methodology first — it is the most important to separate.
    if any(k in h for k in _METHODOLOGY_KEYWORDS):
        return "methodology"
    if any(k in h for k in _ABSTRACT_CONCLUSION_KEYWORDS):
        return "abstract_conclusion"
    if any(k in h for k in _RESULTS_KEYWORDS):
        return "results_figs"
    return "other"


def _build_header_block(
    title: str,
    pdf_name: str,
    raw_text: str,
    organism: str,
    technology: str,
    tissue: str,
    geo_ids: list[str],
) -> str:
    """Build the common header (title, DOI, authors, metadata table)."""
    parts: list[str] = [f"# {title}\n", f"**Source**: {pdf_name}"]

    doi_match = re.search(r"(https?://doi\.org/\S+)", raw_text)
    if doi_match:
        parts.append(f"**DOI**: {doi_match.group(1).rstrip('.)}')}")

    author_line = _extract_authors(raw_text, title)
    if author_line:
        parts.append(f"\n**Authors**: {author_line}")
    parts.append("")

    parts.append("## Metadata\n")
    parts.append("| Field | Value |")
    parts.append("|-------|-------|")
    parts.append(f"| Organism | {organism} |")
    parts.append(f"| Technology | {technology} |")
    parts.append(f"| Tissue | {tissue} |")
    if geo_ids:
        parts.append(f"| GEO Accessions | {', '.join(geo_ids)} |")
    parts.append("")
    return "\n".join(parts)


def _build_modular_fs(
    *,
    title: str,
    pdf_name: str,
    raw_text: str,
    organism: str,
    technology: str,
    tissue: str,
    geo_ids: list[str],
) -> dict[str, str]:
    """Build the four modular Markdown files for the Macro Agentic FS.

    Returns a dict mapping filename → content string::

        {
            "01_abstract_conclusion.md": ...,
            "02_methodology.md":        ...,
            "03_results_figs.md":        ...,
            "04_fulltext.md":            ...,
        }

    Key design choices
    ------------------
    * ``02_methodology.md`` is **never truncated** — it preserves complete
      methods/parameters so that the planner-agent can formulate precise
      experiment plans.
    * ``01_abstract_conclusion.md`` caps the abstract at 500 words but
      otherwise keeps introduction/conclusion intact (≤ 2000 words each).
    * ``03_results_figs.md`` caps each sub-section at 2000 words.
    * ``04_fulltext.md`` stores the cleaned full text (up to 100 000 chars)
      as a reference / fallback.
    """
    header = _build_header_block(
        title=title, pdf_name=pdf_name, raw_text=raw_text,
        organism=organism, technology=technology, tissue=tissue,
        geo_ids=geo_ids,
    )

    sections = _extract_sections(raw_text)

    # ── Bucketise sections ────────────────────────────────────────
    buckets: dict[str, list[tuple[str, str]]] = {
        "abstract_conclusion": [],
        "methodology": [],
        "results_figs": [],
        "other": [],
    }
    for heading, content in sections:
        bucket = _classify_section(heading)
        buckets[bucket].append((heading, content))

    # ── 01_abstract_conclusion.md ─────────────────────────────────
    parts_01: list[str] = [header]
    abstract = _extract_abstract(raw_text) or ""
    if abstract:
        words = abstract.split()
        if len(words) > 500:
            abstract = " ".join(words[:500]) + " [...]"
        parts_01.append("## Abstract\n")
        parts_01.append(abstract)
        parts_01.append("")
    for heading, content in buckets["abstract_conclusion"]:
        words = content.split()
        if len(words) > 2000:
            content = " ".join(words[:2000]) + " [...]"
        parts_01.append(f"## {heading}\n")
        parts_01.append(content.strip())
        parts_01.append("")

    # ── 02_methodology.md (NO truncation) ─────────────────────────
    parts_02: list[str] = [
        f"# Detailed Methodology — {title}\n",
        header,
        "> This file contains the **complete, untruncated** methods from "
        "the paper. The planner-agent should read this in its entirety "
        "before formulating any experiment plan.\n",
    ]
    if buckets["methodology"]:
        for heading, content in buckets["methodology"]:
            parts_02.append(f"## {heading}\n")
            parts_02.append(content.strip())
            parts_02.append("")
    else:
        # Fallback: if no method-like sections were detected, include a
        # notice so the planner knows to consult the full text instead.
        parts_02.append(
            "*No dedicated Methods section was detected in the paper. "
            "The planner-agent should consult `04_fulltext.md` for "
            "methodological details.*\n"
        )

    # ── 03_results_figs.md ────────────────────────────────────────
    parts_03: list[str] = [f"# Results & Discussion — {title}\n", header]
    for heading, content in buckets["results_figs"]:
        words = content.split()
        if len(words) > 2000:
            content = " ".join(words[:2000]) + " [...]"
        parts_03.append(f"## {heading}\n")
        parts_03.append(content.strip())
        parts_03.append("")
    # Also include "other" sections that didn't match any keyword
    for heading, content in buckets["other"]:
        words = content.split()
        if len(words) > 1000:
            content = " ".join(words[:1000]) + " [...]"
        parts_03.append(f"## {heading}\n")
        parts_03.append(content.strip())
        parts_03.append("")

    # ── 04_fulltext.md ────────────────────────────────────────────
    full_text = _clean_body_text(raw_text)
    if len(full_text) > 100_000:
        full_text = full_text[:100_000] + "\n\n[... text truncated at 100 000 chars ...]"
    parts_04 = [f"# Full Text — {title}\n", header, full_text]

    return {
        "01_abstract_conclusion.md": "\n".join(parts_01),
        "02_methodology.md": "\n".join(parts_02),
        "03_results_figs.md": "\n".join(parts_03),
        "04_fulltext.md": "\n".join(parts_04),
    }


def _extract_authors(raw_text: str, title: str) -> str:
    """Try to extract the author line from near the title.

    Looks for lines with multiple comma- or &-separated names
    (containing uppercase initials typical of author lists).
    """
    lines = [l.strip() for l in raw_text.split("\n") if l.strip()]

    # Find the title line first, then look at the next few lines
    title_lower = title.lower().strip()
    start_idx = 0
    for i, line in enumerate(lines):
        if title_lower in line.lower():
            start_idx = i + 1
            break

    # Scan at most 5 lines after the title for author-like content
    for line in lines[start_idx:start_idx + 5]:
        # Skip short lines, URLs, page markers
        if len(line) < 20:
            continue
        if line.startswith("http") or line.startswith("#"):
            continue
        # Author lines typically have commas and uppercase words
        comma_count = line.count(",")
        has_ampersand = "&" in line
        # Crude heuristic: >2 commas or has & and commas
        if comma_count >= 2 or (has_ampersand and comma_count >= 1):
            # Remove affiliations (superscript numbers)
            author_line = re.sub(r"\d+,\d+|\d{1,2}(?=[A-Z])", "", line)
            # Truncate if very long
            if len(author_line) > 300:
                author_line = author_line[:300] + " et al."
            return author_line.strip()

    return ""


def _pdf_to_markdown(pdf_path: str, raw_text: str) -> str:
    """Convert extracted PDF text to structured Markdown.

    Produces a clean, well-organized summary with:
    - Proper title extraction (skips page markers and noise)
    - Robust abstract detection (multiple strategies)
    - Extracted metadata (organism, technology, tissue, GEO)
    - Cleaned body text (figure/table noise filtered)
    """
    # ── Title ──────────────────────────────────────────────────────
    title = _extract_title(raw_text, pdf_path)

    # ── Abstract ───────────────────────────────────────────────────
    abstract = _extract_abstract(raw_text)

    # ── Metadata ───────────────────────────────────────────────────
    geo_ids = _extract_geo_accessions(raw_text)
    organism = _extract_organism(raw_text)
    technology = _extract_technology(raw_text)
    tissue = _extract_tissue(raw_text)

    # ── DOI ────────────────────────────────────────────────────────
    doi_match = re.search(r"(https?://doi\.org/\S+)", raw_text)
    doi = doi_match.group(1).rstrip(".)") if doi_match else ""

    # ── Authors (first occurrence of institutional affiliations) ──
    # Look for a block of names followed by affiliation superscripts
    authors = ""
    author_match = re.search(
        r"([A-Z][a-z]+ [A-Z][a-z\-]+(?:\d|,).*?(?:University|Institute|Department|School))",
        raw_text[:3000],
        re.DOTALL,
    )
    if author_match:
        author_block = author_match.group(1)
        # Take just first ~300 chars to capture author names
        author_lines = author_block[:300].split("\n")
        authors = " ".join(l.strip() for l in author_lines if l.strip())

    # ── Build structured markdown ──────────────────────────────────
    md_parts = [
        f"# {title}\n",
        f"**Source**: {Path(pdf_path).name}",
    ]
    if doi:
        md_parts.append(f"**DOI**: {doi}")
    if authors:
        md_parts.append(f"**Authors**: {authors[:300]}{'...' if len(authors) > 300 else ''}")
    md_parts.append("")

    if abstract:
        md_parts.append(f"## Abstract\n\n{abstract}\n")

    md_parts.append("## Extracted Metadata\n")
    md_parts.append(f"- **Organism**: {organism}")
    md_parts.append(f"- **Technology**: {technology}")
    md_parts.append(f"- **Tissue**: {tissue}")
    if geo_ids:
        md_parts.append(f"- **GEO Accessions**: {', '.join(geo_ids)}")
    md_parts.append("")

    # ── Key sections (cleaned) ─────────────────────────────────────
    sections = _extract_sections(raw_text)
    if sections:
        md_parts.append("## Key Sections\n")
        for heading, content in sections:
            # Clean noise from section content
            content_clean = _clean_body_text(content)
            # Collapse multiple blank lines
            content_clean = re.sub(r"\n{3,}", "\n\n", content_clean).strip()
            if len(content_clean) > 50:
                md_parts.append(f"### {heading}\n")
                md_parts.append(content_clean)
                md_parts.append("")

    # ── Full text (cleaned, truncated) ─────────────────────────────
    full_text = _clean_body_text(raw_text)
    if len(full_text) > 50000:
        full_text = full_text[:50000] + "\n\n[... text truncated at 50,000 chars ...]"

    md_parts.append("## Full Text\n")
    md_parts.append(full_text)

    return "\n".join(md_parts)


# =========================================================================
# h5ad metadata extraction
# =========================================================================


def _extract_h5ad_metadata(h5ad_path: str) -> dict[str, Any]:
    """Extract metadata from an h5ad file without loading full data."""
    try:
        import anndata
        adata = anndata.read_h5ad(h5ad_path, backed="r")
        meta = {
            "n_obs": adata.n_obs,
            "n_vars": adata.n_vars,
            "obs_columns": list(adata.obs.columns)[:20],
            "var_columns": list(adata.var.columns)[:20],
            "obsm_keys": list(adata.obsm.keys()) if adata.obsm else [],
            "uns_keys": list(adata.uns.keys())[:20] if adata.uns else [],
            "has_spatial": "spatial" in (adata.obsm.keys() if adata.obsm else []),
            "file_path": str(h5ad_path),
        }
        adata.file.close()
        return meta
    except Exception as e:
        logger.warning("Failed to read h5ad metadata: %s", e)
        return {"error": str(e), "file_path": str(h5ad_path)}


# =========================================================================
# Main intake function
# =========================================================================


def prepare_intake(
    idea: str,
    pdf_path: str | None = None,
    h5ad_path: str | None = None,
    output_dir: str | None = None,
) -> IntakeResult:
    """Prepare intake: convert PDF to Markdown and assemble context.

    Supports three input modes:
    - Mode A: ``pdf_path`` + ``idea`` (data from paper / GEO)
    - Mode B: ``pdf_path`` + ``idea`` + ``h5ad_path`` (user-provided data)
    - Mode C: ``idea`` only (no PDF — pure research from scratch)

    Parameters
    ----------
    idea : str
        User's research idea / hypothesis (always required).
    pdf_path : str, optional
        Path to the scientific paper PDF (Mode A/B).
    h5ad_path : str, optional
        Path to user-provided h5ad data file (Mode B).
    output_dir : str, optional
        Directory to save generated Markdown files.
        Defaults to current directory for Mode C, or
        alongside the PDF for Mode A/B.

    Returns
    -------
    IntakeResult
        Structured intake output ready for pipeline consumption.
    """
    # ── Mode C: idea only ─────────────────────────────────────────
    if not pdf_path:
        return _prepare_intake_idea_only(idea, output_dir)

    # ── Mode A / B: PDF-based ─────────────────────────────────────
    pdf_path = str(Path(pdf_path).resolve())
    if not Path(pdf_path).exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    # Determine output directory early (needed by opendataloader)
    if output_dir:
        out_dir = Path(output_dir)
    else:
        out_dir = Path(pdf_path).parent
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── Strategy 1: opendataloader-pdf (best quality) ─────────────
    odl_md = _convert_pdf_opendataloader(pdf_path, str(out_dir))

    if odl_md:
        raw_text = odl_md
        title = _extract_title(raw_text, pdf_path)
        logger.info("Using opendataloader-pdf output for %s", pdf_path)
    else:
        # ── Strategy 2: pypdf / pdftotext fallback ────────────────
        logger.info("Extracting text from PDF (fallback): %s", pdf_path)
        raw_text = _extract_pdf_text(pdf_path)
        title = _extract_title(raw_text, pdf_path)

    # Extract metadata
    geo_ids = _extract_geo_accessions(raw_text)
    organism = _extract_organism(raw_text)
    technology = _extract_technology(raw_text)
    tissue = _extract_tissue(raw_text)

    # ── Build Macro Agentic FS: workspace/paper/ ──────────────────
    paper_dir = out_dir / "paper"
    paper_dir.mkdir(parents=True, exist_ok=True)

    modular_files = _build_modular_fs(
        title=title,
        pdf_name=Path(pdf_path).name,
        raw_text=raw_text,
        organism=organism,
        technology=technology,
        tissue=tissue,
        geo_ids=geo_ids,
    )
    for fname, content in modular_files.items():
        fpath = paper_dir / fname
        fpath.write_text(content, encoding="utf-8")
        logger.info("Paper module saved to: %s (%d chars)", fpath, len(content))

    # The "summary" path now points to the abstract/conclusion module
    md_path = paper_dir / "01_abstract_conclusion.md"
    paper_md = modular_files["01_abstract_conclusion.md"]

    # 6. Handle h5ad (Mode B)
    h5ad_meta = None
    input_mode = "A"
    if h5ad_path:
        h5ad_path = str(Path(h5ad_path).resolve())
        if not Path(h5ad_path).exists():
            raise FileNotFoundError(f"h5ad file not found: {h5ad_path}")
        h5ad_meta = _extract_h5ad_metadata(h5ad_path)
        input_mode = "B"
        logger.info("Input mode B: user-provided h5ad data")
    else:
        logger.info("Input mode A: data from paper/GEO")

    # 7. Build research request document
    request_md = _build_research_request(
        title=title,
        idea=idea,
        paper_md_path=str(md_path),
        geo_ids=geo_ids,
        organism=organism,
        technology=technology,
        tissue=tissue,
        h5ad_meta=h5ad_meta,
        input_mode=input_mode,
    )
    request_path = out_dir / "research_request.md"
    request_path.write_text(request_md, encoding="utf-8")

    return IntakeResult(
        paper_markdown=paper_md,
        paper_title=title,
        idea=idea,
        geo_accessions=geo_ids,
        organism=organism,
        tissue=tissue,
        technology=technology,
        h5ad_metadata=h5ad_meta,
        input_mode=input_mode,
        paper_md_path=str(md_path),
        h5ad_path=h5ad_path or "",
    )


def _prepare_intake_idea_only(
    idea: str,
    output_dir: str | None = None,
) -> IntakeResult:
    """Mode C: prepare intake with only a research idea.

    The research-agent will handle literature discovery and data sourcing
    autonomously via web search.
    """
    out_dir = Path(output_dir) if output_dir else Path.cwd()
    out_dir.mkdir(parents=True, exist_ok=True)

    # Build a minimal research request
    request_md = (
        "# Research Request\n\n"
        "## Input Mode: C (idea only — no reference paper)\n\n"
        f"## User Idea\n\n{idea}\n\n"
        "## Instructions\n\n"
        "No reference paper was provided. The research-agent should:\n"
        "1. Search for relevant literature and prior work on this topic.\n"
        "2. Identify suitable datasets (GEO, public repositories).\n"
        "3. Recommend appropriate analysis methods and OmicsClaw skills.\n"
        "4. The planner-agent should then create the experimental plan.\n"
    )
    request_path = out_dir / "research_request.md"
    request_path.write_text(request_md, encoding="utf-8")
    logger.info("Mode C: idea-only intake saved to %s", request_path)

    return IntakeResult(
        paper_markdown="",
        paper_title="",
        idea=idea,
        input_mode="C",
        paper_md_path="",
    )


def _build_research_request(
    title: str,
    idea: str,
    paper_md_path: str,
    geo_ids: list[str],
    organism: str,
    technology: str,
    tissue: str,
    h5ad_meta: dict | None,
    input_mode: str,
) -> str:
    """Build the research_request.md that feeds into the pipeline."""
    _MODE_LABELS = {"A": "A (data from paper/GEO)", "B": "B (user-provided h5ad)", "C": "C (idea only)"}
    mode_label = _MODE_LABELS.get(input_mode, input_mode)
    parts = [
        "# Research Request\n",
        f"## Paper: {title}\n",
        f"Full paper summary: [{Path(paper_md_path).name}]({paper_md_path})\n",
        f"## User Idea\n\n{idea}\n",
        f"## Input Mode: {mode_label}\n",
        "## Extracted Metadata\n",
        f"- **Organism**: {organism}",
        f"- **Technology**: {technology}",
        f"- **Tissue**: {tissue}",
    ]
    if geo_ids:
        parts.append(f"- **GEO Accessions**: {', '.join(geo_ids)}")
    parts.append("")

    if h5ad_meta:
        parts.append("## User-Provided Dataset\n")
        parts.append(f"- **File**: {h5ad_meta.get('file_path', 'N/A')}")
        parts.append(f"- **Cells**: {h5ad_meta.get('n_obs', 'N/A')}")
        parts.append(f"- **Genes**: {h5ad_meta.get('n_vars', 'N/A')}")
        if h5ad_meta.get("has_spatial"):
            parts.append("- **Spatial data**: Yes")
        obs_cols = h5ad_meta.get("obs_columns", [])
        if obs_cols:
            parts.append(f"- **Annotations**: {', '.join(obs_cols[:10])}")
        parts.append("")

    return "\n".join(parts)
