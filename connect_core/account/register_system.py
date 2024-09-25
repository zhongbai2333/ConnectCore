from cryptography.fernet import Fernet
import threading, time, base64, requests, psutil, socket, json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from connect_core.interface.control_interface import CoreControlInterface

global _control_interface
_password = ""


def spawn_password():
    """
    生成密钥, 并存储到password中
    """
    global _password
    while True:
        _password = Fernet.generate_key().decode()
        _control_interface.debug(f"New Password! {_password}")
        time.sleep(180)


def encode_base64(data: str) -> str:
    """
    对输入的数据进行Base64编码

    Args:
        data (str): 需要编码的字节数据
    :return: 编码后的字符串
    """
    encoded_bytes = base64.b64encode(data.encode("utf-8"))
    return encoded_bytes.decode("utf-8")


def decode_base64(encoded_data: str) -> str:
    """
    对Base64编码的数据进行解码

    Args:
        encoded_data(str): Base64编码的字符串
    :return: 解码后的字节数据
    """
    decoded_bytes = base64.b64decode(encoded_data)
    return decoded_bytes.decode("utf-8")


def get_all_internal_ips():
    """
    获取所有网卡的内网IP地址
    :return: 一个列表, 包含所有内网IP地址
    """
    ip_addresses = []
    # 获取所有网络接口的信息
    for interface, addrs in psutil.net_if_addrs().items():
        for addr in addrs:
            if addr.family == socket.AF_INET:  # 只获取IPv4地址
                ip_addresses.append(addr.address)
    return ip_addresses


def get_external_ip() -> str:
    """
    获取公网地址
    :return: 一个公网IP
    """
    response = requests.get("https://ifconfig.me/ip")
    return response.text.strip()


# Public
def register_system_main(control_interface: "CoreControlInterface"):
    """
    子服务器账户系统主程序

    Args:
        control_interface (CoreControlInterface): 控制核心
    """
    global _control_interface
    _control_interface = control_interface

    _control_interface.save_config({}, "account.json")

    spawn_password_thread = threading.Thread(target=spawn_password)
    spawn_password_thread.daemon = True
    spawn_password_thread.start()


def get_password() -> str:
    """
    获取初始化密钥

    :return str: 密钥字符串
    """
    data = {
        "ip": {
            "config": _control_interface.get_config()["ip"],
            "inside": get_all_internal_ips(),
            "outside": get_external_ip(),
        },
        "port": _control_interface.get_config()["port"],
        "http_port": _control_interface.get_config()["http_port"],
        "password": _password,
    }
    data = encode_base64(json.dumps(data))
    return data


def get_register_password() -> str:
    """
    获取初始化临时密钥

    :return: 密钥字符串
    """
    return _password


def analyze_password(key: str) -> dict:
    """
    解析初始化密钥

    Args:
        key (str): 密钥
    :return: 初始化字典
    """
    data = json.loads(decode_base64(key))
    return data
