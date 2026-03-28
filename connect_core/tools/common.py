from __future__ import annotations

import base64
import hashlib
import json
import os
import random
import string
from typing import Any, Optional

try:  # pragma: no cover - optional dependency
    from cryptography.fernet import Fernet
except ImportError:  # pragma: no cover - fallback when cryptography is unavailable
    Fernet = None  # type: ignore[misc,assignment]

__all__ = [
    "generate_md5_checksum",
    "verify_md5_checksum",
    "get_file_hash",
    "verify_file_hash",
    "generate_random_id",
    "generate_password",
    "encrypt_data",
    "decrypt_data",
    "encode_file_to_base64",
    "decode_base64_to_file",
]


def generate_md5_checksum(data: Any) -> str:
    """Return the SHA-256 checksum for arbitrary serialisable data."""

    if isinstance(data, (dict, list)):
        encoded = json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")
    elif isinstance(data, str):
        encoded = data.encode("utf-8")
    elif isinstance(data, bytes):
        encoded = data
    else:
        encoded = json.dumps(data, ensure_ascii=False).encode("utf-8")

    digest = hashlib.sha256()
    digest.update(encoded)
    return digest.hexdigest()


def verify_md5_checksum(data: Any, checksum: Optional[str]) -> bool:
    """Validate that *data* matches the given SHA-256 checksum."""

    if checksum is None:
        return False
    return generate_md5_checksum(data) == checksum


def get_file_hash(file_path: str, algorithm: str = "sha256") -> Optional[str]:
    """Calculate the hash of a file using the given algorithm."""

    try:
        hash_func = hashlib.new(algorithm)
        with open(file_path, "rb") as handle:
            for chunk in iter(lambda: handle.read(8192), b""):
                hash_func.update(chunk)
        return hash_func.hexdigest()
    except (OSError, ValueError):  # pragma: no cover - IO dependent
        return None


def verify_file_hash(
    file_path: str,
    expected_hash: Optional[str],
    algorithm: str = "sha256",
) -> bool:
    """Check whether the file hash matches *expected_hash*."""

    if expected_hash is None:
        return True
    return get_file_hash(file_path, algorithm) == expected_hash


def generate_random_id(length: int) -> str:
    """Generate a random alphanumeric identifier with the requested length."""

    if length <= 0:
        return ""

    digit_count = random.randint(1, length)
    numeric_part = "".join(str(random.randint(0, 9)) for _ in range(digit_count))
    alpha_part = "".join(
        random.choice(string.ascii_letters) for _ in range(length - len(numeric_part))
    )
    return "".join(random.sample(list(numeric_part + alpha_part), length))


def generate_password() -> str:
    """Generate a Fernet-compatible password.

    Falls back to a random base64 string when ``cryptography`` is unavailable.
    """

    if Fernet is None:  # pragma: no cover - cryptography missing
        alphabet = string.ascii_letters + string.digits
        return "".join(random.choice(alphabet) for _ in range(32))
    return Fernet.generate_key().decode()


def encrypt_data(data: bytes, key: str) -> bytes:
    """Encrypt *data* using Fernet when available, else return plaintext."""

    if Fernet is None:  # pragma: no cover - cryptography missing
        return data
    return Fernet(key.encode()).encrypt(data)


def decrypt_data(data: bytes, key: str) -> bytes:
    """Decrypt Fernet-encrypted *data*; passthrough when Fernet is missing."""

    if Fernet is None:  # pragma: no cover - cryptography missing
        return data
    return Fernet(key.encode()).decrypt(data)


def encode_file_to_base64(file_path: str) -> Optional[str]:
    """Encode the file at *file_path* as a base64 string."""

    try:
        with open(file_path, "rb") as file:
            return base64.b64encode(file.read()).decode()
    except OSError:  # pragma: no cover - IO dependent
        return None


def decode_base64_to_file(data: str, target_path: str) -> None:
    """Decode base64 *data* into *target_path*, creating directories if needed."""

    directory = os.path.dirname(target_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(target_path, "wb") as handle:
        handle.write(base64.b64decode(data.encode()))
