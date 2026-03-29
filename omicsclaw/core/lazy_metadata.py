from __future__ import annotations

from pathlib import Path
import yaml

class LazySkillMetadata:
    def __init__(self, skill_path: Path):
        self.path = skill_path
        self._basic = None
        self._full = None

    def _load_basic(self):
        skill_md = self.path / "SKILL.md"
        if not skill_md.exists():
            self._basic = {}
            return

        content = skill_md.read_text(encoding="utf-8")
        if not content.startswith("---"):
            self._basic = {}
            return

        parts = content.split("---", 2)
        if len(parts) < 3:
            self._basic = {}
            return

        try:
            frontmatter = yaml.safe_load(parts[1])
            omicsclaw_meta = frontmatter.get("metadata", {}).get("omicsclaw", {})
            self._basic = {
                "name": frontmatter.get("name", ""),
                "description": frontmatter.get("description", ""),
                "domain": omicsclaw_meta.get("domain", ""),
                "trigger_keywords": omicsclaw_meta.get("trigger_keywords", []),
                "allowed_extra_flags": omicsclaw_meta.get("allowed_extra_flags", []),
                "legacy_aliases": omicsclaw_meta.get("legacy_aliases", []),
                "saves_h5ad": omicsclaw_meta.get("saves_h5ad", False),
                "requires_preprocessed": omicsclaw_meta.get("requires_preprocessed", False),
                "param_hints": omicsclaw_meta.get("param_hints", {}),
            }
        except yaml.YAMLError:
            self._basic = {}

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
