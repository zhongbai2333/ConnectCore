import os
import time
import html
import threading
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit import print_formatted_text

from mcdreforged.api.all import PluginServerInterface


# 日志系统类
class LogSystem:
    def __init__(
        self,
        sid: str,
        debug: bool = False,
        filelog: str = None,
        path: str = "logs/",
        mcdr: PluginServerInterface | None = None,
    ) -> None:
        """
        初始化日志系统，创建日志文件夹和文件。

        Args:
            sid (str): 插件ID
            debug (bool): 是否启用debug, 默认为 False
            filelog (str): 日志文件的名称。
            path (str): 日志文件的存储路径。
        """
        from connect_core.mcdr.mcdr_entry import get_mcdr

        if not os.path.exists(path):
            os.makedirs(path)
        if not filelog:
            filelog = f"Log-{time.strftime('%b_%d-%H_%M_%S', time.localtime())}.log"
        self.logfile = os.path.join(path, filelog)
        self.mcdr_core = mcdr if mcdr else get_mcdr()
        self.sid = sid
        self.debug_mode = debug

    def _log(self, level: str, msg: str) -> None:
        """
        输出带有时间戳和颜色的日志信息，同时写入日志文件。

        Parameters:
            level (str): 日志级别，如'INFO'、'WARN'、'ERROR'、'DEBUG'。
            msg (str): 要记录的日志消息。
        """
        with open(self.logfile, "a", encoding="utf-8") as file:
            timestamp = time.strftime("%H:%M:%S", time.localtime())
            colored_level = self._get_colored_text(level)
            # 使用 html.escape 转义日志消息中的特殊字符
            escaped_msg = html.escape(msg)
            # 解析颜色代码并转换为HTML格式
            formatted_message = f"({threading.current_thread().name}) [{timestamp}] {colored_level} [{self.sid}] {self._parse_color_codes(escaped_msg)}"
            print_formatted_text(HTML(formatted_message))
            file.write(
                f"({threading.current_thread().name}) [{timestamp}] [{level}] [{self.sid}] {msg}\n"
            )

    def info(self, *msg) -> None:
        """
        输出INFO级别的日志信息。

        Args:
            msg (str): 日志消息内容。
        """
        self._log_msg("INFO", *msg)

    def warn(self, *msg) -> None:
        """
        输出WARN级别的日志信息。

        Args:
            msg (str): 日志消息内容。
        """
        self._log_msg("WARN", *msg)

    def error(self, *msg) -> None:
        """
        输出ERROR级别的日志信息。

        Args:
            msg (str): 日志消息内容。
        """
        self._log_msg("ERROR", *msg)

    def debug(self, *msg) -> None:
        """
        如果处于DEBUG模式, 输出DEBUG级别的日志信息。

        Args:
            msg (str): 日志消息内容。
        """
        if self.debug_mode:
            self._log_msg("DEBUG", *msg)

    def _log_msg(self, level: str, *msg) -> None:
        """
        根据是否有mcdr_core来决定日志输出方式。

        Args:
            level (str): 日志级别。
            msg (str): 日志消息内容。
        """
        if self.mcdr_core:
            if level == "DEBUG":
                self.mcdr_core.logger.info("[DEBUG] " + "".join(msg))
            else:
                getattr(self.mcdr_core.logger, level.lower())("".join(msg))
        else:
            self._log(level, "".join(msg))

    def _get_colored_text(self, level: str) -> str:
        """
        获取带颜色的日志等级文本。

        Args:
            level (str): 日志级别。

        Returns:
            str: 带颜色的日志等级字符串。
        """
        color_codes = {
            "INFO": "green",
            "WARN": "yellow",
            "ERROR": "red",
            "DEBUG": "blue",
        }
        return f'<b><style fg="{color_codes[level]}">[{level}]</style></b>'

    def _parse_color_codes(self, msg: str) -> str:
        """
        解析颜色代码并转换为HTML格式。

        Args:
            msg (str): 包含颜色代码的日志消息。

        Returns:
            str: 转换后的日志消息，带有HTML格式的颜色。
        """
        color_map = {
            "§0": "black",
            "§1": "darkblue",
            "§2": "darkgreen",
            "§3": "darkaqua",
            "§4": "darkred",
            "§5": "darkpurple",
            "§6": "gold",
            "§7": "gray",
            "§8": "darkgray",
            "§9": "blue",
            "§a": "green",
            "§b": "aqua",
            "§c": "red",
            "§d": "lightpurple",
            "§e": "yellow",
            "§f": "white",
        }
        for code, color in color_map.items():
            msg = msg.replace(code, f'<style fg="{color}">')
        msg = msg.replace("§r", "</style>")
        # 确保所有颜色代码都被关闭
        open_tags = msg.count("<style")
        close_tags = msg.count("</style>")
        msg += "</style>" * (open_tags - close_tags)
        return msg
