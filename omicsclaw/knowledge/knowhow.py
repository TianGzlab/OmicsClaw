"""
Preflight Know-How (KH) Injection System.

Loads KH-*.md documents from knowledge_base/knowhows/ and injects them as
mandatory scientific constraints into the LLM system prompt before analysis.

Matching priority:
1. Exact skill match from KH frontmatter
2. Domain + query-term match
3. Query-term-only match

Global KH docs (for example related_skills: [__all__]) are always included.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import os
from pathlib import Path
import re
from typing import Any, Optional

try:
    import yaml
except Exception:  # pragma: no cover - optional fallback
    yaml = None

logger = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", flags=re.DOTALL)
_PHASE_ALIASES = {
    "after_run": "post_run",
}


@dataclass(frozen=True)
class KnowHowMetadata:
    filename: str
    doc_id: str
    label: str
    critical_rule: str
    skills: tuple[str, ...]
    domains: tuple[str, ...]
    keywords: tuple[str, ...]
    phases: tuple[str, ...]
    priority: float


def _unique(values: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return tuple(result)


def _normalize_phase(value: str) -> str:
    text = str(value or "").strip().lower()
    return _PHASE_ALIASES.get(text, text)


def _normalize_list(
    value: Any,
    *,
    normalizer: Any | None = None,
) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple, set)):
        items = [str(item) for item in value]
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return ()
        items = [text]
    else:
        text = str(value).strip()
        if not text:
            return ()
        items = [text]

    if normalizer is not None:
        items = [normalizer(item) for item in items]
    return _unique(items)


def _pick_first_present(frontmatter: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in frontmatter:
            return frontmatter[key]
    return None


def _parse_simple_frontmatter(raw: str) -> dict[str, Any]:
    """Fallback parser for simple YAML-like frontmatter."""
    result: dict[str, Any] = {}
    for line in raw.splitlines():
        text = line.strip()
        if not text or text.startswith("#") or ":" not in text:
            continue
        key, value = text.split(":", 1)
        key = key.strip()
        value = value.strip()

        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            if not inner:
                result[key] = []
            else:
                result[key] = [
                    item.strip().strip("'\"")
                    for item in inner.split(",")
                    if item.strip()
                ]
            continue

        clean = value.strip().strip("'\"")
        try:
            result[key] = float(clean)
            if clean.isdigit():
                result[key] = int(clean)
        except ValueError:
            result[key] = clean
    return result


def _extract_frontmatter(text: str) -> dict[str, Any]:
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}

    raw = match.group(1)
    if yaml is not None:
        try:
            parsed = yaml.safe_load(raw) or {}
            if isinstance(parsed, dict):
                return parsed
        except Exception as exc:  # pragma: no cover - fallback path
            logger.warning("Failed to parse KH frontmatter via yaml: %s", exc)

    return _parse_simple_frontmatter(raw)


def _priority_value(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.5


def _metadata_from_document(filename: str, text: str) -> KnowHowMetadata:
    frontmatter = _extract_frontmatter(text)
    label = str(frontmatter.get("title") or frontmatter.get("label") or filename).strip()
    doc_id = str(frontmatter.get("doc_id") or Path(filename).stem).strip()
    critical_rule = str(frontmatter.get("critical_rule") or "").strip()
    skills = _normalize_list(_pick_first_present(frontmatter, "related_skills", "skills"))
    domains = _normalize_list(frontmatter.get("domains"))
    keywords = _normalize_list(_pick_first_present(frontmatter, "search_terms", "keywords"))
    phases = _normalize_list(
        _pick_first_present(frontmatter, "phases", "phase"),
        normalizer=_normalize_phase,
    )

    return KnowHowMetadata(
        filename=filename,
        doc_id=doc_id or Path(filename).stem,
        label=label or filename,
        critical_rule=critical_rule,
        skills=skills,
        domains=domains,
        keywords=keywords,
        phases=phases,
        priority=_priority_value(frontmatter.get("priority")),
    )


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
        self._metadata: dict[str, KnowHowMetadata] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        """Lazily load all KH documents and their frontmatter metadata."""
        if self._loaded:
            return
        self._loaded = True
        if not self._dir.is_dir():
            logger.warning("Know-Hows directory not found: %s", self._dir)
            return

        for path in sorted(self._dir.glob("KH-*.md")):
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
                self._cache[path.name] = content
                self._metadata[path.name] = _metadata_from_document(path.name, content)
                logger.debug("Loaded know-how: %s (%d chars)", path.name, len(content))
            except Exception as exc:
                logger.warning("Failed to load know-how %s: %s", path.name, exc)

        logger.info("Loaded %d know-how documents from %s", len(self._cache), self._dir)

    @staticmethod
    def _contains_term(text: str, terms: tuple[str, ...]) -> bool:
        haystack = (text or "").lower()
        return any(str(term).lower() in haystack for term in terms if str(term).strip())

    def _match_score(
        self,
        meta: KnowHowMetadata,
        *,
        skill: str,
        query: str,
        domain: str,
        phase: str,
    ) -> tuple[float, str] | None:
        skill_lower = (skill or "").lower().strip()
        query_lower = (query or "").lower()
        domain_lower = (domain or "").lower().strip()
        phase_lower = _normalize_phase(phase or "")

        skill_terms = tuple(item.lower() for item in meta.skills)
        domain_terms = tuple(item.lower() for item in meta.domains)
        keyword_terms = tuple(item.lower() for item in meta.keywords)
        phase_terms = tuple(_normalize_phase(item) for item in meta.phases)

        if phase_lower and phase_terms and phase_lower not in phase_terms:
            return None

        if "__all__" in skill_terms:
            return 1000.0 + meta.priority, "global"

        if skill_lower and skill_lower in skill_terms:
            return 800.0 + meta.priority, "skill"

        keyword_match = bool(query_lower) and self._contains_term(query_lower, keyword_terms)
        domain_match = bool(domain_lower) and (
            "__all__" in domain_terms or domain_lower in domain_terms
        )

        if domain_match and keyword_match:
            return 500.0 + meta.priority, "domain+query"

        if keyword_match:
            return 300.0 + meta.priority, "query"

        return None

    def get_constraints(
        self,
        skill: Optional[str] = None,
        query: Optional[str] = None,
        domain: Optional[str] = None,
        phase: Optional[str] = None,
    ) -> str:
        """Return formatted constraint text for the given analysis context."""
        matched = self._collect_matches(
            skill=skill or "",
            query=query or "",
            domain=domain or "",
            phase=phase or "",
        )
        if not matched:
            return ""

        parts = [
            "## ⚠️ MANDATORY SCIENTIFIC CONSTRAINTS",
            "",
            "Before starting this analysis, you MUST read and follow ALL of the ",
            "following know-how guides. These are NON-NEGOTIABLE. Violations will ",
            "produce scientifically invalid results.",
            "",
            "**Active guards for this task:**",
        ]

        seen: set[str] = set()
        for _score, filename, meta, _content in matched:
            if filename in seen:
                continue
            seen.add(filename)
            if meta.critical_rule:
                parts.append(f"  → {meta.label}: {meta.critical_rule}")
            else:
                parts.append(f"  → {meta.label}")

        parts.extend(["", "---", ""])

        seen.clear()
        for _score, filename, meta, content in matched:
            if filename in seen:
                continue
            seen.add(filename)
            parts.append(f"### 📋 {meta.label}")
            parts.append(_strip_kh_header(content))
            parts.append("")

        return "\n".join(parts)

    def _collect_matches(
        self,
        *,
        skill: str,
        query: str,
        domain: str,
        phase: str,
    ) -> list[tuple[float, str, KnowHowMetadata, str]]:
        """Collect matched KH documents sorted by priority."""
        self._ensure_loaded()
        if not self._cache:
            return []

        matched: list[tuple[float, str, KnowHowMetadata, str]] = []
        for filename, meta in self._metadata.items():
            score_reason = self._match_score(
                meta,
                skill=skill,
                query=query,
                domain=domain,
                phase=phase,
            )
            if score_reason is None:
                continue
            score, _reason = score_reason
            matched.append((score, filename, meta, self._cache[filename]))

        matched.sort(key=lambda item: (-item[0], item[1]))
        return matched

    def get_kh_for_skill(self, skill: str) -> list[str]:
        """Return KH filenames relevant to a specific skill."""
        self._ensure_loaded()
        skill_lower = (skill or "").lower().strip()
        matched: list[tuple[float, str]] = []

        for filename, meta in self._metadata.items():
            skill_terms = tuple(item.lower() for item in meta.skills)
            if "__all__" in skill_terms:
                matched.append((1000.0 + meta.priority, filename))
                continue
            if skill_lower and skill_lower in skill_terms:
                matched.append((800.0 + meta.priority, filename))

        matched.sort(key=lambda item: (-item[0], item[1]))
        return [filename for _score, filename in matched]

    def get_matching_kh_ids(
        self,
        skill: Optional[str] = None,
        query: Optional[str] = None,
        domain: Optional[str] = None,
        phase: Optional[str] = None,
    ) -> list[str]:
        """Return matched KH filenames for the current execution context."""
        matched = self._collect_matches(
            skill=skill or "",
            query=query or "",
            domain=domain or "",
            phase=phase or "",
        )
        seen: set[str] = set()
        result: list[str] = []
        for _score, filename, _meta, _content in matched:
            if filename in seen:
                continue
            seen.add(filename)
            result.append(filename)
        return result


def _strip_kh_header(content: str) -> str:
    """Remove the metadata header lines but keep the markdown body."""
    content = re.sub(r"^---\s*\n.*?\n---\s*\n", "", content, flags=re.DOTALL)

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
