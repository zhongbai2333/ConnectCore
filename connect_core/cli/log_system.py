import time, os

global log_system


class LogSystem:
    def __init__(
        self,
        filelog: str = f"Log-{time.strftime('%b_%d-%H_%M_%S', time.localtime())}.log",
        path: str = "logs/",
    ):
        if not os.path.exists(path):
            os.makedirs(path)
        self.logfile = path + filelog

    def _print(self, level: str, msg: str, enter: bool = True):
        """总输出"""
        with open(self.logfile, "a", encoding="utf-8") as file:
            if enter:
                print(msg)
            else:
                print(msg, end="")
            file.write(
                f"[{time.strftime('%H:%M:%S', time.localtime())}][{level}] {msg}" + "\n"
            )

    def info_print(self, *msg):
        self._print("INFO", "".join(msg))

    def info_input(self, *msg):
        self._print("INFO", "".join(msg), False)
        return input()


def info_print(*msg):
    log_system.info_print("".join(msg))


def info_input(*msg):
    return log_system.info_input("".join(msg))


def log_main():
    global log_system
    log_system = LogSystem()
