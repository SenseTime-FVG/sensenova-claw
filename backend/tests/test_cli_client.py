"""cli_client 输入解析测试"""

from cli_client import char_display_width, parse_user_input, should_trigger_menu_on_keypress


def test_parse_user_input_should_ignore_empty():
    action, value = parse_user_input("   ")
    assert action == "ignore"
    assert value == ""


def test_parse_user_input_should_show_menu_for_slash():
    action, value = parse_user_input(" / ")
    assert action == "show_menu"
    assert value == "/"


def test_parse_user_input_should_quit_only_for_quit():
    action, value = parse_user_input("  /quit  ")
    assert action == "quit"
    assert value == "/quit"


def test_parse_user_input_should_mark_unknown_command():
    action, value = parse_user_input("/help")
    assert action == "unknown_command"
    assert value == "/help"


def test_parse_user_input_should_send_normal_message():
    action, value = parse_user_input("你好")
    assert action == "send"
    assert value == "你好"


def test_should_trigger_menu_on_keypress_only_for_initial_slash():
    assert should_trigger_menu_on_keypress("", "/") is True
    assert should_trigger_menu_on_keypress("a", "/") is False
    assert should_trigger_menu_on_keypress("", "a") is False


def test_char_display_width_should_handle_ascii_and_cjk():
    assert char_display_width("a") == 1
    assert char_display_width("你") == 2
