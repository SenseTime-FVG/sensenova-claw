from agentos.adapters.channels.websocket_channel import WebSocketChannel
from agentos.kernel.events.envelope import EventEnvelope
from agentos.kernel.events.types import LLM_CALL_RESULT


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
