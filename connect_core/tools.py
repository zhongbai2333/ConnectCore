import os
import sys
import time
import base64
import psutil
import socket
import requests
import functools
import threading
from typing import Optional, Union, Callable

try:
    from mcdreforged.api.all import new_thread
except ImportError:
    class FunctionThread(threading.Thread):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.daemon = True  # 确保线程为守护线程

    def new_thread(arg: Optional[Union[str, Callable]] = None):
        """
        启动一个新的线程运行装饰的函数，同时支持类方法和普通函数。
        """

        def wrapper(func):
            @functools.wraps(func)
            def wrap(*args, **kwargs):
                # 检查是否是类方法
                if len(args) > 0 and hasattr(args[0], func.__name__):
                    # 将未绑定方法绑定到实例
                    bound_func = func.__get__(args[0])
                else:
                    # 普通函数
                    bound_func = func

                # 创建线程
                thread = FunctionThread(
                    target=bound_func, args=args, kwargs=kwargs, name=thread_name
                )
                thread.start()
                return thread

            wrap.original = func  # 保留原始函数
            return wrap

        if isinstance(arg, Callable):  # @new_thread 用法
            thread_name = None
            return wrapper(arg)
        else:  # @new_thread(...) 用法
            thread_name = arg
            return wrapper


def auto_trigger(interval: float, thread_name: Optional[str] = None):
    """
    创建一个自动触发的装饰器。

    Args:
        interval (float): 触发间隔时间（秒）。
        thread_name (Optional[str]): 线程名称，默认为函数名。

    Returns:
        Callable: 装饰后的函数。
    """

    def decorator(func: Callable):
        stop_event = threading.Event()

        def trigger_loop(instance=None, *args, **kwargs):
            while not stop_event.is_set():
                if instance:
                    wrapped_func = new_thread(thread_name)(func.__get__(instance))
                else:
                    wrapped_func = new_thread(thread_name)(func)
                wrapped_func(*args, **kwargs)
                time.sleep(interval)

        @new_thread(f"{thread_name or func.__name__}_trigger_loop")
        def start_trigger(instance=None, *args, **kwargs):
            trigger_thread = threading.Thread(
                target=trigger_loop,
                args=(instance,) + args,
                kwargs=kwargs,
                name=thread_name,
                daemon=True,
            )
            trigger_thread.start()
            return trigger_thread

        def stop():
            stop_event.set()

        start_trigger.stop = stop
        return start_trigger

    return decorator


def restart_program() -> None:
    """
    重启程序，使用当前的Python解释器重新执行当前脚本。
    """
    from connect_core.mcdr.mcdr_entry import get_mcdr

    if not get_mcdr():
        python = sys.executable
        os.execl(python, python, *sys.argv)
    else:
        get_mcdr().reload_plugin("connect_core")


def check_file_exists(file_path: str) -> bool:
    """
    检查目录中的特定文件是否存在。

    Args:
        file_path (str): 文件路径

    Returns:
        bool: 如果文件存在则返回 True，否则返回 False
    """
    return os.path.isfile(file_path)


def append_to_path(path: str, filename: str) -> str:
    """
    将文件名附加到给定路径中，如果路径是一个目录的话。

    Args:
        path (str): 要检查和修改的路径。
        filename (str): 如果路径是目录则附加的文件名。

    Returns:
        str: 修改后的路径。
    """
    if os.path.isdir(path):
        return os.path.join(path, filename)
    return path


def encode_base64(data: str) -> str:
    """
    对输入的数据进行Base64编码

    Args:
        data (str): 需要编码的字节数据

    Returns:
        str: 编码后的字符串
    """
    encoded_bytes = base64.b64encode(data.encode("utf-8"))
    return encoded_bytes.decode("utf-8")


def decode_base64(encoded_data: str) -> str:
    """
    对Base64编码的数据进行解码

    Args:
        encoded_data (str): Base64编码的字符串

    Returns:
        str: 解码后的字节数据
    """
    decoded_bytes = base64.b64decode(encoded_data)
    return decoded_bytes.decode("utf-8")


def get_all_internal_ips() -> list:
    """
    获取所有网卡的内网IP地址

    Returns:
        list: 包含所有内网IP地址的列表
    """
    ip_addresses = []
    for interface, addrs in psutil.net_if_addrs().items():
        for addr in addrs:
            if addr.family == socket.AF_INET:  # 只获取IPv4地址
                ip_addresses.append(addr.address)
    return ip_addresses


def get_external_ip() -> str:
    """
    获取公网IP地址

    Returns:
        str: 一个公网IP
    """
    response = requests.get("https://ifconfig.me/ip")
    return response.text.strip()
