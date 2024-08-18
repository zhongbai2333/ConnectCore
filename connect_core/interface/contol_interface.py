# public
class ControlInterface:
    def __init__(self, sid: str, self_path: str, config_path: str):
        """
        控制接口初始化
        """
        from connect_core.log_system import LogSystem
        from connect_core.cli.cli_core import CommandLineInterface

        self.sid = sid  # ID
        self.self_path = self_path  # 自身路径
        self.config_path = config_path  # 配置文件路径
        self.log_system = LogSystem(
            sid,
            (
                self.get_config()["debug"]
                if "debug" in self.get_config().keys()
                else False
            ),
        )
        self.language = (
            self.get_config()["language"]
            if "language" in self.get_config().keys()
            else "en_us"
        )
        self.cli_core = CommandLineInterface(self)

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
    def translate(self, key: str) -> str:
        """
        获取翻译项

        Args:
            key (str): 翻译文件关键字

        Returns:
            str: 翻译文本
        """
        from connect_core.storage import YmlLanguage
        from connect_core.mcdr.mcdr_entry import get_mcdr

        if get_mcdr():
            return self._tr(key)
        else:
            key_n = f"{self.sid}." + key
            key_n = key_n.split(".")
            return self._get_nested_value(
                YmlLanguage(self.self_path, self.language).translate, key_n
            )

    def tr(self, key: str):
        """
        获取翻译项 | `translate函数的别称`

        Args:
            key (str): 翻译文件关键字

        Returns:
            str: 翻译文本
        """
        return self.translate(key)

    def _get_nested_value(self, data, keys_path, default=None):
        for key in keys_path:
            if isinstance(data, dict) and key in data:
                data = data[key]
            else:
                return default
        return data

    def _tr(self, key: str) -> str:
        from mcdreforged.api.all import ServerInterface

        return ServerInterface.si().tr(f"{self.sid}." + key)

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

    # ========
    #   Send
    # ========
    def send_data(self, server_id: str, data: dict):
        """
        向指定的服务器发送消息。

        Args:
            server_id (str): 子服务器的唯一标识符。
            data (str): 要发送的数据。
        """
        from connect_core.websocket.websocket_server import websocket_server

        if websocket_server:
            from connect_core.websocket.websocket_server import (
                send_data as server_send_data,
            )

            server_send_data(self.sid, server_id, data)
        else:
            from connect_core.websocket.websocket_client import (
                send_data as client_send_data,
            )

            client_send_data(self.sid, server_id, data)

    def send_file(self, server_id: str, file_path: str, save_path: str = None):
        """
        向指定的服务器发送文件。

        Args:
            server_id (str): 子服务器的唯一标识符。
            file_path (str): 要发送的文件目录。
            save_path (str): 要保存的位置。
        """
        from connect_core.websocket.websocket_server import websocket_server

        if websocket_server:
            from connect_core.websocket.websocket_server import (
                send_file as server_send_file,
            )

            server_send_file(self.sid, server_id, file_path, save_path)
        else:
            from connect_core.websocket.websocket_client import (
                send_file as client_send_file,
            )

            client_send_file(self.sid, server_id, file_path, save_path)
