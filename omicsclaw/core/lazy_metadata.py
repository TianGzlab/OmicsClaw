from __future__ import annotations

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


class LazySkillMetadata:
    def __init__(self, skill_path: Path):
        self.path = skill_path
        self._basic = None
        self._full = None

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
