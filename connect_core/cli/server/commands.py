from connect_core.websocket.websocket_server import get_servers_info
from connect_core.cli.tools import restart_program, check_file_exists, append_to_path
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from connect_core.interface.contol_interface import ControlInterface

global _control_interface


# 启动核心命令行程序
def do_list(args):
    """
    显示当前可用的子服务器列表。
    """
    _control_interface.info("==list==")
    server_list = get_servers_info()
    for num, key in enumerate(server_list.keys()):
        _control_interface.info(f"{num + 1}. {key}: {server_list[key]['path']}")


def do_send(args):
    """
    向指定服务器发送消息或文件。
    """

    commands = args.split()
    if len(commands) < 3:
        _control_interface.info(_control_interface.tr("cli.server_commands.send"))
        return None

    server_name, content = commands[1], commands[2]
    if commands[0] == "msg" and (
        server_name == "all" or server_name in get_servers_info()
    ):
        _control_interface.send_data(server_name, {"msg": content})
    elif (
        commands[0] == "file"
        and (server_name == "all" or server_name in get_servers_info())
        and len(commands) == 4
    ):
        save_path = commands[3]
        if check_file_exists(content):
            _control_interface.send_file(
                server_name,
                content,
                append_to_path(save_path, os.path.basename(content)),
            )
        else:
            _control_interface.info(_control_interface.tr("cli.server_commands.no_file"))
    else:
        _control_interface.info(_control_interface.tr("cli.server_commands.send"))


def do_help(args):
    """
    显示所有可用命令的帮助信息。
    """
    _control_interface.info(_control_interface.tr("cli.server_commands.help"))


def do_reload(args):
    """
    重载程序和插件
    """
    restart_program()


def do_exit(args):
    """
    退出命令行系统
    """
    _control_interface.cli_core.running = False


def commands_main(control_interface: "ControlInterface"):
    """
    Server 命令行系统主程序

    Args:
        connect_interface (ControlInterface): API接口
    """
    global _control_interface

    _control_interface = control_interface

    _control_interface.cli_core.add_command("help", do_help)
    _control_interface.cli_core.add_command("list", do_list)
    _control_interface.cli_core.add_command("send", do_send)
    _control_interface.cli_core.add_command("reload", do_reload)
    _control_interface.cli_core.add_command("exit", do_exit)

    _control_interface.cli_core.set_completer_words(
        {
            "help": None,
            "list": None,
            "send": {"msg": {"all": None}, "file": {"all": None}},
            "reload": None,
            "exit": None,
        }
    )

    os.system(f"title ConnectCore Server")

    _control_interface.cli_core.set_prompt("ConnectCoreServer> ")

    _control_interface.cli_core.start()
