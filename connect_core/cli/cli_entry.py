import random, string, sys, os, threading

from time import sleep
from connect_core.cli.log_system import info_input, info_print
from connect_core.cli.get_config_translate import config, translate

global translate_temp


def main():
    from connect_core.cli.storage import JsonDataEditor

    config_edit = JsonDataEditor()
    info_print("\nConnectCore Starting...")
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
    from connect_core.cli.create_key import create_ssl_key
    from connect_core.http.http_server import http_main

    info_print(
        translate()["connect_core"]["cli"]["starting"]["welcome"].format(
            f"{config()['ip']}:{config()['port']}"
        )
    )
    info_print(
        translate()["connect_core"]["cli"]["starting"]["welcome_password"].format(
            config()["password"]
        )
    )
    create_ssl_key(config()["ip"])
    # 创建 http服务器 线程
    http_server_thread = threading.Thread(target=http_main)
    http_server_thread.daemon = True
    http_server_thread.start()
    try:
        while True:
            sleep(1)
    except KeyboardInterrupt:
        print()
        sys.exit(0)


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
    }
