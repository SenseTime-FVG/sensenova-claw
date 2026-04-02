from __future__ import annotations

import pytest

from sensenova_claw.kernel.events.envelope import EventEnvelope
from sensenova_claw.kernel.events.types import PROACTIVE_RESULT, USER_INPUT


@pytest.mark.asyncio
async def test_list_pending_recommendations_filters_consumed_items(test_repo):
    await test_repo.create_session(
        "sess_source_001",
        meta={"title": "市场分析", "agent_id": "office-main"},
    )

    await test_repo.log_event(EventEnvelope(
        type=PROACTIVE_RESULT,
        session_id="sess_source_001",
        source="proactive",
        ts=1000.0,
        payload={
            "job_id": "builtin-turn-end-recommendation",
            "job_name": "会话推荐",
            "session_id": "sess_source_001",
            "source_session_id": "sess_source_001",
            "recommendation_type": "turn_end",
            "items": [
                {
                    "id": "rec_1",
                    "title": "继续分析竞争对手",
                    "prompt": "请继续分析三个最强竞争对手",
                    "category": "follow-up",
                },
                {
                    "id": "rec_2",
                    "title": "整理市场规模",
                    "prompt": "请整理这个市场最近三年的规模变化",
                    "category": "research",
                },
            ],
        },
    ))

    await test_repo.log_event(EventEnvelope(
        type=USER_INPUT,
        session_id="sess_source_001",
        source="websocket",
        ts=1001.0,
        payload={
            "content": "请继续分析三个最强竞争对手",
            "meta": {
                "recommendation_id": "rec_1",
                "recommendation_source_session_id": "sess_source_001",
            },
        },
    ))

    recommendations = await test_repo.list_pending_recommendations(limit=10)

    assert len(recommendations) == 1
    assert recommendations[0]["source_session_id"] == "sess_source_001"
    assert [item["id"] for item in recommendations[0]["items"]] == ["rec_2"]


@pytest.mark.asyncio
async def test_list_pending_recommendations_only_returns_latest_group_per_session(test_repo):
    await test_repo.create_session(
        "sess_source_001",
        meta={"title": "市场分析", "agent_id": "office-main"},
    )

    await test_repo.log_event(EventEnvelope(
        type=PROACTIVE_RESULT,
        session_id="sess_source_001",
        source="proactive",
        ts=1000.0,
        payload={
            "job_id": "builtin-turn-end-recommendation",
            "job_name": "会话推荐",
            "session_id": "sess_source_001",
            "source_session_id": "sess_source_001",
            "recommendation_type": "turn_end",
            "items": [
                {
                    "id": "rec_old",
                    "title": "旧推荐",
                    "prompt": "旧 prompt",
                    "category": "follow-up",
                },
            ],
        },
    ))

    await test_repo.log_event(EventEnvelope(
        type=PROACTIVE_RESULT,
        session_id="sess_source_001",
        source="proactive",
        ts=1002.0,
        payload={
            "job_id": "builtin-turn-end-recommendation",
            "job_name": "会话推荐",
            "session_id": "sess_source_001",
            "source_session_id": "sess_source_001",
            "recommendation_type": "turn_end",
            "items": [
                {
                    "id": "rec_new",
                    "title": "新推荐",
                    "prompt": "新 prompt",
                    "category": "action",
                },
            ],
        },
    ))

    recommendations = await test_repo.list_pending_recommendations(limit=10)

    assert len(recommendations) == 1
    assert [item["id"] for item in recommendations[0]["items"]] == ["rec_new"]
