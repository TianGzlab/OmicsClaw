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
    primary_skill: str = ""


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


def _resolve_primary_skill(frontmatter: dict[str, Any], related_skills: tuple[str, ...]) -> str:
    """Pick the KH's *primary* skill from frontmatter.

    Preference order:
      1. ``skill:`` (singular string) — explicit primary; other ``related_skills``
         entries are treated as loosely-related and require domain + keyword
         corroboration to fire.
      2. ``primary_skill:`` (explicit field, future-proof).
      3. Single-element ``related_skills`` — implied primary.
      4. Otherwise empty: every ``related_skills`` entry is treated as primary
         (multi-primary mode), preserving the legacy behaviour for KH guards
         that intentionally span many skills (e.g. input-contract guards).
    """
    explicit = frontmatter.get("skill")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    primary_field = frontmatter.get("primary_skill")
    if isinstance(primary_field, str) and primary_field.strip():
        return primary_field.strip()
    if len(related_skills) == 1:
        return related_skills[0]
    return ""


def _metadata_from_document(filename: str, text: str) -> KnowHowMetadata:
    frontmatter = _extract_frontmatter(text)
    label = str(frontmatter.get("title") or frontmatter.get("label") or filename).strip()
    doc_id = str(frontmatter.get("doc_id") or Path(filename).stem).strip()
    critical_rule = str(frontmatter.get("critical_rule") or "").strip()
    skills = _normalize_list(_pick_first_present(frontmatter, "related_skills", "skills"))
    domains = _normalize_list(_pick_first_present(frontmatter, "domains", "domain"))
    keywords = _normalize_list(_pick_first_present(frontmatter, "search_terms", "keywords"))
    phases = _normalize_list(
        _pick_first_present(frontmatter, "phases", "phase"),
        normalizer=_normalize_phase,
    )
    primary_skill = _resolve_primary_skill(frontmatter, skills)

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
        primary_skill=primary_skill,
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

    @staticmethod
    def _related_skill_signal_in_query(
        related_skills: tuple[str, ...],
        *,
        requested_skill: str,
        query: str,
    ) -> bool:
        """True iff a related skill (other than the requested one) is mentioned
        in the query, either by full name or by its trailing ``-stem``.

        Used as the cross-skill corroboration check on the loose-related tier
        so that, e.g., ``KH-sc-enrichment-guardrails`` fires on
        ``query="do enrichment after sc-de"`` (stem ``enrichment``) but not
        on ``query="run sc-de"`` (no enrichment-side mention).
        """
        if not query:
            return False
        for rel in related_skills:
            rel_lower = rel.lower()
            if rel_lower == requested_skill:
                continue
            if rel_lower in query:
                return True
            stem = rel_lower.rsplit("-", 1)[-1]
            # Require >=4 chars to avoid noise from short tokens like "de" or "qc".
            if stem and stem != rel_lower and len(stem) >= 4 and stem in query:
                return True
        return False

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
        primary_skill_lower = (meta.primary_skill or "").lower().strip()

        if phase_lower and phase_terms and phase_lower not in phase_terms:
            return None

        if "__all__" in skill_terms:
            return 1000.0 + meta.priority, "global"

        # Primary-skill tier (800).
        # When the KH declares an explicit primary (singular ``skill:``), only
        # that skill earns the 800 score; other ``related_skills`` entries are
        # demoted to the loose-related tier below. When no explicit primary is
        # declared, every ``related_skills`` entry counts as primary
        # (multi-primary mode preserves legacy behaviour for cross-skill
        # guards like ``KH-sc-input-contract-guardrails``).
        if skill_lower:
            if primary_skill_lower:
                if skill_lower == primary_skill_lower:
                    return 800.0 + meta.priority, "primary_skill"
            elif skill_lower in skill_terms:
                return 800.0 + meta.priority, "skill"

        domain_match = bool(domain_lower) and (
            "__all__" in domain_terms or "general" in domain_terms or domain_lower in domain_terms
        )
        if domain_lower and domain_terms and not domain_match:
            return None

        keyword_match = bool(query_lower) and self._contains_term(query_lower, keyword_terms)

        # Loose-related tier (600). Only reachable when an explicit primary
        # exists, the requested skill is in ``related_skills`` but is not
        # primary, the domain matches, AND there is corroborating signal in
        # the query (an explicit search_term hit or a cross-skill name/stem
        # mention). This is the over-match guard that prevents KHs like
        # ``sc-enrichment`` from firing on plain ``sc-de`` requests.
        if (
            primary_skill_lower
            and skill_lower
            and skill_lower != primary_skill_lower
            and skill_lower in skill_terms
            and domain_match
        ):
            cross_skill_signal = self._related_skill_signal_in_query(
                meta.skills,
                requested_skill=skill_lower,
                query=query_lower,
            )
            if keyword_match or cross_skill_signal:
                return 600.0 + meta.priority, "related+domain+signal"

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
        *,
        headline_only: bool = False,
    ) -> str:
        """Return formatted constraint text for the given analysis context.

        ``headline_only`` (default ``False`` for backward compatibility,
        callers in the production system-prompt path pass ``True``): emit
        only the one-line ``→ {label}: {critical_rule}`` rows so the
        prompt stays compact. Models that need the full body should fetch
        on demand via the ``read_knowhow(name)`` tool.

        Existing tests and any caller that relied on the full-body output
        keep working unchanged. Set ``headline_only=True`` to opt into the
        compressed format.
        """
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

        if headline_only:
            parts.append("")
            # Hint covers both surfaces: bot has the ``read_knowhow`` tool
            # registered; interactive / pipeline surfaces use Claude Code's
            # built-in file_read against the canonical markdown path. Pointing
            # at both keeps the headline payload surface-agnostic.
            parts.append(
                "If a guard's full content is needed, call "
                "`read_knowhow(name=\"<filename>\")` (bot surface) or read "
                "`knowledge_base/knowhows/<filename>` directly."
            )
            return "\n".join(parts)

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

    # Maximum number of KH guards surfaced per turn. Caps prompt growth on
    # broad queries; the model can still fetch any specific guard via
    # ``read_knowhow(name)``.
    DEFAULT_MAX_RESULTS: int = 4

    def _collect_matches(
        self,
        *,
        skill: str,
        query: str,
        domain: str,
        phase: str,
        max_results: int | None = None,
    ) -> list[tuple[float, str, KnowHowMetadata, str]]:
        """Collect matched KH documents sorted by priority, capped at ``max_results``.

        ``max_results=None`` uses ``DEFAULT_MAX_RESULTS`` (=4). Pass a non-positive
        value (e.g. ``0`` or ``-1``) to disable the cap; tests and tooling that
        need the full match list rely on this opt-out.
        """
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
        cap = self.DEFAULT_MAX_RESULTS if max_results is None else max_results
        if cap > 0:
            matched = matched[:cap]
        return matched

    def read_knowhow(self, name: str) -> str:
        """Resolve a KH by filename, doc_id, or label and return its full
        markdown body.

        Used by the ``read_knowhow(name)`` RAG tool — the model fetches the
        full text on demand when a headline-only constraint payload is
        insufficient. Lookup order:

          1. Exact filename (``KH-…-guardrails.md``).
          2. Filename with auto-prefix/suffix (``sc-de-guardrails`` →
             ``KH-sc-de-guardrails.md``).
          3. ``doc_id`` from frontmatter, case-insensitive.
          4. ``label`` (frontmatter ``title`` or ``label``), case-insensitive.

        Returns ``""`` for unknown / empty input — never raises — so a
        misspelled tool argument doesn't break the conversation.
        """
        if not name:
            return ""
        target = str(name).strip()
        if not target:
            return ""
        self._ensure_loaded()

        if target in self._cache:
            return self._cache[target]

        candidate = target if target.startswith("KH-") else f"KH-{target}"
        if not candidate.endswith(".md"):
            candidate = f"{candidate}.md"
        if candidate in self._cache:
            return self._cache[candidate]

        target_lower = target.lower()
        for filename, meta in self._metadata.items():
            if meta.doc_id and meta.doc_id.lower() == target_lower:
                return self._cache.get(filename, "")
        for filename, meta in self._metadata.items():
            if meta.label and meta.label.lower() == target_lower:
                return self._cache.get(filename, "")
        return ""

    def get_all_kh_ids(self) -> list[str]:
        """Return list of all loaded KH document identifiers."""
        self._ensure_loaded()
        return list(self._cache.keys())

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
