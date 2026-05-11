#!/usr/bin/env python3
"""Extract negative routing eval cases from SKILL.md Skip-when clauses.

ADR 2026-05-11: every `Skip when X — use sibling-skill instead` clause is
a negative case for the host skill AND a positive case for the sibling.
Extraction runs at write-time via LLM; the snapshot is committed and
read by `tests/test_routing_skip_when.py` for deterministic CI.

Usage:
    python scripts/extract_skip_when_cases.py \\
        --domain spatial \\
        --output tests/eval/skip_when_cases.json

    # Dry-run (no LLM key required) — emits stub snapshot showing schema
    python scripts/extract_skip_when_cases.py --domain spatial --stub

The model is pinned in pyproject.toml [tool.omicsclaw.eval]; bumping it
is a PR with a re-extracted snapshot diff for human review.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Project root on path so we can import omicsclaw.* without install.
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

try:
    import tomllib  # py311+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

import yaml

LOGGER = logging.getLogger("extract_skip_when_cases")


# --------------------------------------------------------------------------- #
# Snapshot schema
# --------------------------------------------------------------------------- #

SNAPSHOT_SCHEMA_VERSION = 1


@dataclass
class SkillEntry:
    skill: str
    description: str
    description_hash: str


def _hash_description(description: str) -> str:
    normalised = " ".join(description.split())
    return "sha256:" + hashlib.sha256(normalised.encode("utf-8")).hexdigest()[:32]


# --------------------------------------------------------------------------- #
# SKILL.md discovery
# --------------------------------------------------------------------------- #

def _load_skill_entries(domain: str) -> list[SkillEntry]:
    domain_dir = _ROOT / "skills" / domain
    if not domain_dir.exists():
        raise FileNotFoundError(f"Domain dir not found: {domain_dir}")

    entries: list[SkillEntry] = []
    for skill_md in sorted(domain_dir.rglob("SKILL.md")):
        # Discover every SKILL.md under the domain dir.  Some domains
        # (e.g. literature) keep a single SKILL.md at the domain root
        # rather than nested in per-skill subdirs; those must be picked
        # up, not skipped.  Domain-level INDEX files are .md without the
        # SKILL prefix so they are not confused with skills.
        text = skill_md.read_text(encoding="utf-8")
        if not text.startswith("---"):
            continue
        parts = text.split("---", 2)
        if len(parts) < 3:
            continue
        try:
            frontmatter = yaml.safe_load(parts[1]) or {}
        except yaml.YAMLError:
            continue
        description = str(frontmatter.get("description", "") or "").strip()
        skill_name = str(frontmatter.get("name", "") or skill_md.parent.name).strip()
        if not description:
            continue
        entries.append(SkillEntry(
            skill=skill_name,
            description=description,
            description_hash=_hash_description(description),
        ))
    return entries


# --------------------------------------------------------------------------- #
# LLM extractor
# --------------------------------------------------------------------------- #

_EXTRACTION_PROMPT = """\
You extract structured routing-eval cases from a skill description.

The description follows this contract:
  "Load when <intent>. Skip when <off-target X> (use sibling-skill) [or ...]."

Your job: enumerate every (off-target trigger, sibling skill) pair from the
Skip-when clauses, and synthesise a realistic natural-language user query
that exhibits that off-target trigger.

Skill name: {skill}
Skill description:
{description}

Valid sibling skill names (use EXACTLY one of these per case; never invent):
{valid_skills}

Output ONLY a JSON array (no markdown fence, no prose).  Each element:
{{
  "trigger": "<realistic user query that should NOT route to {skill}>",
  "must_not_pick": "{skill}",
  "expected_pick": "<one of the valid sibling names above>"
}}

Rules:
- Generate ONE case per (trigger, sibling) pair from Skip-when.  If Skip-when
  is a hard precondition with NO sibling (e.g. "Skip when var[chromosome] is
  missing"), emit:
  {{"trigger": "...", "must_not_pick": "{skill}", "expected_pick": null}}
- Make triggers concrete and varied (different phrasings users actually type),
  not paraphrases of the description.
- 3-12 words per trigger, no quotes inside the trigger string.
- If the description has no Skip-when clause, output exactly: []
"""


def _resolve_llm_config(model_override: str | None) -> tuple[str, str, str]:
    """Reuse the project's provider registry to resolve API key/url/model."""
    from omicsclaw.core.provider_registry import resolve_provider
    base_url, model, api_key = resolve_provider(
        provider=os.getenv("LLM_PROVIDER", ""),
        base_url=os.getenv("LLM_BASE_URL", ""),
        model=model_override or os.getenv("OMICSCLAW_MODEL") or os.getenv("LLM_MODEL", ""),
        api_key=os.getenv("LLM_API_KEY", ""),
    )
    return api_key, (base_url or "https://api.openai.com/v1"), (model or "")


def _call_llm(prompt: str, *, api_key: str, base_url: str, model: str, temperature: float) -> str:
    import requests
    url = f"{base_url.rstrip('/')}/chat/completions"
    response = requests.post(
        url,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def _parse_llm_json(raw: str) -> list[dict[str, Any]]:
    text = raw.strip()
    if text.startswith("```"):
        # tolerate a fenced block ``` ... ```
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip("\n").strip("`").strip()
    return json.loads(text)


def _extract_for_skill(
    entry: SkillEntry,
    *,
    valid_skill_names: list[str],
    llm_config: tuple[str, str, str],
    temperature: float,
) -> dict[str, Any]:
    """Extract Skip-when cases for one skill.

    Return shape::

        {"cases": list[dict], "extraction_failed": bool, "error": str | None}

    A failure (LLM returned non-JSON) is recorded with ``extraction_failed=true``
    and an empty ``cases`` list — distinct from a real "no Skip-when clauses"
    skill, which yields ``extraction_failed=false`` and an empty ``cases`` list.
    The drift test inspects ``extraction_failed`` so reviewers see failures
    instead of them silently masquerading as "no negative cases".
    """
    prompt = _EXTRACTION_PROMPT.format(
        skill=entry.skill,
        description=entry.description,
        valid_skills="\n".join(f"  - {s}" for s in sorted(valid_skill_names) if s != entry.skill),
    )
    api_key, base_url, model = llm_config
    if not api_key:
        raise RuntimeError(
            "LLM_API_KEY not set.  Set it, or run with --stub to emit a "
            "schema-only snapshot."
        )
    raw = _call_llm(prompt, api_key=api_key, base_url=base_url, model=model, temperature=temperature)
    try:
        cases = _parse_llm_json(raw)
    except json.JSONDecodeError as exc:
        LOGGER.error("LLM returned non-JSON for %s: %s\nraw: %s", entry.skill, exc, raw[:500])
        return {
            "cases": [],
            "extraction_failed": True,
            "error": f"json_decode_error: {exc}",
        }
    # Light validation — discard cases that name an unknown sibling.
    cleaned: list[dict[str, Any]] = []
    for c in cases:
        if not isinstance(c, dict):
            continue
        trigger = str(c.get("trigger", "") or "").strip()
        expected = c.get("expected_pick")
        if not trigger:
            continue
        if expected is not None and expected not in valid_skill_names:
            LOGGER.warning(
                "[%s] LLM proposed sibling %r not in valid list — dropping",
                entry.skill, expected,
            )
            continue
        cleaned.append({
            "trigger": trigger,
            "must_not_pick": entry.skill,
            "expected_pick": expected,
        })
    return {"cases": cleaned, "extraction_failed": False, "error": None}


# --------------------------------------------------------------------------- #
# Snapshot emission
# --------------------------------------------------------------------------- #

def _read_eval_config() -> dict[str, Any]:
    with (_ROOT / "pyproject.toml").open("rb") as f:
        data = tomllib.load(f)
    return data.get("tool", {}).get("omicsclaw", {}).get("eval", {})


def _write_snapshot(
    output_path: Path,
    *,
    domain: str,
    entries: list[SkillEntry],
    results_by_skill: dict[str, dict[str, Any]],
    model: str,
    schema_version: int,
) -> None:
    """Write the eval snapshot.

    ``results_by_skill`` maps skill name to the dict returned by
    ``_extract_for_skill`` — keys are ``cases`` (list), ``extraction_failed``
    (bool), ``error`` (str | None).  Both flags are surfaced at snapshot
    top level so the drift test and any operator-facing tools can see
    failures without parsing nested structure.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    def _skill_entry(e: SkillEntry) -> dict[str, Any]:
        result = results_by_skill.get(e.skill) or {}
        entry: dict[str, Any] = {
            "skill": e.skill,
            "description_hash": e.description_hash,
            "cases": result.get("cases", []),
        }
        if result.get("extraction_failed"):
            entry["extraction_failed"] = True
            entry["error"] = result.get("error", "unknown")
        return entry

    snapshot = {
        "schema_version": schema_version,
        "domain": domain,
        "model": model,
        "extracted_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "skills": [_skill_entry(e) for e in entries],
    }
    output_path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _emit_stub_snapshot(
    output_path: Path,
    *,
    domain: str,
    entries: list[SkillEntry],
    model: str,
    schema_version: int,
) -> None:
    """Emit a snapshot with empty cases lists — shows the schema without
    requiring an LLM call.  Operators run this when scaffolding the file
    or running offline."""
    results_by_skill = {
        e.skill: {"cases": [], "extraction_failed": False, "error": None}
        for e in entries
    }
    _write_snapshot(
        output_path,
        domain=domain,
        entries=entries,
        results_by_skill=results_by_skill,
        model=f"{model} (STUB — set LLM_API_KEY and re-run to populate)",
        schema_version=schema_version,
    )


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", required=True, help="Domain to extract (e.g. spatial)")
    parser.add_argument(
        "--output",
        type=Path,
        default=_ROOT / "tests" / "eval" / "skip_when_cases.json",
    )
    parser.add_argument(
        "--stub",
        action="store_true",
        help="Emit an empty-cases snapshot showing the schema without calling the LLM",
    )
    parser.add_argument(
        "--only",
        nargs="*",
        default=None,
        help="Restrict extraction to these skill names (debug aid)",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    cfg = _read_eval_config()
    model = str(cfg.get("skip_when_extractor_model", "claude-haiku-4-5-20251001"))
    temperature = float(cfg.get("skip_when_extractor_temperature", 0.0))
    schema_version = int(cfg.get("skip_when_snapshot_schema_version", SNAPSHOT_SCHEMA_VERSION))

    entries = _load_skill_entries(args.domain)
    if args.only:
        entries = [e for e in entries if e.skill in set(args.only)]
    LOGGER.info("Loaded %d skill descriptions from domain=%s", len(entries), args.domain)

    if args.stub:
        _emit_stub_snapshot(
            args.output,
            domain=args.domain,
            entries=entries,
            model=model,
            schema_version=schema_version,
        )
        LOGGER.info("Wrote STUB snapshot to %s", args.output)
        return 0

    # Real extraction — need API key.
    valid_names = [e.skill for e in entries]
    llm_cfg = _resolve_llm_config(model)
    results_by_skill: dict[str, dict[str, Any]] = {}
    for i, entry in enumerate(entries, 1):
        LOGGER.info("[%d/%d] extracting for %s", i, len(entries), entry.skill)
        try:
            result = _extract_for_skill(
                entry,
                valid_skill_names=valid_names,
                llm_config=llm_cfg,
                temperature=temperature,
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.error("Extraction failed for %s: %s", entry.skill, exc)
            result = {"cases": [], "extraction_failed": True, "error": str(exc)}
        results_by_skill[entry.skill] = result

    _write_snapshot(
        args.output,
        domain=args.domain,
        entries=entries,
        results_by_skill=results_by_skill,
        model=model,
        schema_version=schema_version,
    )
    total_cases = sum(len(r.get("cases", [])) for r in results_by_skill.values())
    failed = sum(1 for r in results_by_skill.values() if r.get("extraction_failed"))
    LOGGER.info(
        "Wrote snapshot to %s: %d skills, %d cases total (avg %.1f / skill)",
        args.output, len(entries), total_cases,
        (total_cases / len(entries)) if entries else 0.0,
    )
    if failed:
        LOGGER.warning(
            "%d skill(s) had extraction_failed=true — review snapshot before commit",
            failed,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
