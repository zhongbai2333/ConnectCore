import threading
from time import sleep
from connect_core.api.server_interface import ConnectCoreServerInterface

global translate_temp, connect_interface, config


####################
# Public
####################
def cli_main():
    """
    程序主入口。
    检查是否为第一次启动，决定初始化配置或直接启动服务器。
    """
    from connect_core.cli.storage import JsonDataEditor

    global connect_interface, config

    connect_interface = ConnectCoreServerInterface()
    config_edit = JsonDataEditor()
    config = connect_interface.get_config()
    connect_interface.info("\nConnectCore Server Starting...")

    # 判断是否是第一次启动
    if config_edit.read():
        start_server()
    else:
        from connect_core.api.tools import restart_program

        # 初始化配置
        config_edit.write(initialization_config())
        connect_interface.info(
            translate_temp["connect_core"]["cli"]["initialization_config"]["finish"]
        )
        sleep(3)
        restart_program()


####################
# Private
####################
def start_server():
    """
    启动服务器并初始化核心命令行程序。
    """
    connect_interface.info(
        connect_interface.tr("cli.starting.welcome").format(
            f"{config['ip']}:{config['port']}"
        )
    )
    connect_interface.info(
        connect_interface.tr("cli.starting.welcome_password").format(config["password"])
    )

    # 启动服务器线程
    start_servers_thread = threading.Thread(target=start_servers)
    start_servers_thread.start()

    from connect_core.cli.server.commands import commands_main
    from connect_core.api.rsa import rsa_main

    rsa_main(connect_interface)
    commands_main(connect_interface)


def start_servers():
    """
    创建并启动HTTP和WebSocket服务器的线程。
    """
    from connect_core.api.http import http_main
    from connect_core.api.websocket.server import websocket_server_init

    sleep(0.3)

    # 创建并启动HTTP服务器线程
    http_server_thread = threading.Thread(target=http_main, args=(connect_interface,))
    http_server_thread.daemon = True

    # 创建并启动WebSocket服务器线程
    websocket_server_thread = threading.Thread(
        target=websocket_server_init, args=(connect_interface,)
    )
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
