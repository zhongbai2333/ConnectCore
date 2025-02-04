# API

## Account

`connect_core.api.account`

服务端密钥相关接口

 1. **analyze_password**

    解析初始化密钥

    **Args:**
    >key (str): 密钥

    **Returns:**
    >dict: 初始化字典

    ```python
    def analyze_password(key: str) -> dict:
    """
    解析初始化密钥

    Args:
        key (str): 密钥
    :return: 初始化字典
    """
    ```

 2. **get_password**

    获取初始化密钥

    **Returns:**
    >str: 密钥字符串

    ```python
    def get_password() -> str:
    """
    获取初始化密钥

    :return str: 密钥字符串
    """
    ```

 3. **def get_register_password**

    获取初始化临时密钥

    **Returns:**
    >str: 密钥字符串

    ```python
    def get_register_password() -> str:
    """
    获取初始化临时密钥

    :return: 密钥字符串
    """
    ```

## Data Packet

`connect_core.api.data_packet`

数据包相关代码

 1. `Class` **DataPacket**

    数据包类，包含数据包的类型和内容

    预设的类型和内容：

    ```python
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
    ```

    详情见：[websocket.md](./websocket.md)。

 2. **DataPacket.get_data_packet**

    获取数据包格式

    **Args:**
    >Type (tuple): 数据包类型和状态
    >ToInfo (tuple): 数据包目标信息
    >FromInfo (tuple): 数据包来源信息
    >Data (any): 数据

    **Returns:**
    >dict: 数据包字典

    ```python
    def get_data_packet(
        self, Type: tuple, ToInfo: tuple, FromInfo: tuple, Data: any
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
    ```

 3. **DataPacket.get_history_packet**

    获取历史数据包

    **Args:**
    >server_id (str): 服务器id
    >old_sid (int): 旧sid\

    **Returns:**
    >list: 历史数据包

    ```python
    def get_history_packet(self, server_id: str, old_sid: int) -> list:
        """
        获取历史数据包

        Args:
            server_id (str): 服务器id
            old_sid (int): 旧sid
        :return: 历史数据包
        """
    ```

 4. **DataPacket.add_recv_packet**

    添加接收到的数据包

    **Args:**
    >server_id (str): 服务器id
    >packet (dict): 数据包

    ```python
    def add_recv_packet(self, server_id: str, packet: dict) -> None:
        """
        添加接收到的数据包

        Args:
            server_id (str): 服务器id
            packet (dict): 数据包
        """
    ```

 5. **DataPacket.del_server_id**

    删除指定服务器id的数据包

    **Args:**
    >server_id (str): 服务器id

    ```python
    def del_server_id(self, server_id: str) -> None:
        """
        删除指定服务器id的数据包

        Args:
            server_id (str): 服务器id
        """
    ```

 6. **DataPacket.get_file_hash**

    获取指定文件的哈希值。默认使用 'sha256' 算法。

    **Args:**
    >file_path (str): 文件路径
    >algorithm (str): 哈希算法，默认使用 'sha256'

    **Returns:**
    >str: 文件的哈希值，如果文件不存在则返回 None

    ```python
    def get_file_hash(self, file_path, algorithm="sha256") -> str | None:
        """
        获取文件的哈希值。

        Args:
            file_path (str): 文件路径
            algorithm (str): 哈希算法，默认使用 'sha256'

        Returns:
            str: 文件的哈希值，如果文件不存在则返回 None
        """
    ```

 7. **DataPacket.verify_file_hash**

    验证指定文件的哈希值是否与预期的哈希值匹配。默认使用 'sha256' 算法。

    **Args:**
    >file_path (str): 文件路径
    >expected_hash (str): 预期的哈希值
    >algorithm (str): 哈希算法，默认使用 'sha256'

    **Returns:**
    >bool: 如果哈希值匹配则返回 True，否则返回 False

    ```python
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
    ```

 8. **DataPacket.generate_md5_checksum**

    验证文件的哈希值。

    **Args:**
    >data (bytes): 数据

    **Returns:**
    >str: MD5 哈希值

    ```python
    def generate_md5_checksum(self, data):
        """
        验证文件的哈希值。

        Args:
            data: 数据

        Returns:
            str: MD5 哈希值

        """
    ```

 9. **DataPacket.verify_md5_checksum**

    校验数据是否匹配给定的 MD5 校验和。

    **Args:**
    >data (bytes): 数据
    >checksum (str): MD5 校验和

    **Returns:**
    >bool: 如果哈希值匹配则返回 True，否则返回 False

    ```python
    def verify_md5_checksum(self, data, checksum) -> bool:
        """
        校验数据是否匹配给定的 MD5 校验和。

        :param data: 输入数据，类型为 bytes。
        :param checksum: 输入的 MD5 校验和，类型为 str。
        :return: 如果校验通过返回 True，否则返回 False。
        """
    ```

## Interface

`connect_core.api.interface`

控制器接口模块

 1. `Class` **ControlInterface**

    控制器接口类

 2. **ControlInterface.get_config**

    获取配置文件

    **Args:**
    >config_path (str): 配置文件路径，默认为插件或服务器默认 config 路径

    **Returns:**
    >dict: 配置文件字典

    ```python
    def get_config(self, config_path: str = None) -> dict:
        """
        获取配置文件

        Args:
            config_path (str): 配置文件目录, 默认为插件或服务器默认 config 路径

        Returns:
            dict: 配置文件字典
        """
    ```

 3. **ControlInterface.save_config**

    写入配置文件

    **Args:**
    >config_data (dict): 新的配置项字典
    >config_path (str): 配置文件目录, 默认为插件或服务器默认 config 路径

    ```python
    def save_config(self, config_data: dict, config_path: str = None) -> None:
        """
        写入配置文件

        Args:
            config_data (dict): 新的配置项字典
            config_path (str): 配置文件目录, 默认为插件或服务器默认 config 路径
        """
    ```

 4. **ControlInterface.translate**

    获取翻译项

    **Args:**
    >key (str): 翻译文件关键字
    >*args (tuple): 字段插入内容

    **Returns:**
    >str: 翻译文本

    ```python
    def translate(self, key: str, *args) -> str:
        """
        获取翻译项

        Args:
            key (str): 翻译文件关键字
            *args (tuple): 字段插入内容

        Returns:
            str: 翻译文本
        """
    ```

 5. **ControlInterface.tr**

    获取翻译项 | `translate函数的别称`

    **Args:**
    >key (str): 翻译文件关键字
    >*args (tuple): 字段插入内容

    **Returns:**
    >str: 翻译文本

    ```python
    def tr(self, key: str, *args):
        """
        获取翻译项 | `translate函数的别称`

        Args:
            key (str): 翻译文件关键字
            *args (tuple): 字段插入内容

        Returns:
            str: 翻译文本
        """
    ```

 6. **ControlInterface.info**

    输出INFO级别的日志信息

    **Args:**
    >msg (any): 日志消息内容。

    ```python
    def info(self, msg: any):
        """
        输出INFO级别的日志信息。

        Args:
            msg (any): 日志消息内容。
        """
    ```

 7. **ControlInterface.warn**

    输出WARN级别的日志信息

    **Args:**
    >msg (any): 日志消息内容。

    ```python
    def warn(self, msg: any):
        """
        输出WARN级别的日志信息。

        Args:
            msg (any): 日志消息内容。
        """
    ```

 8. **ControlInterface.error**

    输出ERROR级别的日志信息

    **Args:**
    >msg (any): 日志消息内容。

    ```python
    def error(self, msg: any):
        """
        输出ERROR级别的日志信息。

        Args:
            msg (any): 日志消息内容。
        """
    ```

 9. **ControlInterface.debug**

    输出DEBUG级别的日志信息

    **Args:**
    >msg (any): 日志消息内容。

    ```python
    def debug(self, msg: any):
        """
        输出DEBUG级别的日志信息。

        Args:
            msg (any): 日志消息内容。
        """
    ```

10. **ControlInterface.is_server**

    判断是否为服务器

    **Returns:**
    >bool: 是/否

    ```python
    def is_server(self) -> bool:
        """
        判断是否为服务器

        Returns:
            bool: 是/否
        """
    ```

11. **ControlInterface.get_server_list**

    获取服务器列表

    **Returns:**
    >list: 服务器列表

    ```python
    def get_server_list(self) -> list:
        """
        获取服务器列表
        
        Returns:
            list: 服务器列表
        """
    ```

12. **ControlInterface.get_server_id**

    获取客户端的服务器ID。

    **Returns:**
    >str: 服务器ID

    ```python
    def get_server_id(self) -> str:
        """
        客户端反馈服务器ID

        Returns:
            str: 服务器ID
        """
    ```

13. **ControlInterface.add_command**

    添加命令到命令行界面中。

    **Args:**
    >command (str): 命令名称。
    >func (callable): 命令对应的函数。

    ```python
    def add_command(self, command: str, func: callable):
        """
        添加命令到命令行界面中。

        Args:
            command (str): 命令名称。
            func (callable): 命令对应的函数。
        """
    ```

14. **ControlInterface.remove_command**

    移除命令从命令行界面中。

    **Args:**
    >command (str): 命令名称。

    ```python
    def remove_command(self, command: str):
        """
        移除命令从命令行界面中。

        Args:
            command (str): 命令名称。
        """
    ```

15. **ControlInterface.set_prompt**

    设置命令行提示符。

    **Args:**
    >prompt (str): 命令行提示符内容。

    ```python
    def set_prompt(self, prompt: str):
        """
        设置命令行提示符。

        Args:
            prompt (str): 命令行提示符内容。
        """
    ```

16. **ControlInterface.set_completer_words**

    设置命令行补全词典。

    **Args:**
    >words (dict): 命令行补全词典内容。

    ```python
    def set_completer_words(self, words: dict):
        """
        设置命令行补全词典。

        Args:
            words (dict): 命令行补全词典内容。
        """
    ```

17. **ControlInterface.flush_cli**

    清空命令行界面。

    ```python
    def flush_cli(self):
        """
        清空命令行界面。
        """
    ```

18. `Class` **PluginControlInterface**

    插件控制接口，继承自 `CoreControlInterface`。

    **Args:**
    >sid (str): 插件ID
    >sinfo (dict): 插件Info
    >self_path (str): 自身路径
    >config_path (str): 配置文件路径

    ```python
    class PluginControlInterface(CoreControlInterface):
        def __init__(self, sid: str, sinfo: dict, self_path: str, config_path: str):
            """
            插件控制接口

            Args:
                sid (str): 插件ID
                sinfo (dict): 插件Info
                self_path (str): 自身路径
                config_path (str): 配置文件路径
            """
            # 导入
            super().__init__()
    ```

19. **PluginControlInterface.send_data**

    向指定的服务器发送消息。

    **Args:**
    >server_id (str): 目标服务器的唯一标识符。
    >plugin_id (str): 目标服务器插件的唯一标识符
    >data (str): 要发送的数据。

    ```python
    def send_data(self, server_id: str, plugin_id: str, data: dict):
        """
        向指定的服务器发送消息。

        Args:
            server_id (str): 目标服务器的唯一标识符。
            plugin_id (str): 目标服务器插件的唯一标识符
            data (str): 要发送的数据。
        """
    ```

20. **PluginControlInterface.send_file**

    向指定的服务器发送文件。

    **Args:**
    >server_id (str): 目标服务器的唯一标识符。
    >plugin_id (str): 目标服务器插件的唯一标识符
    >file_path (str): 要发送的文件目录。
    >save_path (str): 要保存的位置。

    ```python
    def send_file(
        self, server_id: str, plugin_id: str, file_path: str, save_path: str
    ):
        """
        向指定的服务器发送文件。

        Args:
            server_id (str): 目标服务器的唯一标识符。
            plugin_id (str): 目标服务器插件的唯一标识符
            file_path (str): 要发送的文件目录。
            save_path (str): 要保存的位置。
        """
    ```

21. **PluginControlInterface.get_history_packet**

    获取历史数据包。

    **Args:**
    >str: 服务器ID

    **Returns:**
    >dict: 数据包

    ```python
    def get_history_packet(self, server_id: str = None) -> list | None:
        """
        获取历史数据包，客户端无需参数

        Args:
            server_id (str): 服务器ID

        Returns:
            dict: 数据包
        """
    ```

## MCDR

`connect_core.api.mcdr`

MCDR插件的API。

1. **get_plugin_control_interface**

    获取插件控制接口。

    **Args:**
    >sid (str): 服务器ID
    >enter_point (str): 入口点
    >mcdr (PluginServerInterface): MCDR接口

    **Returns:**
    >PluginControlInterface: 插件控制接口

    ```python
    def get_plugin_control_interface(
        sid: str, enter_point: str, mcdr: PluginServerInterface
    ) -> PluginControlInterface:
        """
        获取插件控制接口

        Args:
            sid (str): 插件ID
            enter_point (str): 入口点
            mcdr (PluginServerInterface): MCDR接口
        Returns:
            PluginControlInterface: 插件控制接口
        """
    ```

## Plugin

`connect_core.api.plugin`

控制插件的API。

 1. **unload_plugin**

    卸载插件。

    **Args:**
    >sid (str): 服务器ID

    ```python
    def unload_plugin(sid: str):
        """
        卸载插件

        Args:
            sid (str): 插件ID
        """
    ```

 2. **reload_plugin**

    重载插件。

    **Args:**
    >sid (str): 服务器ID

    ```python
    def reload_plugin(sid: str):
        """
        重载插件

        Args:
            sid (str): 插件ID
        """
    ```

 3. **get_plugins**

    获取插件列表。

    **Returns:**
    >dict: 插件列表

    ```python
    def get_plugins() -> dict:
        """
        获取插件列表

        :return: 插件列表
        """
    ```

## RSA

`connect_core.api.rsa`

RSA加密模块。

 1. **rsa_encrypt**

    RSA加密数据。

    **Args:**
    >data (bytes): 要加密的数据。

    **Returns:**
    >bytes: 加密后的数据。

    **Exceptions:**
    >InvalidToken: 如果未初始化密码或初始化错误时抛出异常。

    ```python
    def aes_encrypt(data: bytes) -> bytes:
        """
        加密数据

        Args:
            data (bytes): 需要加密的字节数据。

        Returns:
            bytes: 加密后的字节数据。

        Exceptions:
            InvalidToken: 如果未初始化密码或初始化错误时抛出异常。
        """
    ```

 2. **aes_decrypt**

    RSA解密数据。

    **Args:**
    >data (bytes): 要解密的数据。

    **Returns:**
    >bytes: 解密后的数据。

    **Exceptions:**
    >InvalidToken: 如果未初始化密码、数据为空或解密失败时抛出异常。

    ```python
    def aes_decrypt(data: bytes) -> bytes:
        """
        解密数据

        Args:
            data (bytes): 需要解密的字节数据。

        Returns:
            bytes: 解密后的字节数据。

        Exceptions:
            InvalidToken: 如果未初始化密码、数据为空或解密失败时抛出异常。
        """
    ```

## Tools

`connect_core.api.tools`

实用工具

 1. **new_thread**

    启动一个新的线程运行装饰的函数，同时支持类方法和普通函数。

    ```python
    def new_thread(arg: Optional[Union[str, Callable]] = None):
        """
        启动一个新的线程运行装饰的函数，同时支持类方法和普通函数。
        """
    ```

 2. **auto_trigger**

    定时启动一个新的线程运行装饰的函数，同时支持类方法和普通函数。

    ```python
    def auto_trigger(interval: float, thread_name: Optional[str] = None):
        """
        定时启动一个新的线程运行装饰的函数，同时支持类方法和普通函数。
        """
    ```

 3. **restart_program**

    重启程序，使用当前的Python解释器重新执行当前脚本。

    ```python
    def restart_program() -> None:
        """
        重启程序，使用当前的Python解释器重新执行当前脚本。
        """
    ```

 4. **check_file_exists**

    检查目录中的特定文件是否存在。

    **Args**:
    >file_path (str): 文件路径

    **Returns**:
    >bool: 如果文件存在则返回 True，否则返回 False

    ```python
    def check_file_exists(file_path) -> bool:
        """
        检查目录中的特定文件是否存在。

        Args:
            file_path (str): 文件路径

        Returns:
            bool: 如果文件存在则返回 True，否则返回 False
        """
    ```

 5. **append_to_path**

    如果给定的路径是一个目录，则将文件名附加到该路径上。

    **Args**:
    >path (str): 要检查和修改的路径。
    >filename (str): 如果路径是目录，则附加的文件名。

    **Returns**:
    >str: 修改后的路径。

    ```python
    def append_to_path(path, filename) -> str:
        """
        如果给定的路径是一个目录，则将文件名附加到该路径上。
        :param path: 要检查和修改的路径。
        :param filename: 如果路径是目录，则附加的文件名。
        :return: 修改后的路径。
        """
    ```

 6. **encode_base64**

    对输入的数据进行Base64编码。

    **Args**:
    >data (str): 需要编码的字节数据

    **Returns**:
    >str: 编码后的字符串。

    ```python
    def encode_base64(data: str) -> str:
        """
        对输入的数据进行Base64编码

        Args:
            data (str): 需要编码的字节数据
        :return: 编码后的字符串
        """
    ```

 7. **decode_base64**

    对Base64编码的数据进行解码。

    **Args**:
    >encoded_data (str): Base64编码的字符串

    **Returns**:
    >str: 解码后的字节数据。

    ```python
    def decode_base64(encoded_data: str) -> str:
        """
        对Base64编码的数据进行解码

        Args:
            encoded_data(str): Base64编码的字符串
        :return: 解码后的字节数据
        """
    ```

 8. **get_all_internal_ips**

    获取所有网卡的内网IP地址。

    **Returns**:
    >list: 一个列表, 包含所有内网IP地址

    ```python
    def get_all_internal_ips() -> list:
        """
        获取所有网卡的内网IP地址
        :return: 一个列表, 包含所有内网IP地址
        """
    ```

 9. **get_external_ip**

    获取公网地址。

    **Returns**:
    >str: 一个公网IP

    ```python
    def get_external_ip() -> str:
        """
        获取公网地址
        :return: 一个公网IP
        """
    ```
