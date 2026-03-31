"""Web-search utilities shared by chat fallback and research agents."""

from __future__ import annotations

import asyncio


async def _fetch_webpage(url: str, timeout: float = 10.0) -> str:
    import httpx
    from markdownify import markdownify

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/91.0.4472.124 Safari/537.36"
        )
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            return markdownify(response.text)
    except Exception as e:  # pragma: no cover - network dependent
        return f"Error fetching {url}: {e}"


async def search_web_markdown(
    query: str,
    *,
    max_results: int = 3,
    topic: str = "general",
) -> str:
    """Search the web and return fetched pages as markdown."""
    from tavily import TavilyClient

    def _sync_search() -> dict:
        client = TavilyClient()
        return client.search(query, max_results=max_results, topic=topic)

    search_results = await asyncio.to_thread(_sync_search)
    results = search_results.get("results", [])
    if not results:
        return f"No results found for '{query}'"

    contents = await asyncio.gather(*[_fetch_webpage(r["url"]) for r in results])

    parts = [f"Found {len(results)} result(s) for '{query}':", ""]
    for result, content in zip(results, contents):
        parts.extend(
            [
                f"## {result.get('title', 'Untitled')}",
                f"URL: {result.get('url', '')}",
                "",
                content,
                "",
                "---",
                "",
            ]
        )
    return "\n".join(parts).strip()
