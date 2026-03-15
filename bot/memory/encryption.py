"""AES-256-GCM encryption for sensitive memory fields."""

import base64
import json
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from bot.memory.models import BaseMemory


SENSITIVE_FIELDS = {
    "DatasetMemory": ["file_path"],
    "AnalysisMemory": ["parameters", "output_path"],
    "PreferenceMemory": ["value"],
    "InsightMemory": ["biological_label", "evidence"],
    "ProjectContextMemory": ["project_goal"],
}


class SecureFieldEncryptor:
    """Encrypts sensitive fields in memory objects."""

    def __init__(self, key: bytes):
        if len(key) != 32:
            raise ValueError("Key must be 32 bytes for AES-256")
        self.cipher = AESGCM(key)

    def encrypt_field(self, plaintext: str) -> str:
        """Encrypt a single field value."""
        nonce = os.urandom(12)
        ciphertext = self.cipher.encrypt(nonce, plaintext.encode(), None)
        return base64.b64encode(nonce + ciphertext).decode()

    def decrypt_field(self, encrypted: str) -> str:
        """Decrypt a single field value."""
        data = base64.b64decode(encrypted.encode())
        nonce, ciphertext = data[:12], data[12:]
        plaintext = self.cipher.decrypt(nonce, ciphertext, None)
        return plaintext.decode()

    def encrypt_memory(self, memory: BaseMemory) -> dict:
        """Encrypt sensitive fields in memory object."""
        data = memory.model_dump()
        memory_type = type(memory).__name__
        sensitive = SENSITIVE_FIELDS.get(memory_type, [])

        for field in sensitive:
            if field in data and data[field] is not None:
                value = json.dumps(data[field]) if not isinstance(data[field], str) else data[field]
                data[field] = self.encrypt_field(value)

        return data

    def decrypt_memory(self, memory_type: str, data: dict) -> dict:
        """Decrypt sensitive fields in memory data."""
        sensitive = SENSITIVE_FIELDS.get(memory_type, [])

        for field in sensitive:
            if field in data and data[field] is not None:
                decrypted = self.decrypt_field(data[field])
                try:
                    data[field] = json.loads(decrypted)
                except json.JSONDecodeError:
                    data[field] = decrypted

        return data
