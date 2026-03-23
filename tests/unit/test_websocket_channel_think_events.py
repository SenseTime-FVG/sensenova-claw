from agentos.adapters.channels.websocket_channel import WebSocketChannel
from agentos.kernel.events.envelope import EventEnvelope
from agentos.kernel.events.types import ERROR_RAISED, LLM_CALL_RESULT


def test_map_llm_call_result_exposes_thinking_payload():
    channel = WebSocketChannel("websocket")
    event = EventEnvelope(
        type=LLM_CALL_RESULT,
        session_id="sess_think",
        turn_id="turn_think",
        payload={
            "response": {
                "content": "<think>先思考</think>\n最终回答",
                "tool_calls": [],
                "reasoning_details": [
                    {"type": "thinking", "thinking": "第一步"},
                    {"type": "text", "text": "忽略"},
                    {"type": "thinking", "thinking": "第二步"},
                ],
            }
        },
    )

    mapped = channel._map(event)

    assert mapped == {
        "type": "llm_result",
        "session_id": "sess_think",
        "payload": {
            "turn_id": "turn_think",
            "content": "<think>先思考</think>\n最终回答",
            "tool_calls": [],
            "reasoning_details": [
                {"type": "thinking", "thinking": "第一步"},
                {"type": "text", "text": "忽略"},
                {"type": "thinking", "thinking": "第二步"},
            ],
        },
        "timestamp": event.ts,
    }


def test_map_error_exposes_error_code_and_user_message():
    channel = WebSocketChannel("websocket")
    event = EventEnvelope(
        type=ERROR_RAISED,
        session_id="sess_error",
        payload={
            "error_type": "BadRequestError",
            "error_message": "raw provider error",
            "error_code": "max_tokens_out_of_range",
            "user_message": "当前模型允许的最大输出长度超限，请调小 max_tokens 后重试。",
            "context": {
                "provider": "qwen",
                "model": "qwen3.5-plus",
                "limit": 65536,
            },
        },
    )

    mapped = channel._map(event)

    assert mapped == {
        "type": "error",
        "session_id": "sess_error",
        "payload": {
            "error_type": "BadRequestError",
            "error_code": "max_tokens_out_of_range",
            "message": "当前模型允许的最大输出长度超限，请调小 max_tokens 后重试。",
            "user_message": "当前模型允许的最大输出长度超限，请调小 max_tokens 后重试。",
            "raw_message": "raw provider error",
            "details": {
                "provider": "qwen",
                "model": "qwen3.5-plus",
                "limit": 65536,
            },
        },
        "timestamp": event.ts,
    }
