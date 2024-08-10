from prompt_toolkit import PromptSession
from prompt_toolkit.completion import NestedCompleter
import cmd

from connect_core.log_system import info_print, wait_msg
from connect_core.get_config_translate import translate, is_mcdr
from connect_core.websocket.websocket_server import get_servers_info, send_msg


# 服务端命令行处理类
class MyServerCmd(cmd.Cmd):
    # 提示符
    prompt = "ConnectCoreServer> "

    def __init__(self, *args, **kwargs):
        """
        初始化服务端命令行处理类，设置命令补全功能。
        """
        super().__init__(*args, **kwargs)
        self.session = PromptSession()
        self.update_completer({"all": None})

    def update_completer(self, server_dict: dict):
        """
        更新命令行补全器，以便根据服务器列表动态更新可用命令。

        Args:
            server_dict (dict): 服务器字典，键为服务器名，值为None。
        """
        self.completer = NestedCompleter.from_nested_dict(
            {
                "list": None,
                "send": {"msg": server_dict, "file": server_dict},
                "exit": None,
                "help": None,
            }
        )
        # 更新 completer 之后，立即刷新提示符
        self.session.app.current_buffer.completer = self.completer
        self.session.app.invalidate()

    def cmdloop(self, intro=None):
        """
        运行命令行主循环，持续接受用户输入并处理命令。

        Args:
            intro (str, optional): 命令行提示信息，默认为None。
        """
        print(intro) if intro else self.preloop()
        stop = None
        while not stop:
            try:
                wait_msg(self.prompt)
                line = self.session.prompt(self.prompt, completer=self.completer)
                line = line if line else "else"
                wait_msg("")
                stop = self.onecmd(line)
            except EOFError:
                stop = self.onecmd("EOF")
            except KeyboardInterrupt:
                self.intro = None
                stop = self.onecmd("^C")
        self.postloop()

    def do_list(self, args):
        """
        显示当前可用的子服务器列表。
        """
        info_print("==list==")
        server_list = get_servers_info()
        for num, key in enumerate(server_list.keys()):
            info_print(f"{num + 1}. {key}: {server_list[key]['path']}")

    def do_send(self, args):
        """
        向指定服务器发送消息或文件。

        Args:
            args (str): 用户输入的命令参数，格式为"msg|file server_name content"。
        """
        commands = args.split()
        if len(commands) != 3:
            info_print(translate("cli.server_commands.send"))
            return None
        if commands[0] == "msg":
            if commands[1] == "all" or commands[1] in get_servers_info().keys():
                send_msg(commands[1], commands[2])
        elif commands[0] == "file":
            pass
        else:
            info_print(translate("cli.server_commands.send"))

    def do_exit(self, args):
        """
        退出程序。
        """
        print("Goodbye!")
        return True

    def do_help(self, args):
        """
        显示所有可用命令的帮助信息。
        """
        info_print(translate("cli.server_commands.help"))

    def do_else(self, args):
        """
        处理无法识别的命令，无特殊操作。
        """
        return None


# 客户端命令行处理类
class MyClientCmd(cmd.Cmd):
    # 提示符
    prompt = "ConnectCoreClient> "

    def __init__(self, *args, **kwargs):
        """
        初始化客户端命令行处理类，设置命令补全功能。
        """
        super().__init__(*args, **kwargs)
        self.session = PromptSession()
        self.completer = NestedCompleter.from_nested_dict(
            {"info": None, "exit": None, "help": None}
        )

    def cmdloop(self, intro=None):
        """
        运行命令行主循环，持续接受用户输入并处理命令。

        Args:
            intro (str, optional): 命令行提示信息，默认为None。
        """
        print(intro) if intro else self.preloop()
        stop = None
        while not stop:
            try:
                wait_msg(self.prompt)
                line = self.session.prompt(self.prompt, completer=self.completer)
                line = line if line else "else"
                wait_msg("")
                stop = self.onecmd(line)
            except EOFError:
                stop = self.onecmd("EOF")
            except KeyboardInterrupt:
                self.intro = None
                stop = self.onecmd("^C")
        self.postloop()

    def do_info(self, args):
        """
        显示主服务器信息。
        """
        from connect_core.websocket.websocket_client import get_server_id

        info_print("==info==")
        server_id = get_server_id()
        if server_id:
            info_print(f"Main Server Connected! Server ID: {server_id}")
        else:
            info_print("Main Server Disconnected!")

    def do_exit(self, args):
        """
        退出程序。
        """
        print("Goodbye!")
        return True

    def do_help(self, args):
        """
        显示所有可用命令的帮助信息。
        """
        info_print(translate("cli.client_commands.help"))

    def do_else(self, args):
        """
        处理无法识别的命令，无特殊操作。
        """
        return None


# CLI核心初始化函数
def cli_core_init(is_server: bool) -> None:
    """
    根据参数初始化服务端或客户端命令行界面。

    Args:
        is_server (bool): 如果为True，初始化服务端命令行；否则初始化客户端命令行。
    """
    if is_server:
        global my_server_cmd
        my_server_cmd = MyServerCmd()
        my_server_cmd.cmdloop()
    else:
        global my_client_cmd
        my_client_cmd = MyClientCmd()
        my_client_cmd.cmdloop()


# 刷新服务器列表并更新补全器
def flush_completer(server_list: list):
    """
    刷新服务器列表提示词，并更新命令行补全器。

    Args:
        server_list (list): 服务器名的列表。
    """
    if is_mcdr():
        return None
    server_dict = {"all": None}
    for i in server_list:
        server_dict[i] = None
    my_server_cmd.update_completer(server_dict)
