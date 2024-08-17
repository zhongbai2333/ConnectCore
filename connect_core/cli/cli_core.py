from prompt_toolkit import PromptSession
from prompt_toolkit.completion import NestedCompleter
from prompt_toolkit.patch_stdout import patch_stdout
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from connect_core.api.server_interface import ConnectCoreServerInterface

# 命令行界面类
class CommandLineInterface:
    def __init__(self, interface: 'ConnectCoreServerInterface', prompt: str = ">>> "):
        """
        初始化命令行界面类，设置默认提示符和补全器。

        Args:
            connect_interface (ConnectCoreServerInterface): API接口
        """
        self.prompt = prompt
        self.completer = NestedCompleter.from_nested_dict({})
        self.commands = {}
        self.session = PromptSession(completer=self.completer)
        self.running = True
        self.interface = interface

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
                self.interface.info("正在退出...")

    def handle_input(self, text):
        """
        处理用户输入的命令并执行相应的操作。

        Args:
            text (str): 用户输入的文本。
        """
        if text:
            command = text.split()[0]
            if command in self.commands:
                self.commands[command](" ".join(text.split()[1:]))
            else:
                self.interface.warn(f"未知命令: {command}")

    def start(self):
        """
        启动命令行界面，开启输入循环。
        """
        self.input_loop()
