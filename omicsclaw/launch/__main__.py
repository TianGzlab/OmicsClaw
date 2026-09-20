"""``python -m omicsclaw.launch`` —— the process, in three lines.

The console scripts ``oc`` and ``omicsclaw`` call
:func:`omicsclaw.launch.main` directly; this module exists so the same
command is reachable from a source checkout with nothing installed,
which is how this repository's own tests run it.

``omicsclaw/__main__.py`` reaches the same :func:`~omicsclaw.launch.main`
and is the spelling a reader guesses first; it was repointed here from
the legacy launcher on the owner's ruling (2026-09-20). Both are listed
in ``tests/launch/test_grammar.py``'s ``MODULE_GUARDS`` with a reason, so
a third one cannot appear without that test going red.
"""

from omicsclaw.launch import main

if __name__ == "__main__":
    raise SystemExit(main())
