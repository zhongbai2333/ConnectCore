from connect_core.interface.contol_interface import ControlInterface

interface_list = {}

# Public
def get_interface_main(sid: str, self_path: str, config_path: str) -> 'ControlInterface':
    """
    获取控制接口

    Args:
        sid (str): 插件或服务器ID
        self_path (str): 插件或服务器自身路径, 带文件名
        config_path (str): 插件或服务器配置文件路径
    """
    _control_interface = ControlInterface(sid, self_path, config_path)
    interface_list[sid] = (self_path, config_path, _control_interface)
    return _control_interface

def del_interface(sid: str) -> None:
    """
    删除控制接口

    Args:
        sid (str): 插件或服务器ID
    """
    del interface_list[sid]
    return