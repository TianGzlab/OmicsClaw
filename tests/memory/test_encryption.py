"""Test encryption module."""

import pytest
from bot.memory.encryption import SecureFieldEncryptor
from bot.memory.models import DatasetMemory, AnalysisMemory


def test_encrypt_decrypt_field():
    """Test field encryption/decryption."""
    key = b"0" * 32  # 32 bytes for AES-256
    encryptor = SecureFieldEncryptor(key)

    plaintext = "data/brain.h5ad"
    encrypted = encryptor.encrypt_field(plaintext)
    decrypted = encryptor.decrypt_field(encrypted)

    assert decrypted == plaintext
    assert encrypted != plaintext


def test_encrypt_memory():
    """Test memory object encryption."""
    key = b"0" * 32
    encryptor = SecureFieldEncryptor(key)

    memory = DatasetMemory(
        file_path="data/test.h5ad",
        platform="Visium",
        n_obs=1000,
        n_vars=500,
    )

    encrypted_data = encryptor.encrypt_memory(memory)

    # Sensitive field should be encrypted
    assert encrypted_data["file_path"] != "data/test.h5ad"
    # Non-sensitive fields should be plaintext
    assert encrypted_data["platform"] == "Visium"
    assert encrypted_data["n_obs"] == 1000


def test_decrypt_memory():
    """Test memory object decryption."""
    key = b"0" * 32
    encryptor = SecureFieldEncryptor(key)

    memory = AnalysisMemory(
        source_dataset_id="dataset123",
        skill="spatial-preprocessing",
        method="leiden",
        parameters={"resolution": 0.8},
        output_path="output/results",
    )

    encrypted_data = encryptor.encrypt_memory(memory)
    decrypted_data = encryptor.decrypt_memory("AnalysisMemory", encrypted_data)

    assert decrypted_data["parameters"] == {"resolution": 0.8}
    assert decrypted_data["output_path"] == "output/results"


def test_invalid_key_length():
    """Test that invalid key length raises error."""
    with pytest.raises(ValueError, match="Key must be 32 bytes"):
        SecureFieldEncryptor(b"short")
