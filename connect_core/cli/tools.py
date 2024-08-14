import sys, os


def restart_program():
    """
    重启程序，使用当前的Python解释器重新执行当前脚本。
    """
    python = sys.executable
    os.execl(python, python, *sys.argv)
