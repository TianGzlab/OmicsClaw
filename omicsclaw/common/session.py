"""OmicsSession — upload once, analyse many times.

Stores metadata about an omics dataset and accumulated skill results
in a JSON file so multiple skills can share processed data.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from omicsclaw.common.checksums import sha256_file


class OmicsSession:
    """In-memory omics analysis session with JSON persistence."""

    def __init__(
        self,
        session_id: str = "",
        input_file: str = "",
        data_type: str = "generic",
        species: str = "human",
        checksum: str = "",
        created_at: str = "",
        primary_data_path: str = "",
        domain: str = "spatial",
        processing_state: dict[str, bool] | None = None,
        skill_results: dict[str, Any] | None = None,
        h5ad_path: str = "",  # Backward compatibility
    ):
        self.metadata = {
            "session_id": session_id,
            "input_file": input_file,
            "data_type": data_type,
            "species": species,
            "checksum": checksum,
            "created_at": created_at or datetime.now(timezone.utc).isoformat(),
            "domain": domain,
        }
        self.primary_data_path: str = primary_data_path or h5ad_path
        self.processing_state: dict[str, bool] = processing_state or {}
        self.skill_results: dict[str, Any] = skill_results or {}

    @property
    def h5ad_path(self) -> str:
        """Backward compatibility alias for primary_data_path."""
        return self.primary_data_path

    @classmethod
    def from_file(
        cls,
        filepath: str | Path,
        data_type: str = "generic",
        species: str = "human",
        session_id: str = "",
        domain: str = "spatial",
    ) -> "OmicsSession":
        """Create a new session from a primary data file."""
        filepath = Path(filepath)
        checksum = sha256_file(filepath)
        if not session_id:
            session_id = filepath.stem.replace(" ", "_")[:32]
        return cls(
            session_id=session_id,
            input_file=str(filepath.resolve()),
            data_type=data_type,
            species=species,
            checksum=checksum,
            primary_data_path=str(filepath.resolve()),
            domain=domain,
        )

    @classmethod
    def from_h5ad(cls, *args, **kwargs) -> "OmicsSession":
        """Backward compatibility alias for from_file."""
        return cls.from_file(*args, **kwargs)

    def add_skill_result(
        self,
        skill_name: str,
        result_dict: dict,
        output_dir: str = "",
    ) -> None:
        """Store the result of a skill run."""
        self.skill_results[skill_name] = {
            "run_at": datetime.now(timezone.utc).isoformat(),
            "output_dir": output_dir,
            "data": result_dict,
        }

    def get_skill_result(self, skill_name: str) -> dict | None:
        """Retrieve a previous skill result."""
        entry = self.skill_results.get(skill_name)
        if entry:
            return entry.get("data")
        return None

    def mark_step(self, step: str, done: bool = True) -> None:
        """Mark a processing step as completed."""
        self.processing_state[step] = done

    def is_step_done(self, step: str) -> bool:
        return self.processing_state.get(step, False)

    # --- Persistence ---

    def save(self, path: str | Path) -> Path:
        """Save session to a JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "metadata": self.metadata,
            "primary_data_path": self.primary_data_path,
            "processing_state": self.processing_state,
            "skill_results": self.skill_results,
        }
        path.write_text(json.dumps(data, indent=2, default=str))
        return path

    @classmethod
    def load(cls, path: str | Path) -> "OmicsSession":
        """Load session from a JSON file."""
        path = Path(path)
        data = json.loads(path.read_text())
        meta = data.get("metadata", {})
        return cls(
            session_id=meta.get("session_id", ""),
            input_file=meta.get("input_file", ""),
            data_type=meta.get("data_type", "generic"),
            species=meta.get("species", "human"),
            checksum=meta.get("checksum", ""),
            created_at=meta.get("created_at", ""),
            primary_data_path=data.get("primary_data_path", data.get("h5ad_path", "")),
            domain=meta.get("domain", "spatial"),
            processing_state=data.get("processing_state"),
            skill_results=data.get("skill_results"),
        )

    def __repr__(self) -> str:
        sid = self.metadata.get("session_id", "unknown")
        dtype = self.metadata.get("data_type", "?")
        domain = self.metadata.get("domain", "?")
        skills = list(self.skill_results.keys())
        return f"OmicsSession(id={sid!r}, domain={domain!r}, type={dtype!r}, skills={skills})"


# Backward compatibility alias
SpatialSession = OmicsSession
