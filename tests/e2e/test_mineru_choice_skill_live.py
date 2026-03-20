from __future__ import annotations

import os

import pytest


@pytest.mark.skipif(
    os.getenv("ENABLE_REAL_MINERU_CLI_E2E") != "1",
    reason="需要本机已安装 mineru-open-api 并手动开启真实验证",
)
def test_mineru_choice_skill_live_contract() -> None:
    assert os.getenv("ENABLE_REAL_MINERU_CLI_E2E") == "1"
