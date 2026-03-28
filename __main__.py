from __future__ import annotations

import argparse
import sys

from connect_core.tools.self_read import get_version
from connect_core.context import GlobalContext
from connect_core.cli.cli_entry import core_entry


class HelpOnErrorArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        print(f"Error 错误: {message}", file=sys.stderr)
        # 遇到错误时直接打印帮助并退出（退出码 0）
        self.print_help()
        sys.exit(0)


def main():
    parser = HelpOnErrorArgumentParser(
        description="ConnectCore",
        formatter_class=argparse.RawTextHelpFormatter,
        add_help=False,  # 我们手动添加 -h/--help
    )

    parser.add_argument(
        "mode",
        choices=["client", "server"],
        help="运行模式：client（客户端） 或 server（服务器）",
    )
    parser.add_argument("-h", "--help", action="store_true", help="显示帮助信息并退出")
    parser.add_argument("-v", "--version", action="store_true", help="显示程序版本信息")
    parser.add_argument(
        "-d",
        "--debug",
        nargs="?",
        const=1,
        default=0,
        type=int,
        help="设置调试等级：0=关闭，1=收发数据日志，2=流程阶段日志，3=包含RAW/HANDSHAKE详情",
    )

    try:
        args = parser.parse_args()
    except SystemExit:
        # 上面 error() 里已经 print_help() 了，这里直接退出
        return

    # 处理 -h
    if args.help:
        parser.print_help()
        sys.exit(0)

    # 处理 -v
    if args.version:
        print(f"ConnectCore v{get_version(__file__)}")
        sys.exit(0)

    # 主逻辑分发
    GlobalContext(args.debug, args.mode == "server", False)
    core_entry()


if __name__ == "__main__":
    main()
