"""
Preflight Know-How (KH) Injection System.

Loads KH-*.md documents from knowledge_base/knowhows/ and forcibly injects
them as hard scientific constraints into the LLM system prompt BEFORE
analysis begins.  These are not optional tips — they are mandatory guardrails
derived from high-frequency AI errors observed in real-world analyses.

Architecture (from optimization plan Stage 1):
    User Request → PreflightKnowHowInjector
        → identifies relevant domain / task keywords
        → loads matching KH rules
        → returns formatted constraint block for system prompt

Usage:
    injector = KnowHowInjector()
    constraints = injector.get_constraints(skill="bulk-rnaseq-counts-to-de-deseq2")
    # → returns string block to append to system prompt
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# KH metadata: maps each KH doc to the skills / keywords it constrains.
# This is the single canonical mapping — no double-maintenance.
# ---------------------------------------------------------------------------

_KH_SKILL_MAP: dict[str, dict] = {
    "KH-bulk-rnaseq-differential-expression.md": {
        "label": "Bulk RNA-Seq Differential Expression",
        "critical_rule": "MUST use padj (not pvalue) for DEG filtering; MUST NOT confuse log2FC sign direction",
        "skills": [
            "bulk-rnaseq-counts-to-de-deseq2",
            "bulkrna-de", "bulkrna-deseq2", "de",
        ],
        "keywords": [
            "differential expression", "DEG", "padj", "pvalue",
            "fold change", "DESeq2", "edgeR", "limma",
            # Chinese aliases
            "差异表达", "差异基因", "差异分析",
        ],
        "domains": ["bulkrna", "singlecell"],
    },
    "KH-data-analysis-best-practices.md": {
        "label": "Best Practices for Data Analyses",
        "critical_rule": "MUST validate data before analysis; MUST handle duplicates and missing values explicitly",
        "skills": ["__all__"],     # applies to every analysis
        "keywords": [
            "data validation", "duplicates", "missing values",
            "data quality", "metadata",
            # Chinese aliases
            "数据验证", "数据质量", "缺失值", "重复值",
        ],
        "domains": ["__all__"],
    },
    "KH-gene-essentiality.md": {
        "label": "Gene Essentiality (DepMap/CRISPR)",
        "critical_rule": "MUST invert DepMap scores before correlation (negative raw = essential)",
        "skills": [
            "pooled-crispr-screens", "lasso-biomarker-panel",
        ],
        "keywords": [
            "essentiality", "DepMap", "CRISPR", "gene effect",
            "correlation", "essential",
            # Chinese aliases
            "基因关键性", "必需基因", "基因敲除",
        ],
        "domains": ["genomics", "general"],
    },
    "KH-pathway-enrichment.md": {
        "label": "Pathway Enrichment (ORA/GSEA)",
        "critical_rule": "MUST separate up/down genes for ORA; MUST NOT use keyword filtering to select pathways",
        "skills": [
            "functional-enrichment-from-degs",
        ],
        "keywords": [
            "enrichment", "pathway", "ORA", "GSEA", "KEGG",
            "Reactome", "clusterProfiler", "enrichr",
            # Chinese aliases
            "富集分析", "通路富集", "通路分析", "功能富集",
        ],
        "domains": ["bulkrna", "singlecell", "general"],
    },
}


def _find_knowhows_dir() -> Path:
    """Locate the knowledge_base/knowhows/ directory."""
    # 1. Environment variable
    env_path = os.getenv("OMICSCLAW_KNOWLEDGE_PATH")
    if env_path:
        p = Path(env_path) / "knowhows"
        if p.is_dir():
            return p

    # 2. Relative to this file (omicsclaw/knowledge/knowhow.py → project root)
    project_root = Path(__file__).resolve().parent.parent.parent
    kh = project_root / "knowledge_base" / "knowhows"
    if kh.is_dir():
        return kh

    # 3. CWD fallback
    cwd_kh = Path.cwd() / "knowledge_base" / "knowhows"
    if cwd_kh.is_dir():
        return cwd_kh

    return kh  # Return default even if missing


class KnowHowInjector:
    """Mandatory pre-analysis scientific constraint injector.

    Reads KH-*.md documents and matches them against the current
    analysis context (skill name, user query keywords, domain).
    Returns formatted constraint text for system prompt injection.
    """

    def __init__(self, knowhows_dir: Optional[Path] = None):
        self._dir = knowhows_dir or _find_knowhows_dir()
        self._cache: dict[str, str] = {}  # filename → content
        self._loaded = False

    def _ensure_loaded(self) -> None:
        """Lazily load all KH documents into memory cache."""
        if self._loaded:
            return
        self._loaded = True
        if not self._dir.is_dir():
            logger.warning("Know-Hows directory not found: %s", self._dir)
            return
        for p in sorted(self._dir.glob("KH-*.md")):
            try:
                content = p.read_text(encoding="utf-8", errors="replace")
                self._cache[p.name] = content
                logger.debug("Loaded know-how: %s (%d chars)", p.name, len(content))
            except Exception as e:
                logger.warning("Failed to load know-how %s: %s", p.name, e)
        logger.info("Loaded %d know-how documents from %s", len(self._cache), self._dir)

    # ----- public API -----

    def get_constraints(
        self,
        skill: Optional[str] = None,
        query: Optional[str] = None,
        domain: Optional[str] = None,
    ) -> str:
        """Return formatted constraint text for the given analysis context.

        Matches KH documents based on:
        1. Exact skill name match (highest priority)
        2. Domain match
        3. Keyword match against user query

        The universal ``KH-data-analysis-best-practices.md`` is ALWAYS
        included for any analysis.

        Returns an empty string if no relevant KH documents are found.
        """
        self._ensure_loaded()
        if not self._cache:
            return ""

        matched: list[tuple[str, str]] = []  # (filename, content)
        query_lower = (query or "").lower()
        skill_lower = (skill or "").lower()
        domain_lower = (domain or "").lower()

        for filename, meta in _KH_SKILL_MAP.items():
            if filename not in self._cache:
                continue
            content = self._cache[filename]

            # Check if this KH applies universally
            if "__all__" in meta.get("skills", []):
                matched.append((filename, content))
                continue

            # Check skill match
            if skill_lower and skill_lower in [s.lower() for s in meta.get("skills", [])]:
                matched.append((filename, content))
                continue

            # Check domain match
            domains = meta.get("domains", [])
            if domain_lower and ("__all__" in domains or domain_lower in domains):
                # Also require at least one keyword match for non-universal domains
                if query_lower:
                    kw_match = any(kw.lower() in query_lower for kw in meta.get("keywords", []))
                    if kw_match:
                        matched.append((filename, content))
                        continue

            # Check keyword match in user query
            if query_lower:
                keywords = meta.get("keywords", [])
                if any(kw.lower() in query_lower for kw in keywords):
                    matched.append((filename, content))

        if not matched:
            return ""

        # Build routing index (concise 'which guide for which task' table)
        seen = set()
        routing_lines = []
        for filename, _content in matched:
            if filename in seen:
                continue
            seen.add(filename)
            meta = _KH_SKILL_MAP.get(filename, {})
            label = meta.get("label", filename)
            rule = meta.get("critical_rule", "")
            if rule:
                routing_lines.append(f"  → {label}: {rule}")
            else:
                routing_lines.append(f"  → {label}")

        # Format as a mandatory constraint block with routing index + full content
        parts = [
            "## ⚠️ MANDATORY SCIENTIFIC CONSTRAINTS",
            "",
            "Before starting this analysis, you MUST read and follow ALL of the ",
            "following know-how guides. These are NON-NEGOTIABLE. Violations will ",
            "produce scientifically invalid results.",
            "",
            "**Active guards for this task:**",
        ]
        parts.extend(routing_lines)
        parts.append("")
        parts.append("---")
        parts.append("")

        # Append full KH content for each matched guide
        seen2 = set()
        for filename, content in matched:
            if filename in seen2:
                continue
            seen2.add(filename)
            meta = _KH_SKILL_MAP.get(filename, {})
            label = meta.get("label", filename)
            cleaned = _strip_kh_header(content)
            parts.append(f"### 📋 {label}")
            parts.append(cleaned)
            parts.append("")

        return "\n".join(parts)

    def get_all_kh_ids(self) -> list[str]:
        """Return list of all loaded KH document identifiers."""
        self._ensure_loaded()
        return list(self._cache.keys())

    def get_kh_for_skill(self, skill: str) -> list[str]:
        """Return KH filenames relevant to a specific skill."""
        skill_lower = skill.lower()
        result = []
        for filename, meta in _KH_SKILL_MAP.items():
            skills = [s.lower() for s in meta.get("skills", [])]
            if "__all__" in skills or skill_lower in skills:
                result.append(filename)
        return result


def _strip_kh_header(content: str) -> str:
    """Remove the metadata header lines (YAML frontmatter and old **Key:** lines)
    but keep the markdown body."""
    import re

    # 1. Strip YAML frontmatter if present
    content = re.sub(r'^---\s*\n.*?\n---\s*\n', '', content, flags=re.DOTALL)

    lines = content.split("\n")
    body_start = 0
    in_header = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("# "):
            # Keep the title
            continue
        if stripped.startswith("**Knowhow ID:") or stripped.startswith("**Category:") or stripped.startswith("**Keywords:"):
            in_header = True
            continue
        if in_header and (stripped.startswith("**") or stripped == "---" or stripped == ""):
            continue
        if in_header and not stripped.startswith("**"):
            body_start = i
            break
    
    # Return from body_start onwards, but keep the title line if it was skipped
    title_line = ""
    for line in lines:
        if line.strip().startswith("# "):
            title_line = line
            break
            
    body = "\n".join(lines[body_start:]).strip()
    if title_line and not body.startswith("# "):
        body = f"{title_line}\n\n{body}"
    return body


# Module-level singleton for convenience
_global_injector: Optional[KnowHowInjector] = None


def get_knowhow_injector() -> KnowHowInjector:
    """Get or create the global KnowHowInjector singleton."""
    global _global_injector
    if _global_injector is None:
        _global_injector = KnowHowInjector()
    return _global_injector
