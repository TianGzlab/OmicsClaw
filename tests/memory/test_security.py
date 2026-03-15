"""Test security validations."""

import pytest
from pydantic import ValidationError
from bot.memory.models import DatasetMemory


def test_reject_absolute_paths():
    """Test that absolute paths are rejected."""
    with pytest.raises(ValidationError, match="Absolute paths not allowed"):
        DatasetMemory(file_path="/absolute/path/data.h5ad")


def test_relative_paths_allowed():
    """Test that relative paths are accepted."""
    memory = DatasetMemory(file_path="data/brain.h5ad")
    assert memory.file_path == "data/brain.h5ad"


def test_no_raw_data_fields():
    """Test that raw data fields don't exist in model."""
    memory = DatasetMemory(file_path="data/test.h5ad")

    # These fields should not exist
    assert not hasattr(memory, "raw_counts")
    assert not hasattr(memory, "gene_sequences")
    assert not hasattr(memory, "patient_id")
    assert not hasattr(memory, "sample_id")
