import os
import time
import json
import random
import string
import hashlib
import asyncio
from cryptography.fernet import Fernet
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from connect_core.interface.control_interface import CoreControlInterface
    from connect_core.websocket.server import WebsocketServer
    from connect_core.websocket.client import WebsocketClient

from connect_core.plugin.init_plugin import (
    new_connect,
    del_connect,
    recv_data,
    recv_file,
)
from connect_core.tools import restart_program

_control_interface = None


class DataPacket(object):
    """数据包处理相关代码"""

    def __init__(self):
        self._packet_list = {}
        self._is_server = None

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
        self,
        packet_type: Tuple[int, int],
        to_info: Tuple[str, str],
        from_info: Tuple[str, str],
        data: Any,
        exclude_server_ids: Optional[List[str]] = None,
    ) -> Dict[str, dict]:
        """
        获取数据包格式

        Args:
            Type (tuple): 数据包类型和状态
            ToInfo (tuple): 数据包目标信息
            FromInfo (tuple): 数据包来源信息
            Data (any): 数据
        :return: 数据包字典
        """
        exclude_server_ids = exclude_server_ids or []
        packets = {}

        sid_map = self._get_sid(
            to_info[0],
            add_sid=(packet_type[0] != 0),
            exclude_server_ids=exclude_server_ids,
        )

        if data is not None:
            data = {
                "payload": data,
                "timestamp": time.time(),
                "checksum": self.generate_md5_checksum(data),
            }
        else:
            data = {}

        for server_id, sid in sid_map.items():
            packet = {
                "sid": sid,
                "type": packet_type,
                "to": to_info,
                "from": from_info,
                "data": data,
            }

            if sid != -1 and packet_type[0] != 0:
                self._packet_list.setdefault(server_id, []).append(packet)

            packets[server_id] = packet

        return packets

    def get_history_packet(self, server_id: str, old_sid: int) -> List[dict]:
        """
        获取历史数据包

        Args:
            server_id (str): 服务器id
            old_sid (int): 旧sid
        :return: 历史数据包
        """
        return self._packet_list.get(server_id, [])[old_sid:]

    def add_recv_packet(self, server_id: str, packet: dict) -> None:
        """
        添加接收到的数据包

        Args:
            server_id (str): 服务器id
            packet (dict): 数据包
        """
        if (server_id != "-----" or not self._is_server) and packet["type"][0] != 0:
            self._packet_list.setdefault(server_id, []).append(packet)

    def del_server_id(self, server_id: str) -> None:
        """
        删除指定服务器id的数据包

        Args:
            server_id (str): 服务器id
        """
        self._packet_list.pop(server_id, None)

    def del_recv_packet(self, server_id: str, count: int) -> None:
        """
        删除接收到的数据包

        Args:
            server_id (str): 服务器id
            num (int): 从后往前删除的数据包数量
        """
        if server_id in self._packet_list:
            self._packet_list[server_id] = self._packet_list[server_id][:-count]

    def _get_sid(
        self,
        server_id: str,
        add_sid: bool = True,
        exclude_server_ids: Optional[List[str]] = None,
    ) -> Dict[str, int]:
        """
        获取sid

        Args:
            server_id (str): 服务器id
            add_sid (bool): 是否添加sid，默认为True
            But_sevrer_id (list): 排除的服务器id
        :return: sid字典
        """
        exclude_server_ids = exclude_server_ids or []
        sid_map = {}

        if self._is_server:
            if server_id == "all":
                for sid in self._packet_list:
                    if sid not in exclude_server_ids:
                        sid_map[sid] = len(self._packet_list[sid]) + 1
            elif server_id == "-----":
                sid_map["-----"] = 0
            elif server_id in self._packet_list:
                sid_map[server_id] = len(self._packet_list[server_id]) + (
                    1 if add_sid else 0
                )
            elif add_sid:
                self._packet_list[server_id] = []
                sid_map[server_id] = 1
            else:
                sid_map[server_id] = 0
        else:
            self._packet_list.setdefault("-----", [])
            sid_map["-----"] = len(self._packet_list["-----"]) + (1 if add_sid else 0)

        return sid_map

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


class ServerDataPacket(DataPacket):
    """服务器数据包处理相关代码"""

    def __init__(
        self,
        control_interface: "CoreControlInterface",
        websocket_server: "WebsocketServer",
    ):
        global _control_interface
        super().__init__()

        self._is_server = True
        self._wait_file_list = {}
        self._websocket_server = websocket_server
        self._send = self._websocket_server.send
        self._broadcast = self._websocket_server.broadcast

        _control_interface = control_interface

    async def parse_msg(self, data: dict, websocket) -> None:
        server_id = data["from"][0]
        to_server_id = data["to"][0]
        data_type = tuple(data["type"])

        # Log and record the received packet
        self.add_recv_packet(server_id, data)
        self._log_debug(data)

        # Handle messages for all servers or specific servers
        if to_server_id in ("-----", "all"):
            await self._handle_broadcast_or_global(
                data, websocket, server_id, to_server_id, data_type
            )
        else:
            await self._handle_direct_message(
                data, websocket, server_id, to_server_id, data_type
            )

    def _log_debug(self, data):
        _control_interface.debug(
            f"[R][{data['type']}][{data['from']} -> {data['to']}][{data['sid']}] {data['data']}"
        )

    async def _handle_broadcast_or_global(
        self, data, websocket, server_id, to_server_id, data_type
    ):
        if to_server_id == "all":
            data_return = data["data"].get("payload") if data["data"] else None
            packet = self.get_data_packet(
                data["type"], data["to"], data["from"], data_return, [server_id]
            )
            if data_type == self.TYPE_DATA_SEND:
                self._websocket_server.last_send_packet.update(packet)
            await self._broadcast(packet)

        match data_type:
            case self.TYPE_PING:
                await self._handle_ping(data, websocket, server_id)
            case self.TYPE_CONTROL_STOP:
                pass  # Placeholder for future implementation
            case self.TYPE_REGISTER:
                await self._handle_register(data, websocket)
            case self.TYPE_REGISTER_ERROR:
                await self._handle_register_error(data, websocket)
            case self.TYPE_LOGIN:
                await self._handle_login(data, websocket, server_id)
            case self.TYPE_DATA_SEND:
                await self._handle_data_send(data, websocket, server_id)
            case self.TYPE_DATA_SENDOK:
                await self._handle_data_sendok(data, websocket, server_id)
            case self.TYPE_DATA_ERROR:
                await self._handle_data_error(data, websocket, server_id)
            case self.TYPE_FILE_SEND:
                await self._handle_file_send(data, websocket, server_id)
            case self.TYPE_FILE_SENDING:
                await self._handle_file_sending(data, websocket, server_id)
            case self.TYPE_FILE_SENDOK:
                await self._handle_file_sendok(data, websocket, server_id)

    async def _handle_direct_message(
        self, data, websocket, server_id, to_server_id, data_type
    ):
        data_return = data["data"].get("payload") if data["data"] else None
        packet = self.get_data_packet(
            data["type"], data["to"], data["from"], data_return
        )
        if data_type == self.TYPE_DATA_SEND:
            self._websocket_server.last_send_packet[to_server_id] = packet
            await self._send_acknowledgement(websocket, server_id)
        await self._return_send_packet(
            data, self._websocket_server.websockets[to_server_id], to_server_id
        )

    async def _handle_ping(self, data, websocket, server_id):
        history_packet = self.get_history_packet(server_id, data["sid"])
        if not history_packet:
            await self._send(
                self.get_data_packet(
                    self.TYPE_PONG,
                    (server_id, "system"),
                    self.DEFAULT_SERVER,
                    None,
                ),
                websocket,
                server_id,
            )
        else:
            for packet in history_packet:
                await self._send(packet, websocket, server_id)

    async def _handle_register(self, data, websocket):
        server_id, password = self._generate_server_credentials()
        self._save_credentials(server_id, password)
        await self._send_registration_response(websocket, server_id, password)

    async def _handle_register_error(self, data, websocket):
        server_id, password = self._generate_server_credentials()
        accounts = _control_interface.get_config("account.json")
        del accounts[list(accounts.keys())[-1]]  # Remove the last account
        accounts[server_id] = password
        _control_interface.save_config(accounts, "account.json")
        await self._send_registration_response(websocket, server_id, password)

    async def _handle_login(self, data, websocket, server_id):
        if server_id not in self._websocket_server.websockets:
            self._websocket_server.websockets[server_id] = websocket
            self._websocket_server.servers_info[server_id] = data["data"].get("payload")
            _control_interface.info(f"Server {server_id} Login")
            await self._send_login_response(websocket, server_id)
            new_connect(list(self._websocket_server.servers_info.keys()))
            await self._broadcast_server_list()
        else:
            await self._send_login_error(websocket, server_id)

    async def _handle_data_send(self, data, websocket, server_id):
        if not data["data"].get("payload", None) or self.verify_md5_checksum(
            data["data"].get("payload"), data["data"].get("checksum")
        ):
            recv_data(data["to"][1], data["data"].get("payload", None))
            await self._send_data_response(websocket, server_id)
        else:
            await self._send_data_error(websocket, server_id)

    async def _handle_data_sendok(self, data, websocket, server_id):
        self._websocket_server.last_send_packet.pop(server_id, None)

    async def _handle_data_error(self, data, websocket, server_id):
        await self._send_last_data_packet(websocket, server_id)

    async def _handle_file_send(self, data, websocket, server_id):
        if self.verify_md5_checksum(
            data["data"].get("payload"), data["data"].get("checksum")
        ):
            self._wait_file_list[server_id] = open(
                data["data"].get("payload")["save_path"], "wb"
            )
        else:
            await self._send_file_error(websocket, server_id)

    async def _handle_file_sending(self, data, websocket, server_id):
        if self.verify_md5_checksum(
            data["data"].get("payload"), data["data"].get("checksum")
        ):
            if server_id in self._wait_file_list:
                self._wait_file_list[server_id].write(
                    data["data"].get("payload")["file"]
                )
                self._wait_file_list[server_id].flush()
            else:
                await self._send_file_error(websocket, server_id)
        else:
            await self._send_file_error(websocket, server_id)

    async def _handle_file_sendok(self, data, websocket, server_id):
        if self.verify_md5_checksum(
            data["data"].get("payload"), data["data"].get("checksum")
        ):
            if server_id in self._wait_file_list:
                self._wait_file_list[server_id].close()
                self._wait_file_list.pop(server_id, [])
                if self.verify_file_hash(
                    data["data"].get("payload")["save_path"],
                    data["data"].get("payload")["hash"],
                ):
                    recv_file(
                        data["to"][1],
                        data["data"].get("payload")["save_path"],
                    )
                else:
                    await self._send_file_error(websocket, server_id)
            else:
                await self._send_file_error(websocket, server_id)
        else:
            await self._send_file_error(websocket, server_id)

    # Helper methods for repetitive actions
    def _generate_server_credentials(self):
        server_id = self._generate_random_id(5)
        while server_id in self._websocket_server.websockets:
            server_id = self._generate_random_id(5)
        password = Fernet.generate_key().decode()
        return server_id, password

    def _save_credentials(self, server_id, password):
        accounts = _control_interface.get_config("account.json")
        accounts[server_id] = password
        _control_interface.save_config(accounts, "account.json")

    async def _send_acknowledgement(self, websocket, server_id):
        await self._send(
            self.get_data_packet(
                self.TYPE_DATA_SENDOK, (server_id, "system"), self.DEFAULT_SERVER, None
            ),
            websocket,
            server_id,
        )

    async def _return_send_packet(self, data, to_websocket, to_server_id):
        await self._send(
            self.get_data_packet(
                data["type"],
                data["to"],
                data["from"],
                data["data"].get("payload", None),
            ),
            to_websocket,
            to_server_id,
        )

    async def _send_registration_response(self, websocket, server_id, password):
        await self._send(
            self.get_data_packet(
                self.TYPE_REGISTERED,
                (server_id, "system"),
                self.DEFAULT_SERVER,
                {"password": password},
            )[server_id],
            websocket,
            "-----",
        )

    async def _send_login_response(self, websocket, server_id):
        await self._send(
            self.get_data_packet(
                self.TYPE_LOGINED,
                (server_id, "system"),
                self.DEFAULT_SERVER,
                None,
            ),
            websocket,
            server_id,
        )

    async def _send_login_error(self, websocket, server_id):
        await self._send(
            self.get_data_packet(
                self.TYPE_LOGIN_ERROR,
                (server_id, "system"),
                self.DEFAULT_SERVER,
                {"error": "Already Login"},
            ),
            websocket,
            server_id,
        )
        self.del_recv_packet(server_id, 2)
        await websocket.close(reason="401")

    async def _broadcast_server_list(self):
        await self._broadcast(
            self.get_data_packet(
                self.TYPE_NEW_LOGIN,
                self.DEFAULT_ALL,
                self.DEFAULT_SERVER,
                {"server_list": list(self._websocket_server.servers_info.keys())},
            )
        )

    async def _send_data_response(self, websocket, server_id):
        await self._send(
            self.get_data_packet(
                self.TYPE_DATA_SENDOK, (server_id, "system"), self.DEFAULT_SERVER, None
            ),
            websocket,
            server_id,
        )

    async def _send_data_error(self, websocket, server_id):
        await self._send(
            self.get_data_packet(
                self.TYPE_DATA_ERROR, (server_id, "system"), self.DEFAULT_SERVER, None
            ),
            websocket,
            server_id,
        )

    async def _send_last_data_packet(self, websocket, server_id):
        self._send(
            self._websocket_server.last_send_packet.get(server_id, None),
            websocket,
            server_id,
        )

    async def _send_file_error(self, websocket, server_id):
        await self._send(
            self.get_data_packet(
                self.TYPE_FILE_ERROR,
                (server_id, "system"),
                self.DEFAULT_SERVER,
                None,
            ),
            websocket,
            server_id,
        )

    # Tools
    def _generate_random_id(self, n: int) -> str:
        """生成指定长度的随机字符串，包含字母和数字。"""
        numeric_part = "".join(
            [str(random.randint(0, 9)) for _ in range(random.randint(1, n))]
        )
        alpha_part = "".join(
            [random.choice(string.ascii_letters) for _ in range(n - len(numeric_part))]
        )
        return "".join(random.sample(list(numeric_part + alpha_part), n))


class ClientDataPacket(DataPacket):
    """客户端数据包处理相关代码"""

    def __init__(
        self,
        control_interface: "CoreControlInterface",
        websocket_client: "WebsocketClient",
    ):
        global _control_interface
        super().__init__()

        self._is_server = False
        self._wait_file = None
        self._websocket_client = websocket_client
        self._send = self._websocket_client.send

        _control_interface = control_interface

    async def parse_msg(self, data: dict) -> None:
        data_type = tuple(data["type"])

        # Log and record the received packet
        self.add_recv_packet("-----", data)
        self._log_debug(data)

        # Handle messages for all servers or specific servers
        await self._handle_global(data, data_type)

    def _log_debug(self, data):
        _control_interface.debug(
            f"[R][{data['type']}][{data['from']} -> {data['to']}][{data['sid']}] {data['data']}"
        )

    async def _handle_global(self, data, data_type):
        match data_type:
            case self.TYPE_PONG:
                pass
            case self.TYPE_CONTROL_STOP:
                pass  # Placeholder for future implementation
            case self.TYPE_REGISTERED:
                await self._handle_registered(data)
            case self.TYPE_REGISTER_ERROR:
                await self._handle_register_error(data)
            case self.TYPE_LOGINED:
                await self._handle_logined(data)
            case self.TYPE_NEW_LOGIN:
                await self._handle_new_login(data)
            case self.TYPE_DEL_LOGIN:
                await self._handle_del_login(data)
            case self.TYPE_LOGIN_ERROR:
                await self._handle_login_error(data)
            case self.TYPE_DATA_SEND:
                await self._handle_data_send(data)
            case self.TYPE_DATA_SENDOK:
                await self._handle_data_sendok(data)
            case self.TYPE_DATA_ERROR:
                await self._handle_data_error(data)
            case self.TYPE_FILE_SEND:
                await self._handle_file_send(data)
            case self.TYPE_FILE_SENDING:
                await self._handle_file_sending(data)
            case self.TYPE_FILE_SENDOK:
                await self._handle_file_sendok(data)

    async def _handle_registered(self, data):
        if self.verify_md5_checksum(
            data["data"].get("payload"), data["data"].get("checksum")
        ):
            self._config["account"] = data["to"][0]
            self._config["password"] = data["data"].get("payload")["password"]
            _control_interface.save_config(self._config)
            restart_program()
        else:
            await self._send_register_error()

    async def _handle_register_error(self, data):
        _control_interface.error(f"Register Error: {data["data"]["payload"]}")
        self._websocket_client.stop_server()

    async def _handle_logined(self, data):
        os.system(f"title ConnectCore Client {data["to"][0]}")
        self._websocket_client.server_id = data["to"][0]
        self._websocket_client._start_trigger_websocket_client()

    async def _handle_new_login(self, data):
        new_connect(data["data"].get("payload")["server_list"])

    async def _handle_del_login(self, data):
        del_connect(data["data"].get("payload")["server_list"])

    async def _handle_login_error(self, data):
        _control_interface.error(f"Login Error: {data["data"]["payload"]["error"]}")
        self._websocket_client.stop_server()

    async def _handle_data_send(self, data):
        if not data["data"].get("payload", None) or self.verify_md5_checksum(
            data["data"].get("payload"), data["data"].get("checksum")
        ):
            recv_data(data["to"][1], data["data"].get("payload", None))
            await self._send_data_response()
        else:
            await self._send_data_error()

    async def _handle_data_sendok(self, data):
        self._websocket_client.last_data_packet = None

    async def _handle_data_error(self, data):
        await self._send_last_data_packet()

    async def _handle_file_send(self, data):
        if self.verify_md5_checksum(
            data["data"].get("payload"), data["data"].get("checksum")
        ):
            self._wait_file = open(data["data"].get("payload")["save_path"], "wb")
        else:
            await self._send_file_error()

    async def _handle_file_sending(self, data):
        if self.verify_md5_checksum(
            data["data"].get("payload"), data["data"].get("checksum")
        ):
            if self._wait_file:
                self._wait_file.write(data["data"].get("payload")["file"])
                self._wait_file.flush()
            else:
                await self._send_file_error()
        else:
            await self._send_file_error()

    async def _handle_file_sendok(self, data):
        if self.verify_md5_checksum(
            data["data"].get("payload"), data["data"].get("checksum")
        ):
            if self._wait_file:
                self._wait_file.close()
                self._wait_file = None
                if self.verify_file_hash(
                    data["data"].get("payload")["save_path"],
                    data["data"].get("payload")["hash"],
                ):
                    recv_file(
                        data["to"][1],
                        data["data"].get("payload")["save_path"],
                    )
                else:
                    await self._send_file_error()
            else:
                await self._send_file_error()
        else:
            await self._send_file_error()

    # Helper methods for repetitive actions
    async def _send_register_error(self):
        await self._send(
            self.get_data_packet(
                self.TYPE_REGISTER_ERROR,
                self.DEFAULT_SERVER,
                self.DEFAULT_TO_FROM,
                None,
            )
        )

    async def _send_data_response(self):
        await self._send(
            self.get_data_packet(
                self.TYPE_DATA_SENDOK,
                self.DEFAULT_SERVER,
                (self._websocket_client.server_id, "system"),
                None,
            )
        )

    async def _send_data_error(self):
        await self._send(
            self.get_data_packet(
                self.TYPE_DATA_ERROR,
                self.DEFAULT_SERVER,
                (self._websocket_client.server_id, "system"),
                None,
            )
        )

    async def _send_last_data_packet(self):
        self._send(self._last_send_packet)

    async def _send_file_error(self):
        await self._send(
            self.get_data_packet(
                self.TYPE_FILE_ERROR,
                self.DEFAULT_SERVER,
                (self._websocket_client.server_id, "system"),
                None,
            )
        )
