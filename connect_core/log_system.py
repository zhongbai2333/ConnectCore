import os
import sys
import time
from mcdreforged.api.all import PluginServerInterface

global log_system


class LogSystem:
    def __init__(
        self,
        mcdr_core: PluginServerInterface = None,
        filelog: str = None,
        path: str = "logs/",
    ) -> None:
        if not os.path.exists(path):
            os.makedirs(path)
        if filelog is None:
            filelog = f"Log-{time.strftime('%b_%d-%H_%M_%S', time.localtime())}.log"
        self.logfile = os.path.join(path, filelog)
        self.mcdr_core = mcdr_core
        self.wait_msg = None

    def _log(self, level: str, msg: str, enter: bool = True) -> None:
        with open(self.logfile, "a", encoding="utf-8") as file:
            timestamp = time.strftime("%H:%M:%S", time.localtime())
            if enter:
                if self.wait_msg:
                    self._delete_current_line()
                colored_level = self._get_colored_text(level)
                print(f"[{timestamp}] {colored_level} {msg}")
                if self.wait_msg:
                    print(self.wait_msg, end="")
                    self._move_cursor_to_end_of_line(len(self.wait_msg))
            else:
                print(msg, end="")
                self.wait_msg = msg
            file.write(f"[{timestamp}] [{level}] {msg}\n")

    def info(self, *msg) -> None:
        self._log_msg("INFO", *msg)

    def warn(self, *msg) -> None:
        self._log_msg("WARN", *msg)

    def error(self, *msg) -> None:
        self._log_msg("ERROR", *msg)

    def debug(self, *msg) -> None:
        if self._is_debug_mode():
            self._log_msg("DEBUG", *msg)

    def input_info(self, *msg) -> str:
        self._log("INFO", "".join(msg), False)
        user_input = input()
        self.wait_msg = None
        return user_input

    def _log_msg(self, level: str, *msg) -> None:
        if self.mcdr_core:
            getattr(self.mcdr_core.logger, level.lower())("".join(msg))
        else:
            self._log(level, "".join(msg))

    def _get_colored_text(self, level: str) -> str:
        color_codes = {"INFO": 32, "WARN": 33, "ERROR": 31, "DEBUG": 34}
        return f"[\033[{color_codes[level]}m{level}\033[0m]"

    def _is_debug_mode(self) -> bool:
        from connect_core.get_config_translate import config

        return config("debug")

    @staticmethod
    def _delete_current_line() -> None:
        sys.stdout.write("\033[2K")
        sys.stdout.write("\033[1G")
        sys.stdout.flush()

    @staticmethod
    def _move_cursor_to_end_of_line(text_len: int) -> None:
        sys.stdout.write(f"\033[{text_len / 2}C")
        sys.stdout.flush()


def log_main() -> None:
    global log_system
    log_system = LogSystem()


def info_print(*msg) -> None:
    log_system.info(*msg)


def warn_print(*msg) -> None:
    log_system.warn(*msg)


def error_print(*msg) -> None:
    log_system.error(*msg)


def debug_print(*msg) -> None:
    log_system.debug(*msg)


def info_input(*msg) -> str:
    return log_system.input_info(*msg)


def wait_msg(*msg) -> None:
    log_system.wait_msg = "".join(msg)