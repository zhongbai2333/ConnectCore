import time, os, sys

from mcdreforged.api.all import PluginServerInterface

global log_system

class LogSystem:
    def __init__(
        self,
        mcdr_core: PluginServerInterface = None,
        filelog: str = f"Log-{time.strftime('%b_%d-%H_%M_%S', time.localtime())}.log",
        path: str = "logs/",
    ) -> None:
        if not os.path.exists(path):
            os.makedirs(path)
        self.logfile = path + filelog
        self.mcdr_core = mcdr_core
        self.wait_msg = None

    def _print(self, level: str, msg: str, enter: bool = True) -> None:
        """总输出"""
        with open(self.logfile, "a", encoding="utf-8") as file:
            if enter:
                if self.wait_msg:
                    delete_current_line()
                match level:
                    case "INFO":
                        colored_text = self.colored_text(32, "INFO")
                    case "WARN":
                        colored_text = self.colored_text(33, "WARN")
                    case "ERROR":
                        colored_text = self.colored_text(31, "ERROR")
                    case "DEBUG":
                        colored_text = self.colored_text(34, "DEBUG")
                print(
                    f"[{time.strftime('%H:%M:%S', time.localtime())}] {colored_text} {msg}"
                )
                if self.wait_msg:
                    print(self.wait_msg, end="")
                    move_cursor_to_end_of_line(len(self.wait_msg))
            else:
                print(msg, end="")
                self.wait_msg = msg
            file.write(
                f"[{time.strftime('%H:%M:%S', time.localtime())}] [{level}] {msg}" + "\n"
            )

    def info_print(self, *msg) -> None:
        if self.mcdr_core:
            self.mcdr_core.logger.info("".join(msg))
        else:
            self._print("INFO", "".join(msg))

    def warn_print(self, *msg) -> None:
        if self.mcdr_core:
            self.mcdr_core.logger.warn("".join(msg))
        else:
            self._print("WARN", "".join(msg))

    def error_print(self, *msg) -> None:
        if self.mcdr_core:
            self.mcdr_core.logger.error("".join(msg))
        else:
            self._print("ERROR", "".join(msg))

    def debug_print(self, *msg) -> None:
        from connect_core.get_config_translate import config
        if config("debug"):
            if self.mcdr_core:
                self.mcdr_core.logger.info("[DEBUG] " + "".join(msg))
            else:
                self._print("DEBUG", "".join(msg))

    def info_input(self, *msg) -> str:
        self._print("INFO", "".join(msg), False)
        put = input()
        self.wait_msg = None
        return put

    def colored_text(self, color_code, text):
        return f"[\033[{color_code}m{text}\033[0m]"


def delete_current_line():
    # 使用 ANSI 转义序列删除光标所在的行
    sys.stdout.write("\033[2K")  # 清除整行
    sys.stdout.write("\033[1G")  # 将光标移至行首
    sys.stdout.flush()


def move_cursor_to_end_of_line(text_len):
    # 将光标移动到行末（假设行长度已知）
    sys.stdout.write(f"\033[{text_len / 2}C")
    sys.stdout.flush()


def info_print(*msg) -> None:
    log_system.info_print("".join(msg))


def warn_print(*msg) -> None:
    log_system.warn_print("".join(msg))


def error_print(*msg) -> None:
    log_system.error_print("".join(msg))


def debug_print(*msg) -> None:
    log_system.debug_print("".join(msg))


def info_input(*msg) -> str:
    return log_system.info_input("".join(msg))


def log_main() -> None:
    global log_system
    log_system = LogSystem()
