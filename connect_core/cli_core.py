import os
import time
import html
from prompt_toolkit import PromptSession, print_formatted_text
from prompt_toolkit.completion import NestedCompleter
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.formatted_text import HTML
from mcdreforged.api.all import PluginServerInterface

global cli


# 日志系统类
class LogSystem:
    def __init__(
        self,
        mcdr_core: PluginServerInterface = None,
        filelog: str = None,
        path: str = "logs/",
    ) -> None:
        """
        初始化日志系统，创建日志文件夹和文件。

        Args:
            mcdr_core (PluginServerInterface): MCDR核心接口, 用于集成日志系统。
            filelog (str): 日志文件的名称。
            path (str): 日志文件的存储路径。
        """
        if not os.path.exists(path):
            os.makedirs(path)
        if not filelog:
            filelog = f"Log-{time.strftime('%b_%d-%H_%M_%S', time.localtime())}.log"
        self.logfile = os.path.join(path, filelog)
        self.mcdr_core = mcdr_core

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
            formatted_message = f"[{timestamp}] {colored_level} {escaped_msg}"
            print_formatted_text(HTML(formatted_message))
            file.write(f"[{timestamp}] [{level}] {msg}\n")

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
        if self._is_debug_mode():
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

    def _is_debug_mode(self) -> bool:
        """
        判断是否处于DEBUG模式。

        Returns:
            bool: 如果处于DEBUG模式, 返回True; 否则返回False。
        """
        from connect_core.get_config_translate import config

        return config("debug")


# 命令行界面类
class CommandLineInterface:

    def __init__(self, mcdr_core: PluginServerInterface = None, prompt: str = ">>> "):
        """
        初始化命令行界面类，设置默认提示符和补全器。
        """
        self.prompt = prompt
        self.completer = NestedCompleter.from_nested_dict({})
        self.commands = {}
        self.session = PromptSession(completer=self.completer)
        self.running = True
        self.log_system = LogSystem(mcdr_core)

    def set_prompt(self, prompt):
        """
        设置提示符文本。

        Args:
            prompt (str): 新的提示符文本。
        """
        self.prompt = prompt

    def set_completer_words(self, words):
        """
        设置补全器的单词列表。

        Args:
            words (dict): 新的补全单词列表。
        """
        self.completer = NestedCompleter.from_nested_dict(words)

    def add_command(self, command, action):
        """
        注册一个新的命令。

        Args:
            command (str): 命令的名称。
            action (callable): 执行该命令的函数。
        """
        self.commands[command] = action

    def remove_command(self, command):
        """
        移除一个已注册的命令。

        Args:
            command (str): 要移除的命令名称。
        """
        if command in self.commands:
            del self.commands[command]

    def flush_cli(self):
        """
        刷新命令系统
        """
        self.session.app.current_buffer.completer = self.completer
        self.session.app.invalidate()

    def log_output(self, message, level="info"):
        """
        根据指定的日志级别输出日志信息。

        Args:
            message (str): 要记录的日志消息。
            level (str): 日志级别，默认为"info"。
        """
        if level == "info":
            self.log_system.info(message)
        elif level == "warn":
            self.log_system.warn(message)
        elif level == "error":
            self.log_system.error(message)
        elif level == "debug":
            self.log_system.debug(message)

    def input_loop(self):
        """
        开始输入循环，处理用户输入。

        捕获KeyboardInterrupt和EOFError以安全地停止循环。
        """
        while self.running:
            try:
                with patch_stdout():
                    text = self.session.prompt(self.prompt, completer=self.completer)
                    self.handle_input(text)
            except (KeyboardInterrupt, EOFError):
                self.running = False
                self.log_output("正在退出...", level="info")

    def handle_input(self, text):
        """
        处理用户输入的命令并执行相应的操作。

        Args:
            text (str): 用户输入的文本。
        """
        command = text.split()[0]
        if command in self.commands:
            self.commands[command](" ".join(text.split()[1:]))
        else:
            self.log_output(f"未知命令: {command}", level="warn")

    def start(self):
        """
        启动命令行界面，开启输入循环。
        """
        self.input_loop()


# 主函数
def cli_core_init(mcdr_core: PluginServerInterface = None, prompt: str = ">>> "):
    """
    命令行界面初始化函数

    Args:
        mcdr_core (PluginServerInterface): MCDR核心导入, 默认为None
        prompt (str): 命令提示词, 默认为">>> "
    """
    global cli

    cli = CommandLineInterface(mcdr_core, prompt)


def add_command(command, action) -> None:
    """
    注册一个新的命令。

    Args:
        command (str): 命令的名称。
        action (callable): 执行该命令的函数。
    """
    cli.add_command(command, action)


def remove_command(command):
    """
    移除一个已注册的命令。

    Args:
        command (str): 要移除的命令名称。
    """
    cli.remove_command(command)


def set_completer_words(words):
    """
    设置补全器的单词列表。

    Args:
        words (list): 新的补全单词列表。
    """
    cli.set_completer_words(words)


def set_prompt(prompt):
    """
    设置提示符文本。

    Args:
        prompt (str): 新的提示符文本。
    """
    cli.set_prompt(prompt)


def stop_cli_core():
    """
    退出命令行界面。
    """
    cli.running = False


def start_cli_core():
    """
    开始命令行界面。
    """
    cli.start()


def restart_cli_core():
    """
    重启命令行界面
    """
    cli.flush_cli()


def info_print(msg):
    """
    输出INFO级别的日志信息。

    Args:
        msg (str): 日志消息内容。
    """
    cli.log_output(msg, level="info")


def warn_print(msg):
    """
    输出WARN级别的日志信息。

    Args:
        msg (str): 日志消息内容。
    """
    cli.log_output(msg, level="warn")


def error_print(msg):
    """
    输出ERROR级别的日志信息。

    Args:
        msg (str): 日志消息内容。
    """
    cli.log_output(msg, level="error")


def debug_print(msg):
    """
    输出ERROR级别的日志信息。

    Args:
        msg (str): 日志消息内容。
    """
    cli.log_output(msg, level="debug")
