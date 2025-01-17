import os
import time
import html
import threading
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit import print_formatted_text


# 日志系统类
class LogSystem:
    def __init__(
        self,
        sid: str,
        debug: bool = False,
        filelog: str = None,
        path: str = "logs/",
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
        self.mcdr_core = get_mcdr()
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
            formatted_message = f"({threading.current_thread().name}) [{timestamp}] {colored_level} [{self.sid}] {escaped_msg}"
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
