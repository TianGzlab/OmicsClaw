"""One spelling list for "this module reads the command line or the environment".

``tests/entry/test_config.py`` and ``tests/launch/test_launch_is_above_entry.py``
enforce the same rule on two neighbouring packages, and until plan 0037's
review they did it with two verbatim copies of the same three-needle loop.
That is a family weakness rather than two bugs: a spelling the rule does not
know about is invisible to *both* copies at once, and the review found three
of them —— the most embarrassing being ``from os import environ``, which reads
the environment without ever writing the word ``os.environ``.

The list lives here so that widening it is one edit, and so that the two
rules cannot drift into disagreeing about what the rule is.

**Why a source scan at all.** The property is about modules that do not exist
yet: a session, turn or adapter module added tomorrow inherits the rule the
moment it is written, which no mock of today's modules can express. The
behavioural half —— what is actually in :data:`sys.modules` after the code has
run —— lives next to each source scan and is what catches a read that arrives
through a helper in another package.
"""

from __future__ import annotations

import pathlib

FORBIDDEN_SPELLINGS = (
    "os.environ",
    "os.getenv",
    "sys.argv",
    "from os import",
    "from sys import",
    "environb",
)
"""Every way a module can name a process global, including the indirect ones.

``from os import`` and ``from sys import`` are blunt on purpose. They also
refuse ``from os import pathsep``, which is harmless —— and refusing a
harmless spelling costs one word (``import os``) while allowing the family
costs the rule. ``environb`` is the bytes-valued twin of ``os.environ`` and is
reachable as ``posix.environb`` without the word ``os`` appearing at all.

The needles are matched against the **whole file, prose included**. That is
deliberate: after plan 0037 these packages genuinely do not touch either
global, so a docstring that says they do is wrong rather than merely
untested.
"""


def offending_sources(
    root: pathlib.Path, *, exempt: tuple[str, ...] = ()
) -> list[str]:
    """``"<file>:<spelling>"`` for every hit under *root*.

    *exempt* is matched against the file name, and every caller that has
    one asserts separately that it is empty —— an exemption list is the
    only way this rule degrades, so it has to be visible rather than
    folded into a condition inside the loop.
    """
    offenders: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if path.name in exempt:
            continue
        source = path.read_text(encoding="utf-8")
        for needle in FORBIDDEN_SPELLINGS:
            if needle in source:
                offenders.append(f"{path.name}:{needle}")
    return offenders
