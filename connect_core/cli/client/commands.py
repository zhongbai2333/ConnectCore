from connect_core.api.command_interface import CommandLineInterface
from connect_core.api.websocket.client import get_server_id, get_server_list, send_msg
from connect_core.api.tools import restart_program, check_file_exists, append_to_path
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from connect_core.api.server_interface import ConnectCoreServerInterface

global _connect_interface, _command_interface


def do_info(args):
    """
    显示主服务器信息。
    """
    _connect_interface.info("==info==")
    server_id = get_server_id()
    if server_id:
        _connect_interface.info(f"Main Server Connected! Server ID: {server_id}")
    else:
        _connect_interface.info("Main Server Disconnected!")


def do_list(args):
    """
    显示当前可用的子服务器列表。
    """
    _connect_interface.info("==list==")
    server_list = get_server_list()
    for num, key in enumerate(server_list):
        _connect_interface.info(f"{num + 1}. {key}")


def do_send(args):
    """
    向指定服务器发送消息或文件。
    """

    commands = args.split()
    if len(commands) > 3:
        _connect_interface.info(_connect_interface.tr("cli.client_commands.send"))
        return None

    server_name, content = commands[1], commands[2]
    if commands[0] == "msg" and (
        server_name == "all"
        or server_name == "-----"
        or server_name in get_server_list()
    ):
        send_msg(server_name, content)
    elif (
        commands[0] == "file"
        and (
            server_name == "all"
            or server_name == "-----"
            or server_name in get_server_list()
        )
        and len(commands) == 4
    ):
        if check_file_exists(content):
            save_path = commands[3]
            send_file(
                server_name,
                content,
                append_to_path(save_path, os.path.basename(content)),
            )
        else:
            _connect_interface.info(_connect_interface.tr("cli.server_commands.no_file"))
    else:
        _connect_interface.info(_connect_interface.tr("cli.server_commands.send"))


def do_reload(args):
    """
    重载程序和插件
    """
    restart_program()


def do_help(args):
    """
    显示所有可用命令的帮助信息。
    """
    _connect_interface.info(_connect_interface.tr("cli.client_commands.help"))


def do_exit(args):
    """
    退出命令行系统
    """
    _command_interface.running = False


def commands_main(connect_interface: 'ConnectCoreServerInterface'):
    """
    Client 命令行系统主程序

    Args:
        connect_interface (ConnectCoreServerInterface): API接口
    """
    global _connect_interface, _command_interface

    _connect_interface = connect_interface
    _command_interface = CommandLineInterface(connect_interface, "ConnectCoreClient> ")

    _command_interface.add_command("help", do_help)
    _command_interface.add_command("info", do_info)
    _command_interface.add_command("list", do_list)
    _command_interface.add_command("send", do_send)
    _command_interface.add_command("reload", do_reload)
    _command_interface.add_command("exit", do_exit)

    _command_interface.set_completer_words(
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

    os.system(f"title ConnectCore Client")

    _command_interface.start()
