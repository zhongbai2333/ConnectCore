import time
import json
from cryptography.fernet import Fernet

from typing import TYPE_CHECKING
from connect_core.tools import new_thread
from connect_core.tools import (
    encode_base64,
    get_all_internal_ips,
    get_external_ip,
)

if TYPE_CHECKING:
    from connect_core.interface.control_interface import CoreControlInterface

global _control_interface, _respawn_password
_password = ""


@new_thread("RegisterSystem")
def _spawn_password():
    """
    生成密钥, 并存储到password中
    """
    global _password, _respawn_password
    _respawn_password = False
    while True:
        i = 0
        _password = Fernet.generate_key().decode()
        _control_interface.debug(f"New Password! {_password}")
        while not _respawn_password and i <= 180:
            time.sleep(1)
            i += 1
        _respawn_password = False


# Public
def register_system_main(control_interface: "CoreControlInterface"):
    """
    子服务器账户系统主程序

    Args:
        control_interface (CoreControlInterface): 控制核心
    """
    global _control_interface
    _control_interface = control_interface

    _spawn_password()


def get_password() -> str:
    """
    获取初始化密钥

    :return str: 密钥字符串
    """
    _control_interface.info("Wait...")
    global _respawn_password
    _respawn_password = True
    time.sleep(1.2)
    data = {
        "ip": {
            "config": _control_interface.get_config()["ip"],
            "inside": get_all_internal_ips(),
            "outside": get_external_ip(),
        },
        "port": _control_interface.get_config()["port"],
        "password": _password,
    }
    data = encode_base64(json.dumps(data))
    return data


def get_register_password() -> str:
    """
    获取初始化临时密钥

    :return: 密钥字符串
    """
    return _password
