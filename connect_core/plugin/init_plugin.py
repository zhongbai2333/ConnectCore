import os
import zipfile
import json
import traceback
import sys
import importlib.util
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from connect_core.interface.control_interface import CoreControlInterface

from connect_core.interface.control_interface import PluginControlInterface

_control_interface = None


class PluginLoader:
    def __init__(self, plugin_dir: str):
        """初始化插件加载器，指定插件目录"""
        self.plugin_dir = plugin_dir
        self.plugins = {}

    def load_plugins(self):
        """加载插件目录中的所有插件"""
        if not os.path.exists(self.plugin_dir):
            os.makedirs(self.plugin_dir)
        for plugin_file in os.listdir(self.plugin_dir):
            if plugin_file.endswith(".mcdr"):
                self.load_plugin(plugin_file)

    def load_plugin(self, plugin_file: str):
        """加载单个插件"""
        plugin_path = os.path.join(self.plugin_dir, plugin_file)

        try:
            # 将插件路径添加到 sys.path，以便从压缩包中导入
            sys.path.insert(0, plugin_path)

            # 读取 mcdr (zip) 文件并解析 connectcore.plugin.json
            with zipfile.ZipFile(plugin_path, "r") as z:
                with z.open("connectcore.plugin.json") as f:
                    plugin_info = json.load(f)

                entry_point = plugin_info["entrypoint"]
                plugin_id = plugin_info["id"]

                # 使用 importlib.util 加载指定的入口点模块
                module_spec = importlib.util.find_spec(entry_point)
                if module_spec is None:
                    _control_interface.error(
                        f"Module {entry_point} not found in {plugin_file}"
                    )
                    return

                plugin_module = importlib.util.module_from_spec(module_spec)
                module_spec.loader.exec_module(plugin_module)

                # 创建 PluginControlInterface 并传递给插件的 on_load
                plugin_control_interface = PluginControlInterface(
                    plugin_info["id"],
                    plugin_path,
                    f"config/{plugin_info['id']}/config.json",
                )

                if hasattr(plugin_module, "on_load"):
                    plugin_module.on_load(plugin_control_interface)
                    _control_interface.info(
                        _control_interface.tr(
                            "plugin.load_finish",
                            plugin_info["name"],
                            plugin_info["version"],
                        )
                    )
                else:
                    _control_interface.warn(
                        _control_interface.tr(
                            "plugin.cant_initialize", plugin_info["name"]
                        )
                    )

                # 保存插件信息和模块
                self.plugins[plugin_id] = {
                    "info": plugin_info,
                    "module": plugin_module,
                    "path": plugin_path,
                }

        except Exception as e:
            _control_interface.error(
                _control_interface.tr("plugin.cant_load", plugin_info["name"])
            )
            _control_interface.error(traceback.format_exc())

    def unload(self, plugin_id: str):
        """卸载插件并调用其 on_unload 函数"""
        if plugin_id in self.plugins:
            plugin = self.plugins[plugin_id]
            plugin_module = plugin["module"]

            if hasattr(plugin_module, "on_unload"):
                try:
                    plugin_module.on_unload()
                    _control_interface.info(
                        _control_interface.tr(
                            "plugin.unload_finish", plugin["info"]["name"]
                        )
                    )
                except Exception as e:
                    _control_interface.error(
                        f"Error while unloading plugin {plugin['info']['name']}: \n{traceback.format_exc()}"
                    )

            # 删除插件
            del self.plugins[plugin_id]

            # 从 sys.path 中移除插件路径
            sys.path.remove(plugin["path"])

    def reload(self, plugin_id: str):
        """重载插件，先卸载再加载"""
        if plugin_id in self.plugins and "path" in self.plugins[plugin_id].keys():
            plugin_file = self.plugins[plugin_id]["path"].split("/")[-1]
            self.unload(plugin_id)
            self.load_plugin(plugin_file)
        else:
            from connect_core.mcdr.mcdr_entry import get_mcdr

            get_mcdr().reload_plugin(plugin_id)

    def mcdr_add_entry_point(self, sid: str, entry_point: str) -> bool:
        """添加入口点"""
        try:
            self.plugins[sid] = {
                "module": importlib.import_module(entry_point),
            }
            return True
        except ImportError as e:
            _control_interface.error(f"[{sid}] Import error: {e}")
            return False
        except Exception as e:
            _control_interface.error(f"[{sid}] An error occurred: {e}")
            return False

    def handle_event(self, event: str, plugin_id: str = None, *args):
        """处理插件事件，通知所有插件，如 new_connect, del_connect, recv_data 等"""
        if plugin_id:
            if plugin_id not in self.plugins.keys():
                _control_interface.log_system.error(f"Unkown Plugin ID: {plugin_id}")
                return
            plugin_module = self.plugins[plugin_id]["module"]
            if hasattr(plugin_module, event):
                try:
                    getattr(plugin_module, event)(*args)  # 传递参数
                except Exception as e:
                    _control_interface.error(
                        f"Plugin {plugin_id} Error: \n{traceback.format_exc()}"
                    )
        else:
            for _, plugin in self.plugins.items():
                plugin_module = plugin["module"]

                if hasattr(plugin_module, event):
                    try:
                        getattr(plugin_module, event)(*args)  # 传递参数
                    except Exception as e:
                        _control_interface.error(
                            f"Plugin {plugin_id} Error: \n{traceback.format_exc()}"
                        )

    # 事件处理函数，通知所有插件
    def new_connect(self, server_list: list):
        self.handle_event("new_connect", None, server_list)

    def del_connect(self, server_list: list):
        self.handle_event("del_connect", None, server_list)

    def connected(self):
        self.handle_event("connected")

    def disconnected(self):
        self.handle_event("disconnected")

    def recv_data(self, plugin_id: str, from_server_id: str, data: dict):
        self.handle_event("recv_data", plugin_id, from_server_id, data)

    def recv_file(self, plugin_id, from_server_id: str, file_path: str):
        self.handle_event("recv_file", plugin_id, from_server_id, file_path)


# Public
def init_plugin_main(control_interface: "CoreControlInterface"):
    """
    插件初始化
    """
    from connect_core.mcdr.mcdr_entry import get_mcdr

    global _control_interface, _plugin_loader
    _control_interface = control_interface
    if get_mcdr():
        _plugin_loader = PluginLoader(
            os.path.dirname(get_mcdr().get_plugin_file_path("connect_core"))
        )
    else:
        _plugin_loader = PluginLoader("plugins/")
        _plugin_loader.load_plugins()


def mcdr_add_entry_point(sid: str, entry_point: str) -> bool:
    """MCDR添加入口点"""
    return _plugin_loader.mcdr_add_entry_point(sid, entry_point)


def new_connect(server_list: list) -> None:
    """
    新的连接

    Args:
        sid (str): 插件ID
        server_list (list): 服务器列表
    """
    _plugin_loader.new_connect(server_list)


def del_connect(server_list: list) -> None:
    """
    断开的连接

    Args:
        sid (str): 插件ID
        server_list (list): 服务器列表
    """
    _plugin_loader.del_connect(server_list)


def connected():
    """
    连接成功
    """
    _plugin_loader.connected()


def disconnected():
    """
    断开连接
    """
    _plugin_loader.disconnected()


def recv_data(sid: str, from_server_id: str, data: dict):
    """
    收到数据包

    Args:
        sid (str): 插件ID
        from_server_id (str): 来自的服务器ID
        data (dict): 收到的数据
    """
    _plugin_loader.recv_data(sid, from_server_id, data)


def recv_file(sid: str, from_server_id: str, file: str):
    """
    收到文件

    Args:
        sid (str): 插件ID
        from_server_id (str): 来自的服务器ID
        file (str): 收到的文件地址
    """
    _plugin_loader.recv_file(sid, from_server_id, file)


def load_plugin(plugin_file: str):
    """
    加载插件
    Args:
        plugin_file (str): 插件文件路径
    """
    _plugin_loader.load_plugin(plugin_file)


def unload_plugin(sid: str):
    """
    卸载插件

    Args:
        sid (str): 插件ID
    """
    _plugin_loader.unload(sid)


def reload_plugin(sid: str):
    """
    重载插件

    Args:
        sid (str): 插件ID
    """
    _plugin_loader.reload(sid)


def get_plugins() -> dict:
    """
    获取插件列表

    :return: 插件列表
    """
    return _plugin_loader.plugins
