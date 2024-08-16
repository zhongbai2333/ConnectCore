from connect_core.api.cli_command import (
    add_command,
    start_cli_core,
    set_completer_words,
    set_prompt,
    stop_cli_core,
)
from connect_core.api.websocket.client import get_server_id, get_server_list, send_msg
from connect_core.api.log_system import info_print
from connect_core.api.c_t import translate
from connect_core.api.tools import restart_program
import os


def do_info(args):
    """
    显示主服务器信息。
    """
    info_print("==info==")
    server_id = get_server_id()
    if server_id:
        info_print(f"Main Server Connected! Server ID: {server_id}")
    else:
        info_print("Main Server Disconnected!")


def do_list(args):
    """
    显示当前可用的子服务器列表。
    """
    info_print("==list==")
    server_list = get_server_list()
    for num, key in enumerate(server_list):
        info_print(f"{num + 1}. {key}")


def do_send(args):
    """
    向指定服务器发送消息或文件。
    """

    commands = args.split()
    if len(commands) != 3:
        info_print(translate("cli.client_commands.send"))
        return None

    server_name, content = commands[1], commands[2]
    if commands[0] == "msg" and (
        server_name == "all" or server_name == "-----" or server_name in get_server_list()
    ):
        send_msg(server_name, content)
    elif commands[0] == "file":
        pass  # Implement file sending logic here
    else:
        info_print(translate("cli.server_commands.send"))


def do_reload(args):
    """
    重载程序和插件
    """
    restart_program()


def do_help(args):
    """
    显示所有可用命令的帮助信息。
    """
    info_print(translate("cli.client_commands.help"))


def do_exit(args):
    """
    退出命令行系统
    """
    stop_cli_core()


def commands_main():
    """
    Client 命令行系统主程序
    """
    add_command("help", do_help)
    add_command("info", do_info)
    add_command("list", do_list)
    add_command("send", do_send)
    add_command("reload", do_reload)
    add_command("exit", do_exit)

    set_completer_words(
        {
            "help": None,
            "info": None,
            "list": None,
            "send": {
                "msg": {"all": None, "-----": None},
                "file": {"all": None, "-----": None},
            },
            "reload": None,
            "exit": None,
        }
    )

    set_prompt("ConnectCoreClient> ")

    os.system(f"title ConnectCore Client")

    start_cli_core()
