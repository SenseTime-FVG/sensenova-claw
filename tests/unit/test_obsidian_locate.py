"""单元测试 - Obsidian vault 定位与初始化工具"""
import asyncio
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from sensenova_claw.capabilities.tools.obsidian_locate import (
    ObsidianLocateTool,
    VaultInfo,
    _get_configured_vaults,
    _validate_vault,
    _parse_vault_name,
    _check_knowledge_structure,
    _ensure_knowledge_structure,
    _create_default_vault,
    _dedup_and_rank_vaults,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def temp_vault_dir():
    """创建临时 vault 目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_path = Path(tmpdir) / "test-vault"
        vault_path.mkdir(parents=True)

        # 创建 .obsidian 目录
        obsidian_dir = vault_path / ".obsidian"
        obsidian_dir.mkdir()

        yield vault_path


@pytest.fixture
def tool():
    """创建工具实例"""
    return ObsidianLocateTool()


# ============================================================================
# 测试 - 配置检查
# ============================================================================

def test_get_configured_vaults_empty():
    """测试 - 无配置时返回空列表"""
    with patch("sensenova_claw.capabilities.tools.obsidian_locate.config") as mock_config:
        mock_config.get.return_value = []

        vaults = _get_configured_vaults()

        assert vaults == []


def test_validate_vault_valid(temp_vault_dir):
    """测试 - 有效 vault 验证"""
    result = _validate_vault(temp_vault_dir)
    assert result is True


def test_validate_vault_invalid(temp_vault_dir):
    """测试 - 无效 vault 验证（缺少 .obsidian）"""
    invalid_dir = temp_vault_dir.parent / "invalid"
    invalid_dir.mkdir()

    result = _validate_vault(invalid_dir)
    assert result is False


def test_parse_vault_name(temp_vault_dir):
    """测试 - vault 名称解析"""
    name = _parse_vault_name(temp_vault_dir)
    assert name == "test-vault"


# ============================================================================
# 测试 - 知识库结构
# ============================================================================

def test_check_knowledge_structure_incomplete(temp_vault_dir):
    """测试 - 不完整的知识库结构"""
    result = _check_knowledge_structure(temp_vault_dir)
    assert result is False


def test_ensure_knowledge_structure(temp_vault_dir):
    """测试 - 补全知识库结构"""
    result = _ensure_knowledge_structure(temp_vault_dir)

    assert result["created"] is True
    assert result["error"] is None
    assert result["has_structure"] is True

    # 验证结构已创建
    assert _check_knowledge_structure(temp_vault_dir) is True
    assert (temp_vault_dir / "Knowledge").exists()
    assert (temp_vault_dir / "Knowledge" / "user-profile.md").exists()
    assert (temp_vault_dir / "Knowledge" / "qa-history").exists()
    assert (temp_vault_dir / "Knowledge" / "facts").exists()


def test_ensure_knowledge_structure_idempotent(temp_vault_dir):
    """测试 - 补全结构是幂等的（重复调用不出错）"""
    _ensure_knowledge_structure(temp_vault_dir)
    result = _ensure_knowledge_structure(temp_vault_dir)

    assert result["created"] is True
    assert result["error"] is None


# ============================================================================
# 测试 - Vault 排序
# ============================================================================

def test_dedup_and_rank_vaults_configured_priority(temp_vault_dir):
    """测试 - 配置的 vault 优先级最高"""
    vault1_path = temp_vault_dir / "vault1"
    vault1_path.mkdir()
    (vault1_path / ".obsidian").mkdir()

    vault2_path = temp_vault_dir / "vault2"
    vault2_path.mkdir()
    (vault2_path / ".obsidian").mkdir()

    vaults_with_source = [
        (vault1_path, "standard"),
        (vault2_path, "configured"),
    ]

    ranked = _dedup_and_rank_vaults(vaults_with_source)

    # vault2 应该在前面（configured 优先）
    assert ranked[0].source == "configured"
    assert ranked[0].path == str(vault2_path)


def test_dedup_and_rank_vaults_removes_duplicates(temp_vault_dir):
    """测试 - 重复 vault 被移除"""
    vault_path = temp_vault_dir / "vault"
    vault_path.mkdir()
    (vault_path / ".obsidian").mkdir()

    vaults_with_source = [
        (vault_path, "standard"),
        (vault_path, "standard"),
        (vault_path, "standard"),
    ]

    ranked = _dedup_and_rank_vaults(vaults_with_source)

    assert len(ranked) == 1
    assert ranked[0].path == str(vault_path)


# ============================================================================
# 测试 - 工具执行
# ============================================================================

@pytest.mark.asyncio
async def test_tool_execute_success(tool):
    """测试 - 工具执行成功"""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("sensenova_claw.capabilities.tools.obsidian_locate._get_configured_vaults") as mock_get_configured:
            with patch("sensenova_claw.capabilities.tools.obsidian_locate._detect_vaults_windows") as mock_detect_win:
                with patch("sensenova_claw.capabilities.tools.obsidian_locate._detect_vaults_macos") as mock_detect_mac:
                    with patch("sensenova_claw.capabilities.tools.obsidian_locate._detect_vaults_linux") as mock_detect_linux:
                        with patch("sensenova_claw.capabilities.tools.obsidian_locate._create_default_vault") as mock_create:
                            # 模拟：无配置，无检测，创建默认 vault
                            mock_get_configured.return_value = []
                            mock_detect_win.return_value = []
                            mock_detect_mac.return_value = []
                            mock_detect_linux.return_value = []

                            default_vault = Path(tmpdir) / "Obsidian"
                            default_vault.mkdir()
                            (default_vault / ".obsidian").mkdir()
                            (default_vault / "Knowledge").mkdir()

                            mock_create.return_value = default_vault

                            result = await tool.execute()

                            assert result["success"] is True
                            assert len(result["vaults"]) > 0
                            assert result["primary_vault"] is not None
                            assert result["error"] is None


@pytest.mark.asyncio
async def test_tool_execute_with_exception(tool):
    """测试 - 工具异常处理"""
    with patch("sensenova_claw.capabilities.tools.obsidian_locate._get_all_vaults") as mock_get_all:
        mock_get_all.side_effect = RuntimeError("Test error")

        result = await tool.execute()

        assert result["success"] is False
        assert "Test error" in result["error"]
        assert result["vaults"] == []


@pytest.mark.asyncio
async def test_configured_vault_gets_knowledge_structure(tool):
    """测试 - 配置的 vault 会自动补全知识库结构"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建一个配置的 vault（只有 .obsidian，没有 Knowledge 结构）
        vault_path = Path(tmpdir) / "configured-vault"
        vault_path.mkdir()
        (vault_path / ".obsidian").mkdir()

        with patch("sensenova_claw.capabilities.tools.obsidian_locate.config") as mock_config:
            mock_config.get.return_value = [str(vault_path)]

            result = await tool.execute()

            # 验证执行成功
            assert result["success"] is True
            assert len(result["vaults"]) == 1

            # 验证知识库结构已创建
            assert (vault_path / "Knowledge").exists()
            assert (vault_path / "Knowledge" / "user-profile.md").exists()
            assert (vault_path / "Knowledge" / "qa-history").exists()
            assert (vault_path / "Knowledge" / "facts").exists()

            # 验证 vault 信息正确
            vault_info = result["vaults"][0]
            assert vault_info["source"] == "configured"
            assert vault_info["has_structure"] is True


# ============================================================================
# 测试 - 平台特定
# ============================================================================

@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_windows_registry_query():
    """测试 - Windows 注册表查询（仅在 Windows 上运行）"""
    from sensenova_claw.capabilities.tools.obsidian_locate import _query_registry_windows

    result = _query_registry_windows()
    # 结果可能是 None（未安装）或字符串（安装路径）
    assert result is None or isinstance(result, str)


def test_all_platforms_return_lists():
    """测试 - 所有平台检测函数返回列表"""
    from sensenova_claw.capabilities.tools.obsidian_locate import (
        _detect_vaults_windows,
        _detect_vaults_macos,
        _detect_vaults_linux,
    )

    assert isinstance(_detect_vaults_windows(), list)
    assert isinstance(_detect_vaults_macos(), list)
    assert isinstance(_detect_vaults_linux(), list)
