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
            self._basic = {
                "name": frontmatter.get("name", ""),
                "description": frontmatter.get("description", ""),
                "domain": frontmatter.get("metadata", {}).get("omicsclaw", {}).get("domain", ""),
            }
        except yaml.YAMLError:
            self._basic = {}

    @property
    def name(self) -> str:
        if self._basic is None:
            self._load_basic()
        return self._basic.get("name", "")

    @property
    def description(self) -> str:
        if self._basic is None:
            self._load_basic()
        return self._basic.get("description", "")

    @property
    def domain(self) -> str:
        if self._basic is None:
            self._load_basic()
        return self._basic.get("domain", "")

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
