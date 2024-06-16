import random, string, sys, os, threading, ctypes

from time import sleep
from connect_core.cli.log_system import LogSystem

global translate, config
global info_print, info_input


def main():
    from connect_core.cli.storage import JsonDataEditor

    global info_print, info_input
    config_edit = JsonDataEditor()
    log_system = LogSystem()
    info_print = log_system.info_print
    info_input = log_system.info_input
    info_print("\nConnectCore Starting...")
    if config_edit.read():
        from connect_core.cli.storage import YmlLanguage

        global translate, config
        config = config_edit.read()
        translate = YmlLanguage(config["language"]).translate
        start_server()
    else:
        config_edit.write(initialization_config())
        info_print(translate["connect_core"]["cli"]["initialization_config"]["finish"])
        sleep(3)
        restart_program()


def restart_program():
    python = sys.executable
    os.execl(python, python, *sys.argv)


def start_server():
    from connect_core.cli.create_key import create_ssl_key
    from connect_core.https.flask_server import https_main
    info_print(
            translate["connect_core"]["cli"]["starting"]["welcome"].format(
                f"{config['ip']}:{config['port']}"
            )
        )
    info_print(
            translate["connect_core"]["cli"]["starting"]["welcome_password"].format(
                config["password"]
            )
        )
    create_ssl_key(config['ip'])
    https_server = threading.Thread(target=https_main)
    https_server.daemon = True
    https_server.start()
    try:
        while True:
            sleep(1)
    except KeyboardInterrupt:
        print()
        sys.exit(0)


def create_string_number(n) -> str:
    m = random.randint(1, n)
    a = "".join([str(random.randint(0, 9)) for _ in range(m)])
    b = "".join([random.choice(string.ascii_letters) for _ in range(n - m)])
    return "".join(random.sample(list(a + b), n))


def initialization_config() -> dict:
    from connect_core.cli.storage import YmlLanguage

    lang = info_input("Choose language | 请选择语言: [EN_US/zh_cn] ")
    lang = lang if lang else "en_us"
    lang.lower()
    global translate
    translate = YmlLanguage(lang).translate
    ip = info_input(
        translate["connect_core"]["cli"]["initialization_config"]["enter_ip"]
    )
    ip = ip if ip else "127.0.0.1"
    port = info_input(
        translate["connect_core"]["cli"]["initialization_config"]["enter_port"]
    )
    port = int(port) if port else 23233
    password_create = create_string_number(10)
    password = info_input(
        translate["connect_core"]["cli"]["initialization_config"][
            "enter_password"
        ].format(password_create)
    )
    password = password if password else password_create
    return {"language": lang, "ip": ip, "port": port, "password": password}
