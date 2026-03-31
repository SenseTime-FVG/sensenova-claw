"""T04: ToolRegistry 注册/发现"""
from unittest.mock import patch

from sensenova_claw.capabilities.tools.registry import ToolRegistry
from sensenova_claw.capabilities.tools.base import Tool, ToolRiskLevel


class MockTool(Tool):
    name = "mock_tool"
    description = "A mock tool"
    parameters = {"type": "object", "properties": {}, "required": []}
    risk_level = ToolRiskLevel.LOW

    async def execute(self, **kwargs):
        return {"ok": True}


class TestToolRegistry:
    def test_builtin_registered(self):
        r = ToolRegistry()
        assert r.get("apply_patch") is not None
        assert r.get("bash_command") is not None
        assert r.get("get_secret") is not None
        assert r.get("serper_search") is not None
        assert r.get("fetch_url") is not None
        assert r.get("read_file") is not None
        assert r.get("write_secret") is not None
        assert r.get("write_file") is not None
        assert r.get("ask_user") is not None

    def test_email_tools_not_registered_by_default(self):
        """email 工具默认不注册（tools.email.enabled=False）"""
        r = ToolRegistry()
        names = {t["name"] for t in r.as_llm_tools()}
        email_tools = {"send_email", "list_emails", "read_email", "download_attachment", "mark_email", "search_emails"}
        assert email_tools.isdisjoint(names)

    def test_email_tools_registered_when_enabled(self):
        """tools.email.enabled=True 时 email 工具应注册"""
        from sensenova_claw.platform.config.config import config
        original = config.data["tools"]["email"]["enabled"]
        try:
            config.data["tools"]["email"]["enabled"] = True
            r = ToolRegistry()
            names = {t["name"] for t in r.as_llm_tools()}
            assert {
                "send_email",
                "list_emails",
                "read_email",
                "download_attachment",
                "mark_email",
                "search_emails",
            }.issubset(names)
        finally:
            config.data["tools"]["email"]["enabled"] = original

    def test_register_custom(self):
        r = ToolRegistry()
        r.register(MockTool())
        assert r.get("mock_tool") is not None
        assert r.get("mock_tool").description == "A mock tool"

    def test_get_nonexist(self):
        r = ToolRegistry()
        assert r.get("nope") is None

    def test_as_llm_tools(self):
        r = ToolRegistry()
        tools = r.as_llm_tools()
        assert len(tools) >= 5
        names = [t["name"] for t in tools]
        assert "bash_command" in names
        assert "get_secret" in names
        assert "write_secret" in names
        for t in tools:
            assert "name" in t
            assert "description" in t
            assert "parameters" in t

    def test_apply_patch_schema_explicitly_restricts_format(self):
        r = ToolRegistry()
        tool = r.get("apply_patch")
        assert tool is not None
        assert tool.description == (
            "Apply a patch to one or more files using the apply_patch format. "
            "The input should include *** Begin Patch and *** End Patch markers."
        )
        input_desc = tool.parameters["properties"]["input"]["description"]
        assert input_desc == (
            "Patch content using the *** Begin Patch/End Patch format. "
            "Use *** Add File:, *** Delete File:, or *** Update File: as hunk headers. "
            "Within an update hunk, @@ starts a chunk; use plain @@ for no explicit context, "
            "or @@ <context> to anchor the chunk on an existing line. "
            "Use *** Move to: inside *** Update File: to rename a file, and *** End of File "
            "for EOF-only inserts. "
            "Example:\n"
            "*** Begin Patch\n"
            "*** Add File: path/to/file.txt\n"
            "+line 1\n"
            "+line 2\n"
            "*** Update File: src/app.py\n"
            "@@\n"
            "-old line\n"
            "+new line\n"
            "*** Delete File: obsolete.txt\n"
            "*** End Patch"
        )

    def test_config_disabled_tool_not_in_llm_tools(self):
        """tools.<name>.enabled=False → as_llm_tools() 不含该工具"""
        from sensenova_claw.platform.config.config import config
        # 确保 bash_command 默认存在
        r = ToolRegistry()
        names_before = {t["name"] for t in r.as_llm_tools()}
        assert "bash_command" in names_before

        # 设置 bash_command.enabled=False
        config.set("tools.bash_command.enabled", False)
        try:
            r2 = ToolRegistry()
            names_after = {t["name"] for t in r2.as_llm_tools()}
            assert "bash_command" not in names_after
        finally:
            # 清理：恢复默认值
            tools_section = config.data.get("tools", {})
            if "bash_command" in tools_section and "enabled" in tools_section["bash_command"]:
                del tools_section["bash_command"]["enabled"]

    def test_config_disabled_file_operations_hides_related(self):
        """tools.file_operations.enabled=False → read_file/write_file/edit/apply_patch 不暴露"""
        from sensenova_claw.platform.config.config import config
        r = ToolRegistry()
        names_before = {t["name"] for t in r.as_llm_tools()}
        file_ops = {"read_file", "write_file", "edit", "apply_patch"}
        assert file_ops.issubset(names_before)

        config.set("tools.file_operations.enabled", False)
        try:
            r2 = ToolRegistry()
            names_after = {t["name"] for t in r2.as_llm_tools()}
            assert file_ops.isdisjoint(names_after), (
                f"file_operations 关闭后仍暴露: {file_ops & names_after}"
            )
        finally:
            tools_section = config.data.get("tools", {})
            if "file_operations" in tools_section:
                del tools_section["file_operations"]

    def test_unconfigured_tool_enabled_by_default(self):
        """无 enabled 配置的工具默认暴露"""
        from sensenova_claw.capabilities.tools.registry import _is_tool_config_enabled
        # fetch_url 没有在 DEFAULT_CONFIG 中显式设置 enabled
        assert _is_tool_config_enabled("fetch_url") is True
        # 一个完全不存在的工具名也应默认启用
        assert _is_tool_config_enabled("nonexistent_tool_xyz") is True
