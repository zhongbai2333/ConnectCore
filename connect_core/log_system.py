import time, os

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

    def _print(self, level: str, msg: str, enter: bool = True) -> None:
        """总输出"""
        with open(self.logfile, "a", encoding="utf-8") as file:
            if enter:
                print(msg)
            else:
                print(msg, end="")
            file.write(
                f"[{time.strftime('%H:%M:%S', time.localtime())}][{level}] {msg}" + "\n"
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
        return input()


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
