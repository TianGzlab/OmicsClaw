"""Unified routing logic supporting keyword, LLM, and hybrid modes."""

import logging
from typing import Dict, Tuple, Optional

logger = logging.getLogger(__name__)

def route_query_unified(
    query: str,
    keyword_map: Dict[str, str],
    skill_descriptions: Dict[str, str],
    domain: str,
    routing_mode: str = "keyword",
    confidence_threshold: float = 0.5
) -> Tuple[Optional[str], float]:
    """Unified routing function supporting multiple modes.
    
    Args:
        query: User query
        keyword_map: Keyword to skill mapping
        skill_descriptions: Skill descriptions
        domain: Omics domain
        routing_mode: "keyword", "llm", or "hybrid"
        confidence_threshold: Threshold for hybrid mode
    
    Returns:
        (skill_name, confidence) tuple
    """
    if routing_mode == "keyword":
        return _route_keyword(query, keyword_map)
    elif routing_mode == "llm":
        return _route_llm(query, skill_descriptions, domain)
    elif routing_mode == "hybrid":
        skill, conf = _route_keyword(query, keyword_map)
        if skill and conf >= confidence_threshold:
            return skill, conf
        # Fallback to LLM
        return _route_llm(query, skill_descriptions, domain)
    else:
        logger.warning(f"Unknown routing mode: {routing_mode}, using keyword")
        return _route_keyword(query, keyword_map)

def route_keyword(query: str, keyword_map: Dict[str, str]) -> Tuple[Optional[str], float]:
    """Keyword-based routing — public API.

    Scores each skill by summing lengths of matching keywords.
    Returns ``(best_skill, confidence)`` where confidence is
    ``min(1.0, total_score / 20.0)``.
    """
    query_lower = query.lower().strip()
    scores: Dict[str, int] = {}
    for kw, skill in keyword_map.items():
        if kw in query_lower:
            scores[skill] = scores.get(skill, 0) + len(kw)
    if scores:
        best_skill = max(scores, key=lambda s: scores[s])
        confidence = min(1.0, scores[best_skill] / 20.0)
        return best_skill, round(confidence, 2)
    return None, 0.0


# Keep private alias for internal use
_route_keyword = route_keyword

def _route_llm(query: str, skills: Dict[str, str], domain: str) -> Tuple[Optional[str], float]:
    """LLM-based routing."""
    try:
        from omicsclaw.routing.llm_router import route_with_llm
        return route_with_llm(query, skills, domain)
    except Exception as e:
        logger.error(f"LLM routing failed: {e}")
        return None, 0.0
