"""The step runner: run a project's analysis modules and record what they did.

Call it from the project root (the folder holding ``analysis/`` and
``results/``)::

    python <skills>/_sdk/notebook/run.py new clustering
    python <skills>/_sdk/notebook/run.py run analysis/03_clustering
    python <skills>/_sdk/notebook/run.py status

Locks are ``fcntl.flock`` files inside ``results/``; they do not exclude
reliably across network filesystems or Docker Desktop's macOS file sharing.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if sys.path and Path(sys.path[0] or ".").resolve() == Path(__file__).resolve().parent:
    sys.path.pop(0)

_SDK_ANCHOR = next(
    (p for p in Path(__file__).resolve().parents if (p / "skills" / "_sdk" / "__init__.py").is_file()),
    None,
)
if _SDK_ANCHOR is not None and str(_SDK_ANCHOR) not in sys.path:
    sys.path.insert(0, str(_SDK_ANCHOR))

from skills._sdk.notebook import _executor, _layout  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run.py",
        description="Run the steps of a project's analysis modules and record their inputs, outputs and skill calls.",
        epilog="Exit codes: 0 ok, 1 a step failed, 2 cannot run as asked, 3 the module is locked, "
               "4 accept conditions not met. Module locks use fcntl.flock, which may not exclude "
               "across network filesystems or Docker Desktop's macOS file sharing.",
    )
    commands = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    new = commands.add_parser("new", help="create the next module (and any missing project folders)")
    new.add_argument("slug", help="short lowercase name, for example clustering")

    run = commands.add_parser("run", help="run a module's stale steps, or the given step files")
    run.add_argument("targets", nargs="+", metavar="target", help="analysis/<NN_slug> or a step file in it")
    run.add_argument("--force", action="store_true", help="run even the steps that are up to date")
    run.add_argument("--wait", type=float, default=0.0, metavar="SECONDS", help="wait this long for a busy module")

    status = commands.add_parser("status", help="show every module's status and stale steps")
    status.add_argument("target", nargs="?", help="one module; default: all of them")
    return parser


def _root(target: str | None) -> Path:
    """The project root: the folder above ``analysis/`` or ``results/`` in *target*, else the working directory."""
    if target:
        found = _layout.project_root_of(target)
        if found is not None:
            return found
    return Path.cwd()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "new":
        return _executor.new_module(Path.cwd(), args.slug)
    if args.command == "run":
        return _executor.run_targets(_root(args.targets[0]), args.targets, force=args.force, wait=args.wait)
    if args.command == "status":
        return _executor.status(_root(args.target), args.target)
    raise AssertionError(args.command)


if __name__ == "__main__":
    sys.exit(main())
