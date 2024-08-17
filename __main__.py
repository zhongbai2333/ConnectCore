import sys


####################
# Private
####################
def start_server_cli():
    from connect_core.cli.server import cli_main

    cli_main()


def start_client_cli():
    from connect_core.cli.client import cli_main

    cli_main()


def display_help():
    """
    显示CLI系统帮助

    Returns:
        None
    """
    print("Connect Core Help Assistant")
    print("    client: Start Client")
    print("    server: Start Server")


def main():
    """
    CLI程序入口

    Returns:
        None
    """
    # 根据启动命令控制
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "server":
            start_server_cli()
        elif command == "client":
            start_client_cli()
        else:
            display_help()
    else:
        display_help()


####################
# Public
####################
# First Start Point
if __name__ == "__main__":
    main()
