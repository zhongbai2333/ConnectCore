import asyncio, json, websockets


class BabyServer:
    def __init__(self):
        self.fin_start = False
        self.main_task = None
        self.main_server_name = None
        self.server_id = None
        self.finish_quit = False
        self.receive_task = None
        self.websocket = None

    def start_server(self):
        asyncio.run(self.init_main())

    def stop_server(self):
        if self.receive_task:
            self.receive_task.cancel()
        else:
            self.finish_quit = True
            pass

    async def init_main(self):
        self.main_task = asyncio.create_task(self.main())
        try:
            await self.main_task
        except asyncio.CancelledError:
            self.__mcdr_server.logger.info("Baby Websockets 关闭！")

    async def main(self):
        while True:
            try:
                async with websockets.connect(
                    f"ws://{self.config.far_server_host}:{self.config.far_server_port}"
                ) as self.websocket:
                    self.fin_start = True
                    self.__mcdr_server.logger.info("Group Websockets 连接成功！")
                    await self.receive()
                break
            except ConnectionRefusedError:
                self.fin_start = False
                await asyncio.sleep(1)

    async def receive(self):
        await self.websocket.send(
            json.dumps(
                {
                    "s": 1,
                    "password": self.config.password,
                    "status": "Connect",
                    "data": {
                        "server_name": self.config.server_name,
                        "command_group": self.botdata.command_group,
                        "talk_groups": self.botdata.talk_groups,
                    },
                }
            )
        )
        while True:
            self.receive_task = asyncio.create_task(self.get_recv())
            try:
                recv_data = await self.receive_task
                if recv_data:
                    if self.debug:
                        self.__mcdr_server.logger.info(
                            f"已收到 Baby 数据包：{recv_data}"
                        )
                    self.parse_msg_service(json.loads(recv_data))
                else:
                    break
            except asyncio.CancelledError:
                self.__mcdr_server.logger.info("Receive 服务已退出！")
                self.finish_quit = True
                return None

    async def get_recv(self):
        while True:
            try:
                return await asyncio.wait_for(self.websocket.recv(), timeout=4)
            except asyncio.TimeoutError:
                pass
            except (websockets.ConnectionClosedError, websockets.ConnectionClosedOK):
                self.__mcdr_server.say(f"§7{self.main_server_name} 已关闭！")
                self.__mcdr_server.logger.error("已与主服务器断开连接！")
                init()
                return None
