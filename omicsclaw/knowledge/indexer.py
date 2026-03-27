"""
Document parser and section chunker for the OmicsClaw knowledge base.

Handles two asset types:
  1. Markdown documents (.md) with optional YAML frontmatter
  2. Reference scripts (.py, .R) — extracts docstrings and function signatures

Each document is split into section-level chunks so that search results
return focused, relevant snippets rather than entire 500-line files.
"""

from __future__ import annotations

import hashlib
import os
import re
import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

import yaml

# ---------------------------------------------------------------------------
# Domain and category inference
# ---------------------------------------------------------------------------

# Map directory-name fragments / frontmatter fields → canonical domain
_DOMAIN_HINTS: dict[str, str] = {
    "spatial": "spatial",
    "scrna": "singlecell",
    "scrnaseq": "singlecell",
    "single-cell": "singlecell",
    "singlecell": "singlecell",
    "genomic": "genomics",
    "variant": "genomics",
    "gwas": "genomics",
    "prs": "genomics",
    "vcf": "genomics",
    "chip-atlas": "genomics",
    "genetic": "genomics",
    "proteomic": "proteomics",
    "peptide": "proteomics",
    "metabolomic": "metabolomics",
    "xcms": "metabolomics",
    "bulk-rna": "bulkrna",
    "bulkrna": "bulkrna",
    "rnaseq": "bulkrna",
    "deseq": "bulkrna",
    "coexpression": "bulkrna",
    "wgcna": "bulkrna",
    "survival": "bulkrna",
    "crispr": "genomics",
    "grn": "singlecell",
    "pyscenic": "singlecell",
    "trajectory": "singlecell",
    "mendelian": "genomics",
    "enrichment": "general",
    "experimental-design": "general",
    "statistics": "general",
    "clinical": "general",
    "literature": "general",
    "pcr": "general",
    "primer": "general",
    "lasso": "general",
    "biomarker": "general",
    "multi-omics": "general",
    "cell-cell-communication": "singlecell",
    "longitudinal": "general",
    "disease-progression": "general",
    "upstream-regulator": "general",
}

# Map knowledge_base/ subdirectory prefixes → canonical doc_type
_CATEGORY_MAP: dict[str, str] = {
    "01_workflow_guides": "workflow",
    "02_decision_guides": "decision-guide",
    "03_best_practices": "best-practices",
    "04_troubleshooting": "troubleshooting",
    "05_method_references": "method-reference",
    "06_interpretation_guides": "interpretation",
    "07_data_preprocessing_qc": "preprocessing-qc",
    "08_statistical_methods": "statistics",
    "09_tool_setup": "tool-setup",
    "10_domain_knowledge": "domain-knowledge",
    "scripts": "reference-script",
}


def _infer_domain(path: Path, frontmatter: dict) -> str:
    """Infer the omics domain from frontmatter, path, or content hints."""
    # 1. Explicit frontmatter
    fm_cat = (frontmatter.get("category") or "").lower()
    for hint, domain in _DOMAIN_HINTS.items():
        if hint in fm_cat:
            return domain

    # 2. File stem / parent directory
    combined = f"{path.parent.name}/{path.stem}".lower()
    for hint, domain in _DOMAIN_HINTS.items():
        if hint in combined:
            return domain

    return "general"


def _infer_doc_type(path: Path) -> str:
    """Infer doc_type from the knowledge_base subdirectory."""
    parts = path.parts
    for part in parts:
        if part in _CATEGORY_MAP:
            return _CATEGORY_MAP[part]
    # Fallback for scripts by extension
    if path.suffix in (".py", ".R", ".r"):
        return "reference-script"
    return "reference"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Chunk:
    """A searchable section from a knowledge document."""
    source_path: str          # relative to knowledge_base root
    title: str                # document title
    domain: str               # canonical domain
    doc_type: str             # category tag
    section_title: str        # heading of this section (or "overview")
    content: str              # section text
    search_terms: str = ""    # additional search keywords
    content_hash: str = ""    # SHA-256 of content for dedup


@dataclass
class ParseResult:
    """Result of parsing a single file."""
    source_path: str
    title: str
    domain: str
    doc_type: str
    chunks: list[Chunk] = field(default_factory=list)


def _make_chunk(
    source_path: str,
    title: str,
    domain: str,
    doc_type: str,
    section_title: str,
    content: str,
    search_terms: str = "",
) -> Chunk:
    """Create a Chunk with auto-computed content hash."""
    return Chunk(
        source_path=source_path,
        title=title,
        domain=domain,
        doc_type=doc_type,
        section_title=section_title,
        content=content,
        search_terms=search_terms,
        content_hash=hashlib.sha256(content.encode()).hexdigest()[:16],
    )


# ---------------------------------------------------------------------------
# Markdown parser
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Extract YAML frontmatter if present; return (metadata, remaining_body)."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        meta = {}
    return meta, text[m.end():]


def _split_sections(body: str, max_chunk: int = 3000) -> list[tuple[str, str]]:
    """Split markdown body into (heading, content) pairs.

    Sections longer than *max_chunk* characters are further split at
    paragraph boundaries to keep chunks manageable for search result display.
    """
    sections: list[tuple[str, str]] = []
    headings = list(_HEADING_RE.finditer(body))

    if not headings:
        return [("overview", body.strip())]

    # Content before first heading
    preamble = body[:headings[0].start()].strip()
    if preamble:
        sections.append(("overview", preamble))

    for i, m in enumerate(headings):
        heading_text = m.group(2).strip()
        start = m.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(body)
        content = body[start:end].strip()

        if len(content) <= max_chunk:
            sections.append((heading_text, content))
        else:
            # Split at double-newline (paragraph boundary)
            paragraphs = re.split(r"\n{2,}", content)
            buf, buf_heading = "", heading_text
            part_idx = 0
            for para in paragraphs:
                if len(buf) + len(para) > max_chunk and buf:
                    sections.append((buf_heading, buf.strip()))
                    part_idx += 1
                    buf_heading = f"{heading_text} (part {part_idx + 1})"
                    buf = para + "\n\n"
                else:
                    buf += para + "\n\n"
            if buf.strip():
                sections.append((buf_heading, buf.strip()))

    return sections


def _extract_search_terms(frontmatter: dict, title: str) -> str:
    """Build auxiliary search terms from frontmatter keywords and title."""
    terms: list[str] = []
    for key in ("id", "name", "short-description", "category"):
        val = frontmatter.get(key, "")
        if val:
            terms.append(str(val))
    # Add title words
    terms.append(title)
    return " ".join(terms)


def parse_markdown(path: Path, kb_root: Path) -> ParseResult:
    """Parse a single markdown file into section chunks."""
    text = path.read_text(encoding="utf-8", errors="replace")
    fm, body = _parse_frontmatter(text)

    rel_path = str(path.relative_to(kb_root))
    title = fm.get("name") or fm.get("title") or ""
    if not title:
        # Extract from first H1
        h1 = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
        title = h1.group(1).strip() if h1 else path.stem.replace("-", " ").title()

    domain = _infer_domain(path, fm)
    doc_type = _infer_doc_type(path)
    search_terms = _extract_search_terms(fm, title)

    sections = _split_sections(body)
    chunks = []
    for sec_title, sec_content in sections:
        if not sec_content.strip():
            continue
        chunks.append(_make_chunk(
            rel_path, title, domain, doc_type, sec_title, sec_content, search_terms,
        ))

    return ParseResult(
        source_path=rel_path,
        title=title,
        domain=domain,
        doc_type=doc_type,
        chunks=chunks,
    )


# ---------------------------------------------------------------------------
# Script parser (Python + R)
# ---------------------------------------------------------------------------

def _parse_python_script(path: Path, kb_root: Path) -> ParseResult:
    """Parse a Python script — extract module docstring and function signatures."""
    text = path.read_text(encoding="utf-8", errors="replace")
    rel_path = str(path.relative_to(kb_root))
    doc_type = "reference-script"

    # Workflow name from parent directory
    workflow_name = path.parent.name
    domain = _infer_domain(path, {})

    # Try to get module docstring via AST
    module_doc = ""
    func_summaries: list[str] = []
    try:
        tree = ast.parse(text)
        module_doc = ast.get_docstring(tree) or ""
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fdoc = ast.get_docstring(node) or ""
                sig_line = f"def {node.name}(...)"
                summary = f"{sig_line}: {fdoc[:200]}" if fdoc else sig_line
                func_summaries.append(summary)
    except SyntaxError:
        # Fallback: extract top comment block
        lines = text.split("\n")
        comment_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                comment_lines.append(stripped.lstrip("# "))
            elif stripped == "":
                continue
            else:
                break
        module_doc = "\n".join(comment_lines)

    title = f"{workflow_name}/{path.name}"
    search_terms = f"{workflow_name} {path.stem} python script"

    chunks = []
    if module_doc:
        chunks.append(_make_chunk(
            rel_path, title, domain, doc_type, "module docstring", module_doc, search_terms,
        ))

    if func_summaries:
        func_text = "\n".join(func_summaries)
        chunks.append(_make_chunk(
            rel_path, title, domain, doc_type, "function signatures", func_text, search_terms,
        ))

    # If no docstring at all, index the first 50 lines as overview
    if not chunks:
        preview = "\n".join(text.split("\n")[:50])
        chunks.append(_make_chunk(
            rel_path, title, domain, doc_type, "code preview", preview, search_terms,
        ))

    return ParseResult(
        source_path=rel_path, title=title,
        domain=domain, doc_type=doc_type, chunks=chunks,
    )


def _parse_r_script(path: Path, kb_root: Path) -> ParseResult:
    """Parse an R script — extract header comments and function definitions."""
    text = path.read_text(encoding="utf-8", errors="replace")
    rel_path = str(path.relative_to(kb_root))
    doc_type = "reference-script"

    workflow_name = path.parent.name
    domain = _infer_domain(path, {})
    title = f"{workflow_name}/{path.name}"
    search_terms = f"{workflow_name} {path.stem} R script"

    chunks = []

    # Extract leading comment block
    lines = text.split("\n")
    header_comments = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            header_comments.append(stripped.lstrip("# "))
        elif stripped == "":
            if header_comments:
                break
            continue
        else:
            break

    if header_comments:
        header = "\n".join(header_comments)
        chunks.append(_make_chunk(
            rel_path, title, domain, doc_type, "script header", header, search_terms,
        ))

    # Extract function definitions: name <- function(args) { ... }
    func_re = re.compile(
        r"^(\w+)\s*<-\s*function\s*\(([^)]*)\)",
        re.MULTILINE,
    )
    func_summaries = []
    for m in func_re.finditer(text):
        fname = m.group(1)
        fargs = m.group(2).strip()
        # Look for preceding comment as description
        pos = m.start()
        preceding = text[:pos].rstrip()
        desc_lines = []
        for line in reversed(preceding.split("\n")):
            stripped = line.strip()
            if stripped.startswith("#"):
                desc_lines.insert(0, stripped.lstrip("# "))
            else:
                break
        desc = " ".join(desc_lines) if desc_lines else ""
        summary = f"{fname}({fargs}): {desc[:200]}" if desc else f"{fname}({fargs})"
        func_summaries.append(summary)

    if func_summaries:
        func_text = "\n".join(func_summaries)
        chunks.append(_make_chunk(
            rel_path, title, domain, doc_type, "function definitions", func_text, search_terms,
        ))

    # Fallback: code preview
    if not chunks:
        preview = "\n".join(lines[:50])
        chunks.append(_make_chunk(
            rel_path, title, domain, doc_type, "code preview", preview, search_terms,
        ))

    return ParseResult(
        source_path=rel_path, title=title,
        domain=domain, doc_type=doc_type, chunks=chunks,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def iter_documents(kb_root: Path) -> Iterator[ParseResult]:
    """Recursively scan *kb_root* and yield parsed documents/scripts."""
    if not kb_root.is_dir():
        return

    for root, _dirs, files in os.walk(kb_root):
        # Skip hidden directories
        root_path = Path(root)
        if any(part.startswith(".") for part in root_path.parts):
            continue

        for fname in sorted(files):
            fpath = root_path / fname
            suffix = fpath.suffix.lower()

            try:
                if suffix == ".md":
                    yield parse_markdown(fpath, kb_root)
                elif suffix == ".py":
                    yield _parse_python_script(fpath, kb_root)
                elif suffix in (".r", ".R"):
                    yield _parse_r_script(fpath, kb_root)
                # Skip other file types (images, data files, etc.)
            except Exception as exc:
                # Log but don't crash on individual parse failures
                import logging
                logging.getLogger(__name__).warning(
                    "Failed to parse %s: %s", fpath, exc
                )
