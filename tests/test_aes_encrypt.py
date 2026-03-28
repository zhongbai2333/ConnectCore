"""Tests for AES encryption / decryption utilities."""

from __future__ import annotations

import base64

import pytest
from cryptography.fernet import Fernet

from connect_core.aes_encrypt import (
    DecryptionError,
    aes_decrypt,
    aes_encrypt,
    aes_main,
)


@pytest.fixture(autouse=True)
def _reset_aes_globals():
    """Reset module-level globals before each test."""
    import connect_core.aes_encrypt as mod

    mod._fernet = None
    mod._control_interface = None
    yield
    mod._fernet = None
    mod._control_interface = None


def _make_key() -> str:
    """Generate a valid Fernet key as a string."""
    return Fernet.generate_key().decode()


class TestAesEncryptDecrypt:
    def test_round_trip_with_password(self):
        key = _make_key()
        plaintext = b"hello world"
        ciphertext = aes_encrypt(plaintext, password=key)
        assert aes_decrypt(ciphertext, password=key) == plaintext

    def test_round_trip_with_init(self):
        key = _make_key()
        aes_main(None, password=key)
        plaintext = b"test data"
        ciphertext = aes_encrypt(plaintext)
        assert aes_decrypt(ciphertext) == plaintext

    def test_encrypt_str_input(self):
        key = _make_key()
        ciphertext = aes_encrypt("hello", password=key)
        assert aes_decrypt(ciphertext, password=key) == b"hello"

    def test_encrypt_without_init_raises(self):
        with pytest.raises(Exception):
            aes_encrypt(b"data")

    def test_decrypt_without_init_raises(self):
        with pytest.raises(DecryptionError):
            aes_decrypt(b"data")

    def test_decrypt_invalid_token(self):
        key1 = _make_key()
        key2 = _make_key()
        ciphertext = aes_encrypt(b"secret", password=key1)
        with pytest.raises(DecryptionError):
            aes_decrypt(ciphertext, password=key2)

    def test_aes_main_without_password(self):
        aes_main(None, password=None)
        with pytest.raises(Exception):
            aes_encrypt(b"data")
