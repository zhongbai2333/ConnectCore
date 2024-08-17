from mcdreforged.api.all import PluginServerInterface


####################
# Public
####################
class ConnectCoreServerInterface:
    def __init__(
        self, pluginid: str = "system", mcdr_core: PluginServerInterface = None
    ):
        """
        ConnectCore 的主 API 控制器

        Args:
            pluginid (str): 插件的ID
            mcdr_core (PluginServerInterface): MCDR 插件控制器, 默认为 None
        """
        from connect_core.cli import LogSystem
        self.pluginid = pluginid
        self.mcdr_core = mcdr_core
        self.language = (
            self.get_config()["language"]
            if "language" in self.get_config().keys()
            else "en_us"
        )
        self.log_system = LogSystem(
            pluginid,
            (
                self.get_config()["debug"]
                if "debug" in self.get_config().keys()
                else False
            ),
            mcdr_core,
        )

    def is_mcdr(self):
        """
        获取MCDR状态

        Returns:
            bool: 是/否，MCDR状态
        """
        return True if self.mcdr_core else False

    def get_config(self):
        """
        获取设置文件

        **注: MCDR环境下请使用MCDR相关API, 使用此函数将不被响应！**

        Returns:
            dict: 完整的配置项字典
        """
        from connect_core.api.storage import JsonDataEditor

        config_path = (
            f"./config/{self.pluginid}/config.json"
            if self.pluginid != "system"
            else "./config.json"
        )
        return JsonDataEditor(config_path).read()

    def translate(self, key: str) -> str:
        """
        获取翻译项

        **注: MCDR环境下请使用MCDR相关API, 使用此函数将不被响应！**

        Args:
            key (str): 翻译文件关键字

        Returns:
            str: 翻译文本
        """
        from connect_core.api.storage import YmlLanguage

        if self.mcdr_core:
            if self.pluginid == "system":
                return self._tr(key)
        else:
            key_n = "connect_core." + key
            key_n = key_n.split(".")
            return self._get_nested_value(
                YmlLanguage(self.language).translate, key_n
            )

    def tr(self, key: str):
        """
        获取翻译项 | `translate函数的别称`

        **注: MCDR环境下请使用MCDR相关API, 使用此函数将不被响应！**

        Args:
            key (str): 翻译文件关键字

        Returns:
            str: 翻译文本
        """
        return self.translate(key)

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

    def _get_nested_value(self, data, keys_path, default=None):
        for key in keys_path:
            if isinstance(data, dict) and key in data:
                data = data[key]
            else:
                return default
        return data

    def _tr(self, key: str) -> str:
        from mcdreforged.api.all import ServerInterface

        return ServerInterface.si().tr("connect_core." + key)
