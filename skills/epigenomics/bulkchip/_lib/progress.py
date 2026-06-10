"""Live step-progress to the controlling terminal.

The OmicsClaw runner launches each skill with its stdout/stderr piped and
— unless the CLI passes streaming callbacks — only displays that output
once the skill process exits. Long steps (reference downloads, alignment)
therefore look frozen while they run.

``tty_write`` sidesteps the pipe by writing straight to ``/dev/tty`` — the
controlling terminal — so step markers appear live regardless of how the
parent runner buffers the piped stdout. When there is no controlling
terminal (CI, redirected output, no TTY) it reports failure so the caller
can fall back to ordinary ``print`` and the line is never silently lost.

stdlib-only, so it stays import-safe in the lightweight agent env as well
as the ``omicsclaw_bulkchip`` sub-env.
"""
from __future__ import annotations


def _open_tty():
    """Open the controlling terminal for writing, or return None."""
    try:
        return open("/dev/tty", "w")  # noqa: SIM115 — kept open for process lifetime
    except OSError:
        return None


# Opened once at import and reused for every write; None when the process
# has no controlling terminal.
_TTY = _open_tty()


def tty_write(msg: str) -> bool:
    """Write *msg* (one logical line, may be multi-line) to the terminal.

    Returns True if it reached a terminal, False otherwise — letting the
    caller fall back to stdout.
    """
    if _TTY is None:
        return False
    try:
        _TTY.write(msg + "\n")
        _TTY.flush()
        return True
    except OSError:
        return False
