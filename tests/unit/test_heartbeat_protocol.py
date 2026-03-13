"""Heartbeat 协议单元测试"""

from agentos.kernel.heartbeat.protocol import HEARTBEAT_TOKEN, StripResult, strip_heartbeat_token


class TestStripHeartbeatToken:
    def test_exact_token(self):
        result = strip_heartbeat_token("HEARTBEAT_OK")
        assert result.found is True
        assert result.remaining == ""
        assert result.should_skip is True

    def test_token_with_whitespace(self):
        result = strip_heartbeat_token("  HEARTBEAT_OK  ")
        assert result.found is True
        assert result.should_skip is True

    def test_token_prefix(self):
        result = strip_heartbeat_token("HEARTBEAT_OK 一切正常")
        assert result.found is True
        assert result.remaining == "一切正常"
        assert result.should_skip is True  # 剩余 ≤ 300

    def test_token_suffix(self):
        result = strip_heartbeat_token("一切正常 HEARTBEAT_OK")
        assert result.found is True
        assert result.remaining == "一切正常"
        assert result.should_skip is True

    def test_long_remaining_text(self):
        long_text = "HEARTBEAT_OK " + "x" * 500
        result = strip_heartbeat_token(long_text, max_ack_chars=300)
        assert result.found is True
        assert result.should_skip is False  # 剩余 > 300

    def test_no_token(self):
        result = strip_heartbeat_token("There is an issue with the server")
        assert result.found is False
        assert result.should_skip is False

    def test_empty_text(self):
        result = strip_heartbeat_token("")
        assert result.found is False
        assert result.remaining == ""
        assert result.should_skip is True

    def test_whitespace_only(self):
        result = strip_heartbeat_token("   ")
        assert result.found is False
        assert result.should_skip is True

    def test_token_in_middle(self):
        # 令牌在中间时不应被识别
        result = strip_heartbeat_token("before HEARTBEAT_OK after")
        assert result.found is False
        assert result.should_skip is False

    def test_custom_max_ack_chars(self):
        result = strip_heartbeat_token("HEARTBEAT_OK short", max_ack_chars=3)
        assert result.found is True
        assert result.remaining == "short"
        assert result.should_skip is False  # "short" > 3 chars
