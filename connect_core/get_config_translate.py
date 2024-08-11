from connect_core.cli.storage import JsonDataEditor, YmlLanguage

from mcdreforged.api.all import *

global __mcdr_server


def config(key: str):
    """
    获取配置文件相关信息

    Args:
        key (str): 配置文件关键字
    
    Returns:
        item (str): 配置项, 如果key无效则为 None
    """
    if __mcdr_server:
        pass
    else:
        if JsonDataEditor().read():
            return JsonDataEditor().read()[key]
        else:
            return None


def translate(key: str):
    """
    获取翻译项

    Args:
        key (str): 翻译文件关键字

    Returns:
        item (str): 翻译文本
    """
    if __mcdr_server:
        return _tr(key)
    else:
        key_n = "connect_core." + key
        key_n = key_n.split(".")
        return get_nested_value(YmlLanguage(config("language")).translate, key_n)


def is_mcdr() -> bool:
    """
    获取运行环境是否为MCDR

    Returns:
        is_mcdr (bool): 返回布尔值
    """
    return True if __mcdr_server else False


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
