from connect_core.cli.storage import JsonDataEditor, YmlLanguage

from mcdreforged.api.all import *

global __mcdr_server


def config(key: str):
    if __mcdr_server:
        pass
    else:
        return JsonDataEditor().read()[key]


def translate(key: str):
    if __mcdr_server:
        return _tr(key)
    else:
        key_n = "connect_core." + key
        key_n = key_n.split(".")
        return get_nested_value(YmlLanguage(config("language")).translate, key_n)


def get_nested_value(data, keys_path, default=None):
    for key in keys_path:
        if isinstance(data, dict) and key in data:
            data = data[key]
        else:
            return default
    return data


def _tr(key: str) -> str:
    return ServerInterface.si().tr("connect_core."+ key)


def c_t_main(mcdr_core: PluginServerInterface = None):
    global __mcdr_server

    __mcdr_server = mcdr_core
