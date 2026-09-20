#!/usr/bin/env python3
"""Repo-root entrypoint for the OmicsClaw CLI.

The CLI body lives in ``omicsclaw/launch/`` so that it ships inside the
installed package and the ``omicsclaw`` / ``oc`` console scripts work from
anywhere — under a pip install, an npm install, or the OmicsClaw-App bundled
runtime. This file stays behind for two reasons:

1. **Ergonomics.** ``python omicsclaw.py <args>`` keeps working in a source
   checkout, which is what the README, the docs, and a decade of muscle memory
   use.
2. **It is the source-checkout sentinel.** Several places key off this file's
   *existence* next to the ``omicsclaw/`` package to decide "is this a real
   checkout, or site-packages?" — see
   ``omicsclaw.common.workspace.resolve_omicsclaw_dir`` (step 2) and
   ``OmicsClaw-App/electron/python-env.ts`` (``isOmicsClawSourceCheckout``).
   A module named ``omicsclaw`` can never be importable — it would collide with
   the package — so the file only ever exists in a checkout, which is exactly
   what makes it a reliable marker. Do not delete it.

   Its docstring used to list two more consumers,
   ``omicsclaw/execution/executors/default.py`` (``_ENTRY_POINT``) and
   ``omicsclaw.runtime.agent.state`` (``OMICSCLAW_PY``). Both files were
   deleted with the old architecture; verified absent 2026-09-20 (plan 0037
   §1.4-1). The sentinel conclusion is unchanged — it simply has two
   consumers, not four.

Note that ``import omicsclaw`` resolves to the *package*, not this file:
Python's finder prefers a directory package over a same-named module within the
same ``sys.path`` entry.
"""

from __future__ import annotations

from omicsclaw.launch import main

if __name__ == "__main__":
    raise SystemExit(main())
