import os, time, sys, threading

global _control_interface, _config


def initialization_config() -> None:
    """
    第一次启动时的配置初始化过程。
    收集用户输入的信息并生成初始配置字典。
    """
    from connect_core.storage import YmlLanguage
    from cryptography.fernet import Fernet

    # 选择语言
    lang = input("Choose language | 请选择语言: [EN_US/zh_cn] ")
    lang = lang if lang else "en_us"
    lang.lower()

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

    print(translate_temp["connect_core"]["cli"]["initialization_config"]["finish"])

    from connect_core.storage import JsonDataEditor
    from connect_core.cli.tools import restart_program

    JsonDataEditor("config.json").write(
        {
            "language": lang,
            "ip": ip,
            "port": port,
            "http_port": http_port,
            "password": password,
            "debug": False,
        }
    )
    time.sleep(3)
    restart_program()


def start_servers() -> None:
    """
    创建并启动HTTP和WebSocket服务器的线程。
    """
    from connect_core.http.http_server import http_main
    from connect_core.websocket.websocket_server import websocket_server_init

    time.sleep(0.3)

    # 创建并启动HTTP服务器线程
    http_server_thread = threading.Thread(target=http_main, args=(_control_interface,))
    http_server_thread.daemon = True

    # 创建并启动WebSocket服务器线程
    websocket_server_thread = threading.Thread(
        target=websocket_server_init, args=(_control_interface,)
    )
    websocket_server_thread.daemon = True

    http_server_thread.start()
    websocket_server_thread.start()


# Public
def cli_main() -> None:
    """
    服务器启动主程序
    """
    if not os.path.exists("config.json"):
        initialization_config()
        return
    # 获取控制接口
    from connect_core.interface.get_interface import get_interface_main

    global _control_interface, _config

    _control_interface = get_interface_main("connect_core", sys.argv[0], "config.json")
    _config = _control_interface.get_config()

    _control_interface.info(
        _control_interface.tr("cli.starting.welcome").format(
            f"{_config['ip']}:{_config['port']}"
        )
    )
    _control_interface.info(
        _control_interface.tr("cli.starting.welcome_password").format(
            _config["password"]
        )
    )

    # 启动服务器线程
    start_servers_thread = threading.Thread(target=start_servers)
    start_servers_thread.start()

    from connect_core.cli.server.commands import commands_main
    from connect_core.rsa_encrypt import rsa_main

    rsa_main(_control_interface)
    commands_main(_control_interface)
