from __future__ import annotations

import re
from pathlib import Path
import yaml

# Fields that lazy_metadata exposes as properties.  When a v2 sidecar
# (`parameters.yaml`) is present, every field except name/description is read
# from the sidecar; otherwise we fall back to the legacy
# `metadata.omicsclaw` block in the SKILL.md frontmatter.
_RUNTIME_FIELDS = (
    "domain",
    "script",
    "trigger_keywords",
    "allowed_extra_flags",
    "legacy_aliases",
    "saves_h5ad",
    "requires_preprocessed",
    "param_hints",
)

_RUNTIME_DEFAULTS: dict[str, object] = {
    "domain": "",
    "script": "",
    "trigger_keywords": [],
    "allowed_extra_flags": [],
    "legacy_aliases": [],
    "saves_h5ad": False,
    "requires_preprocessed": False,
    "param_hints": {},
}


_GOTCHA_BOLD_LEAD = re.compile(r"^\*\*(.+?)\*\*")
_GOTCHA_PLACEHOLDER = re.compile(r"^_None\b", re.IGNORECASE)


def _extract_gotcha_leads(body: str) -> list[str]:
    """Extract the lead sentence of each `## Gotchas` bullet.

    Reads the body until the next `## ` heading.  Each bullet starts with
    `- ` at the line start (indented continuations are ignored).  The lead
    sentence is the bold-marked first sentence; missing bold falls back to
    the first '. '-terminated sentence.  Italic placeholder bullets like
    `- _None yet — append as failure modes are reported._` are filtered.
    """
    in_section = False
    bullets: list[str] = []
    for line in body.splitlines():
        stripped = line.lstrip()
        if line.startswith("## "):
            if in_section:
                break
            if line.startswith("## Gotchas"):
                in_section = True
            continue
        if not in_section:
            continue
        if not line.startswith("- "):
            continue
        # `- ` at start = new bullet; capture the rest of the line.
        bullets.append(stripped[2:].strip())

    leads: list[str] = []
    for bullet in bullets:
        if _GOTCHA_PLACEHOLDER.match(bullet):
            continue
        m = _GOTCHA_BOLD_LEAD.match(bullet)
        if m:
            leads.append(m.group(1).strip())
            continue
        # Fallback: first sentence on '. ' boundary, else whole bullet.
        first_period = bullet.find(". ")
        if first_period > 0:
            leads.append(bullet[: first_period + 1].strip())
        else:
            leads.append(bullet.rstrip("."))
    return leads


class LazySkillMetadata:
    def __init__(self, skill_path: Path):
        self.path = skill_path
        self._basic = None
        self._full = None
        self._gotchas: list[str] | None = None

    def _parse_frontmatter(self) -> dict | None:
        skill_md = self.path / "SKILL.md"
        if not skill_md.exists():
            return None

        content = skill_md.read_text(encoding="utf-8")
        if not content.startswith("---"):
            return None

        parts = content.split("---", 2)
        if len(parts) < 3:
            return None

        try:
            return yaml.safe_load(parts[1]) or {}
        except yaml.YAMLError:
            return None

    def _load_sidecar(self) -> dict | None:
        sidecar = self.path / "parameters.yaml"
        if not sidecar.exists():
            return None
        try:
            data = yaml.safe_load(sidecar.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            return None
        return data if isinstance(data, dict) else None

    def _load_basic(self):
        # Tolerate missing/malformed frontmatter — the sidecar may still hold
        # the runtime contract.  Identity fields default to safe empties.
        frontmatter = self._parse_frontmatter() or {}
        legacy = (frontmatter.get("metadata") or {}).get("omicsclaw") or {}
        sidecar = self._load_sidecar() or {}

        # Per-field merge: sidecar wins where it speaks, frontmatter fills
        # gaps, defaults backstop both.  A bare YAML key (`field:`) parses to
        # None — treat that as "field absent" so partial migration and
        # null-valued collections do not crash callers.
        runtime: dict[str, object] = {}
        for key in _RUNTIME_FIELDS:
            # `dict.get(missing_key)` already returns None, so this two-step
            # fallthrough handles both "key absent" and "value is None" (bare
            # YAML key) uniformly.
            value = sidecar.get(key)
            if value is None:
                value = legacy.get(key)
            if value is None:
                value = _RUNTIME_DEFAULTS[key]
            runtime[key] = value

        self._basic = {
            "name": frontmatter.get("name", ""),
            "description": frontmatter.get("description", ""),
            **runtime,
        }

    def _ensure_basic(self):
        if self._basic is None:
            self._load_basic()

    @property
    def name(self) -> str:
        self._ensure_basic()
        return self._basic.get("name", "")

    @property
    def description(self) -> str:
        self._ensure_basic()
        return self._basic.get("description", "")

    @property
    def domain(self) -> str:
        self._ensure_basic()
        return self._basic.get("domain", "")

    @property
    def script(self) -> str:
        self._ensure_basic()
        return self._basic.get("script", "")

    @property
    def trigger_keywords(self) -> list[str]:
        self._ensure_basic()
        return self._basic.get("trigger_keywords", [])

    @property
    def allowed_extra_flags(self) -> set[str]:
        self._ensure_basic()
        return set(self._basic.get("allowed_extra_flags", []))

    @property
    def legacy_aliases(self) -> list[str]:
        self._ensure_basic()
        return self._basic.get("legacy_aliases", [])

    @property
    def saves_h5ad(self) -> bool:
        self._ensure_basic()
        return self._basic.get("saves_h5ad", False)

    @property
    def requires_preprocessed(self) -> bool:
        self._ensure_basic()
        return self._basic.get("requires_preprocessed", False)

    @property
    def param_hints(self) -> dict:
        """Method-keyed parameter tuning hints declared in SKILL.md."""
        self._ensure_basic()
        return self._basic.get("param_hints", {})

    @property
    def gotchas(self) -> list[str]:
        """Lead sentences of each `## Gotchas` bullet from SKILL.md body.

        Loaded lazily on first access and cached.  Empty list when SKILL.md
        is missing, has no `## Gotchas` section, or only contains the
        template placeholder.
        """
        if self._gotchas is not None:
            return self._gotchas
        skill_md = self.path / "SKILL.md"
        if not skill_md.exists():
            self._gotchas = []
            return self._gotchas
        content = skill_md.read_text(encoding="utf-8")
        # Strip frontmatter so `## ` matching only operates on the body.
        if content.startswith("---"):
            parts = content.split("---", 2)
            body = parts[2] if len(parts) >= 3 else content
        else:
            body = content
        self._gotchas = _extract_gotcha_leads(body)
        return self._gotchas

    def _load_full(self):
        skill_md = self.path / "SKILL.md"
        if not skill_md.exists():
            self._full = {}
            return

        content = skill_md.read_text(encoding="utf-8")
        if not content.startswith("---"):
            self._full = {}
            return

        parts = content.split("---", 2)
        if len(parts) < 3:
            self._full = {}
            return

        try:
            self._full = yaml.safe_load(parts[1])
        except yaml.YAMLError:
            self._full = {}

    def get_full(self) -> dict:
        if self._full is None:
            self._load_full()
        return self._full
