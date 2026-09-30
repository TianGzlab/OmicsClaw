"""consensus-domains — thin shim over the generic consensus entry (ADR 0016).

All orchestration (fan-out, scoring, BC selection, operator, report) lives in
``omicsclaw.runtime.consensus.run``; this binds the flavour name so ``run_skill``
and the CLI can invoke it. See ``CONSENSUS_SOURCES["consensus-domains"]`` for the
declarative contract.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Bootstrap sys.path so `omicsclaw` resolves on direct invocation
# (`python consensus_domains.py --help`) without an editable install.
_SDK_ANCHOR = next(
    (p for p in Path(__file__).resolve().parents if (p / "skills" / "_sdk" / "__init__.py").is_file()),
    None,
)
if _SDK_ANCHOR is not None and str(_SDK_ANCHOR) not in sys.path:
    sys.path.insert(0, str(_SDK_ANCHOR))

from omicsclaw.runtime.consensus.run import main as _run_main  # noqa: E402

SKILL_NAME = "consensus-domains"
SKILL_VERSION = "0.1.0"
SOURCE = "consensus-domains"


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    return _run_main(["--source", SOURCE, *argv])


if __name__ == "__main__":
    raise SystemExit(main())
