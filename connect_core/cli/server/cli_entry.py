import sys, os, threading
from time import sleep
from connect_core.api.log_system import info_print
from connect_core.api.c_t import config, translate

global translate_temp


def main():
    """
    程序主入口。
    检查是否为第一次启动，决定初始化配置或直接启动服务器。
    """
    from connect_core.cli.storage import JsonDataEditor

    config_edit = JsonDataEditor()
    info_print("\nConnectCore Server Starting...")

    # 判断是否是第一次启动
    if config_edit.read():
        start_server()
    else:
        # 初始化配置
        config_edit.write(initialization_config())
        info_print(
            translate_temp["connect_core"]["cli"]["initialization_config"]["finish"]
        )
        sleep(3)
        restart_program()


def restart_program():
    """
    重启程序，使用当前的Python解释器重新执行当前脚本。
    """
    python = sys.executable
    os.execl(python, python, *sys.argv)


def start_server():
    """
    启动服务器并初始化核心命令行程序。
    """
    info_print(
        translate("cli.starting.welcome").format(f"{config('ip')}:{config('port')}")
    )
    info_print(translate("cli.starting.welcome_password").format(config("password")))

    # 启动服务器线程
    start_servers_thread = threading.Thread(target=start_servers)
    start_servers_thread.start()

    from connect_core.api.cli_command import (
        add_command,
        start_cli_core,
        set_completer_words,
        set_prompt,
        stop_cli_core,
    )
    from connect_core.api.websocket.server import get_servers_info, send_msg

    # 启动核心命令行程序
    def do_list(args):
        """
        显示当前可用的子服务器列表。
        """
        info_print("==list==")
        server_list = get_servers_info()
        for num, key in enumerate(server_list.keys()):
            info_print(f"{num + 1}. {key}: {server_list[key]['path']}")

    def do_send(args):
        """
        向指定服务器发送消息或文件。
        """

        commands = args.split()
        if len(commands) != 3:
            info_print(translate("cli.server_commands.send"))
            return None

        server_name, content = commands[1], commands[2]
        if commands[0] == "msg" and (
            server_name == "all" or server_name in get_servers_info()
        ):
            send_msg(server_name, content)
        elif commands[0] == "file":
            pass  # Implement file sending logic here
        else:
            info_print(translate("cli.server_commands.send"))

    def do_help(args):
        """
        显示所有可用命令的帮助信息。
        """
        info_print(translate("cli.server_commands.help"))

    def do_exit(args):
        """
        退出命令行系统
        """
        stop_cli_core()

    add_command("help", do_help)
    add_command("list", do_list)
    add_command("send", do_send)
    add_command("exit", do_exit)

    set_completer_words(
        {
            "help": None,
            "list": None,
            "send": {"msg": {"all": None}, "file": {"all": None}},
            "exit": None,
        }
    )

    set_prompt("ConnectCoreServer> ")

    start_cli_core()


def start_servers():
    """
    创建并启动HTTP和WebSocket服务器的线程。
    """
    from connect_core.api.http import http_main
    from connect_core.api.websocket.server import websocket_server_init

    sleep(0.3)

    # 创建并启动HTTP服务器线程
    http_server_thread = threading.Thread(target=http_main)
    http_server_thread.daemon = True

    # 创建并启动WebSocket服务器线程
    websocket_server_thread = threading.Thread(target=websocket_server_init)
    websocket_server_thread.daemon = True

    http_server_thread.start()
    websocket_server_thread.start()


def initialization_config() -> dict:
    """
    第一次启动时的配置初始化过程。
    收集用户输入的信息并生成初始配置字典。

    Returns:
        dict: 包含初始配置的字典。
    """
    from connect_core.cli.storage import YmlLanguage
    from cryptography.fernet import Fernet

    # 选择语言
    lang = input("Choose language | 请选择语言: [EN_US/zh_cn] ")
    lang = lang if lang else "en_us"
    lang.lower()

    global translate_temp
    translate_temp = YmlLanguage(lang).translate

    # 输入IP地址
    ip = input(
        translate_temp["connect_core"]["cli"]["initialization_config"]["enter_ip"]
    )
    ip = ip if ip else "127.0.0.1"

    # 输入端口
    port = input(
        translate_temp["connect_core"]["cli"]["initialization_config"]["enter_port"]
    )
    port = int(port) if port else 23233

    # 输入HTTP端口
    http_port = input(
        translate_temp["connect_core"]["cli"]["initialization_config"][
            "enter_http_port"
        ]
    )
    http_port = int(http_port) if http_port else 4443

    # 生成和输入密码
    password_create = Fernet.generate_key().decode()
    password = input(
        translate_temp["connect_core"]["cli"]["initialization_config"][
            "enter_password"
        ].format(password_create)
    )
    password = password if password else password_create

    # 返回配置字典
    return {
        "language": lang,
        "ip": ip,
        "port": port,
        "http_port": http_port,
        "password": password,
        "debug": False,
    }
