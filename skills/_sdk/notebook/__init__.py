"""What a step file uses: read inputs, write outputs, load skills and demo data, run a skill's CLI.

A step is a percent-format Python file in ``analysis/<NN_slug>/``. The
step runner (``run.py`` beside this file) executes it in a fresh kernel and
records every call these functions make; run on its own with
``python analysis/<NN_slug>/<step>.py`` the same calls work without being
recorded.
"""

from __future__ import annotations

from skills._sdk.notebook._io import load_demo, read_input, write_output
from skills._sdk.notebook._skills import load_skill, run_cli

__all__ = ["read_input", "write_output", "load_skill", "load_demo", "run_cli"]
