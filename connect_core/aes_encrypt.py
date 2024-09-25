from cryptography.fernet import Fernet, InvalidToken
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from connect_core.interface.control_interface import CoreControlInterface

# 全局变量，用于存储 Fernet 实例
_fernet = None


def aes_main(control_interface: "CoreControlInterface", password: str = None):
    """
    初始化 Fernet 实例。如果配置中存在密码，则使用该密码初始化 Fernet。

    Args:
        connect_interface (CoreControlInterface): API接口
        password (str): 临时密码
    """
    global _fernet, _control_interface

    _control_interface = control_interface
    if password:
        _fernet = Fernet(password.encode())
    else:
        _fernet = None


def aes_encrypt(data: bytes, password: str = None) -> bytes:
    """
    加密数据

    Args:
        data (bytes): 需要加密的字节数据。
        password (str): 密钥, 默认为None

    Returns:
        bytes: 加密后的字节数据。

    Exceptions:
        InvalidToken: 如果未初始化密码或初始化错误时抛出异常。
    """
    fernet = _fernet
    if password:
        fernet = Fernet(password.encode())
        return fernet.encrypt(data)
    else:
        if fernet:
            return fernet.encrypt(data)
        else:
            raise InvalidToken("Password initialization error!")


def aes_decrypt(data: bytes, password: str = None) -> bytes:
    """
    解密数据

    Args:
        data (bytes): 需要解密的字节数据。
        password (str): 密钥, 默认为None

    Returns:
        bytes: 解密后的字节数据。

    Exceptions:
        InvalidToken: 如果未初始化密码、数据为空或解密失败时抛出异常。
    """
    fernet = _fernet
    if password:
        fernet = Fernet(password.encode())
        if data:
            try:
                return _fernet.decrypt(data)
            except InvalidToken as e:
                _control_interface.error(_control_interface.tr("rsa.decrypt_error"))
                raise InvalidToken(f"Decryption failed: {e}")
        else:
            raise InvalidToken("Password initialization error or data error!")
    else:
        if fernet and data:
            try:
                return _fernet.decrypt(data)
            except InvalidToken as e:
                _control_interface.error(_control_interface.tr("rsa.decrypt_error"))
                raise InvalidToken(f"Decryption failed: {e}")
        else:
            raise InvalidToken("Password initialization error or data error!")
