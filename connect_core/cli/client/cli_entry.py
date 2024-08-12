import os, sys
from time import sleep
from connect_core.api.log_system import info_print
from connect_core.api.c_t import config, translate

global translate_temp


def main():
    """
    程序主入口。
    检查是否为第一次启动，决定初始化配置或直接启动客户端。
    """
    from connect_core.cli.storage import JsonDataEditor

    config_edit = JsonDataEditor()
    info_print("\nConnectCore Client Starting...")

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
    启动WebSocket客户端并初始化核心命令行程序。
    """
    from connect_core.api.websocket.client import websocket_client_init

    info_print(
        translate("cli.starting.welcome").format(f"{config('ip')}:{config('port')}")
    )
    info_print(translate("cli.starting.welcome_password").format(config("password")))

    # 启动WebSocket客户端
    websocket_client_init()

    from connect_core.api.cli_command import (
        add_command,
        start_cli_core,
        set_completer_words,
        set_prompt,
        stop_cli_core,
    )

    def do_info(args):
        """
        显示主服务器信息。
        """
        from connect_core.api.websocket.client import get_server_id

        info_print("==info==")
        server_id = get_server_id()
        if server_id:
            info_print(f"Main Server Connected! Server ID: {server_id}")
        else:
            info_print("Main Server Disconnected!")

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

    add_command("help", do_help)
    add_command("info", do_info)
    add_command("exit", do_exit)

    set_completer_words({"info": None, "exit": None, "help": None})

    set_prompt("ConnectCoreClient> ")

    start_cli_core()

def initialization_config() -> dict:
    """
    第一次启动时的配置初始化过程。
    收集用户输入的信息并生成初始配置字典。

    Returns:
        dict: 包含初始配置的字典。
    """
    from connect_core.cli.storage import YmlLanguage

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
    password_create = "---"
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
