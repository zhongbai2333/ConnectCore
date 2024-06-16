from mcdreforged.api.all import *

global __mcdr_server


def on_load(server: PluginServerInterface, _):
    global __mcdr_server
    __mcdr_server = server

    __mcdr_server.logger.info("Hello")
