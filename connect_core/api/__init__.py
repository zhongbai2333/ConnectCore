"""
ConnectCore Public API

统一的公共接口模块，为插件开发者提供稳定的 API 入口。
所有公开符号均从此模块重新导出，插件应通过此模块访问功能。

Usage:
    from connect_core.api import PluginControlInterface, DataModel, BaseConfig
"""

# ===== Interface =====
from connect_core.interface.control_interface import (
    CoreControlInterface,
    PluginControlInterface,
)

# ===== Plugin =====
from connect_core.plugin.init_plugin import (
    unload_plugin,
    reload_plugin,
    get_plugins,
)

# ===== Encryption =====
from connect_core.aes_encrypt import (
    aes_encrypt,
    aes_decrypt,
)

# ===== Tools =====
from connect_core.tools.tools import (
    restart_program,
    check_file_exists,
    append_to_path,
    encode_base64,
    decode_base64,
    get_all_internal_ips,
    get_external_ip,
    new_thread,
    auto_trigger,
)

# ===== Data Packet =====
from connect_core.websockets.data_packet import (
    DataModel,
    PacketType,
    PacketStatus,
    StatusRegistry,
    status_registry,
    PROTOCOL_VERSION,
)

# 向后兼容: 原名 DataPacket -> 现名 DataModel
DataPacket = DataModel

# ===== Account =====
from connect_core.account.login_system import analyze_password
from connect_core.account.register_system import (
    get_password,
    get_register_password,
)

# ===== MCDR =====
from connect_core.mcdr.mcdr_entry import get_plugin_control_interface

# ===== Config =====
from connect_core.tools.base_config import (
    BaseConfig,
    ConfigError,
    ConfigTypeError,
    ConfigValidationError,
    Field,
)

__all__ = [
    # Interface
    "CoreControlInterface",
    "PluginControlInterface",
    # Plugin
    "unload_plugin",
    "reload_plugin",
    "get_plugins",
    # Encryption
    "aes_encrypt",
    "aes_decrypt",
    # Tools
    "restart_program",
    "check_file_exists",
    "append_to_path",
    "encode_base64",
    "decode_base64",
    "get_all_internal_ips",
    "get_external_ip",
    "new_thread",
    "auto_trigger",
    # Data Packet
    "DataModel",
    "DataPacket",  # 向后兼容别名
    "PacketType",
    "PacketStatus",
    "StatusRegistry",
    "status_registry",
    "PROTOCOL_VERSION",
    # Account
    "analyze_password",
    "get_password",
    "get_register_password",
    # MCDR
    "get_plugin_control_interface",
    # Config
    "BaseConfig",
    "ConfigError",
    "ConfigTypeError",
    "ConfigValidationError",
    "Field",
]
