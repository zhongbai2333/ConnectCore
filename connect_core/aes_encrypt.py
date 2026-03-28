from __future__ import annotations

import threading

from typing import Optional, TYPE_CHECKING

from cryptography.fernet import Fernet, InvalidToken

if TYPE_CHECKING:  # pragma: no cover
    from connect_core.interface.control_interface import CoreControlInterface

_fernet: Fernet | None = None
_control_interface: Optional["CoreControlInterface"] = None
_fernet_lock = threading.Lock()


class DecryptionError(ValueError):
    """Raised when decrypting data fails due to invalid key or payload."""


def aes_main(
    control_interface: "CoreControlInterface", password: str | None = None
) -> None:
    """Initialize global Fernet cipher with optional password."""
    global _fernet, _control_interface

    _control_interface = control_interface
    with _fernet_lock:
        if password:
            _fernet = Fernet(password.encode())
        else:
            _fernet = None


def aes_encrypt(data: bytes | str, password: str | None = None) -> bytes:
    """Encrypt *data* using configured Fernet cipher or provided password."""
    payload = data.encode() if isinstance(data, str) else data
    with _fernet_lock:
        fernet = _fernet

    if password:
        fernet = Fernet(password.encode())
        return fernet.encrypt(payload)

    if fernet is None:
        raise InvalidToken("Password initialization error!")

    return fernet.encrypt(payload)


def aes_decrypt(data: bytes | str, password: str | None = None) -> bytes:
    """Decrypt *data* using configured Fernet cipher or provided password."""
    payload = data.encode() if isinstance(data, str) else data
    with _fernet_lock:
        fernet = _fernet

    if password:
        fernet = Fernet(password.encode())
    if fernet is None or not payload:
        raise DecryptionError("Password initialization error or data error!")

    try:
        return fernet.decrypt(payload)
    except InvalidToken as exc:  # pragma: no cover - log side-effect
        if _control_interface is not None:
            _control_interface.warning(_control_interface.tr("rsa.decrypt_error"))
        raise DecryptionError("Decryption failed: invalid token") from exc
