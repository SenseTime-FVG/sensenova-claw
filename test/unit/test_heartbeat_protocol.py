"""R03: HeartbeatProtocol"""
from agentos.kernel.heartbeat.protocol import strip_heartbeat_token, StripResult, HEARTBEAT_TOKEN


class TestHeartbeatProtocol:
    def test_empty_text(self):
        r = strip_heartbeat_token("")
        assert r.found is False
        assert r.should_skip is True

    def test_exact_token(self):
        r = strip_heartbeat_token(HEARTBEAT_TOKEN)
        assert r.found is True
        assert r.should_skip is True
        assert r.remaining.strip() == ""

    def test_token_at_start(self):
        r = strip_heartbeat_token(f"{HEARTBEAT_TOKEN} some text")
        assert r.found is True
        assert "some text" in r.remaining

    def test_token_at_end(self):
        r = strip_heartbeat_token(f"some text {HEARTBEAT_TOKEN}")
        assert r.found is True
        assert "some text" in r.remaining

    def test_no_token(self):
        r = strip_heartbeat_token("just regular text")
        assert r.found is False
        assert r.should_skip is False

    def test_long_remaining_not_skipped(self):
        """remaining 超过 max_ack_chars 不应 skip"""
        long_text = "x" * 500
        r = strip_heartbeat_token(f"{HEARTBEAT_TOKEN} {long_text}", max_ack_chars=300)
        assert r.found is True
        assert r.should_skip is False

    def test_short_remaining_skipped(self):
        """remaining 在 max_ack_chars 内应 skip"""
        short_text = "ok"
        r = strip_heartbeat_token(f"{HEARTBEAT_TOKEN} {short_text}", max_ack_chars=300)
        assert r.found is True
        assert r.should_skip is True
