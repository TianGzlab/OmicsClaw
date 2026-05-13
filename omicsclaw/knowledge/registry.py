"""Frontmatter parsing and indexing utilities for knowledge documents.

Current role in OmicsClaw:
- validate knowledge metadata in tests/tooling
- normalize SKILL.md-style frontmatter for extension validation

This module is not on the main retrieval hot path.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Required and optional frontmatter fields
_REQUIRED_FIELDS = {"doc_id", "title", "doc_type"}
_OPTIONAL_FIELDS = {
    "critical_rule", "domains", "related_skills", "phases", "signals",
    "search_terms", "audience", "priority",
}
_VALID_DOC_TYPES = {
    "workflow", "decision-guide", "best-practices", "troubleshooting",
    "method-reference", "interpretation", "preprocessing-qc",
    "statistics", "tool-setup", "domain-knowledge", "knowhow",
    "reference-script",
}
_VALID_DOMAINS = {
    "spatial", "singlecell", "genomics", "proteomics",
    "metabolomics", "bulkrna", "general",
}
_VALID_PHASES = {
    "before_run", "post_run", "on_warning", "on_error",
}
_FRONTMATTER_ALIASES: dict[str, str] = {
    "skills": "related_skills",
    "keywords": "search_terms",
    "phase": "phases",
}
_PHASE_ALIASES: dict[str, str] = {
    "after_run": "post_run",
}

# SKILL.md category → domain mapping (for compatibility)
_CATEGORY_TO_DOMAIN: dict[str, str] = {
    "transcriptomics": "bulkrna",
    "single-cell": "singlecell",
    "singlecell": "singlecell",
    "spatial": "spatial",
    "genomics": "genomics",
    "proteomics": "proteomics",
    "metabolomics": "metabolomics",
    "epigenomics": "genomics",
    "multi-omics": "general",
    "statistics": "general",
    "clinical": "general",
    "literature": "general",
    "tools": "general",
}

# SKILL.md field name → registry field name mapping
_SKILLMD_FIELD_MAP: dict[str, str] = {
    "id": "doc_id",
    "name": "title",
    "short-description": "description",
    "detailed-description": "extended_description",
    "starting-prompt": "starting_prompt",
}


def _normalize_phase_name(value: Any) -> str:
    text = str(value or "").strip().lower()
    return _PHASE_ALIASES.get(text, text)


def _normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        items = value
    elif isinstance(value, (tuple, set)):
        items = list(value)
    else:
        items = [value]

    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def _normalize_metadata_aliases(meta: dict) -> dict:
    """Normalize compatibility aliases to canonical registry keys."""
    normalized = dict(meta)

    for alias_key, canonical_key in _FRONTMATTER_ALIASES.items():
        if alias_key in normalized and canonical_key not in normalized:
            normalized[canonical_key] = normalized[alias_key]

    for key in ("domains", "related_skills", "signals", "search_terms", "audience"):
        if key in normalized:
            normalized[key] = _normalize_list(normalized[key])

    if "phases" in normalized:
        normalized["phases"] = [
            _normalize_phase_name(item)
            for item in _normalize_list(normalized["phases"])
        ]

    return normalized


def _normalize_skillmd_frontmatter(meta: dict) -> dict:
    """Map SKILL.md-style frontmatter fields to registry schema.

    SKILL.md uses: id, name, category, short-description
    Registry uses: doc_id, title, doc_type, domains, related_skills
    """
    normalized = dict(meta)
    is_skillmd = "id" in meta and "name" in meta and "category" in meta

    if not is_skillmd:
        return normalized

    # Map field names
    for old_key, new_key in _SKILLMD_FIELD_MAP.items():
        if old_key in normalized and new_key not in normalized:
            normalized[new_key] = normalized[old_key]

    # Infer doc_type from category
    if "doc_type" not in normalized:
        normalized["doc_type"] = "workflow"

    # Infer domains from category
    if "domains" not in normalized:
        category = meta.get("category", "").lower()
        domain = _CATEGORY_TO_DOMAIN.get(category, "general")
        normalized["domains"] = [domain]

    # Self-reference: the skill's own ID is a related skill
    if "related_skills" not in normalized:
        normalized["related_skills"] = [meta["id"]]

    # Extract search terms from description
    if "search_terms" not in normalized:
        desc = meta.get("short-description", "")
        if desc:
            # Simple keyword extraction: words > 4 chars
            words = [w.strip(".,;:!?()\"'") for w in desc.lower().split()]
            terms = [w for w in words if len(w) > 4 and w.isalpha()]
            normalized["search_terms"] = list(set(terms))[:10]

    # Mark as SKILL.md-originated
    normalized["_from_skillmd"] = True

    return normalized


def parse_frontmatter(text: str) -> dict[str, Any]:
    """Extract YAML frontmatter from a markdown document.

    Supports the standard --- delimited format.
    Returns empty dict if no frontmatter is found.
    """
    # Match YAML front matter between --- delimiters
    match = re.match(r'^---\s*\n(.*?)\n---\s*\n', text, re.DOTALL)
    if not match:
        return {}

    raw = match.group(1)
    meta: dict[str, Any] = {}

    for line in raw.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue

        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()

        # Parse YAML-style lists: [item1, item2]
        if value.startswith("[") and value.endswith("]"):
            items = [
                item.strip().strip("'\"")
                for item in value[1:-1].split(",")
                if item.strip()
            ]
            meta[key] = items
        # Parse numbers
        elif re.match(r'^-?\d+\.?\d*$', value):
            meta[key] = float(value) if "." in value else int(value)
        # Parse booleans
        elif value.lower() in ("true", "false"):
            meta[key] = value.lower() == "true"
        else:
            meta[key] = value.strip("'\"")

    return meta


def validate_frontmatter(meta: dict, filepath: str = "") -> list[str]:
    """Validate frontmatter against the canonical schema.

    Returns a list of validation errors (empty if valid).
    """
    meta = _normalize_metadata_aliases(meta)
    errors = []
    prefix = f"[{filepath}] " if filepath else ""

    # Check required fields
    for field in _REQUIRED_FIELDS:
        if field not in meta:
            errors.append(f"{prefix}Missing required field: '{field}'")

    # Validate doc_type
    doc_type = meta.get("doc_type", "")
    if doc_type and doc_type not in _VALID_DOC_TYPES:
        errors.append(f"{prefix}Invalid doc_type: '{doc_type}'. "
                       f"Must be one of: {sorted(_VALID_DOC_TYPES)}")

    # Validate domains
    domains = meta.get("domains", [])
    if isinstance(domains, list):
        for d in domains:
            if d not in _VALID_DOMAINS:
                errors.append(f"{prefix}Invalid domain: '{d}'. "
                               f"Must be one of: {sorted(_VALID_DOMAINS)}")

    # Validate phases
    phases = meta.get("phases", [])
    if isinstance(phases, list):
        for p in phases:
            if p not in _VALID_PHASES:
                errors.append(f"{prefix}Invalid phase: '{p}'. "
                               f"Must be one of: {sorted(_VALID_PHASES)}")

    # Validate priority range
    priority = meta.get("priority")
    if priority is not None:
        if not isinstance(priority, (int, float)) or not (0 <= priority <= 1):
            errors.append(f"{prefix}Invalid priority: {priority}. Must be 0.0–1.0.")

    return errors


class KnowledgeRegistry:
    """Inverted index built from document frontmatter.

    At startup, scans all knowledge documents and builds mappings:
    - skill → doc_ids
    - signal → doc_ids
    - domain → doc_ids
    - phase → doc_ids

    This enables O(1) lookups when the Knowledge Resolver needs to
    find relevant documents for a given skill execution context.
    """

    def __init__(self):
        self._docs: dict[str, dict] = {}  # doc_id → full metadata
        self._skill_index: dict[str, set[str]] = {}    # skill → {doc_ids}
        self._signal_index: dict[str, set[str]] = {}   # signal → {doc_ids}
        self._domain_index: dict[str, set[str]] = {}   # domain → {doc_ids}
        self._phase_index: dict[str, set[str]] = {}    # phase → {doc_ids}
        self._built = False

    def build_from_directory(self, knowledge_dir: Path) -> dict:
        """Scan all markdown files and build the inverted index.

        Returns a summary dict with counts and any validation warnings.
        """
        self._docs.clear()
        self._skill_index.clear()
        self._signal_index.clear()
        self._domain_index.clear()
        self._phase_index.clear()

        summary = {
            "total_files": 0,
            "indexed": 0,
            "no_frontmatter": 0,
            "validation_warnings": [],
        }

        if not knowledge_dir.is_dir():
            logger.warning("Knowledge directory not found: %s", knowledge_dir)
            return summary

        for md_file in sorted(knowledge_dir.rglob("*.md")):
            if md_file.name.startswith("."):
                continue
            summary["total_files"] += 1

            try:
                content = md_file.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                logger.warning("Failed to read %s: %s", md_file, e)
                continue

            meta = parse_frontmatter(content)
            if not meta:
                summary["no_frontmatter"] += 1
                continue

            # Normalize SKILL.md-style frontmatter to registry schema
            meta = _normalize_skillmd_frontmatter(meta)
            meta = _normalize_metadata_aliases(meta)

            # Validate (skip strict validation for auto-normalized SKILL.md files)
            rel_path = str(md_file.relative_to(knowledge_dir))
            if not meta.get("_from_skillmd"):
                errors = validate_frontmatter(meta, rel_path)
                if errors:
                    summary["validation_warnings"].extend(errors)

            doc_id = meta.get("doc_id", rel_path)
            meta["_source_path"] = str(md_file)
            self._docs[doc_id] = meta
            summary["indexed"] += 1

            # Build inverted indices
            for skill in meta.get("related_skills", []):
                self._skill_index.setdefault(skill, set()).add(doc_id)

            for signal in meta.get("signals", []):
                self._signal_index.setdefault(signal, set()).add(doc_id)

            for domain in meta.get("domains", []):
                self._domain_index.setdefault(domain, set()).add(doc_id)

            for phase in meta.get("phases", []):
                self._phase_index.setdefault(phase, set()).add(doc_id)

        self._built = True
        logger.info(
            "Knowledge registry built: %d indexed, %d no frontmatter, %d warnings",
            summary["indexed"], summary["no_frontmatter"],
            len(summary["validation_warnings"]),
        )
        return summary

    def lookup(
        self,
        skill: Optional[str] = None,
        signal: Optional[str] = None,
        domain: Optional[str] = None,
        phase: Optional[str] = None,
    ) -> list[dict]:
        """Find documents matching given criteria (AND logic).

        Returns list of metadata dicts sorted by priority (desc).
        """
        candidates: Optional[set[str]] = None

        if skill:
            skill_docs = self._skill_index.get(skill, set())
            candidates = skill_docs if candidates is None else candidates & skill_docs

        if signal:
            signal_docs = self._signal_index.get(signal, set())
            candidates = signal_docs if candidates is None else candidates & signal_docs

        if domain:
            domain_docs = self._domain_index.get(domain, set())
            candidates = domain_docs if candidates is None else candidates & domain_docs

        if phase:
            phase_docs = self._phase_index.get(phase, set())
            candidates = phase_docs if candidates is None else candidates & phase_docs

        if candidates is None:
            return []

        results = [self._docs[doc_id] for doc_id in candidates if doc_id in self._docs]
        # Sort by priority (higher first)
        results.sort(key=lambda d: d.get("priority", 0.5), reverse=True)
        return results
