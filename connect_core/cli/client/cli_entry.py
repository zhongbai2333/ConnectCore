import os, time, sys, threading

global _control_interface, _config


def initialization_config() -> dict:
    """
    第一次启动时的配置初始化过程。
    收集用户输入的信息并生成初始配置字典。

    Returns:
        dict: 包含初始配置的字典。
    """
    from connect_core.storage import YmlLanguage

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


def start_server():
    """
    启动WebSocket客户端并初始化核心命令行程序。
    """
    from connect_core.websocket.websocket_client import websocket_client_init

    # 启动WebSocket客户端
    websocket_client_init(_control_interface)

    from connect_core.cli.client.commands import commands_main
    from connect_core.rsa_encrypt import rsa_main

    rsa_main(_control_interface)
    commands_main(_control_interface)


# Public
def cli_main():
    """
    客户端启动主程序
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

    start_server()
