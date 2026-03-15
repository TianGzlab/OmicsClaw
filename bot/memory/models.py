"""Pydantic models for memory system."""

from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator


class Session(BaseModel):
    """User session across bot restarts."""
    session_id: str
    user_id: str
    platform: Literal["telegram", "feishu"]
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_activity: datetime = Field(default_factory=datetime.utcnow)
    preferences: dict[str, Any] = Field(default_factory=dict)
    active: bool = True


class BaseMemory(BaseModel):
    """Base class for all memory types."""
    memory_id: str = Field(default_factory=lambda: __import__('uuid').uuid4().hex)
    memory_type: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class DatasetMemory(BaseMemory):
    """Physical dataset metadata - NO raw data."""
    memory_type: Literal["dataset"] = "dataset"
    file_path: str  # Relative path only
    platform: str | None = None  # "Visium", "Xenium"
    n_obs: int | None = None
    n_vars: int | None = None
    preprocessing_state: Literal["raw", "qc", "normalized", "clustered"] = "raw"
    file_exists: bool = True

    @field_validator("file_path")
    @classmethod
    def validate_relative_path(cls, v: str) -> str:
        if v.startswith("/"):
            raise ValueError("Absolute paths not allowed")
        return v


class AnalysisMemory(BaseMemory):
    """Analysis execution record with lineage."""
    memory_type: Literal["analysis"] = "analysis"
    source_dataset_id: str  # Links to DatasetMemory
    parent_analysis_id: str | None = None  # For multi-step workflows
    skill: str
    method: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    output_path: str | None = None
    status: Literal["completed", "failed", "interrupted"] = "completed"
    executed_at: datetime = Field(default_factory=datetime.utcnow)
    duration_seconds: float = 0.0


class PreferenceMemory(BaseMemory):
    """User preferences and habits."""
    memory_type: Literal["preference"] = "preference"
    domain: str  # "global", "spatial-preprocessing"
    key: str
    value: Any
    is_strict: bool = False  # True=mandatory, False=soft
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class InsightMemory(BaseMemory):
    """Biological interpretations - MUST be sanitized."""
    memory_type: Literal["insight"] = "insight"
    source_analysis_id: str
    entity_type: str  # "cluster", "spatial_domain"
    entity_id: str
    biological_label: str  # Encrypted + sanitized
    evidence: str = ""
    confidence: Literal["user_confirmed", "ai_predicted"] = "ai_predicted"


class ProjectContextMemory(BaseMemory):
    """Global scientific context."""
    memory_type: Literal["project_context"] = "project_context"
    project_goal: str = ""
    species: str | None = None
    tissue_type: str | None = None
    disease_model: str | None = None
