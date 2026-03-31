"""Unified capability resolution for OmicsClaw chat and automation flows.

Determines whether a user request is:
- fully covered by an existing skill
- partially covered and needs custom post-processing
- not covered and should fall back to web-guided custom analysis
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import json
import re
from typing import Any

from omicsclaw.core.registry import OmicsRegistry

try:
    from omicsclaw.loaders import EXTENSION_TO_DOMAIN
except Exception:  # pragma: no cover - fallback for partial installs
    EXTENSION_TO_DOMAIN = {}


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

    if file_path:
        ext = Path(file_path).suffix.lower()
        if ext in EXTENSION_TO_DOMAIN:
            return str(EXTENSION_TO_DOMAIN[ext])

    query_lower = query.lower()
    best_domain = ""
    best_score = 0.0

    for domain, info in registry.domains.items():
        score = 0.0
        for alias, skill_info in registry.iter_primary_skills(domain=domain):
            if _mentions_phrase(query_lower, alias.lower()):
                score += 8.0
            description = str(skill_info.get("description", "")).lower()
            overlap = _tokenize(query_lower) & _tokenize(description)
            score += min(len(overlap), 5) * 0.6

        keyword_map = registry.build_keyword_map(domain=domain)
        for kw in keyword_map:
            if kw and _mentions_phrase(query_lower, kw):
                score += max(1.0, min(5.0, len(kw) / 6.0))

        domain_name = str(info.get("name", domain)).lower()
        if domain_name in query_lower or domain.lower() in query_lower:
            score += 4.0

        if score > best_score:
            best_score = score
            best_domain = domain

    return best_domain


def _candidate_score(
    alias: str,
    info: dict[str, Any],
    query_lower: str,
    query_tokens: set[str],
    method_tokens: set[str],
) -> CapabilityCandidate | None:
    score = 0.0
    reasons: list[str] = []

    alias_lower = alias.lower()
    if _mentions_phrase(query_lower, alias_lower):
        score += 12.0
        reasons.append(f"query explicitly mentions skill '{alias}'")

    for legacy in info.get("legacy_aliases", []):
        legacy_lower = str(legacy).lower()
        if legacy_lower and _mentions_phrase(query_lower, legacy_lower):
            score += 9.0
            reasons.append(f"query mentions legacy alias '{legacy}'")

    description = str(info.get("description", ""))
    description_lower = description.lower()
    overlap = query_tokens & _tokenize(description_lower)
    if overlap:
        overlap_score = min(len(overlap), 8) * 0.85
        score += overlap_score
        reasons.append("description token overlap: " + ", ".join(sorted(list(overlap))[:5]))

    for kw in info.get("param_hints", {}):
        kw_lower = str(kw).lower()
        if kw_lower in method_tokens:
            score += 3.0
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

    registry = OmicsRegistry()
    registry.load_all()

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

    candidates: list[CapabilityCandidate] = []
    for alias, info in registry.iter_primary_skills(domain=domain or None):
        candidate = _candidate_score(alias, info, query_lower, query_tokens, method_tokens)
        if candidate is not None:
            candidates.append(candidate)

    candidates.sort(key=lambda c: c.score, reverse=True)

    custom_requested = any(h in query_lower for h in _CUSTOM_FALLBACK_HINTS)
    web_requested = any(h in query_lower for h in _WEB_HINTS)
    composite_requested = any(h in query_lower for h in _COMPOSITE_HINTS)

    if not candidates or candidates[0].score < 3.0:
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
            confidence=0.0 if not candidates else min(candidates[0].score / 10.0, 0.35),
            should_search_web=True,
            should_create_skill=skill_creation_requested,
            skill_candidates=candidates[:5],
            missing_capabilities=missing,
            reasoning=reasons,
        )

    top = candidates[0]
    second = candidates[1] if len(candidates) > 1 else None
    confidence = min(1.0, top.score / 14.0)
    close_second = bool(second and (top.score - second.score) < 1.5)

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
