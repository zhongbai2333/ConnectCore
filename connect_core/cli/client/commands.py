from connect_core.api.cli_command import (
    add_command,
    start_cli_core,
    set_completer_words,
    set_prompt,
    stop_cli_core,
)
from connect_core.api.websocket.client import get_server_id, get_server_list
from connect_core.api.log_system import info_print
from connect_core.api.c_t import translate
from connect_core.api.tools import restart_program

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
    add_command("reload", do_reload)
    add_command("exit", do_exit)

    set_completer_words({"help": None, "info": None, "list": None, "reload":None, "exit": None})

    set_prompt("ConnectCoreClient> ")

    start_cli_core()
