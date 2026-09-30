"""``skills/<domain>/INDEX.md`` against the corpus it describes.

Each domain keeps an index file. With ``skills_index=full`` the system
prompt already carries every skill's description, so these are for a
human reading the repository; with ``skills_index=compact`` the prompt
carries domain names only and the model is pointed at them for detail.
Either way a stale one is worse than none, because it is read as current.

They used to be written by ``scripts/generate_domain_index.py``, which
imported the deleted ``omicsclaw.skill`` and has not run since. By the
time this test was written they had drifted: ``bulkrna-cosinor-rhythm``
was missing outright and seven skills listed a truncated set of
triggers. A generator nobody runs is how that happens, so the check is a
test rather than a script — drift fails here instead of ageing quietly.

Only the ``## Skills`` section and the count line are derived. The prose
above them — the title, the domain key, the primary data types, the
one-paragraph blurb — is written by hand and left alone.

Regenerate after adding or editing a skill::

    OMICSCLAW_WRITE_SKILL_INDEX=1 pytest tests/skills/test_domain_index_is_current.py
"""

from __future__ import annotations

import os
import pathlib

import pytest

from omicsclaw.skills import Skill, SkillIndex, load_skills

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SKILLS_ROOT = REPO_ROOT / "skills"

HEADING = "## Skills"
ANCHOR = f"\n{HEADING}\n"
"""The heading as it appears in the file — at the start of its own line.

Matched this way rather than by substring so that prose above it may
name the section without the split landing inside the sentence.
"""

COUNT_PREFIX = "**Skill count:**"
WRITE_ENV = "OMICSCLAW_WRITE_SKILL_INDEX"

pytestmark = pytest.mark.skipif(
    not SKILLS_ROOT.is_dir(), reason="the skills corpus is not present"
)


def index_files() -> list[pathlib.Path]:
    """Every ``skills/<domain>/INDEX.md``, found without the loader."""
    if not SKILLS_ROOT.is_dir():
        return []
    return sorted(SKILLS_ROOT.glob("*/INDEX.md"))


def render(skills: tuple[Skill, ...]) -> str:
    """The ``## Skills`` section for *skills*, ordered by name.

    One bullet per skill carrying the description the model routes on,
    and an indented ``triggers:`` line for the skills that declare any —
    omitted rather than left empty for the ones that do not.
    """
    lines = [HEADING, ""]
    for skill in sorted(skills, key=lambda item: item.name):
        lines.append(f"- `{skill.name}` — {skill.description}")
        if skill.triggers:
            lines.append(f"  triggers: {', '.join(skill.triggers)}")
    return "\n".join(lines) + "\n"


def expected(path: pathlib.Path, index: SkillIndex) -> str:
    """What *path* should hold: its own prose, then the derived section."""
    domain = path.parent.name
    skills = tuple(skill for skill in index.skills if skill.domain == domain)
    current = path.read_text(encoding="utf-8")

    head, sep, _ = current.partition(ANCHOR)
    assert sep, f"{path} has no {HEADING!r} heading on a line of its own"

    preamble = "\n".join(
        f"{COUNT_PREFIX} {len(skills)}"
        if line.startswith(COUNT_PREFIX)
        else line
        for line in head.split("\n")
    )
    return f"{preamble}\n" + render(skills)


@pytest.fixture(scope="module")
def corpus() -> SkillIndex:
    return load_skills(SKILLS_ROOT)


def test_every_domain_directory_has_an_index(corpus: SkillIndex):
    """A domain the loader found but no index describes is a gap."""
    documented = {path.parent.name for path in index_files()}
    indexed = {skill.domain for skill in corpus.skills if skill.domain}

    assert indexed == documented


@pytest.mark.parametrize(
    "path", index_files(), ids=lambda path: path.parent.name
)
def test_the_index_matches_the_skills_on_disk(path: pathlib.Path, corpus: SkillIndex):
    """The listed skills, descriptions, triggers and count are the real ones."""
    want = expected(path, corpus)

    if os.environ.get(WRITE_ENV):
        path.write_text(want, encoding="utf-8")

    assert path.read_text(encoding="utf-8") == want, (
        f"{path.relative_to(REPO_ROOT)} has drifted from the SKILL.md headers; "
        f"regenerate with {WRITE_ENV}=1 pytest {pathlib.Path(__file__).name}"
    )
