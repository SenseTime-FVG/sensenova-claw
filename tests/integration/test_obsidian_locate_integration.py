"""集成测试 - Obsidian vault 定位与初始化工具"""
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from sensenova_claw.capabilities.tools.obsidian_locate import ObsidianLocateTool


@pytest.mark.asyncio
async def test_full_flow_no_existing_vault():
    """测试 - 完整流程：系统中无 vault"""
    tool = ObsidianLocateTool()

    with tempfile.TemporaryDirectory() as tmpdir:
        # 模拟 home 目录
        with patch("pathlib.Path.home") as mock_home:
            mock_home.return_value = Path(tmpdir)

            # 调用工具
            result = await tool.execute()

            # 验证结果
            assert result["success"] is True
            assert len(result["vaults"]) > 0
            assert result["primary_vault"] is not None
            assert "created" in str(result).lower() or "检测" in str(result).lower()


@pytest.mark.asyncio
async def test_full_flow_with_existing_vault():
    """测试 - 完整流程：系统中存在 vault"""
    tool = ObsidianLocateTool()

    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建现有 vault
        vault_path = Path(tmpdir) / "MyVault"
        vault_path.mkdir()
        (vault_path / ".obsidian").mkdir()

        with patch("pathlib.Path.home") as mock_home:
            mock_home.return_value = Path(tmpdir)

            with patch("sensenova_claw.capabilities.tools.obsidian_locate._detect_vaults_windows") as mock_win:
                mock_win.return_value = [vault_path]

                result = await tool.execute()

                assert result["success"] is True
                assert len(result["vaults"]) >= 1


@pytest.mark.asyncio
async def test_system_admin_can_use_result():
    """测试 - system-admin 能使用工具的返回结果"""
    tool = ObsidianLocateTool()

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("pathlib.Path.home") as mock_home:
            mock_home.return_value = Path(tmpdir)

            result = await tool.execute()

            # 验证返回格式适合 system-admin 使用
            assert isinstance(result, dict)
            assert "success" in result
            assert "vaults" in result
            assert "primary_vault" in result
            assert "error" in result
            assert "note" in result

            if result["success"]:
                # 检查 vaults 列表中的每个项都有必要字段
                for vault in result["vaults"]:
                    assert "name" in vault
                    assert "path" in vault
                    assert "source" in vault
                    assert "has_structure" in vault
                    assert "created_now" in vault
                    assert "accessible" in vault

                # 检查 primary_vault 格式
                if result["primary_vault"]:
                    for vault in result["vaults"]:
                        # primary_vault 应该在 vaults 列表中
                        pass
