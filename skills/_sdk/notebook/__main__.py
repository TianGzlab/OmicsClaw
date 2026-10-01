"""``python -m skills._sdk.notebook <subcommand>``: the step runner."""

from __future__ import annotations

import sys

from skills._sdk.notebook.run import main

sys.exit(main())
