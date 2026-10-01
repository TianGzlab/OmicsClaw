"""The step runner: run a project's analysis modules and record what they did.

Call it from the project root (the folder holding ``analysis/`` and
``results/``)::

    python <skills>/_sdk/notebook/run.py new clustering
    python <skills>/_sdk/notebook/run.py run analysis/03_clustering
    python <skills>/_sdk/notebook/run.py status
    python <skills>/_sdk/notebook/run.py replay analysis/03_clustering
    python <skills>/_sdk/notebook/run.py accept analysis/03_clustering --review results/03_clustering/reviews/2026-10-01_review.md

Locks are ``fcntl.flock`` files inside ``results/``; they do not exclude
reliably across network filesystems or Docker Desktop's macOS file sharing.
``run`` and ``replay`` run in the foreground only: they stop, killing the
running kernel and releasing the lock, once the process that started them
exits, including a shell that put them in the background.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

STARTED_UNDER = (os.getppid(), os.getpgrp())
"""Parent process and process group at start-up, read before anything slow, for the watchdog."""

if sys.path and Path(sys.path[0] or ".").resolve() == Path(__file__).resolve().parent:
    sys.path.pop(0)

_SDK_ANCHOR = next(
    (p for p in Path(__file__).resolve().parents if (p / "skills" / "_sdk" / "__init__.py").is_file()),
    None,
)
if _SDK_ANCHOR is not None and str(_SDK_ANCHOR) not in sys.path:
    sys.path.insert(0, str(_SDK_ANCHOR))

from skills._sdk.notebook import _acceptance, _executor, _layout, _watchdog  # noqa: E402


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

    replay = commands.add_parser("replay", help="rerun every step of a module from scratch, validate last")
    replay.add_argument("target", metavar="module", help="analysis/<NN_slug>")
    replay.add_argument("--new-interpreter", metavar="REASON",
                        help="replay with this interpreter although the module was run with another")
    replay.add_argument("--wait", type=float, default=0.0, metavar="SECONDS", help="wait this long for a busy module")

    accept = commands.add_parser("accept", help="record the user's acceptance and freeze the module")
    accept.add_argument("target", metavar="module", help="analysis/<NN_slug>")
    how = accept.add_mutually_exclusive_group(required=True)
    how.add_argument("--review", metavar="FILE", help="the approving review in results/<NN_slug>/reviews/")
    how.add_argument("--skip-review", metavar="WORDS", help="the user's words asking to skip the review")
    accept.add_argument("--wait", type=float, default=0.0, metavar="SECONDS", help="wait this long for a busy module")

    revise = commands.add_parser("revise", help="snapshot an accepted module into baseline/ so it can change")
    revise.add_argument("target", metavar="module", help="analysis/<NN_slug>")
    revise.add_argument("--wait", type=float, default=0.0, metavar="SECONDS", help="wait this long for a busy module")

    api = commands.add_parser("api", help="check or rewrite the generated ## API section of a skill's SKILL.md")
    api.add_argument("skill_dir", metavar="skill-dir", help="the skill's directory, or its name")
    mode = api.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="exit 1 when the section does not match _api.py")
    mode.add_argument("--write", action="store_true", help="regenerate the section from _api.py")
    return parser


def _api(skill: str, *, write: bool) -> int:
    from skills._sdk.notebook import _apidoc, _skills

    path = Path(skill)
    if not path.is_dir():
        try:
            path = _skills.skill_dir(skill)
        except LookupError as exc:
            print(exc)
            return 2
    try:
        if write:
            changed = _apidoc.write(path)
            print(f"{path / 'SKILL.md'}: API section {'rewritten' if changed else 'already current'}")
            return 0
        problems = _apidoc.check(path)
    except _apidoc.ApiError as exc:
        print(exc)
        return 1
    for problem in problems:
        print(f"{path.name}: {problem}")
    if not problems:
        print(f"{path.name}: API section matches _api.py")
    return 1 if problems else 0


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
        _watchdog.watch_parent(*STARTED_UNDER)
        return _executor.run_targets(_root(args.targets[0]), args.targets, force=args.force, wait=args.wait)
    if args.command == "status":
        return _executor.status(_root(args.target), args.target)
    if args.command == "replay":
        _watchdog.watch_parent(*STARTED_UNDER)
        return _executor.replay(_root(args.target), args.target, new_interpreter=args.new_interpreter, wait=args.wait)
    if args.command == "accept":
        return _acceptance.accept(_root(args.target), args.target, review=args.review,
                                  skip_review=args.skip_review, wait=args.wait)
    if args.command == "revise":
        return _acceptance.revise(_root(args.target), args.target, wait=args.wait)
    if args.command == "api":
        return _api(args.skill_dir, write=args.write)
    raise AssertionError(args.command)


if __name__ == "__main__":
    sys.exit(main())
