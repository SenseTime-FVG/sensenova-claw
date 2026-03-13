"""cli 模块输入解析 + 显示引擎测试"""

from cli.display import char_display_width, read_user_input


def test_char_display_width_should_handle_ascii_and_cjk():
    assert char_display_width("a") == 1
    assert char_display_width("你") == 2
    assert char_display_width("") == 0


def test_char_display_width_combining():
    """组合字符宽度为 0"""
    assert char_display_width("\u0300") == 0
