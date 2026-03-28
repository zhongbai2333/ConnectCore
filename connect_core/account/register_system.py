from __future__ import annotations

import time
import threading
import json
from cryptography.fernet import Fernet
from typing import Optional, TYPE_CHECKING
from connect_core.tools.tools import (
    new_thread,
    encode_base64,
    get_all_internal_ips,
    get_external_ip,
)

if TYPE_CHECKING:
    from connect_core.interface.control_interface import CoreControlInterface

_control_interface: Optional["CoreControlInterface"] = None
_password = ""
_respawn_event = threading.Event()
_thread_started = False


def _require_control_interface() -> "CoreControlInterface":
    if _control_interface is None:
        raise RuntimeError("Register system has not been initialized")
    return _control_interface


@new_thread("RegisterSystem")
def _spawn_password() -> None:
    """
    周期性自动刷新密码：只有在 180 秒内都没有 get_password() 调用，
    才真正生成新密码；每次 get_password() 调用都会把计时器重置。
    """
    global _password

    # 生成第一把密钥
    _password = Fernet.generate_key().decode()
    interface = _require_control_interface()

    # 记录上一次“生成”或“手动延长”时刻
    last_reset = time.monotonic()

    while True:
        time.sleep(1)

        # 如果收到了重置信号，就清标志、刷新 last_reset
        if _respawn_event.is_set():
            _respawn_event.clear()
            last_reset = time.monotonic()
            interface.logger.debug("Password timer reset by get_password()")
            continue

        # 如果已经超过 180 秒，则生成新密钥，并重置计时
        if time.monotonic() - last_reset >= 180:
            _password = Fernet.generate_key().decode()
            last_reset = time.monotonic()


def register_system_main(control_interface: "CoreControlInterface") -> None:
    global _control_interface, _thread_started
    _control_interface = control_interface
    if not _thread_started:
        _spawn_password()  # pyright: ignore[reportCallIssue]
        _thread_started = True


def get_password() -> str:
    """
    获取密钥，并重置自动刷新计时器。
    """
    interface = _require_control_interface()
    interface.logger.info("Wait...")
    _respawn_event.set()

    data = {
        "ip": {
            "config": interface.config.ip,
            "inside": get_all_internal_ips(),
            "outside": get_external_ip(),
        },
        "port": interface.config.port,
        "password": _password,
    }
    return encode_base64(json.dumps(data))


def get_register_password() -> str:
    return _password
