"""Isolated sandbox workspace for harness evolution.

The harness loop must never mutate the user's source worktree while a trial
is still provisional. This module snapshots the current repository into an
isolated git repo under the run output directory, then evaluates each trial in
its own temporary git worktree. Accepted patches are committed inside the
sandbox repo, exported as patch artifacts, and can be promoted back to the
source tree in a controlled final step.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from omicsclaw.autoagent.edit_surface import EditSurface
from omicsclaw.autoagent.patch_engine import PatchPlan

logger = logging.getLogger(__name__)

_IGNORED_TOP_LEVEL_DIRS = {
    # VCS / caches
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".nox",
    ".tox",
    ".venv",
    "__pycache__",
    # Build / output artifacts
    "build",
    "output",
    "workspace",
    # Large data & non-code directories — these are never part of the
    # editable surface and copying them would take hours on big projects.
    "data",
    "examples",
    "frontend",
    "website",
    ".benchmarks",
    "node_modules",
    ".claude",
}
_IGNORED_NAMES = {".DS_Store"}


@dataclass
class AcceptedPatchRecord:
    """Durable metadata for a patch that was kept by the harness."""

    iteration: int
    commit_hash: str
    parent_commit: str
    artifact_path: str
    manifest_path: str
    modified_files: list[str] = field(default_factory=list)
    reasoning: str = ""
    diff_summary: str = ""
    description: str = ""
    expected_improvements: list[str] = field(default_factory=list)
    rollback_conditions: list[str] = field(default_factory=list)
    sandbox_repo: str = ""
    sandbox_worktree: str = ""
    source_project_commit: str = ""
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "iteration": self.iteration,
            "commit_hash": self.commit_hash,
            "parent_commit": self.parent_commit,
            "artifact_path": self.artifact_path,
            "manifest_path": self.manifest_path,
            "modified_files": list(self.modified_files),
            "reasoning": self.reasoning,
            "diff_summary": self.diff_summary,
            "description": self.description,
            "expected_improvements": list(self.expected_improvements),
            "rollback_conditions": list(self.rollback_conditions),
            "sandbox_repo": self.sandbox_repo,
            "sandbox_worktree": self.sandbox_worktree,
            "source_project_commit": self.source_project_commit,
            "timestamp": self.timestamp,
        }


@dataclass
class PromotionResult:
    """Outcome of promoting the accepted sandbox state to the source tree."""

    status: str
    message: str = ""
    promoted_files: list[str] = field(default_factory=list)
    blocked_files: list[str] = field(default_factory=list)
    journal_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "message": self.message,
            "promoted_files": list(self.promoted_files),
            "blocked_files": list(self.blocked_files),
            "journal_path": self.journal_path,
        }


class HarnessWorkspace:
    """Isolated snapshot repo that backs harness evolution trials."""

    def __init__(self, source_project_root: Path, output_root: Path) -> None:
        self.source_project_root = Path(source_project_root).expanduser().resolve()
        self.output_root = Path(output_root).expanduser().resolve()
        self.repo_root = self.output_root / "sandbox_repo"
        self.worktrees_root = self.output_root / "sandbox_worktrees"
        self.accepted_artifacts_root = self.output_root / "accepted_patches"
        self.promotion_journal_path = self.output_root / "promotion_state.json"
        self.accepted_branch = "accepted"
        self.source_project_commit = ""
        self.baseline_commit = ""
        self.accepted_commit = ""
        self._created = False

    def create(self) -> None:
        """Materialize the isolated snapshot repo for this harness run."""
        self.output_root.mkdir(parents=True, exist_ok=True)
        self._reset_path(self.repo_root)
        self._reset_path(self.worktrees_root)
        self._reset_path(self.accepted_artifacts_root)
        self._copy_project_snapshot()
        self._init_git_repo()
        self.source_project_commit = self._detect_source_commit()
        self.baseline_commit = self._git_output(["rev-parse", "HEAD"], cwd=self.repo_root)
        self.accepted_commit = self.baseline_commit
        self._git(["branch", "-f", self.accepted_branch, self.accepted_commit], cwd=self.repo_root)
        self._created = True
        logger.info(
            "Created harness sandbox repo at %s (baseline=%s)",
            self.repo_root,
            self.baseline_commit,
        )

    @contextmanager
    def trial_worktree(self, iteration: int, surface: EditSurface) -> Iterator[tuple[Path, EditSurface]]:
        """Yield a temporary git worktree plus a matching editable surface."""
        worktree = self.create_worktree(iteration)
        try:
            yield worktree, surface.clone_for_project_root(worktree)
        finally:
            self.cleanup_worktree(worktree)

    def create_worktree(self, iteration: int) -> Path:
        """Create an isolated worktree from the latest accepted commit."""
        if not self._created:
            raise RuntimeError("HarnessWorkspace.create() must be called first.")
        worktree = self.worktrees_root / f"iter_{iteration:04d}"
        self._reset_path(worktree)
        self._git(
            ["worktree", "add", "--detach", str(worktree), self.accepted_commit],
            cwd=self.repo_root,
        )
        return worktree

    def cleanup_worktree(self, worktree: Path) -> None:
        """Remove a temporary worktree after the iteration completes."""
        if not worktree.exists():
            return
        try:
            self._git(["worktree", "remove", "--force", str(worktree)], cwd=self.repo_root)
        except RuntimeError as exc:
            logger.warning("Failed to clean git worktree %s: %s", worktree, exc)
            shutil.rmtree(worktree, ignore_errors=True)
        self._git(["worktree", "prune"], cwd=self.repo_root, check=False)

    def commit_accepted_patch(
        self,
        iteration: int,
        worktree: Path,
        patch: PatchPlan,
        modified_files: list[str],
    ) -> AcceptedPatchRecord:
        """Commit a kept patch inside the sandbox repo and export artifacts."""
        if not modified_files:
            raise ValueError("Accepted patch recorded no modified files.")

        parent_commit = self.accepted_commit
        self._git(["add", "--", *modified_files], cwd=worktree)
        message = self._build_commit_message(iteration, patch)
        self._git(["commit", "-m", message], cwd=worktree)
        commit_hash = self._git_output(["rev-parse", "HEAD"], cwd=worktree)
        self._git(["branch", "-f", self.accepted_branch, commit_hash], cwd=self.repo_root)
        self.accepted_commit = commit_hash

        short_hash = commit_hash[:12]
        artifact_path = self.accepted_artifacts_root / f"iter_{iteration:04d}_{short_hash}.patch"
        manifest_path = self.accepted_artifacts_root / f"iter_{iteration:04d}_{short_hash}.json"
        artifact_text = self._git_output(["format-patch", "--stdout", "-1", commit_hash], cwd=self.repo_root)
        artifact_path.write_text(artifact_text, encoding="utf-8")

        record = AcceptedPatchRecord(
            iteration=iteration,
            commit_hash=commit_hash,
            parent_commit=parent_commit,
            artifact_path=str(artifact_path),
            manifest_path=str(manifest_path),
            modified_files=list(modified_files),
            reasoning=patch.reasoning,
            diff_summary=patch.diff_summary,
            description=patch.description,
            expected_improvements=list(patch.expected_improvements),
            rollback_conditions=list(patch.rollback_conditions),
            sandbox_repo=str(self.repo_root),
            sandbox_worktree=str(worktree),
            source_project_commit=self.source_project_commit,
        )
        manifest_path.write_text(
            json.dumps(record.to_dict() | {"patch_plan": patch.to_dict()}, indent=2, default=str),
            encoding="utf-8",
        )
        return record

    def promote_accepted_state(self, accepted_files: list[str]) -> PromotionResult:
        """Promote the latest accepted snapshot back to the source worktree.

        Promotion is conservative: if any target file changed in the source tree
        since the harness snapshot was taken, the function leaves the source tree
        untouched and reports a blocked promotion instead of clobbering user edits.
        """
        journal = {
            "status": "not_needed",
            "source_project_root": str(self.source_project_root),
            "sandbox_repo": str(self.repo_root),
            "baseline_commit": self.baseline_commit,
            "accepted_commit": self.accepted_commit,
            "files": sorted(set(accepted_files)),
            "applied_files": [],
            "blocked_files": [],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.promotion_journal_path.write_text(
            json.dumps(journal, indent=2, default=str),
            encoding="utf-8",
        )

        unique_files = sorted(set(accepted_files))
        if not unique_files:
            journal["status"] = "not_needed"
            journal["message"] = "No accepted files to promote."
            self._write_promotion_journal(journal)
            return PromotionResult(
                status="not_needed",
                message=journal["message"],
                journal_path=str(self.promotion_journal_path),
            )

        blocked: list[str] = []
        for rel_path in unique_files:
            baseline_bytes = self.read_file_from_commit(self.baseline_commit, rel_path)
            source_path = self.source_project_root / rel_path
            current_bytes = source_path.read_bytes() if source_path.exists() else b""
            if current_bytes != baseline_bytes:
                blocked.append(rel_path)

        if blocked:
            journal["status"] = "blocked"
            journal["blocked_files"] = blocked
            journal["message"] = (
                "Source files changed after the harness snapshot was created; "
                "manual promotion is required."
            )
            self._write_promotion_journal(journal)
            return PromotionResult(
                status="blocked",
                message=journal["message"],
                blocked_files=blocked,
                journal_path=str(self.promotion_journal_path),
            )

        journal["status"] = "applying"
        self._write_promotion_journal(journal)
        applied: list[str] = []
        for rel_path in unique_files:
            accepted_bytes = self.read_file_from_commit(self.accepted_commit, rel_path)
            target = self.source_project_root / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            temp_target = target.with_name(target.name + ".omicsclaw.tmp")
            temp_target.write_bytes(accepted_bytes)
            if target.exists():
                shutil.copystat(target, temp_target, follow_symlinks=True)
            os.replace(temp_target, target)
            applied.append(rel_path)
            journal["applied_files"] = list(applied)
            self._write_promotion_journal(journal)

        journal["status"] = "applied"
        journal["message"] = "Promoted accepted sandbox state to the source worktree."
        self._write_promotion_journal(journal)
        return PromotionResult(
            status="applied",
            message=journal["message"],
            promoted_files=applied,
            journal_path=str(self.promotion_journal_path),
        )

    def read_file_from_commit(self, commit_hash: str, rel_path: str) -> bytes:
        """Read a file from a specific sandbox commit."""
        return self._git_output_bytes(["show", f"{commit_hash}:{rel_path}"], cwd=self.repo_root)

    def baseline_code_state(self) -> dict[str, Any]:
        """Metadata that identifies the immutable baseline snapshot."""
        return {
            "kind": "baseline_snapshot",
            "sandbox_repo": str(self.repo_root),
            "sandbox_commit": self.baseline_commit,
            "source_project_commit": self.source_project_commit,
        }

    def accepted_head_state(self) -> dict[str, Any]:
        """Metadata for the latest accepted sandbox commit."""
        return {
            "kind": "accepted_head",
            "sandbox_repo": str(self.repo_root),
            "sandbox_commit": self.accepted_commit,
            "source_project_commit": self.source_project_commit,
        }

    def _copy_project_snapshot(self) -> None:
        self.repo_root.mkdir(parents=True, exist_ok=True)
        excluded_roots = {self.output_root}

        for root, dirs, files in os.walk(self.source_project_root, topdown=True):
            root_path = Path(root)
            if self._is_excluded(root_path, excluded_roots):
                dirs[:] = []
                continue

            rel_root = root_path.relative_to(self.source_project_root)
            kept_dirs: list[str] = []
            for name in dirs:
                src_dir = root_path / name
                if self._should_skip_path(src_dir, excluded_roots, is_dir=True):
                    continue
                if src_dir.is_symlink():
                    self._copy_symlink(src_dir, self.repo_root / rel_root / name)
                    continue
                kept_dirs.append(name)
            dirs[:] = kept_dirs

            for name in files:
                src_file = root_path / name
                if self._should_skip_path(src_file, excluded_roots, is_dir=False):
                    continue
                dst_file = self.repo_root / rel_root / name
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                if src_file.is_symlink():
                    self._copy_symlink(src_file, dst_file)
                else:
                    shutil.copy2(src_file, dst_file)

    def _init_git_repo(self) -> None:
        self._git(["init"], cwd=self.repo_root)
        self._git(["config", "user.name", "OmicsClaw Harness"], cwd=self.repo_root)
        self._git(["config", "user.email", "omicsclaw-autoagent@local"], cwd=self.repo_root)
        self._git(["add", "-A"], cwd=self.repo_root)
        self._git(["commit", "-m", "Harness baseline snapshot"], cwd=self.repo_root)

    def _detect_source_commit(self) -> str:
        try:
            return self._git_output(["rev-parse", "HEAD"], cwd=self.source_project_root)
        except RuntimeError:
            return ""

    def _build_commit_message(self, iteration: int, patch: PatchPlan) -> str:
        headline = patch.description.strip() or patch.diff_summary
        headline = headline.splitlines()[0][:72]
        return f"Harness iteration {iteration:04d}: {headline}"

    def _write_promotion_journal(self, payload: dict[str, Any]) -> None:
        self.promotion_journal_path.write_text(
            json.dumps(payload, indent=2, default=str),
            encoding="utf-8",
        )

    def _should_skip_path(self, path: Path, excluded_roots: set[Path], *, is_dir: bool) -> bool:
        if self._is_excluded(path, excluded_roots):
            return True
        if path.name in _IGNORED_NAMES:
            return True
        if is_dir and path.parent == self.source_project_root and path.name in _IGNORED_TOP_LEVEL_DIRS:
            return True
        return False

    @staticmethod
    def _is_excluded(path: Path, excluded_roots: set[Path]) -> bool:
        resolved = path.resolve()
        for excluded in excluded_roots:
            try:
                resolved.relative_to(excluded)
                return True
            except ValueError:
                continue
        return False

    @staticmethod
    def _copy_symlink(src: Path, dst: Path) -> None:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists() or dst.is_symlink():
            dst.unlink()
        os.symlink(os.readlink(src), dst)

    @staticmethod
    def _reset_path(path: Path) -> None:
        if path.exists() or path.is_symlink():
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink()
        path.mkdir(parents=True, exist_ok=True)

    def _git(self, args: list[str], *, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
        cmd = ["git", *args]
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
        if check and proc.returncode != 0:
            stderr = proc.stderr.strip() or proc.stdout.strip()
            raise RuntimeError(f"git {' '.join(args)} failed in {cwd}: {stderr}")
        return proc

    def _git_output(self, args: list[str], *, cwd: Path) -> str:
        proc = self._git(args, cwd=cwd)
        return proc.stdout.strip()

    def _git_output_bytes(self, args: list[str], *, cwd: Path) -> bytes:
        cmd = ["git", *args]
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=False,
            check=False,
        )
        if proc.returncode != 0:
            stderr = proc.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"git {' '.join(args)} failed in {cwd}: {stderr}")
        return proc.stdout
