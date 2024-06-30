import os, sys
from time import sleep
from connect_core.log_system import info_print, info_input
from connect_core.get_config_translate import config, translate

global translate_temp


def main():
    from connect_core.cli.storage import JsonDataEditor

    config_edit = JsonDataEditor()
    info_print("\nConnectCore Client Starting...")
    # 判断是否是第一次启动
    if config_edit.read():
        start_server()
    else:
        config_edit.write(initialization_config())
        info_print(
            translate_temp["connect_core"]["cli"]["initialization_config"]["finish"]
        )
        sleep(3)
        restart_program()


def restart_program():
    python = sys.executable
    os.execl(python, python, *sys.argv)


def start_server():
    from connect_core.websocket.websocket_client import websocket_client_init

    info_print(
        translate("cli.starting.welcome").format(f"{config('ip')}:{config('port')}")
    )
    info_print(translate("cli.starting.welcome_password").format(config("password")))
    websocket_client_init()
    from connect_core.cli.cli_core import cli_core_init

    cli_core_init(False)


def initialization_config():
    from connect_core.cli.storage import YmlLanguage

    lang = info_input("Choose language | 请选择语言: [EN_US/zh_cn] ")
    lang = lang if lang else "en_us"
    lang.lower()
    global translate_temp
    translate_temp = YmlLanguage(lang).translate
    ip = info_input(
        translate_temp["connect_core"]["cli"]["initialization_config"]["enter_ip"]
    )
    ip = ip if ip else "127.0.0.1"
    port = info_input(
        translate_temp["connect_core"]["cli"]["initialization_config"]["enter_port"]
    )
    port = int(port) if port else 23233
    http_port = info_input(
        translate_temp["connect_core"]["cli"]["initialization_config"][
            "enter_http_port"
        ]
    )
    http_port = int(http_port) if http_port else 4443
    password_create = "---"
    password = info_input(
        translate_temp["connect_core"]["cli"]["initialization_config"][
            "enter_password"
        ].format(password_create)
    )
    password = password if password else password_create
    return {
        "language": lang,
        "ip": ip,
        "port": port,
        "http_port": http_port,
        "password": password,
        "debug": False,
    }
