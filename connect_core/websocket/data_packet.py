import time
import json
import hashlib


class DataPacket(object):
    """数据包处理相关代码"""

    def __init__(self):
        from connect_core.cli.cli_entry import get_is_server

        self._packet_list = {}
        self._is_server = get_is_server()

        self.TYPE_TEST_CONNECT = (-1, 0)
        self.TYPE_PING = (0, 1)
        self.TYPE_PONG = (0, 2)
        self.TYPE_CONTROL_STOP = (1, 0)
        self.TYPE_CONTROL_RELOAD = (1, 1)
        self.TYPE_CONTROL_MAINTENANCE = (1, 2)
        self.TYPE_CONTROL_RESUME = (1, 3)
        self.TYPE_REGISTER = (2, 0)
        self.TYPE_REGISTERED = (2, 1)
        self.TYPE_REGISTER_ERROR = (2, 2)
        self.TYPE_LOGIN = (3, 0)
        self.TYPE_LOGINED = (3, 1)
        self.TYPE_NEW_LOGIN = (3, 2)
        self.TYPE_DEL_LOGIN = (3, 3)
        self.TYPE_LOGIN_ERROR = (3, 4)
        self.TYPE_DATA_SEND = (4, 0)
        self.TYPE_DATA_SENDOK = (4, 1)
        self.TYPE_DATA_ERROR = (4, 2)
        self.TYPE_FILE_SEND = (5, 0)
        self.TYPE_FILE_SENDING = (5, 1)
        self.TYPE_FILE_SENDOK = (5, 2)
        self.TYPE_FILE_ERROR = (5, 3)

        self.DEFAULT_TO_FROM = ("-----", "-----")
        self.DEFAULT_SERVER = ("-----", "system")
        self.DEFAULT_ALL = ("all", "system")

    def get_data_packet(
        self, Type: tuple, ToInfo: tuple, FromInfo: tuple, Data: any, But_sevrer_id: list = []
    ) -> dict:
        """
        获取数据包格式

        Args:
            Type (tuple): 数据包类型和状态
            ToInfo (tuple): 数据包目标信息
            FromInfo (tuple): 数据包来源信息
            Data (any): 数据
        :return: 数据包字典
        """
        packets = {}
        if Type == self.TYPE_TEST_CONNECT:
            sid = {"-----": -1}
        elif Type[0] == 0:
            sid = self._get_sid(ToInfo[0], False)
        else:
            sid = self._get_sid(ToInfo[0], But_sevrer_id=But_sevrer_id)
        if Data is None:
            Data = {}
        else:
            Data = {
                "payload": Data,
                "timestamp": time.time(),
                "checksum": self.generate_md5_checksum(Data),
            }
        for i in sid.keys():
            packet = {
                "sid": sid[i],
                "type": Type,
                "to": ToInfo,
                "from": FromInfo,
                "data": Data,
            }
            if sid[i] != -1 and Type[0] != 0:
                self._packet_list[i].append(packet)
            packets[i] = packet
        return packets

    def get_history_packet(self, server_id: str, old_sid: int) -> list:
        """
        获取历史数据包

        Args:
            server_id (str): 服务器id
            old_sid (int): 旧sid
        :return: 历史数据包
        """
        if server_id in self._packet_list.keys():
            return self._packet_list[server_id][old_sid:]
        return []

    def add_recv_packet(self, server_id: str, packet: dict) -> None:
        """
        添加接收到的数据包

        Args:
            server_id (str): 服务器id
            packet (dict): 数据包
        """
        if (server_id != "-----" or not self._is_server) and packet["type"][0] != 0:
            if server_id in self._packet_list.keys():
                self._packet_list[server_id].append(packet)
            else:
                self._packet_list[server_id] = [packet]

    def del_server_id(self, server_id: str) -> None:
        """
        删除指定服务器id的数据包

        Args:
            server_id (str): 服务器id
        """
        if server_id in self._packet_list.keys():
            del self._packet_list[server_id]
    
    def del_recv_packet(self, server_id: str, num: int) -> None:
        """
        删除接收到的数据包

        Args:
            server_id (str): 服务器id
            num (int): 从后往前删除的数据包数量
        """
        if server_id in self._packet_list.keys():
            self._packet_list[server_id] = self._packet_list[server_id][:-num]

    def _get_sid(
        self, server_id: str, add_sid: bool = True, But_sevrer_id: list = []
    ) -> dict:
        """
        获取sid

        Args:
            server_id (str): 服务器id
            add_sid (bool): 是否添加sid，默认为True
            But_sevrer_id (list): 排除的服务器id
        :return: sid字典
        """
        sid_list = {}
        if self._is_server:  # 服务器
            if server_id == "all":  # 发送给所有服务器
                for i in self._packet_list.keys():
                    if i not in But_sevrer_id:
                        sid_list[i] = len(self._packet_list[i]) + 1
            elif server_id == "-----":  # 发送给陌生客户端
                sid_list["-----"] = 0
            else:  # 发送给指定客户端
                if server_id in self._packet_list.keys():
                    if add_sid:
                        sid_list[server_id] = len(self._packet_list[server_id]) + 1
                    else:
                        sid_list[server_id] = len(self._packet_list[server_id])
                else:
                    if add_sid:
                        self._packet_list[server_id] = []  # 新增客户端
                        sid_list[server_id] = 1
                    else:
                        sid_list[server_id] = 0
        else:  # 客户端
            if "-----" not in self._packet_list.keys():
                self._packet_list["-----"] = []
            if add_sid:
                sid_list["-----"] = len(self._packet_list["-----"]) + 1
            else:
                sid_list["-----"] = len(self._packet_list["-----"])
        return sid_list

    def get_file_hash(self, file_path, algorithm="sha256") -> str | None:
        """
        获取文件的哈希值。

        Args:
            file_path (str): 文件路径
            algorithm (str): 哈希算法，默认使用 'sha256'

        Returns:
            str: 文件的哈希值，如果文件不存在则返回 None
        """
        try:
            hash_func = hashlib.new(algorithm)

            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_func.update(chunk)

            return hash_func.hexdigest()
        except (IOError, OSError) as e:
            print(f"计算哈希值时出错: {e}")
            return None
        except ValueError as e:
            print(f"不支持的哈希算法: {e}")
            return None

    def verify_file_hash(self, file_path, expected_hash, algorithm="sha256") -> bool:
        """
        验证文件的哈希值。

        Args:
            file_path (str): 文件路径
            expected_hash (str): 预期的哈希值
            algorithm (str): 哈希算法，默认使用 'sha256'

        Returns:
            bool: 如果哈希值匹配则返回 True，否则返回 False
        """
        actual_hash = self.get_file_hash(file_path, algorithm)

        if actual_hash is None:
            print("无法获取文件的哈希值。")
            return False

        return actual_hash == expected_hash

    def generate_md5_checksum(self, data):
        """
        Generate MD5 checksum for the given data.

        Args:
            data: The data to generate checksum for. Must be convertible to bytes.

        Returns:
            str: The generated MD5 checksum as a hex string.
        """
        md5_hash = hashlib.md5()

        # 如果 data 是字符串，编码为字节
        if isinstance(data, str):
            md5_hash.update(data.encode("utf-8"))
        # 如果 data 是字典或其他对象，先序列化为字符串
        elif isinstance(data, (dict, list)):
            md5_hash.update(json.dumps(data, ensure_ascii=False).encode("utf-8"))
        else:
            # 如果 data 是字节对象，直接使用
            md5_hash.update(data)

        return md5_hash.hexdigest()

    def verify_md5_checksum(self, data, checksum) -> bool:
        """
        校验数据是否匹配给定的 MD5 校验和。

        :param data: 输入数据，类型为 bytes。
        :param checksum: 输入的 MD5 校验和，类型为 str。
        :return: 如果校验通过返回 True，否则返回 False。
        """
        return self.generate_md5_checksum(data) == checksum
