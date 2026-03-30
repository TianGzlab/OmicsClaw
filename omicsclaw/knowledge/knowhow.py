"""
Preflight Know-How (KH) Injection System.

Loads KH-*.md documents from knowledge_base/knowhows/ and forcibly injects
them as hard scientific constraints into the LLM system prompt BEFORE
analysis begins. These are not optional tips — they are mandatory guardrails
derived from high-frequency AI errors observed in real-world analyses.

Architecture:
    User Request → PreflightKnowHowInjector
        → identifies relevant domain / task keywords
        → loads matching KH rules
        → returns formatted constraint block for system prompt
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
# This is the single canonical mapping in the current hard-coded design.
# ---------------------------------------------------------------------------

_KH_SKILL_MAP: dict[str, dict] = {
    "KH-spatial-domain-guardrails.md": {
        "label": "Spatial Domain Analysis Guardrails",
        "critical_rule": "MUST inspect the dataset and explain method plus key clustering parameters before running spatial domain identification",
        "skills": [
            "spatial-domains", "spatial-domain-identification", "domains",
        ],
        "keywords": [
            "spatial domain", "domain identification", "tissue region", "niche",
            "leiden", "louvain", "cellcharter", "banksy", "spagcn", "stagate", "graphst",
            "聚类", "空间域", "组织区域", "调参",
        ],
        "domains": ["spatial"],
    },
    "KH-spatial-genes-guardrails.md": {
        "label": "Spatial SVG Analysis Guardrails",
        "critical_rule": "MUST inspect matrix type and coordinates, then explain the selected SVG method plus method-specific parameters before running",
        "skills": [
            "spatial-genes", "spatial-svg-detection", "genes",
        ],
        "keywords": [
            "spatially variable gene", "spatial gene", "svg", "moran", "spatialde",
            "spark-x", "flashs", "spatial autocorrelation", "spatial pattern",
            "空间变异基因", "空间基因", "莫兰", "空间模式", "调参",
        ],
        "domains": ["spatial"],
    },
    "KH-bulk-rnaseq-differential-expression.md": {
        "label": "Bulk RNA-Seq Differential Expression",
        "critical_rule": "MUST use padj (not pvalue) for DEG filtering; MUST NOT confuse log2FC sign direction",
        "skills": [
            "bulk-rnaseq-counts-to-de-deseq2",
            "bulkrna-de", "bulkrna-deseq2", "de",
        ],
        "keywords": [
            "differential expression", "deg", "padj", "pvalue",
            "fold change", "deseq2", "edger", "limma",
            "差异表达", "差异基因", "差异分析",
        ],
        "domains": ["bulkrna", "singlecell"],
    },
    "KH-data-analysis-best-practices.md": {
        "label": "Best Practices for Data Analyses",
        "critical_rule": "MUST validate data before analysis; MUST handle duplicates and missing values explicitly",
        "skills": ["__all__"],
        "keywords": [
            "data validation", "duplicates", "missing values",
            "data quality", "metadata",
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
            "essentiality", "depmap", "crispr", "gene effect",
            "correlation", "essential",
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
            "enrichment", "pathway", "ora", "gsea", "kegg",
            "reactome", "clusterprofiler", "enrichr",
            "富集分析", "通路富集", "通路分析", "功能富集",
        ],
        "domains": ["bulkrna", "singlecell", "general"],
    },
}


def _find_knowhows_dir() -> Path:
    """Locate the knowledge_base/knowhows/ directory."""
    env_path = os.getenv("OMICSCLAW_KNOWLEDGE_PATH")
    if env_path:
        p = Path(env_path) / "knowhows"
        if p.is_dir():
            return p

    project_root = Path(__file__).resolve().parent.parent.parent
    kh = project_root / "knowledge_base" / "knowhows"
    if kh.is_dir():
        return kh

    cwd_kh = Path.cwd() / "knowledge_base" / "knowhows"
    if cwd_kh.is_dir():
        return cwd_kh

    return kh


class KnowHowInjector:
    """Mandatory pre-analysis scientific constraint injector."""

    def __init__(self, knowhows_dir: Optional[Path] = None):
        self._dir = knowhows_dir or _find_knowhows_dir()
        self._cache: dict[str, str] = {}
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

    def get_constraints(
        self,
        skill: Optional[str] = None,
        query: Optional[str] = None,
        domain: Optional[str] = None,
    ) -> str:
        """Return formatted constraint text for the given analysis context."""
        self._ensure_loaded()
        if not self._cache:
            return ""

        matched: list[tuple[str, str]] = []
        query_lower = (query or "").lower()
        skill_lower = (skill or "").lower()
        domain_lower = (domain or "").lower()

        for filename, meta in _KH_SKILL_MAP.items():
            if filename not in self._cache:
                continue
            content = self._cache[filename]

            if "__all__" in meta.get("skills", []):
                matched.append((filename, content))
                continue

            if skill_lower and skill_lower in [s.lower() for s in meta.get("skills", [])]:
                matched.append((filename, content))
                continue

            domains = meta.get("domains", [])
            if domain_lower and ("__all__" in domains or domain_lower in domains):
                if query_lower:
                    kw_match = any(kw.lower() in query_lower for kw in meta.get("keywords", []))
                    if kw_match:
                        matched.append((filename, content))
                        continue

            if query_lower:
                keywords = meta.get("keywords", [])
                if any(kw.lower() in query_lower for kw in keywords):
                    matched.append((filename, content))

        if not matched:
            return ""

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
    """Remove the metadata header lines but keep the markdown body."""
    content = re.sub(r'^---\s*\n.*?\n---\s*\n', '', content, flags=re.DOTALL)

    lines = content.split("\n")
    body_start = 0
    in_header = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("# "):
            continue
        if stripped.startswith("**Knowhow ID:") or stripped.startswith("**Category:") or stripped.startswith("**Keywords:"):
            in_header = True
            continue
        if in_header and (stripped.startswith("**") or stripped == "---" or stripped == ""):
            continue
        if in_header and not stripped.startswith("**"):
            body_start = i
            break

    title_line = ""
    for line in lines:
        if line.strip().startswith("# "):
            title_line = line
            break

    body = "\n".join(lines[body_start:]).strip()
    if title_line and not body.startswith("# "):
        body = f"{title_line}\n\n{body}"
    return body


_global_injector: Optional[KnowHowInjector] = None


def get_knowhow_injector() -> KnowHowInjector:
    """Get or create the global KnowHowInjector singleton."""
    global _global_injector
    if _global_injector is None:
        _global_injector = KnowHowInjector()
    return _global_injector
