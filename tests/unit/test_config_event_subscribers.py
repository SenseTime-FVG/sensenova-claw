"""config.updated 事件常量和订阅者测试"""
import pytest
from agentos.kernel.events.types import CONFIG_UPDATED, SYSTEM_SESSION_ID


def test_config_updated_constant():
    assert CONFIG_UPDATED == "config.updated"


def test_system_session_id_constant():
    assert SYSTEM_SESSION_ID == "__system__"
