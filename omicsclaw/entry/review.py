"""Archive a reviewer reply against the project files it was asked to read.

Receipts detect stale inputs and changed text. They are workspace files,
not signatures or proof against a writer who can replace both files.
"""

import hashlib
import json
import re
import uuid
from pathlib import Path

from omicsclaw.tools._workspace import Workspace

from .project import MANIFEST_FILE, MODULE_DIR_PATTERN, REPORT_FILE, REVIEW_BRIEF_FILE


class ReviewArchive:
    def __init__(self, root: Path, module: str):
        match = re.fullmatch(MODULE_DIR_PATTERN, module)
        if match is None:
            raise ValueError("review_module must be NN_slug, for example 01_qc")
        self.workspace = Workspace(root)
        self.module = module
        self.results = f"results/{module}"
        self.report = REPORT_FILE.format(nn=match[1], slug=match[2])
        self.snapshot = self._snapshot()

    def _snapshot(self) -> dict:
        manifest = json.loads(self.workspace.resolve(f"{self.results}/{MANIFEST_FILE}").read_text(encoding="utf-8"))
        replay = manifest.get("replay") or {}
        if manifest.get("frozen") or replay.get("status") != "ok":
            raise ValueError("review_module needs a successful replay and an unfrozen module")
        paths = [f"analysis/{self.module}/README.md", f"{self.results}/{self.report}",
                 f"{self.results}/{REVIEW_BRIEF_FILE}"]
        hashes = replay.get("step_sha256")
        if not isinstance(hashes, dict) or not hashes:
            raise ValueError("replay has no step hashes")
        paths.extend(f"analysis/{self.module}/{name}" for name in hashes)
        files = {name: hashlib.sha256(self.workspace.resolve(name).read_bytes()).hexdigest() for name in paths}
        if any(files[f"analysis/{self.module}/{name}"] != sha for name, sha in hashes.items()):
            raise ValueError("step files changed since replay; replay before reviewing")
        return {"replay": replay, "files": files}

    def save(self, text: str) -> str:
        if self._snapshot() != self.snapshot:
            raise ValueError("module changed during review; review the current replay again")
        if not text.splitlines() or text.splitlines()[0] not in {"VERDICT: APPROVE", "VERDICT: REVISE"}:
            raise ValueError("review must start with VERDICT: APPROVE or VERDICT: REVISE")
        relative = f"{self.results}/reviews/task-review-{uuid.uuid4().hex}.md"
        path = self.workspace.resolve(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        content = text.encode("utf-8")
        receipt = {"schema": 1, "module": self.module, "review_sha256": hashlib.sha256(content).hexdigest(),
                   **self.snapshot}
        # A partial write has no valid receipt and cannot be accepted.
        with path.open("xb") as target:
            target.write(content)
        with path.with_suffix(".json").open("x", encoding="utf-8") as target:
            json.dump(receipt, target, ensure_ascii=False, indent=2)
        return relative
