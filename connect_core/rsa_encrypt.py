from cryptography.fernet import Fernet, InvalidToken
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from connect_core.api.server_interface import ConnectCoreServerInterface

# 全局变量，用于存储 Fernet 实例
fernet = None


def rsa_main(connect_interface: 'ConnectCoreServerInterface'):
    """
    初始化 Fernet 实例。如果配置中存在密码，则使用该密码初始化 Fernet。

    Args:
        connect_interface (ConnectCoreServerInterface): API接口
    """
    global fernet, _connect_interface

    _connect_interface = connect_interface
    config = _connect_interface.get_config()
    password = config["password"]
    if password:
        fernet = Fernet(password.encode())
    else:
        fernet = None


def rsa_encrypt(data: bytes) -> bytes:
    """
    加密数据

    Args:
        data (bytes): 需要加密的字节数据。

    Returns:
        bytes: 加密后的字节数据。

    Exceptions:
        InvalidToken: 如果未初始化密码或初始化错误时抛出异常。
    """
    if fernet:
        return fernet.encrypt(data)
    else:
        raise InvalidToken("Password initialization error!")


def rsa_decrypt(data: bytes) -> bytes:
    """
    解密数据

    Args:
        data (bytes): 需要解密的字节数据。

    Returns:
        bytes: 解密后的字节数据。

    Exceptions:
        InvalidToken: 如果未初始化密码、数据为空或解密失败时抛出异常。
    """
    if fernet and data:
        try:
            return fernet.decrypt(data)
        except InvalidToken as e:
            _connect_interface.error(_connect_interface.tr("rsa.decrypt_error"))
            raise InvalidToken(f"Decryption failed: {e}")
    else:
        raise InvalidToken("Password initialization error or data error!")
