"""builtin.py 工具声明位置测试"""

from sensenova_claw.capabilities.tools import builtin


def test_builtin_declares_apply_patch_and_edit_file_tools():
    assert hasattr(builtin, "ApplyPatchTool")
    assert hasattr(builtin, "EditTool")
    assert builtin.ApplyPatchTool.__module__ == "sensenova_claw.capabilities.tools.builtin"
    assert builtin.EditTool.__module__ == "sensenova_claw.capabilities.tools.builtin"
    assert builtin.ApplyPatchTool.execute.__module__ == "sensenova_claw.capabilities.tools.builtin"
    assert builtin.EditTool.execute.__module__ == "sensenova_claw.capabilities.tools.builtin"
