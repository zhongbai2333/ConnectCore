import websockets
import json
import asyncio
import random
import string
from mcdreforged.api.all import new_thread

from connect_core.log_system import info_print, warn_print, error_print, debug_print
from connect_core.get_config_translate import config, translate, is_mcdr
from connect_core.rsa_encrypt import rsa_encrypt, rsa_decrypt

global websocket_server


def websocket_server_init() -> None:
    if is_mcdr():
        start_mcdr_server()
    else:
        global websocket_server
        websocket_server = WebsocketServer()
        websocket_server.start_server()


def get_server_list() -> dict:
    return websocket_server.servers_info if websocket_server else {}


@new_thread("Websocket_Server")
def start_mcdr_server() -> None:
    global websocket_server
    websocket_server = WebsocketServer()
    websocket_server.start_server()


class WebsocketServer:
    def __init__(self) -> None:
        self.finish_close = False
        self.host = config("ip")
        self.port = config("port")
        self.websockets = {}
        self.broadcast_websockets = set()
        self.servers_info = {}

    def start_server(self) -> None:
        asyncio.run(self.init_main())

    def close_server(self) -> None:
        if hasattr(self, "main_task"):
            self.main_task.cancel()

    def generate_random_id(self, n: int) -> str:
        numeric_part = "".join(
            [str(random.randint(0, 9)) for _ in range(random.randint(1, n))]
        )
        alpha_part = "".join(
            [random.choice(string.ascii_letters) for _ in range(n - len(numeric_part))]
        )
        return "".join(random.sample(list(numeric_part + alpha_part), n))

    async def init_main(self) -> None:
        self.main_task = asyncio.create_task(self.main())
        try:
            await self.main_task
        except asyncio.CancelledError:
            info_print(translate("net_core.service.stop_websocket"))
            self.finish_close = True

    async def main(self) -> None:
        async with websockets.serve(self.handler, self.host, self.port):
            info_print(translate("net_core.service.start_websocket"))
            await asyncio.Future()

    async def handler(self, websocket) -> None:
        server_id = None
        try:
            while True:
                msg = await websocket.recv()
                try:
                    msg = rsa_decrypt(msg).decode()
                    msg = json.loads(msg)
                    debug_print(f"Received data from sub-server: {msg}")

                    if msg["s"] == 1:
                        server_id = self.generate_random_id(5)
                        while server_id in self.websockets:
                            server_id = self.generate_random_id(5)

                        self.websockets[server_id] = websocket
                        self.broadcast_websockets.add(websocket)
                        self.servers_info[server_id] = msg["data"]
                        from connect_core.cli.cli_core import flush_completer
                        
                        flush_completer(list(self.websockets.keys()))
                        info_print(
                            translate("net_core.service.connect_websocket").format(
                                f"Server {server_id}"
                            )
                        )

                        await self.send_msg(
                            websocket,
                            {"s": 1, "id": server_id, "status": "Succeed", "data": {}},
                        )

                except Exception as e:
                    debug_print(f"Error with sub-server connection: {e}")
                    await websocket.close(reason="400")
                    self.close_connection(server_id, websocket)
                    break

        except (
            websockets.exceptions.ConnectionClosedOK,
            websockets.exceptions.ConnectionClosedError,
        ):
            self.close_connection(server_id, websocket)

    def close_connection(self, server_id=None, websocket=None) -> None:
        if server_id and websocket:
            if server_id in self.websockets:
                del self.websockets[server_id]
            if server_id in self.servers_info:
                del self.servers_info[server_id]
            if websocket in self.broadcast_websockets:
                self.broadcast_websockets.remove(websocket)
            from connect_core.cli.cli_core import flush_completer

            flush_completer(list(self.websockets.keys()))
            info_print(
                translate("net_core.service.disconnect_from_sub_websocket").format(
                    server_id
                )
            )
        else:
            warn_print(translate("net_core.service.disconnect_from_unknown_websocket"))

    async def send_msg(self, websocket, msg: dict) -> None:
        await websocket.send(rsa_encrypt(json.dumps(msg).encode()))

    def broadcast(self, msg: dict) -> None:
        websockets.broadcast(
            self.broadcast_websockets, rsa_encrypt(json.dumps(msg).encode())
        )
