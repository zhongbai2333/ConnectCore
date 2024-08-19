import time, os, threading

from connect_core.interface.control_interface import CoreControlInterface


def server() -> None:
    # Function
    def initialization_config() -> None:
        """
        第一次启动时的配置初始化过程。
        收集用户输入的信息并生成初始配置字典。
        """
        from connect_core.storage import YmlLanguage
        from cryptography.fernet import Fernet
        import sys

        # 选择语言
        lang = input("Choose language | 请选择语言: [EN_US/zh_cn] ")
        lang = lang if lang else "en_us"
        lang.lower()

        translate_temp = YmlLanguage(sys.argv[0], lang).translate

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
        from connect_core.websocket.server import websocket_server_main
        from connect_core.rsa_encrypt import rsa_main

        rsa_main(_control_interface)

        time.sleep(0.3)

        # 创建并启动HTTP服务器线程
        http_server_thread = threading.Thread(
            target=http_main, args=(_control_interface,)
        )
        http_server_thread.daemon = True

        # 创建并启动WebSocket服务器线程
        websocket_server_thread = threading.Thread(
            target=websocket_server_main, args=(_control_interface,)
        )
        websocket_server_thread.daemon = True

        http_server_thread.start()
        websocket_server_thread.start()

    if not os.path.exists("config.json"):
        initialization_config()
        return

    _control_interface = CoreControlInterface()
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

    from connect_core.plugin.init_plugin import init_plugin_main

    init_plugin_main(_control_interface)

    # 启动服务器线程
    start_servers()

    try:
        _control_interface.info("Program is running. Press Ctrl+C to exit.")
        while True:
            time.sleep(1)  # 模拟程序的持续运行
    except KeyboardInterrupt:
        _control_interface.info("\nCtrl+C detected. Exiting gracefully.")


def client() -> None:
    # Function
    def initialization_config() -> None:
        """
        第一次启动时的配置初始化过程。
        收集用户输入的信息并生成初始配置字典。

        Returns:
            dict: 包含初始配置的字典。
        """
        from connect_core.storage import YmlLanguage
        import sys

        # 选择语言
        lang = input("Choose language | 请选择语言: [EN_US/zh_cn] ")
        lang = lang if lang else "en_us"
        lang.lower()

        global translate_temp
        translate_temp = YmlLanguage(sys.argv[0], lang).translate

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

    def start_server() -> None:
        """
        启动WebSocket客户端并初始化核心命令行程序。
        """
        from connect_core.websocket.client import websocket_client_main
        from connect_core.rsa_encrypt import rsa_main

        rsa_main(_control_interface)
        # 启动WebSocket客户端
        websocket_client_main(_control_interface)

    if not os.path.exists("config.json"):
        initialization_config()
        return

    _control_interface = CoreControlInterface()
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

    from connect_core.plugin.init_plugin import init_plugin_main

    init_plugin_main(_control_interface)

    # 启动服务器
    start_server()

    try:
        _control_interface.info("Program is running. Press Ctrl+C to exit.")
        while True:
            time.sleep(1)  # 模拟程序的持续运行
    except KeyboardInterrupt:
        _control_interface.info("\nCtrl+C detected. Exiting gracefully.")


# Public
def core_entry_init(is_server: bool) -> None:
    """
    核心程序主程序
    """
    # 获取控制接口
    if is_server:
        server()
    else:
        client()
