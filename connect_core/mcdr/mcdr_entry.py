from mcdreforged.api.all import *
from connect_core.interface.control_interface import (
    CoreControlInterface,
    PluginControlInterface,
)
from connect_core.mcdr.command import CommandActions
from connect_core.websocket.server import websocket_server_main, websocket_server_stop
from connect_core.websocket.client import websocket_client_main, websocket_client_stop
from connect_core.plugin.init_plugin import init_plugin_main, mcdr_add_entry_point
from connect_core.account.register_system import register_system_main

__mcdr_server, _control_interface = None, None


def get_mcdr() -> PluginServerInterface | None:
    """
    获取MCDR

    Returns:
        PluginServerInterface | None: MCDR状态
    """
    return __mcdr_server


def get_plugin_control_interface(
    sid: str, enter_point: str, mcdr: PluginServerInterface
) -> PluginControlInterface:
    """
    获取插件控制接口

    Args:
        sid (str): 插件ID
        enter_point (str): 入口点
        mcdr (PluginServerInterface): MCDR接口
    Returns:
        PluginControlInterface: 插件控制接口
    """
    try:
        if mcdr_add_entry_point(sid, enter_point):
            return PluginControlInterface(sid, None, f"./config/{sid}/config.json", mcdr)
        else:
            _control_interface.error(
                f"Failed to add entry point! Plugin:{sid}|{enter_point}"
            )
    except Exception as e:
        _control_interface.error(
            f"Failed to get plugin control interface! {e}\nMaybe the ConnectCore plugin is not initialized, please reload this Plugin when you initialize ConnectCore."
        )
        return None


# MCDR Start point
def on_load(server: PluginServerInterface, _):
    global __mcdr_server, _control_interface
    __mcdr_server = server
    _control_interface = CoreControlInterface()

    if not _control_interface.get_config():
        CommandActions(__mcdr_server, _control_interface)
    else:

        init_plugin_main(_control_interface)
        _control_interface.info(_control_interface.tr("mcdr.config_loaded"))
        _control_interface.info(
            _control_interface.tr("mcdr.plugin_loaded", "Connect Core")
        )
        config = _control_interface.get_config()
        if config["is_server"]:
            register_system_main(_control_interface)
            websocket_server_main(_control_interface)
        else:
            websocket_client_main(_control_interface)


def on_server_startup(_):
    # 服务器启动后执行的代码
    if not _control_interface.get_config():
        _control_interface.error(
            _control_interface.tr("mcdr.config_need_be_initialized")
        )


def on_unload(_):
    # 插件卸载时执行的代码
    if _control_interface.get_config().get("is_server", False):
        websocket_server_stop()
    else:
        websocket_client_stop()
