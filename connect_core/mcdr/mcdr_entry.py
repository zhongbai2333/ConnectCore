from mcdreforged.api.all import *

__mcdr_server = None


def get_mcdr() -> PluginServerInterface | None:
    """
    获取MCDR

    Returns:
        PluginServerInterface | None: MCDR状态
    """
    return __mcdr_server


# MCDR Start point
def on_load(server: PluginServerInterface, _):
    global __mcdr_server
    __mcdr_server = server

    __mcdr_server.logger.info("Hello")
