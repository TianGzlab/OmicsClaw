"""Unified capability resolution for OmicsClaw chat and automation flows.

Determines whether a user request is:
- fully covered by an existing skill
- partially covered and needs custom post-processing
- not covered and should fall back to web-guided custom analysis

Scoring weights and decision thresholds are kept as module-level named
constants (see ``_SCORE_*`` / ``_DOMAIN_SCORE_*`` / ``_RESOLVE_*`` below).
Previous revisions buried those magic numbers inside arithmetic in
``_candidate_score`` and ``resolve_capability`` — OMI-12 P2.8 lifted them
out so future weight tuning is reviewable diff-by-diff, and the matching
golden routing snapshot (``tests/test_capability_resolver_golden.py``) flags
any silent re-ranking that slips through.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import re
from typing import Any

from omicsclaw.core.registry import OmicsRegistry, ensure_registry_loaded

try:
    from omicsclaw.loaders import detect_domain_from_path
except Exception:  # pragma: no cover - fallback for partial installs
    detect_domain_from_path = None


# ---------------------------------------------------------------------------
# Scoring weights (lifted from inline magic numbers — OMI-12 P2.8).
#
# Each constant documents what its signal source is and why the weight has
# the value it does. Changing any of these will likely re-rank some queries;
# the golden routing test snapshots ``chosen_skill`` for ~20 representative
# queries so re-rankings surface as a single, reviewable test diff.
# ---------------------------------------------------------------------------

# ----- _candidate_score: per-skill scoring -----

# A direct mention of a skill's canonical alias in the query is the strongest
# signal we have — the user named the skill they want. Outweighs every other
# signal so a single alias hit can dominate even a long description overlap.
_SCORE_ALIAS_MENTION = 12.0

# Pre-rename / shorthand aliases (SKILL.md ``legacy_aliases``) score slightly
# lower than the canonical alias so canonical wins on ties.
_SCORE_LEGACY_ALIAS_MENTION = 9.0

# Each shared token between the query and the skill's SKILL.md description
# adds a small bonus. Capped so a very long description can't dominate
# alias mentions or trigger keywords.
_SCORE_DESCRIPTION_OVERLAP_PER_TOKEN = 0.85
_SCORE_DESCRIPTION_OVERLAP_CAP = 8  # max overlap tokens counted

# Trigger keywords (SKILL.md ``trigger_keywords``) get a length-weighted bonus
# so a multi-word phrase ("differential expression") is worth more than a
# generic single word ("run"). Bounded to keep the keyword signal in the
# same order of magnitude as the alias signal.
_SCORE_TRIGGER_KEYWORD_MIN = 1.5
_SCORE_TRIGGER_KEYWORD_MAX = 4.5
_SCORE_TRIGGER_KEYWORD_LENGTH_DIVISOR = 6.0
_SCORE_TRIGGER_KEYWORD_LIMIT = 3  # max distinct keywords counted per skill

# Param-hint match: the user named a specific method (``--method leiden``)
# and that method appears as a parameter hint for the skill's SKILL.md
# methodology block.
_SCORE_PARAM_HINT_MATCH = 3.0


# ----- _detect_domain: per-domain scoring -----

# File path with a known extension is the strongest domain signal.
_DOMAIN_SCORE_FILE_PATH = 5.0
# Per-domain mirrors of the per-skill scores, intentionally weaker so the
# domain detector is more forgiving than the skill picker.
_DOMAIN_SCORE_ALIAS_MENTION = 8.0
_DOMAIN_SCORE_LEGACY_ALIAS_MENTION = 6.0
_DOMAIN_SCORE_DESCRIPTION_OVERLAP_PER_TOKEN = 0.6
_DOMAIN_SCORE_DESCRIPTION_OVERLAP_CAP = 5
_DOMAIN_SCORE_TRIGGER_KEYWORD_LIMIT = 2
# The user typed the domain name verbatim ("bulk RNA-seq", "spatial").
_DOMAIN_SCORE_DOMAIN_NAME_MATCH = 4.0


# ----- resolve_capability: decision thresholds -----

# Below this top-1 score the resolver returns ``coverage="no_skill"`` instead
# of guessing. Tuned so a single description-token overlap (~0.85) or a
# single short keyword hit (~1.5) is not enough to commit.
_RESOLVE_NO_SKILL_THRESHOLD = 3.0

# If top-1 minus top-2 is smaller than this and the query also has composite
# wording ("and then ...", "再 ..."), the resolver downgrades from
# ``exact_skill`` to ``partial_skill`` rather than blindly picking top-1.
_RESOLVE_CLOSE_SECOND_GAP = 1.5

# Top-1 score divided by this gives the reported confidence ∈ [0, 1].
# Chosen so a single strong alias hit (12) + a few description tokens lands
# near 1.0 without saturating on every clear-intent query.
_RESOLVE_CONFIDENCE_DIVISOR = 14.0

# Same idea but tighter, used only on the ``no_skill`` fallback path so that
# a marginal top score doesn't claim higher confidence than the cap below.
_RESOLVE_NO_SKILL_CONFIDENCE_DIVISOR = 10.0

# Confidence ceiling for the ``no_skill`` fallback path; we never claim
# strong confidence when we're below the no-skill threshold.
_RESOLVE_NO_SKILL_CONFIDENCE_CAP = 0.35


_NON_ANALYSIS_HINTS = (
    "what is omicsclaw",
    "help",
    "usage",
    "install",
    "version",
)

_CUSTOM_FALLBACK_HINTS = (
    "custom",
    "bespoke",
    "from scratch",
    "independent",
    "not in omicsclaw",
    "not available in omicsclaw",
    "outside the skill",
    "post-process",
    "post process",
    "after that",
    "then compute",
    "then generate",
    "extra step",
    "additional step",
    "再做",
    "然后再",
    "额外",
    "自定义",
    "独立生成",
    "skill里没有",
    "skill 里没有",
)

_WEB_HINTS = (
    "latest",
    "recent",
    "newest",
    "up-to-date",
    "documentation",
    "docs",
    "paper",
    "papers",
    "literature",
    "web",
    "internet",
    "联网",
    "最新",
    "文献",
    "论文",
    "官网",
)

_IMPLEMENTATION_FROM_LITERATURE_HINTS = (
    "implement",
    "build",
    "develop",
    "code",
    "from latest literature",
    "from recent literature",
    "from literature",
    "基于最新文献实现",
    "根据最新文献实现",
    "按文献实现",
)


def _trigger_keyword_score(phrase: str) -> float:
    """Length-weighted keyword score, clamped to ``[MIN, MAX]``."""
    return max(
        _SCORE_TRIGGER_KEYWORD_MIN,
        min(_SCORE_TRIGGER_KEYWORD_MAX, len(phrase) / _SCORE_TRIGGER_KEYWORD_LENGTH_DIVISOR),
    )


def _score_trigger_keyword_matches(
    query_lower: str,
    keywords: list[str] | tuple[str, ...],
    *,
    limit: int = _SCORE_TRIGGER_KEYWORD_LIMIT,
) -> tuple[float, list[str]]:
    matches: list[str] = []
    score = 0.0
    for keyword in keywords:
        phrase = str(keyword).strip().lower()
        if not phrase or not _mentions_phrase(query_lower, phrase):
            continue
        matches.append(phrase)
        score += _trigger_keyword_score(phrase)
        if len(matches) >= limit:
            break
    return score, matches


def _requests_new_literature_implementation(query_lower: str) -> bool:
    """Return True for requests to implement new methods from literature."""
    has_implementation = any(
        _mentions_phrase(query_lower, hint)
        for hint in _IMPLEMENTATION_FROM_LITERATURE_HINTS[:4]
    )
    has_literature_source = any(
        _mentions_phrase(query_lower, hint)
        for hint in _IMPLEMENTATION_FROM_LITERATURE_HINTS[4:]
    ) or any(_mentions_phrase(query_lower, hint) for hint in _WEB_HINTS)
    return has_implementation and has_literature_source


_SKILL_CREATION_HINTS = (
    "create skill",
    "create a skill",
    "new skill",
    "add skill",
    "build skill",
    "scaffold skill",
    "skill scaffold",
    "generate skill",
    "package as skill",
    "turn into a skill",
    "reusable skill",
    "integrate into omicsclaw",
    "add to omicsclaw",
    "新增skill",
    "新增 skill",
    "创建skill",
    "创建 skill",
    "新建skill",
    "新建 skill",
    "做成skill",
    "做成 skill",
    "封装成skill",
    "封装成 skill",
    "封装为skill",
    "封装为 skill",
    "沉淀成skill",
    "沉淀成 skill",
    "加入omicsclaw",
    "加入 omicsclaw",
)

_COMPOSITE_HINTS = (
    " and then ",
    " followed by ",
    " combine ",
    " plus ",
    " with an extra ",
    "然后",
    "再",
)

_GENERIC_ANALYSIS_HINTS = (
    "analy",
    "run ",
    "perform ",
    "compute ",
    "microenvironment",
    "neighborhood",
    "微环境",
    "邻域",
    "preprocess",
    "qc",
    "cluster",
    "differential",
    "deconvolution",
    "trajectory",
    "velocity",
    "pathway",
    "enrichment",
    "survival",
    "spatial",
    "single cell",
    "single-cell",
    "proteomics",
    "metabolomics",
    "genomics",
    "bulk rna",
    "空间",
    "单细胞",
    "蛋白",
    "代谢",
    "基因组",
    "差异",
    "富集",
)

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_\-+.]{1,}")
_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "into",
    "then",
    "that",
    "this",
    "using",
    "use",
    "analysis",
    "model",
    "run",
    "perform",
    "skill",
    "skills",
}


@dataclass
class CapabilityCandidate:
    skill: str
    domain: str
    score: float
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["score"] = round(float(self.score), 3)
        return data


@dataclass
class CapabilityDecision:
    query: str
    domain: str = ""
    coverage: str = "no_skill"
    confidence: float = 0.0
    chosen_skill: str = ""
    should_search_web: bool = False
    should_create_skill: bool = False
    skill_candidates: list[CapabilityCandidate] = field(default_factory=list)
    missing_capabilities: list[str] = field(default_factory=list)
    reasoning: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "domain": self.domain,
            "coverage": self.coverage,
            "confidence": round(float(self.confidence), 3),
            "chosen_skill": self.chosen_skill,
            "should_search_web": self.should_search_web,
            "should_create_skill": self.should_create_skill,
            "skill_candidates": [c.to_dict() for c in self.skill_candidates],
            "missing_capabilities": list(self.missing_capabilities),
            "reasoning": list(self.reasoning),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    def to_prompt_block(self) -> str:
        lines = [
            "## Deterministic Capability Assessment",
            f"- coverage: {self.coverage}",
            f"- chosen_skill: {self.chosen_skill or 'none'}",
            f"- domain: {self.domain or 'unknown'}",
            f"- confidence: {round(float(self.confidence), 3)}",
            f"- should_search_web: {self.should_search_web}",
            f"- should_create_skill: {self.should_create_skill}",
        ]
        if self.missing_capabilities:
            lines.append("- missing_capabilities: " + "; ".join(self.missing_capabilities))
        if self.reasoning:
            lines.append("- reasoning:")
            for item in self.reasoning[:4]:
                lines.append(f"  * {item}")
        if self.skill_candidates:
            preview = ", ".join(
                f"{c.skill} ({round(float(c.score), 2)})"
                for c in self.skill_candidates[:3]
            )
            lines.append(f"- candidate_skills: {preview}")
        return "\n".join(lines)


def _tokenize(text: str) -> set[str]:
    return {
        token
        for token in _TOKEN_RE.findall(text.lower())
        if token not in _STOPWORDS
    }


def _mentions_phrase(text: str, phrase: str) -> bool:
    phrase = (phrase or "").strip().lower()
    if not phrase:
        return False
    if len(phrase) <= 3 and phrase.replace("-", "").replace("_", "").isalnum():
        pattern = rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])"
        return bool(re.search(pattern, text))
    return phrase in text


def _looks_like_analysis_request(query: str) -> bool:
    lower = query.lower()
    if any(h in lower for h in _NON_ANALYSIS_HINTS):
        return False
    if any(h in lower for h in _GENERIC_ANALYSIS_HINTS):
        return True
    return bool(re.search(r"\.(h5ad|h5|loom|mzml|fastq|fq|bam|vcf|csv|tsv)\b", lower))


def _method_mentions(query: str) -> set[str]:
    return {
        token
        for token in _tokenize(query)
        if len(token) >= 3 and not token.isdigit()
    }


def _requests_skill_creation(query: str) -> bool:
    lower = (query or "").lower()
    if any(hint in lower for hint in _SKILL_CREATION_HINTS):
        return True

    if "skill" in lower and any(
        verb in lower for verb in ("create", "add", "build", "scaffold", "package", "persist")
    ):
        return True

    if "skill" in lower and any(
        verb in lower for verb in ("创建", "新增", "新建", "封装", "沉淀", "加入")
    ):
        return True

    return False


def _detect_domain(
    registry: OmicsRegistry,
    query: str,
    file_path: str = "",
    domain_hint: str = "",
) -> str:
    if domain_hint:
        return domain_hint

    query_lower = query.lower()
    query_tokens = _tokenize(query_lower)
    domain_scores: dict[str, float] = {
        domain: 0.0
        for domain in registry.domains
    }

    if file_path and detect_domain_from_path is not None:
        detected = str(detect_domain_from_path(file_path, fallback="")).strip()
        if detected:
            domain_scores[detected] = (
                domain_scores.get(detected, 0.0) + _DOMAIN_SCORE_FILE_PATH
            )

    best_domain = ""
    best_score = 0.0

    for domain, info in registry.domains.items():
        score = domain_scores.get(domain, 0.0)
        for alias, skill_info in registry.iter_primary_skills(domain=domain):
            if _mentions_phrase(query_lower, alias.lower()):
                score += _DOMAIN_SCORE_ALIAS_MENTION

            for legacy in skill_info.get("legacy_aliases", []):
                legacy_lower = str(legacy).lower()
                if legacy_lower and _mentions_phrase(query_lower, legacy_lower):
                    score += _DOMAIN_SCORE_LEGACY_ALIAS_MENTION

            description = str(skill_info.get("description", "")).lower()
            overlap = query_tokens & _tokenize(description)
            score += (
                min(len(overlap), _DOMAIN_SCORE_DESCRIPTION_OVERLAP_CAP)
                * _DOMAIN_SCORE_DESCRIPTION_OVERLAP_PER_TOKEN
            )

            keyword_score, _ = _score_trigger_keyword_matches(
                query_lower,
                skill_info.get("trigger_keywords", []),
                limit=_DOMAIN_SCORE_TRIGGER_KEYWORD_LIMIT,
            )
            score += keyword_score

        domain_name = str(info.get("name", domain)).lower()
        if domain_name in query_lower or domain.lower() in query_lower:
            score += _DOMAIN_SCORE_DOMAIN_NAME_MATCH

        if score > best_score:
            best_score = score
            best_domain = domain

    return best_domain


def _collect_query_keyword_matches(
    registry: OmicsRegistry,
    domain: str | None,
    query_lower: str,
) -> dict[str, list[str]]:
    """Precompute ``{alias: [matched_keywords]}`` for the query.

    Uses ``registry.build_keyword_map()`` so each (keyword → skill) entry is
    inspected at most once per resolve call, instead of iterating every
    skill's trigger keywords from inside ``_candidate_score``. The matcher
    is still ``_mentions_phrase`` so behavior matches the previous
    implementation byte-for-byte; this only avoids redundant lookups.
    """
    keyword_map = registry.build_keyword_map(domain=domain)
    matches_by_alias: dict[str, list[str]] = {}
    for keyword, alias in keyword_map.items():
        phrase = str(keyword).strip().lower()
        if not phrase or not _mentions_phrase(query_lower, phrase):
            continue
        bucket = matches_by_alias.setdefault(alias, [])
        if len(bucket) < _SCORE_TRIGGER_KEYWORD_LIMIT:
            bucket.append(phrase)
    return matches_by_alias


def _candidate_score(
    alias: str,
    info: dict[str, Any],
    query_lower: str,
    query_tokens: set[str],
    method_tokens: set[str],
    *,
    keyword_matches: list[str] | None = None,
) -> CapabilityCandidate | None:
    score = 0.0
    reasons: list[str] = []

    alias_lower = alias.lower()
    if _mentions_phrase(query_lower, alias_lower):
        score += _SCORE_ALIAS_MENTION
        reasons.append(f"query explicitly mentions skill '{alias}'")

    for legacy in info.get("legacy_aliases", []):
        legacy_lower = str(legacy).lower()
        if legacy_lower and _mentions_phrase(query_lower, legacy_lower):
            score += _SCORE_LEGACY_ALIAS_MENTION
            reasons.append(f"query mentions legacy alias '{legacy}'")

    description = str(info.get("description", ""))
    description_lower = description.lower()
    overlap = query_tokens & _tokenize(description_lower)
    if overlap:
        overlap_score = (
            min(len(overlap), _SCORE_DESCRIPTION_OVERLAP_CAP)
            * _SCORE_DESCRIPTION_OVERLAP_PER_TOKEN
        )
        score += overlap_score
        reasons.append("description token overlap: " + ", ".join(sorted(list(overlap))[:5]))

    if keyword_matches is None:
        keyword_score, kw_match_list = _score_trigger_keyword_matches(
            query_lower,
            info.get("trigger_keywords", []),
        )
    else:
        kw_match_list = keyword_matches
        keyword_score = sum(_trigger_keyword_score(kw) for kw in kw_match_list)
    if keyword_score:
        score += keyword_score
        reasons.append(
            "trigger keyword match: " + ", ".join(kw_match_list[:3])
        )

    for kw in info.get("param_hints", {}):
        kw_lower = str(kw).lower()
        if kw_lower in method_tokens:
            score += _SCORE_PARAM_HINT_MATCH
            reasons.append(f"requested method '{kw_lower}' appears in param hints")

    if score <= 0:
        return None

    return CapabilityCandidate(
        skill=alias,
        domain=str(info.get("domain", "")),
        score=score,
        reasons=reasons,
    )


def resolve_capability(
    query: str,
    *,
    file_path: str = "",
    domain_hint: str = "",
) -> CapabilityDecision:
    """Resolve a user request into exact/partial/no-skill coverage."""
    query = (query or "").strip()
    if not query and not file_path:
        return CapabilityDecision(
            query=query,
            reasoning=["empty request"],
        )

    registry = ensure_registry_loaded()

    skill_creation_requested = _requests_skill_creation(query)

    if not _looks_like_analysis_request(query) and not file_path and not skill_creation_requested:
        return CapabilityDecision(
            query=query,
            reasoning=["request does not look like an omics analysis task"],
        )

    query_lower = query.lower()
    query_tokens = _tokenize(query_lower)
    method_tokens = _method_mentions(query_lower)
    domain = _detect_domain(registry, query, file_path=file_path, domain_hint=domain_hint)
    if _requests_new_literature_implementation(query_lower):
        return CapabilityDecision(
            query=query,
            domain=domain,
            coverage="no_skill",
            confidence=0.0,
            should_search_web=True,
            should_create_skill=skill_creation_requested,
            missing_capabilities=[
                "request asks to implement a new method from external literature",
            ],
            reasoning=[
                "request asks for new method implementation rather than literature parsing",
            ],
        )

    # Precompute keyword matches once via the registry's inverted keyword
    # index — capability_resolver used to rescan every skill's
    # ``trigger_keywords`` from inside the per-skill loop (OMI-12 P2.8).
    keyword_matches_by_alias = _collect_query_keyword_matches(
        registry, domain or None, query_lower
    )

    candidates: list[CapabilityCandidate] = []
    for alias, info in registry.iter_primary_skills(domain=domain or None):
        candidate = _candidate_score(
            alias,
            info,
            query_lower,
            query_tokens,
            method_tokens,
            keyword_matches=keyword_matches_by_alias.get(alias, []),
        )
        if candidate is not None:
            candidates.append(candidate)

    # Sort by score DESC with a stable alphabetical tie-break on the skill
    # alias. Without the tie-break, the post-PR audit caught WGCNA flapping
    # between ``bulkrna-coexpression`` and ``bulkrna-ppi-network`` depending
    # on the order ``registry.iter_primary_skills`` happened to return them
    # in — which itself depends on filesystem traversal at registry load
    # time. Alphabetical order gives a deterministic winner.
    candidates.sort(key=lambda c: (-c.score, c.skill))

    custom_requested = any(h in query_lower for h in _CUSTOM_FALLBACK_HINTS)
    web_requested = any(h in query_lower for h in _WEB_HINTS)
    composite_requested = any(h in query_lower for h in _COMPOSITE_HINTS)

    if not candidates or candidates[0].score < _RESOLVE_NO_SKILL_THRESHOLD:
        reasons = ["no skill achieved a meaningful semantic match"]
        if skill_creation_requested:
            reasons.append("query explicitly asks to create or package a reusable skill")
        missing = ["no existing OmicsClaw skill sufficiently matches the requested task"]
        if web_requested:
            missing.append("request explicitly asks for external literature or documentation lookup")
        return CapabilityDecision(
            query=query,
            domain=domain,
            coverage="no_skill",
            confidence=(
                0.0
                if not candidates
                else min(
                    candidates[0].score / _RESOLVE_NO_SKILL_CONFIDENCE_DIVISOR,
                    _RESOLVE_NO_SKILL_CONFIDENCE_CAP,
                )
            ),
            should_search_web=True,
            should_create_skill=skill_creation_requested,
            skill_candidates=candidates[:5],
            missing_capabilities=missing,
            reasoning=reasons,
        )

    top = candidates[0]
    second = candidates[1] if len(candidates) > 1 else None
    confidence = min(1.0, top.score / _RESOLVE_CONFIDENCE_DIVISOR)
    close_second = bool(second and (top.score - second.score) < _RESOLVE_CLOSE_SECOND_GAP)

    reasoning = [f"top candidate '{top.skill}' scored {round(top.score, 2)}"]
    reasoning.extend(top.reasons[:3])
    missing_capabilities: list[str] = []

    if custom_requested:
        missing_capabilities.append("custom or post-skill analysis step requested")
        reasoning.append("query contains explicit custom-analysis wording")
    if web_requested:
        missing_capabilities.append("latest external methods or documentation requested")
        reasoning.append("query requests web/literature lookups")
    if composite_requested and close_second:
        missing_capabilities.append("request appears to combine multiple analysis intents")
        reasoning.append("query appears composite and candidate gap is narrow")
    if skill_creation_requested:
        reasoning.append("query explicitly asks for a reusable OmicsClaw skill scaffold")

    if custom_requested or web_requested or (composite_requested and close_second):
        coverage = "partial_skill"
        should_search_web = web_requested or not top.reasons
    else:
        coverage = "exact_skill"
        should_search_web = False

    if close_second and coverage == "exact_skill":
        reasoning.append(
            f"second candidate '{second.skill}' is close ({round(second.score, 2)}), but no extra custom step was requested"
        )

    return CapabilityDecision(
        query=query,
        domain=domain,
        coverage=coverage,
        confidence=confidence,
        chosen_skill=top.skill,
        should_search_web=should_search_web,
        should_create_skill=skill_creation_requested,
        skill_candidates=candidates[:5],
        missing_capabilities=missing_capabilities,
        reasoning=reasoning,
    )


__all__ = [
    "CapabilityCandidate",
    "CapabilityDecision",
    "resolve_capability",
]
