from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


def _extract_json_object(text: str) -> dict[str, Any]:
    value = str(text or "").strip()
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", value, re.DOTALL)
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _dedupe_queries(query: str, candidates: list[str], *, max_queries: int) -> list[str]:
    original = " ".join(str(query or "").split()).strip().lower()
    seen = {original} if original else set()
    cleaned: list[str] = []
    for item in candidates:
        value = " ".join(str(item or "").split()).strip()
        lowered = value.lower()
        if not value or lowered in seen:
            continue
        seen.add(lowered)
        cleaned.append(value)
        if len(cleaned) >= max_queries:
            break
    return cleaned


async def generate_query_rewrites(
    *,
    query: str,
    domain: str = "",
    doc_type: str = "",
    llm_client=None,
    model: str = "",
    available_topics: list[dict] | None = None,
    max_queries: int = 4,
) -> list[str]:
    """Use the active LLM to propose semantically aligned search rewrites.

    The rewrites are for retrieval only and must stay faithful to the user query.
    """
    if llm_client is None or not model or not str(query or "").strip():
        return []

    topic_lines = []
    for item in (available_topics or [])[:12]:
        title = str(item.get("title", "")).strip()
        source = str(item.get("source_path", "")).strip()
        if title:
            topic_lines.append(f"- {title}" + (f" [{source}]" if source else ""))
    topic_block = "\n".join(topic_lines) or "- No topic preview available"

    system_prompt = (
        "You rewrite a biological-method search query for a local knowledge base.\n"
        "Return JSON only with key `queries`, a list of 1-4 short retrieval-oriented rewrites.\n"
        "Rules:\n"
        "- Preserve user intent exactly.\n"
        "- Bridge cross-language terminology when useful.\n"
        "- Prefer method names, workflow labels, and canonical scientific phrases.\n"
        "- Do not invent methods not implied by the query.\n"
        "- Each rewrite should be short and retrieval-friendly."
    )
    user_prompt = (
        f"Original query: {query}\n"
        f"Domain: {domain or 'unspecified'}\n"
        f"Document type: {doc_type or 'unspecified'}\n"
        "Representative knowledge-base topics:\n"
        f"{topic_block}\n"
        "Return JSON now."
    )

    try:
        response = await llm_client.chat.completions.create(
            model=model,
            max_tokens=220,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = response.choices[0].message.content if response.choices else ""
        payload = _extract_json_object(content)
        queries = payload.get("queries", []) if isinstance(payload, dict) else []
        if not isinstance(queries, list):
            return []
        return _dedupe_queries(query, [str(item) for item in queries], max_queries=max_queries)
    except Exception as exc:
        logger.warning("Knowledge query rewrite failed (non-fatal): %s", exc)
        return []


async def rerank_candidates_with_llm(
    *,
    query: str,
    candidates: list[dict],
    llm_client=None,
    model: str = "",
    limit: int = 5,
) -> list[dict]:
    """Optionally rerank merged candidates with the active LLM."""
    if llm_client is None or not model or len(candidates) <= 1:
        return candidates[:limit]

    numbered = []
    for idx, item in enumerate(candidates[:8], 1):
        snippet = " ".join(str(item.get("content", "")).split())[:220]
        numbered.append(
            {
                "id": f"r{idx}",
                "title": item.get("title", ""),
                "section": item.get("section_title", ""),
                "domain": item.get("domain", ""),
                "type": item.get("doc_type", ""),
                "snippet": snippet,
            }
        )

    system_prompt = (
        "You rerank biological knowledge-base search results.\n"
        "Return JSON only with key `ordered_ids`, containing result ids from most relevant to least relevant.\n"
        "Rank by direct relevance to the user query and usefulness for scientific guidance."
    )
    user_prompt = json.dumps(
        {"query": query, "results": numbered},
        ensure_ascii=False,
    )

    try:
        response = await llm_client.chat.completions.create(
            model=model,
            max_tokens=180,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = response.choices[0].message.content if response.choices else ""
        payload = _extract_json_object(content)
        ordered_ids = payload.get("ordered_ids", []) if isinstance(payload, dict) else []
        if not isinstance(ordered_ids, list):
            return candidates[:limit]

        by_id = {item["id"]: item for item in numbered}
        order = [item_id for item_id in ordered_ids if item_id in by_id]
        ranked: list[dict] = []
        used: set[str] = set()
        for item_id in order:
            idx = int(item_id[1:]) - 1
            ranked.append(candidates[idx])
            used.add(item_id)
            if len(ranked) >= limit:
                return ranked
        for idx, item in enumerate(candidates[:8], 1):
            item_id = f"r{idx}"
            if item_id in used:
                continue
            ranked.append(item)
            if len(ranked) >= limit:
                break
        return ranked
    except Exception as exc:
        logger.warning("Knowledge candidate rerank failed (non-fatal): %s", exc)
        return candidates[:limit]
