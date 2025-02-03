import re
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import NestedCompleter
from prompt_toolkit.patch_stdout import patch_stdout
from connect_core.tools import new_thread
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from connect_core.api.interface import PluginControlInterface


# 命令行界面类
class CommandLineInterface:
    def __init__(self, interface: "PluginControlInterface", prompt: str = ">>> "):
        """
        初始化命令行界面类，设置默认提示符和补全器。

        Args:
            connect_interface (PluginControlInterface): API接口
        """
        self.prompt = prompt
        self.completer = {}
        self.commands = {}
        self.session = PromptSession(
            completer=NestedCompleter.from_nested_dict(self.completer)
        )
        self.running = True
        self.interface = interface

    def set_prompt(self, prompt):
        """
        设置提示符文本。

        Args:
            prompt (str): 新的提示符文本。
        """
        self.prompt = prompt

    def set_completer_words(self, sid, words):
        """
        设置补全器的单词列表。

        Args:
            sid (int): 插件的标识符。
            words (dict): 新的补全单词列表。
        """
        self.completer.setdefault(sid, {}).update(words)

    def add_command(self, sid, command, action):
        """
        注册一个新的命令。

        Args:
            sid (int): 插件的标识符。
            command (str): 命令的名称。
            action (callable): 执行该命令的函数。
        """
        commands = command.split()
        self.commands.setdefault(sid, {})
        for key in commands[:-1]:  # 迭代到倒数第二个元素，创建或找到路径
            if key not in self.commands[sid]:
                self.commands[sid][key] = {}  # 如果没有这个键，创建一个新的空字典
            self.commands[sid] = self.commands[sid][key]

        # 对于最后一个元素，赋予值
        self.commands[sid][commands[-1]] = action

    def remove_command(self, sid, command):
        """
        移除一个已注册的命令。

        Args:
            sid (int): 插件的标识符。
            command (str): 要移除的命令名称。
        """
        if sid in self.commands.keys():
            commands = command.split()
            for key in commands[:-1]:  # 遍历路径，找到倒数第二个键
                if key in self.commands[sid]:
                    self.commands[sid] = self.commands[sid][key]  # 进入下一层级
                else:
                    return  # 如果路径不存在，直接返回，不做任何修改

            # 删除最后一个键
            if commands[-1] in self.commands[sid]:
                del self.commands[sid][commands[-1]]

            # 删除空字典键（如果有）
            for key in list(self.commands[sid].keys()):
                if (
                    isinstance(self.commands[sid][key], dict)
                    and not self.commands[sid][key]
                ):
                    del self.commands[sid][key]

    def flush_cli(self):
        """
        刷新命令系统
        """
        self.session.app.current_buffer.completer = NestedCompleter.from_nested_dict(
            self.completer
        )
        self.session.app.invalidate()

    def input_loop(self):
        """
        开始输入循环，处理用户输入。

        捕获KeyboardInterrupt和EOFError以安全地停止循环。
        """
        while self.running:
            try:
                with patch_stdout():
                    text = self.session.prompt(
                        self.prompt,
                        completer=NestedCompleter.from_nested_dict(self.completer),
                    )
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
            commands = text.split()
            sid = commands[0]  # 这里将第一个元素作为sid
            params = commands[1:]  # 剩余的部分作为命令路径

            # 检查是否存在该 sid 的命令字典
            if sid not in self.commands:
                self.interface.warn(f"未知插件ID: {sid}")
                return None
            
            # 如果只输入了sid，没有其他命令，默认执行 sid help
            if not params:
                params = ["help"]

            cmd_dict = self.commands[sid]
            command = cmd_dict
            final_params = []

            # 遍历命令路径并执行对应操作
            for key in params:
                # 如果命令存在并且当前路径是字典
                if isinstance(command, dict) and key in command:
                    command = command[key]
                # 如果遇到占位符，进行替换
                elif (
                    isinstance(command, dict)
                    and isinstance(command.get(key), str)
                    and re.match(r"<.*>", key)
                ):
                    final_params.append(key.strip("<>"))  # 提取参数
                else:
                    self.interface.warn(f"未知命令: {key}")
                    return None  # 如果路径不存在或某层不是字典，则返回 None

            # 执行命令，并传入提取到的参数
            if callable(command):
                command(*final_params)  # 传递提取的参数
            else:
                self.interface.warn(f"无法执行命令: {command}")
                return None

    @new_thread("CommandCore")
    def start(self):
        """
        启动命令行界面，开启输入循环。
        """
        self.input_loop()
