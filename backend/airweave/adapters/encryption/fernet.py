"""Fernet-based credential encryption adapter."""

from __future__ import annotations

import json
from typing import Any

from cryptography.fernet import Fernet


class FernetCredentialEncryptor:
    """Encrypt/decrypt credential dicts using Fernet symmetric encryption."""

    def __init__(self, encryption_key: str) -> None:
        """Initialize the encryptor with a base64-encoded Fernet key.

        Args:
            encryption_key: A URL-safe base64-encoded 32-byte key as a string.
        """
        self._fernet = Fernet(encryption_key.encode())

    def encrypt(self, data: dict[str, Any]) -> str:
        """Encrypt a credential dict and return the ciphertext as a string.

        Args:
            data: The plaintext credential dictionary to encrypt.

        Returns:
            URL-safe base64-encoded Fernet token suitable for storage.
        """
        return self._fernet.encrypt(json.dumps(data).encode()).decode()

    def decrypt(self, encrypted: str) -> dict[str, Any]:
        """Decrypt a previously-encrypted credential token back into a dict.

        Args:
            encrypted: The Fernet token produced by ``encrypt``.

        Returns:
            The original credential dictionary.
        """
        return json.loads(self._fernet.decrypt(encrypted).decode())
