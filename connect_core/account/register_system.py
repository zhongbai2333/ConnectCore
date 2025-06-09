import time
import json
from cryptography.fernet import Fernet
from typing import TYPE_CHECKING
from connect_core.tools import (
    new_thread,
    encode_base64,
    get_all_internal_ips,
    get_external_ip,
)

if TYPE_CHECKING:
    from connect_core.interface.control_interface import CoreControlInterface

global _control_interface, _respawn_password
_password = ""
_respawn_password = False


@new_thread("RegisterSystem")
def _spawn_password():
    """
    周期性自动刷新密码：只有在 180 秒内都没有 get_password() 调用，
    才真正生成新密码；每次 get_password() 调用都会把计时器重置。
    """
    global _password, _respawn_password

    # 生成第一把密钥
    _password = Fernet.generate_key().decode()
    _control_interface.debug(f"New Password! {_password}")

    # 记录上一次“生成”或“手动延长”时刻
    last_reset = time.monotonic()

    while True:
        time.sleep(1)

        # 如果收到了重置信号，就清标志、刷新 last_reset
        if _respawn_password:
            _respawn_password = False
            last_reset = time.monotonic()
            _control_interface.debug("Password timer reset by get_password()")
            continue

        # 如果已经超过 180 秒，则生成新密钥，并重置计时
        if time.monotonic() - last_reset >= 180:
            _password = Fernet.generate_key().decode()
            _control_interface.debug(f"New Password! {_password}")
            last_reset = time.monotonic()


def register_system_main(control_interface: "CoreControlInterface"):
    global _control_interface
    _control_interface = control_interface
    _spawn_password()


def get_password() -> str:
    """
    获取密钥，并重置自动刷新计时器。
    """
    global _respawn_password
    _control_interface.info("Wait...")
    _respawn_password = True

    # 等待一下，确保 spawn 线程已处理 reset 信号
    time.sleep(0.1)

    data = {
        "ip": {
            "config": _control_interface.get_config("ip"),
            "inside": get_all_internal_ips(),
            "outside": get_external_ip(),
        },
        "port": _control_interface.get_config("port"),
        "password": _password,
    }
    return encode_base64(json.dumps(data))


def get_register_password() -> str:
    return _password
