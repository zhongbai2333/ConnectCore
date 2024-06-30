from prompt_toolkit import PromptSession
from prompt_toolkit.completion import NestedCompleter
from prompt_toolkit.application import get_app
import cmd

from connect_core.log_system import info_print, wait_msg
from connect_core.get_config_translate import translate, is_mcdr


class MyServerCmd(cmd.Cmd):
    prompt = "ConnectCoreServer> "

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session = PromptSession()
        self.update_completer(None)

    def update_completer(self, server_dict: dict):
        self.completer = NestedCompleter.from_nested_dict(
            {
                "list": None,
                "send": {"msg": server_dict, "file": server_dict},
                "exit": None,
                "help": None,
            }
        )

    def cmdloop(self, intro=None):
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
        """Show sub-servers list"""
        from connect_core.websocket.websocket_server import get_server_list

        info_print("==list==")
        server_list = get_server_list()
        for num, key in enumerate(server_list.keys()):
            info_print(f"{num + 1}. {key}: {server_list[key]['path']}")

    def do_exit(self, args):
        """Exit this program"""
        print("Goodbye!")
        return True

    def do_help(self, args):
        """Show all helps about cmd"""
        info_print(translate("cli.server_commands.help"))

    def do_else(self, args):
        """Anything Nothing"""
        return None


class MyClientCmd(cmd.Cmd):
    prompt = "ConnectCoreClient> "

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session = PromptSession()
        self.completer = NestedCompleter.from_nested_dict(
            {"info": None, "exit": None, "help": None}
        )

    def cmdloop(self, intro=None):
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
        """Show mian-servers info"""
        from connect_core.websocket.websocket_client import get_server_id

        info_print("==info==")
        server_id = get_server_id()
        if server_id:
            info_print(f"Main Server Connected! Server ID: {server_id}")
        else:
            info_print("Main Server Disconnected!")

    def do_exit(self, args):
        """Exit this program"""
        print("Goodbye!")
        return True

    def do_help(self, args):
        """Show all helps about cmd"""
        info_print(translate("cli.client_commands.help"))

    def do_else(self, args):
        """Anything Nothing"""
        return None


def cli_core_init(is_server: bool) -> None:
    if is_server:
        global my_server_cmd
        my_server_cmd = MyServerCmd()
        my_server_cmd.cmdloop()
    else:
        global my_client_cmd
        my_client_cmd = MyClientCmd()
        my_client_cmd.cmdloop()


def flush_completer(server_list: list):
    if is_mcdr():
        return None
    server_dict = {}
    for i in server_list:
        server_dict[i] = None
    my_server_cmd.update_completer(server_dict)
    get_app().invalidate()
