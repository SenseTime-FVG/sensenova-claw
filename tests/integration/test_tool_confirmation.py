"""T05: 工具确认流程 (HIGH risk)"""
import pytest
from agentos.capabilities.tools.base import ToolRiskLevel
from agentos.capabilities.tools.builtin import BashCommandTool, ReadFileTool, WriteFileTool


class TestToolConfirmation:
    def test_bash_is_high_risk(self):
        assert BashCommandTool.risk_level == ToolRiskLevel.HIGH

    def test_read_is_low_risk(self):
        assert ReadFileTool.risk_level == ToolRiskLevel.LOW

    def test_write_is_medium_risk(self):
        assert WriteFileTool.risk_level == ToolRiskLevel.MEDIUM

    def test_risk_level_values(self):
        assert ToolRiskLevel.LOW.value == "low"
        assert ToolRiskLevel.MEDIUM.value == "medium"
        assert ToolRiskLevel.HIGH.value == "high"
