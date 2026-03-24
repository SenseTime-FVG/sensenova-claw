"""
企业微信智能机器人 Python SDK

基于 WebSocket 长连接通道，提供消息收发、流式回复、模板卡片、事件回调、文件下载解密等核心能力。
"""

__version__ = "1.0.0"

from .client import WSClient
from .api import WeComApiClient
from .ws import WsConnectionManager
from .message_handler import MessageHandler
from .crypto_utils import decrypt_file
from .logger import DefaultLogger
from .utils import generate_req_id, generate_random_string
from .types import (
    MessageType,
    EventType,
    TemplateCardType,
    WsCmd,
    WSClientOptions,
    WsFrame,
    WsFrameHeaders,
    Logger,
)

__all__ = [
    "__version__",
    "WSClient",
    "WeComApiClient",
    "WsConnectionManager",
    "MessageHandler",
    "DefaultLogger",
    "decrypt_file",
    "generate_req_id",
    "generate_random_string",
    "MessageType",
    "EventType",
    "TemplateCardType",
    "WsCmd",
    "WSClientOptions",
    "WsFrame",
    "WsFrameHeaders",
    "Logger",
]
