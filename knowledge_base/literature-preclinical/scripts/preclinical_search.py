"""
Preclinical Literature Search Module

Search Consensus (consensus.app) for preclinical studies on a target in a disease.
Returns structured paper metadata compatible with downstream extraction scripts.
"""

import time
import os
import random
from typing import List, Dict, Optional
import requests
import pandas as pd


def search_preclinical(
    target: str,
    disease: str,
    max_results: int = 50,
    years: int = 5,
    output_dir: str = "preclinical_results"
) -> List[Dict]:
    """
    Search for preclinical studies on a target in a disease context.

    Uses the Consensus API (consensus.app) for fast, semantically-ranked
    literature search. Requires CONSENSUS_API_KEY environment variable.

    Parameters
    ----------
    target : str
        Molecular target (e.g., "CDK4/6", "BRAF", "PD-L1")
    disease : str
        Disease context (e.g., "breast cancer", "melanoma")
    max_results : int
        Maximum results to retrieve (default: 50, API max per query: 50)
    years : int
        Search last N years (default: 5)
    output_dir : str
        Output directory for saving search results CSV

    Returns
    -------
    List[Dict]
        List of paper dictionaries with source, pmid, doi, title, authors,
        journal, publication_date, abstract, keywords, url.

    Verification
    ------------
    Prints "✓ Literature search completed successfully!"
    """
    print("=" * 70)
    print("PRECLINICAL LITERATURE SEARCH")
    print("=" * 70)
    print(f"\n  Target:  {target}")
    print(f"  Disease: {disease}")
    print(f"  Years:   last {years}")
    print(f"  Max:     {max_results} results")
    print(f"  Backend: Consensus API (consensus.app)\n")

    api_key = os.getenv("CONSENSUS_API_KEY")
    if not api_key:
        print("  ERROR: CONSENSUS_API_KEY environment variable not set.")
        print("  Set it via: export CONSENSUS_API_KEY='your_key_here'")
        print("  Get a key at: https://consensus.app/home/api/")
        return []

    import datetime
    year_min = datetime.date.today().year - years

    # Build queries — multiple phrasings to maximize coverage
    queries = _build_queries(target, disease)
    print(f"  Running {len(queries)} search queries...\n")

    all_papers = []
    for i, query in enumerate(queries):
        remaining = max_results - len(all_papers)
        if remaining <= 0:
            break

        limit = min(remaining, 50)  # API max is 50 per request
        print(f"  Query {i+1}: \"{query}\" (limit={limit})")

        papers = _query_consensus(
            query=query,
            api_key=api_key,
            limit=limit,
            year_min=year_min,
        )
        all_papers.extend(papers)
        print(f"    → {len(papers)} results")

    # Deduplicate
    unique_papers = _deduplicate(all_papers)

    # Sort by publication date (newest first)
    unique_papers.sort(key=lambda x: x.get("publication_date", ""), reverse=True)

    # Trim to max_results
    unique_papers = unique_papers[:max_results]

    # Save search results CSV
    os.makedirs(output_dir, exist_ok=True)
    _save_results_csv(unique_papers, os.path.join(output_dir, "preclinical_search_results.csv"))

    print(f"\n✓ Literature search completed successfully!")
    print(f"  Total unique papers: {len(unique_papers)}")
    return unique_papers


def _build_queries(target: str, disease: str) -> List[str]:
    """Build multiple search queries for broader coverage."""
    queries = [
        f"{target} {disease} preclinical",
        f"{target} {disease} in vitro in vivo",
    ]
    return queries


def _query_consensus(
    query: str,
    api_key: str,
    limit: int = 50,
    year_min: Optional[int] = None,
    max_retries: int = 3,
) -> List[Dict]:
    """
    Query Consensus API and return papers in the standard format.

    Parameters
    ----------
    query : str
        Search query string
    api_key : str
        Consensus API key
    limit : int
        Max results (1-50)
    year_min : int, optional
        Exclude papers before this year
    max_retries : int
        Retry attempts on failure

    Returns
    -------
    List[Dict]
        Papers in the standard format expected by downstream scripts
    """
    url = "https://api.consensus.app/v1/quick_search"
    headers = {"x-api-key": api_key, "Accept": "application/json"}

    params = {
        "query": query.strip(),
        "limit": max(1, min(int(limit), 50)),
    }
    if year_min is not None:
        params["year_min"] = year_min

    delay = random.uniform(1, 3)

    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)

            if response.status_code == 200:
                data = response.json()
                if not isinstance(data, dict):
                    print(f"    Unexpected response format")
                    return []

                results_list = data.get("results")
                if not results_list or not isinstance(results_list, list):
                    return []

                papers = []
                for item in results_list:
                    if not isinstance(item, dict):
                        continue
                    paper = _parse_consensus_paper(item)
                    if paper:
                        papers.append(paper)
                return papers

            if response.status_code == 401:
                print(f"    ERROR: Invalid or expired Consensus API key")
                return []

            if response.status_code == 429:
                if attempt < max_retries:
                    print(f"    Rate limited, retrying in {delay:.0f}s...")
                    time.sleep(delay)
                    delay = min(delay * 2, 60)
                    continue
                print(f"    Rate limit exceeded after {max_retries} attempts")
                return []

            print(f"    API error (HTTP {response.status_code})")
            return []

        except requests.exceptions.Timeout:
            if attempt < max_retries:
                print(f"    Timeout, retrying in {delay:.0f}s...")
                time.sleep(delay)
                delay = min(delay * 2, 60)
                continue
            print(f"    Timeout after {max_retries} attempts")
            return []

        except requests.exceptions.RequestException as e:
            if attempt < max_retries:
                time.sleep(delay)
                delay = min(delay * 2, 60)
                continue
            print(f"    Connection error: {e}")
            return []

    return []


def _parse_consensus_paper(item: dict) -> Optional[Dict]:
    """
    Parse a Consensus API result into the standard paper format.

    Maps Consensus fields to the format expected by extract_experiments.py,
    preclinical_synthesis.py, and other downstream scripts.
    """
    title = item.get("title", "")
    if not title:
        return None

    # Authors — can be list of dicts or list of strings
    authors_field = item.get("authors", [])
    authors_str = ""
    if isinstance(authors_field, list) and len(authors_field) > 0:
        names = []
        for a in authors_field[:10]:
            if isinstance(a, dict):
                name = a.get("name") or a.get("full_name") or ""
            elif isinstance(a, str):
                name = a
            else:
                name = ""
            if name:
                names.append(name)
        authors_str = ", ".join(names)
        if len(authors_field) > 10:
            authors_str += " et al."

    # Year and publication date
    year = item.get("publish_year") or item.get("year") or ""
    pub_date = f"{year}-01-01" if year else ""

    # Journal
    journal = item.get("journal_name") or item.get("journal") or ""
    if journal and year:
        journal_display = f"{journal} ({year})"
    elif journal:
        journal_display = journal
    else:
        journal_display = ""

    # DOI and URL
    doi = item.get("doi", "") or ""
    consensus_url = item.get("url", "") or ""
    if doi:
        paper_url = f"https://doi.org/{doi}"
    elif consensus_url:
        paper_url = consensus_url
    else:
        paper_url = ""

    # Abstract and takeaway
    abstract = item.get("abstract", "") or ""
    takeaway = item.get("takeaway", "") or ""

    # Build keywords from study_type if available
    keywords = item.get("study_type", "") or ""

    return {
        "source": "Consensus",
        "pmid": "",
        "doi": doi,
        "title": title,
        "authors": authors_str,
        "journal": journal_display,
        "publication_date": pub_date,
        "abstract": abstract,
        "takeaway": takeaway,
        "keywords": keywords,
        "url": paper_url,
    }


def _deduplicate(papers: List[Dict]) -> List[Dict]:
    """Deduplicate papers by DOI and title."""
    seen_dois = set()
    seen_titles = set()
    unique = []

    for paper in papers:
        doi = paper.get("doi", "").strip()
        title = paper.get("title", "").strip().lower()

        if doi and doi in seen_dois:
            continue
        if title and title in seen_titles:
            continue

        unique.append(paper)

        if doi:
            seen_dois.add(doi)
        if title:
            seen_titles.add(title)

    return unique


def _save_results_csv(results: List[Dict], output_file: str) -> None:
    """Save search results to CSV."""
    if not results:
        print("  No results to save")
        return

    df = pd.DataFrame(results)

    column_order = [
        "source", "pmid", "doi", "title", "authors", "journal",
        "publication_date", "keywords", "abstract", "takeaway", "url"
    ]
    df = df[[col for col in column_order if col in df.columns]]
    df.to_csv(output_file, index=False, encoding="utf-8")
    print(f"  Saved {len(df)} results to {output_file}")

