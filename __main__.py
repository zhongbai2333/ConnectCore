import sys

from connect_core.cli.core_entry import core_entry_init


def display_help():
    """
    显示CLI系统帮助
    """
    print("Connect Core Help Assistant")
    print("    client: Start Client")
    print("    server: Start Server")


def main():
    """
    Main Code
    """
    # 根据启动命令控制
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "server":
            core_entry_init(True)
        elif command == "client":
            core_entry_init(False)
        else:
            display_help()
    else:
        core_entry_init(True)

# Public
if __name__ == "__main__":
    main()
