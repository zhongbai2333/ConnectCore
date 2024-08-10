import sys, os, threading
from time import sleep
from connect_core.log_system import info_input, info_print
from connect_core.get_config_translate import config, translate

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

    from connect_core.cli.cli_core import cli_core_init

    # 启动核心命令行程序
    cli_core_init(True)


def start_servers():
    """
    创建并启动HTTP和WebSocket服务器的线程。
    """
    from connect_core.http.http_server import http_main
    from connect_core.websocket.websocket_server import websocket_server_init

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
    lang = info_input("Choose language | 请选择语言: [EN_US/zh_cn] ")
    lang = lang if lang else "en_us"
    lang.lower()

    global translate_temp
    translate_temp = YmlLanguage(lang).translate

    # 输入IP地址
    ip = info_input(
        translate_temp["connect_core"]["cli"]["initialization_config"]["enter_ip"]
    )
    ip = ip if ip else "127.0.0.1"

    # 输入端口
    port = info_input(
        translate_temp["connect_core"]["cli"]["initialization_config"]["enter_port"]
    )
    port = int(port) if port else 23233

    # 输入HTTP端口
    http_port = info_input(
        translate_temp["connect_core"]["cli"]["initialization_config"][
            "enter_http_port"
        ]
    )
    http_port = int(http_port) if http_port else 4443

    # 生成和输入密码
    password_create = Fernet.generate_key().decode()
    password = info_input(
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
