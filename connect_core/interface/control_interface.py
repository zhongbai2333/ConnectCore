from connect_core.log_system import LogSystem

from mcdreforged.api.types import PluginServerInterface

class CoreControlInterface:
    def __init__(self):
        import sys
        from connect_core.mcdr.mcdr_entry import get_mcdr

        self.sid = "connect_core"
        self.self_path = sys.argv[0]
        self.__mcdr_server = get_mcdr()
        if self.__mcdr_server:
            self.config_path = "./config/connect_core/config.json"
            self._is_server = self.get_config().get("is_server", False)
        else:
            from connect_core.cli.cli_entry import get_is_server

            self._is_server = get_is_server()
            self.config_path = "./config.json"
            self.language = self.get_config().get("language", "en_us")
        self.log_system = LogSystem(self.sid, self.get_config().get("debug", False))

    # =============
    #  Json Editer
    # =============
    def get_config(self, config_path: str = None) -> dict:
        """
        获取配置文件

        Args:
            config_path (str): 配置文件目录, 默认为插件或服务器默认 config 路径

        Returns:
            dict: 配置文件字典
        """
        from connect_core.storage import JsonDataEditor

        return JsonDataEditor(config_path if config_path else self.config_path).read()

    def save_config(self, config_data: dict, config_path: str = None) -> None:
        """
        写入配置文件

        Args:
            config_data (dict): 新的配置项字典
            config_path (str): 配置文件目录, 默认为插件或服务器默认 config 路径
        """
        from connect_core.storage import JsonDataEditor

        JsonDataEditor(config_path if config_path else self.config_path).write(
            config_data
        )

    # =============
    #   Translate
    # =============
    def translate(self, key: str, *args) -> str:
        """
        获取翻译项

        Args:
            key (str): 翻译文件关键字
            *args (tuple): 字段插入内容

        Returns:
            str: 翻译文本
        """
        from connect_core.storage import YmlLanguage

        if self.__mcdr_server:
            return self._tr(key, *args)
        else:
            key_n = f"{self.sid}." + key
            key_n = key_n.split(".")
            return self._get_nested_value(
                YmlLanguage(self.self_path, self.language).translate, key_n
            ).format(*args)

    def tr(self, key: str, *args):
        """
        获取翻译项 | `translate函数的别称`

        Args:
            key (str): 翻译文件关键字
            *args (tuple): 字段插入内容

        Returns:
            str: 翻译文本
        """
        return self.translate(key, *args)

    def _get_nested_value(self, data, keys_path, default=None):
        for key in keys_path:
            if isinstance(data, dict) and key in data:
                data = data[key]
            else:
                return default
        return data

    def _tr(self, key: str, *args) -> str:
        try:
            from mcdreforged.api.all import ServerInterface

            return ServerInterface.si().tr(f"{self.sid}." + key, *args)
        except ImportError:
            pass

    # =============
    #   Log Print
    # =============
    def info(self, msg: any):
        """
        输出INFO级别的日志信息。

        Args:
            msg (any): 日志消息内容。
        """
        self.log_system.info(str(msg))

    def warn(self, msg: any):
        """
        输出WARN级别的日志信息。

        Args:
            msg (any): 日志消息内容。
        """
        self.log_system.warn(str(msg))

    def error(self, msg: any):
        """
        输出ERROR级别的日志信息。

        Args:
            msg (any): 日志消息内容。
        """
        self.log_system.error(str(msg))

    def debug(self, msg: any):
        """
        输出DEBUG级别的日志信息。

        Args:
            msg (any): 日志消息内容。
        """
        self.log_system.debug(str(msg))

    # =========
    #   Tools
    # =========
    def is_server(self) -> bool:
        """
        判断是否为服务器

        Returns:
            bool: 是/否
        """
        return self._is_server


class PluginControlInterface(CoreControlInterface):
    def __init__(self, sid: str, self_path: str, config_path: str, mcdr: PluginServerInterface = None):
        """
        插件控制接口

        Args:
            sid (str): 插件ID
            self_path (str): 自身路径
            config_path (str): 配置文件路径
        """
        # 导入
        super().__init__()

        self.sid = sid
        self.self_path = self_path
        self.config_path = config_path
        self.log_system = LogSystem(self.sid, self.get_config().get("debug", False), mcdr=mcdr)

    # ========
    #   Send
    # ========
    def send_data(self, server_id: str, plugin_id: str, data: dict):
        """
        向指定的服务器发送消息。

        Args:
            server_id (str): 目标服务器的唯一标识符。
            plugin_id (str): 目标服务器插件的唯一标识符
            data (str): 要发送的数据。
        """
        if self._is_server:
            from connect_core.websocket.server import (
                send_data as server_send_data,
            )

            server_send_data("-----", self.sid, server_id, plugin_id, data)
        else:
            from connect_core.websocket.client import (
                send_data as client_send_data,
            )

            client_send_data(self.sid, server_id, plugin_id, data)

    def send_file(
        self, server_id: str, plugin_id: str, file_path: str, save_path: str
    ):
        """
        向指定的服务器发送文件。

        Args:
            server_id (str): 目标服务器的唯一标识符。
            plugin_id (str): 目标服务器插件的唯一标识符
            file_path (str): 要发送的文件目录。
            save_path (str): 要保存的位置。
        """
        from connect_core.websocket.server import websocket_server

        if websocket_server:
            from connect_core.websocket.server import (
                send_file as server_send_file,
            )

            server_send_file(
                "-----", self.sid, server_id, plugin_id, file_path, save_path
            )
        else:
            from connect_core.websocket.client import (
                send_file as client_send_file,
            )

            client_send_file(self.sid, server_id, plugin_id, file_path, save_path)

    # =========
    #   Tools
    # =========
    def get_server_id(self) -> str:
        """
        客户端反馈服务器ID

        Returns:
            str: 服务器ID
        """
        from connect_core.websocket.client import get_server_id

        if self.is_server():
            return None
        else:
            return get_server_id()

    def get_history_packet(self, server_id: str = None) -> list | None:
        """
        获取历史数据包，客户端无需参数

        Args:
            server_id (str): 服务器ID

        Returns:
            dict: 数据包
        """
        if self._is_server:
            from connect_core.websocket.server import get_history_data_packet

            if server_id:
                return get_history_data_packet(server_id)
            else:
                return None
        else:
            from connect_core.websocket.client import get_history_data_packet

            return get_history_data_packet()
