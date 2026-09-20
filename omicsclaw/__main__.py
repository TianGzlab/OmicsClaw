"""``python -m omicsclaw`` —— the same shell the console scripts reach.

Repointed from ``omicsclaw.surfaces.cli.launcher`` on the owner's ruling
(2026-09-20). That target has been unimportable since ``omicsclaw/skill/``
was deleted, so this file raised :exc:`ModuleNotFoundError` for every
invocation; the argument for leaving it to the migration that deletes
``omicsclaw/surfaces/`` did not survive the observation that plan 0037's
second wave already repoints ``omicsclaw.py`` and ``[project.scripts]`` at
this shell. One of six ways in staying broken is not a smaller change, it
is a worse one —— and this is the way a reader guesses at first.

Three lines rather than a re-export: :func:`omicsclaw.launch.main`
returns an exit code and raises nothing, so the process boundary is
``raise SystemExit`` and belongs here.
"""

from omicsclaw.launch import main

if __name__ == "__main__":
    raise SystemExit(main())
