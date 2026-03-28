import time
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

import yaml  # type: ignore[import-untyped]
from mcdreforged.api.all import PluginServerInterface

from connect_core.context import GlobalContext
from connect_core.aes_encrypt import aes_main
from connect_core.account.register_system import register_system_main
from connect_core.interface.control_interface import (
    CoreControlInterface,
    PluginControlInterface,
)
from connect_core.plugin.init_plugin import init_plugin_main
from connect_core.websockets.server import websocket_server_main, websocket_server_stop
from connect_core.websockets.client import websocket_client_main, websocket_client_stop

if TYPE_CHECKING:
    from connect_core.mcdr.commands import CommandActions

__mcdr_server: Optional[PluginServerInterface] = None
_control_interface: Optional[CoreControlInterface] = None


def get_mcdr() -> Optional[PluginServerInterface]:
    return __mcdr_server


def _detect_server_mode(config_path: Path) -> bool:
    """通过读取配置文件判断是否为服务端模式。

    如果配置文件不存在或缺少客户端特有字段（account/password），则视为服务端。
    """
    if not config_path.exists():
        return True
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        # 客户端配置中含有 account 和 password 字段
        if "account" in raw and "password" in raw:
            return False
        return True
    except Exception:
        return True


def get_plugin_control_interface(
    sid: str, enter_point: Any, mcdr: PluginServerInterface
) -> Optional[PluginControlInterface]:
    from connect_core.tools.base_config import BaseConfig

    config_path = Path(f"{GlobalContext.get_path().parent}/config/{sid}/config.yml")
    try:
        config_file = BaseConfig.load(config_path=config_path)
    except Exception:
        config_file = None
    return PluginControlInterface(sid, None, config_file, mcdr)


def on_load(server: PluginServerInterface, _: Any) -> None:
    global __mcdr_server, _control_interface
    __mcdr_server = server

    # 在 GlobalContext 初始化前先确定 server_mode
    config_path = Path(
        f"{Path(server.get_data_folder()).parent}/connect_core/config.yml"
    )
    is_server = _detect_server_mode(config_path)

    GlobalContext(debug=0, server=is_server, mcdr=True, mcdr_interface=server)
    _control_interface = CoreControlInterface()

    from connect_core.mcdr.commands import CommandActions

    CommandActions(__mcdr_server, _control_interface)

    init_plugin_main(_control_interface)

    _control_interface.info(_control_interface.tr("mcdr.config_loaded"))
    _control_interface.info(_control_interface.tr("mcdr.plugin_loaded"))

    if GlobalContext.get_config_path().exists():
        if _control_interface.is_server:
            aes_main(_control_interface)
            register_system_main(_control_interface)
            websocket_server_main(
                _control_interface
            )  # pyright: ignore[reportCallIssue]
        else:
            aes_main(_control_interface, _control_interface.config.password)  # type: ignore[union-attr]
            websocket_client_main(
                _control_interface
            )  # pyright: ignore[reportCallIssue]


def on_server_startup(_: Any) -> None:
    if not GlobalContext.get_config_path().exists():
        if _control_interface:
            _control_interface.error(
                _control_interface.tr("mcdr.config_need_be_initialized")
            )


def on_unload(_: Any) -> None:
    if _control_interface is None:
        return

    if _control_interface.is_server:
        ws = websocket_server_stop()
        _control_interface.info("Waiting for WebSocket server to close...")
        if ws:
            while not ws.finish_close:
                time.sleep(0.5)
    else:
        ws = websocket_client_stop()  # type: ignore[assignment]
        _control_interface.info("Waiting for WebSocket client to close...")
        if ws:
            while not ws.finish_close:
                time.sleep(0.5)
