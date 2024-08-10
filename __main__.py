import sys


def start_server_cli():
    from connect_core.cli.server.cli_entry import main

    main()


def start_client_cli():
    from connect_core.cli.client.cli_entry import main

    main()


# First Start Point
if __name__ == "__main__":
    from connect_core.log_system import info_print
    from connect_core.module_initialization import module_initialization_main

    # 初始化
    module_initialization_main()

    # 根据启动命令控制
    if len(sys.argv) > 1:
        if sys.argv[1] == "server":
            start_server_cli()
        elif sys.argv[1] == "client":
            start_client_cli()
        else:
            info_print("Connect Core Help Assistant")
            info_print("    client: Start Client")
            info_print("    server: Start Server")
    else:
        info_print("Connect Core Help Assistant")
        info_print("    client: Start Client")
        info_print("    server: Start Server")
