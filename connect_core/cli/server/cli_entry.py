import sys, os, threading

from time import sleep
from connect_core.log_system import info_input, info_print
from connect_core.get_config_translate import config, translate

global translate_temp


def main():
    from connect_core.cli.storage import JsonDataEditor

    config_edit = JsonDataEditor()
    info_print("\nConnectCore Server Starting...")
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


# 启动服务器
def start_server():
    from connect_core.http.http_server import http_main
    from connect_core.websocket.websocket_server import websocket_server_init

    info_print(
        translate("cli.starting.welcome").format(
            f"{config('ip')}:{config('port')}"
        )
    )
    info_print(
        translate("cli.starting.welcome_password").format(config("password"))
    )
    # 创建 http服务器 线程
    http_server_thread = threading.Thread(target=http_main)
    http_server_thread.daemon = True
    # 创建 websocket服务器 线程
    websocket_server_thread = threading.Thread(target=websocket_server_init)
    websocket_server_thread.daemon = True
    http_server_thread.start()
    websocket_server_thread.start()
    try:
        while True:
            command_system()
    except KeyboardInterrupt:
        print()
        sys.exit(0)


def command_system() -> None:
    cmd = info_input(">>")
    match cmd:
        case "list":
            from connect_core.websocket.websocket_server import get_server_list

            info_print("==list==")
            server_list = get_server_list()
            for num, key in enumerate(server_list.keys()):
                info_print(f"{num + 1}. {key}: {server_list[key]['path']}")
            return None
        case "exit":
            info_print("Bye!")
            sys.exit(0)
        case "stop":
            info_print("Bye!")
            sys.exit(0)
        case "":
            return None
        case _:
            info_print(translate("cli.server_commands.help"))
            return None


# 第一次启动配置
def initialization_config() -> dict:
    from connect_core.cli.storage import YmlLanguage
    from cryptography.fernet import Fernet

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
    password_create = Fernet.generate_key().decode()
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
