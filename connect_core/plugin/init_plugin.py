import os
import zipfile
import importlib.util
import sys
import traceback
from typing import TYPE_CHECKING, Dict

if TYPE_CHECKING:
    from connect_core.interface.control_interface import CoreControlInterface

from connect_core.interface.control_interface import PluginControlInterface

plugin_list: Dict[int, "PluginLoader"] = {}
_control_interface = None


class PluginLoader:
    def __init__(self, plugin_zip_path):
        self.plugin_zip_path = plugin_zip_path
        self.plugin_module = None
        self.plugin_info = {}

    def _load_module_from_memory(self, module_name, module_code):
        """
        从内存中加载模块并返回模块对象。

        Args:
            module_name (str): 模块名称
            module_code (bytes): 模块字节码

        Returns:
            ModuleType: 加载的模块对象
        """
        spec = importlib.util.spec_from_loader(module_name, loader=None)
        module = importlib.util.module_from_spec(spec)
        exec(module_code, module.__dict__)
        sys.modules[module_name] = module
        return module

    def load_plugin(self):
        """
        从 ZIP 文件中加载并初始化插件。
        """
        with zipfile.ZipFile(self.plugin_zip_path, "r") as zip_file:
            # 从 plugin.json 读取入口点
            try:
                with zip_file.open("connectcore.plugin.json") as json_file:
                    import json

                    self.plugin_info = json.load(json_file)
                    entrypoint = self.plugin_info["entrypoint"].replace(".", "/") + ".py"

                # 获取入口点代码
                with zip_file.open(entrypoint) as entry_file:
                    module_code = entry_file.read()

                # 动态加载模块
                module_name = self.plugin_info["id"]
                self.plugin_module = self._load_module_from_memory(module_name, module_code)

                _control_interface.info(
                    _control_interface.tr("plugin.load_finish").format(
                        self.plugin_info["name"], self.plugin_info["version"]
                    )
                )
            except Exception as e:
                _control_interface.error(
                    _control_interface.tr("plugin.cant_load").format(
                        self.plugin_zip_path
                    )
                )

    def initialize_plugin(self):
        """调用插件的初始化函数"""
        if hasattr(self.plugin_module, "on_load"):
            try:
                self.plugin_module.on_load(
                    PluginControlInterface(
                        self.plugin_info["id"],
                        self.plugin_zip_path,
                        f"config/{self.plugin_info['id']}/config.json",
                    )
                )
            except TypeError as e:
                _control_interface.error(
                    f"Plugin {self.plugin_info['name']} Error: \n"
                    + traceback.format_exc()
                )
        else:
            _control_interface.warn(
                _control_interface.tr("plugin.cant_initialize").format(
                    self.plugin_info["name"]
                )
            )

    def new_connect(self, server_list: list):
        """
        服务器新的连接

        Args:
            server_list (list): 服务器列表
        """
        if hasattr(self.plugin_module, "new_connect"):
            try:
                self.plugin_module.new_connect(server_list)
            except TypeError as e:
                _control_interface.error(
                    f"Plugin {self.plugin_info['name']} Error: \n"
                    + traceback.format_exc()
                )

    def del_connect(self, server_list: list):
        """
        服务器断开的连接

        Args:
            server_list (list): 服务器列表
        """
        if hasattr(self.plugin_module, "del_connect"):
            try:
                self.plugin_module.del_connect(server_list)
            except TypeError as e:
                _control_interface.error(
                    f"Plugin {self.plugin_info['name']} Error: \n"
                    + traceback.format_exc()
                )

    def connected(self):
        """
        连接成功
        """
        if hasattr(self.plugin_module, "connected"):
            try:
                self.plugin_module.connected()
            except TypeError as e:
                _control_interface.error(
                    f"Plugin {self.plugin_info['name']} Error: \n"
                    + traceback.format_exc()
                )

    def disconnected(self):
        """
        断开连接
        """
        if hasattr(self.plugin_module, "disconnected"):
            try:
                self.plugin_module.disconnected()
            except TypeError as e:
                _control_interface.error(
                    f"Plugin {self.plugin_info['name']} Error: \n"
                    + traceback.format_exc()
                )

    def recv_data(self, data: dict):
        """
        收到数据包

        Args:
            data (dict): 收到的数据
        """
        if hasattr(self.plugin_module, "recv_data"):
            try:
                self.plugin_module.recv_data(data)
            except TypeError as e:
                _control_interface.error(
                    f"Plugin {self.plugin_info['name']} Error: \n"
                    + traceback.format_exc()
                )

    def recv_file(self, file: str):
        """
        收到文件

        Args:
            file (str): 收到的文件地址
        """
        if hasattr(self.plugin_module, "recv_file"):
            try:
                self.plugin_module.recv_file(file)
            except TypeError as e:
                _control_interface.error(
                    f"Plugin {self.plugin_info['name']} Error: \n"
                    + traceback.format_exc()
                )

    def unload_plugin(self):
        """卸载插件并清理资源"""
        if hasattr(self.plugin_module, "on_unload"):
            try:
                self.plugin_module.on_unload()
            except Exception as e:
                _control_interface.error(
                    f"Plugin {self.plugin_info['name']} Unload Error: \n"
                    + traceback.format_exc()
                )

        # 删除模块并从 sys.modules 中移除
        module_name = self.plugin_info["id"]
        if module_name in sys.modules:
            del sys.modules[module_name]

        self.plugin_module = None
        _control_interface.info(
            _control_interface.tr("plugin.unload_finish").format(
                self.plugin_info["name"]
            )
        )

    def reload_plugin(self):
        """重载插件"""
        self.unload_plugin()
        self.load_plugin()
        self.initialize_plugin()


# Tools
def list_all_files(directory, extension=None):
    """
    获取指定目录下所有指定后缀名的文件。

    Args:
        directory (str): 目标目录的路径。
        extension (str, optional): 文件后缀名（例如 ".txt"）。默认为 None，表示获取所有文件。

    Returns:
        list: 符合条件的文件路径列表。
    """
    files_list = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            if extension is None or file.endswith(extension):
                files_list.append(os.path.join(root, file))
    return files_list


# Public
def init_plugin_main(control_interface: "CoreControlInterface"):
    """
    插件初始化
    """
    global _control_interface
    dirs = "plugins"
    _control_interface = control_interface
    global plugin_list
    if not os.path.exists(dirs):
        os.makedirs(dirs)
    for plugin_path in list_all_files("plugins", ".mcdr"):
        plugin = PluginLoader(plugin_path)
        plugin.load_plugin()
        plugin.initialize_plugin()
        plugin_list[plugin.plugin_info["id"]] = plugin


def new_connect(server_list: list) -> None:
    """
    新的连接

    Args:
        sid (str): 插件ID
        server_list (list): 服务器列表
    """
    for plugin in plugin_list.values():
        plugin.new_connect(server_list)


def del_connect(server_list: list) -> None:
    """
    断开的连接

    Args:
        sid (str): 插件ID
        server_list (list): 服务器列表
    """
    for plugin in plugin_list.values():
        plugin.del_connect(server_list)


def connected():
    """
    连接成功
    """
    for plugin in plugin_list.values():
        plugin.connected()


def disconnected():
    """
    断开连接
    """
    for plugin in plugin_list.values():
        plugin.disconnected()


def recv_data(sid: str, data: dict):
    """
    收到数据包

    Args:
        sid (str): 插件ID
        data (dict): 收到的数据
    """
    if sid in plugin_list.keys():
        plugin_list[sid].recv_data(data)
    else:
        _control_interface.error(f"Can't Found Plugin {sid}")


def recv_file(sid: str, file: str):
    """
    收到文件

    Args:
        sid (str): 插件ID
        file (str): 收到的文件地址
    """
    if sid in plugin_list.keys():
        plugin_list[sid].recv_file(file)
    else:
        _control_interface.error(f"Can't Found Plugin {sid}")


def unload_plugin(sid: str):
    """
    卸载插件

    Args:
        sid (str): 插件ID
    """
    if sid in plugin_list.keys():
        plugin_list[sid].unload_plugin()
    else:
        _control_interface.error(f"Can't Found Plugin {sid}")


def reload_plugin(sid: str):
    """
    重载插件

    Args:
        sid (str): 插件ID
    """
    if sid in plugin_list.keys():
        plugin_list[sid].reload_plugin()
    else:
        _control_interface.error(f"Can't Found Plugin {sid}")
