"""Obsidian Vault 定位与初始化工具

支持在 Windows/macOS/Linux 上定位现有 vault，创建默认 vault，
以及补全知识库必备结构。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from sensenova_claw.capabilities.tools.base import Tool, ToolRiskLevel
from sensenova_claw.platform.config.config import config

logger = logging.getLogger(__name__)


# ============================================================================
# 数据结构
# ============================================================================

@dataclass
class VaultInfo:
    """Vault 信息"""
    name: str                  # vault 名称
    path: str                  # 绝对路径
    source: str                # "configured" | "standard" | "created"
    has_structure: bool        # 知识库结构是否完整
    created_now: bool          # 本次调用是否新创建
    accessible: bool           # 是否可读写

    def to_dict(self) -> dict:
        return asdict(self)


# ============================================================================
# 配置检查
# ============================================================================

def _get_configured_vaults() -> list[Path]:
    """从 config.yml 获取已配置的 vault 路径"""
    vault_paths = config.get("tools.obsidian.vaults", [])
    if isinstance(vault_paths, str):
        vault_paths = [vault_paths]

    vaults: list[Path] = []
    for p in vault_paths:
        try:
            path = Path(p).expanduser().resolve()
            if path.exists() and path.is_dir():
                vaults.append(path)
            else:
                logger.warning(f"配置的 vault 路径不存在: {p}")
        except Exception as e:
            logger.warning(f"处理配置 vault 路径失败 {p}: {e}")

    return vaults


def _validate_vault(vault_path: Path) -> bool:
    """验证是有效的 Obsidian vault（存在 .obsidian 目录）"""
    try:
        obsidian_dir = vault_path / ".obsidian"
        return obsidian_dir.exists() and obsidian_dir.is_dir()
    except Exception:
        return False


def _parse_vault_name(vault_path: Path) -> str:
    """从路径推断 vault 名称"""
    return vault_path.name


# ============================================================================
# 平台检测辅助函数骨架
# ============================================================================

def _detect_vaults_windows() -> list[Path]:
    """Windows 平台 vault 检测 - 检查标准位置"""
    home = Path.home()

    candidates = [
        home / "OneDrive" / "Documents" / "Obsidian",  # OneDrive Documents
        home / "OneDrive" / "Obsidian",                # OneDrive 直接
        home / "Documents" / "Obsidian",               # 本地 Documents
        home / "Obsidian",                             # 主目录下
        home / "Dropbox" / "Obsidian",                 # Dropbox
        home / "Google Drive" / "Obsidian",            # Google Drive
        home / "AppData" / "Local" / "Obsidian" / "data",  # 应用本身
    ]

    vaults: list[Path] = []
    for path in candidates:
        try:
            if path.exists() and path.is_dir():
                if _validate_vault(path):
                    vaults.append(path)
                else:
                    # 检查是否是容器目录（包含多个 vault）
                    try:
                        for subdir in path.iterdir():
                            if subdir.is_dir() and _validate_vault(subdir):
                                vaults.append(subdir)
                    except (PermissionError, OSError) as e:
                        logger.debug(f"Cannot list directory {path}: {e}")
        except Exception as e:
            logger.debug(f"Error checking Windows path {path}: {e}")

    return vaults


def _query_registry_windows() -> str | None:
    """Windows 注册表查询 Obsidian 应用位置"""
    if sys.platform != "win32":
        return None

    try:
        import winreg

        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
            )
        except FileNotFoundError:
            logger.debug("Registry path not found")
            return None

        try:
            i = 0
            while True:
                subkey_name = winreg.EnumKey(key, i)
                try:
                    subkey = winreg.OpenKey(key, subkey_name)
                    try:
                        display_name, _ = winreg.QueryValueEx(subkey, "DisplayName")
                        if "obsidian" in display_name.lower():
                            try:
                                install_location, _ = winreg.QueryValueEx(subkey, "InstallLocation")
                                logger.info(f"Found Obsidian in registry: {install_location}")
                                return install_location
                            except FileNotFoundError:
                                pass
                    finally:
                        winreg.CloseKey(subkey)
                except (FileNotFoundError, OSError):
                    pass
                i += 1
        except WindowsError:
            pass
        finally:
            winreg.CloseKey(key)

    except ImportError:
        logger.debug("winreg module not available (not on Windows)")
    except Exception as e:
        logger.debug(f"Registry query failed: {e}")

    return None


def _detect_vaults_macos() -> list[Path]:
    """macOS 平台 vault 检测 - 检查标准位置"""
    home = Path.home()

    candidates = [
        home / "OneDrive" / "Documents" / "Obsidian",
        home / "Documents" / "Obsidian",
        home / "Obsidian",
        home / "Library" / "Mobile Documents" / "iCloud~md~obsidian" / "Documents",
    ]

    vaults: list[Path] = []
    for path in candidates:
        try:
            if path.exists() and path.is_dir():
                if _validate_vault(path):
                    vaults.append(path)
                else:
                    # 检查子目录
                    try:
                        for subdir in path.iterdir():
                            if subdir.is_dir() and _validate_vault(subdir):
                                vaults.append(subdir)
                    except (PermissionError, OSError) as e:
                        logger.debug(f"Cannot list directory {path}: {e}")
        except Exception as e:
            logger.debug(f"Error checking macOS path {path}: {e}")

    return vaults


def _read_config_macos() -> list[Path]:
    """macOS 配置文件读取 - 从 Obsidian 应用配置解析"""
    home = Path.home()
    vaults: list[Path] = []

    # 尝试两个可能的配置位置
    config_paths = [
        home / "Library" / "Application Support" / "obsidian" / "obsidian.json",
        home / "Library" / "Preferences" / "com.obsidianmd.obsidian.plist",
    ]

    for config_path in config_paths:
        try:
            if config_path.exists() and config_path.is_file():
                if config_path.suffix == ".json":
                    with open(config_path, 'r') as f:
                        data = json.load(f)
                        # Obsidian JSON 配置中通常有 "vaults" 或 "open" 字段
                        if "vaults" in data and isinstance(data["vaults"], dict):
                            for vault_path_str in data["vaults"].values():
                                if isinstance(vault_path_str, str):
                                    vault_path = Path(vault_path_str).expanduser()
                                    if _validate_vault(vault_path):
                                        vaults.append(vault_path)

                        # 也检查 "open" 字段（最近打开的 vault）
                        if "open" in data and isinstance(data["open"], str):
                            vault_path = Path(data["open"]).expanduser()
                            if _validate_vault(vault_path) and vault_path not in vaults:
                                vaults.append(vault_path)

                logger.debug(f"Found {len(vaults)} vault(s) in {config_path}")

        except json.JSONDecodeError as e:
            logger.debug(f"Failed to parse JSON config {config_path}: {e}")
        except Exception as e:
            logger.debug(f"Error reading macOS config {config_path}: {e}")

    return vaults


def _detect_vaults_linux() -> list[Path]:
    """Linux 平台 vault 检测 - 检查标准位置"""
    home = Path.home()

    candidates = [
        home / "Documents" / "Obsidian",
        home / "Obsidian",
        home / ".obsidian-vaults",
        home / "文档" / "Obsidian",  # 中文环境
    ]

    vaults: list[Path] = []
    for path in candidates:
        try:
            if path.exists() and path.is_dir():
                if _validate_vault(path):
                    vaults.append(path)
                else:
                    # 检查子目录
                    try:
                        for subdir in path.iterdir():
                            if subdir.is_dir() and _validate_vault(subdir):
                                vaults.append(subdir)
                    except (PermissionError, OSError) as e:
                        logger.debug(f"Cannot list directory {path}: {e}")
        except Exception as e:
            logger.debug(f"Error checking Linux path {path}: {e}")

    return vaults


def _read_config_linux() -> list[Path]:
    """Linux 配置文件读取 - 从 Obsidian 配置解析"""
    home = Path.home()
    vaults: list[Path] = []

    config_paths = [
        home / ".config" / "obsidian" / "obsidian.json",
        home / ".local" / "share" / "obsidian" / "obsidian.json",
    ]

    for config_path in config_paths:
        try:
            if config_path.exists() and config_path.is_file():
                with open(config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                    # 解析 vaults 字段
                    if "vaults" in data and isinstance(data["vaults"], dict):
                        for vault_path_str in data["vaults"].values():
                            if isinstance(vault_path_str, str):
                                vault_path = Path(vault_path_str).expanduser()
                                if _validate_vault(vault_path):
                                    vaults.append(vault_path)

                    # 解析 open 字段
                    if "open" in data and isinstance(data["open"], str):
                        vault_path = Path(data["open"]).expanduser()
                        if _validate_vault(vault_path) and vault_path not in vaults:
                            vaults.append(vault_path)

                logger.debug(f"Found {len(vaults)} vault(s) in {config_path}")

        except json.JSONDecodeError as e:
            logger.debug(f"Failed to parse JSON config {config_path}: {e}")
        except Exception as e:
            logger.debug(f"Error reading Linux config {config_path}: {e}")

    return vaults


def _ensure_knowledge_structure(vault_path: Path) -> dict:
    """补全知识库必备结构

    Returns:
        {"created": bool, "error": str|None, "has_structure": bool}
    """
    try:
        # 确保 .obsidian 目录存在
        obsidian_dir = vault_path / ".obsidian"
        if not obsidian_dir.exists():
            obsidian_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created .obsidian directory in {vault_path}")

        # 创建或验证 .obsidian/app.json
        app_json_path = obsidian_dir / "app.json"
        if not app_json_path.exists():
            default_app_json = {
                "basePath": None,
                "baseUrl": "",
                "cssTheme": "",
                "enabledCssSnippets": [],
                "foldIndent": False,
                "promptDelete": True,
                "showInlineTitle": False,
                "showLineNumber": False,
                "strictLineBreaks": False,
                "tabSize": 4,
                "useMarkdownLinks": False,
                "vault": None,
                "mobileSyncVersion": 9
            }
            with open(app_json_path, 'w', encoding='utf-8') as f:
                json.dump(default_app_json, f, indent=2, ensure_ascii=False)
            logger.info(f"Created .obsidian/app.json in {vault_path}")

        # 创建 Knowledge 目录结构
        knowledge_dir = vault_path / "Knowledge"
        knowledge_dir.mkdir(parents=True, exist_ok=True)

        # 创建 user-profile.md
        user_profile = knowledge_dir / "user-profile.md"
        if not user_profile.exists():
            user_profile.write_text("---\nupdated: \ntags: [kb/profile]\n---\n\n", encoding='utf-8')
            logger.info(f"Created Knowledge/user-profile.md in {vault_path}")

        # 创建 qa-history 目录
        qa_history_dir = knowledge_dir / "qa-history"
        qa_history_dir.mkdir(parents=True, exist_ok=True)

        # 创建 facts 目录
        facts_dir = knowledge_dir / "facts"
        facts_dir.mkdir(parents=True, exist_ok=True)

        # 创建 README.md
        readme_path = vault_path / "README.md"
        if not readme_path.exists():
            readme_content = """# Obsidian Vault

这是一个 Obsidian vault，用于知识库管理。

## 目录结构

- **Knowledge/** - 知识库根目录
  - **user-profile.md** - 用户档案（自动填充）
  - **qa-history/** - 问答历史
  - **facts/** - 知识点库

## 使用方法

1. 在 Obsidian 中打开此文件夹
2. 将此 vault 路径配置到 Sensenova-Claw 的 config.yml 中
3. 知识库系统将自动管理笔记

---
Created by Sensenova-Claw Obsidian Integration
"""
            readme_path.write_text(readme_content, encoding='utf-8')
            logger.info(f"Created README.md in {vault_path}")

        return {
            "created": True,
            "error": None,
            "has_structure": True,
        }

    except Exception as e:
        logger.exception(f"Error ensuring knowledge structure in {vault_path}: {e}")
        return {
            "created": False,
            "error": str(e),
            "has_structure": False,
        }


def _check_knowledge_structure(vault_path: Path) -> bool:
    """检查 vault 是否有完整的知识库结构"""
    required_items = [
        vault_path / ".obsidian",
        vault_path / ".obsidian" / "app.json",
        vault_path / "Knowledge",
        vault_path / "Knowledge" / "user-profile.md",
        vault_path / "Knowledge" / "qa-history",
        vault_path / "Knowledge" / "facts",
    ]

    for item in required_items:
        if not item.exists():
            return False

    return True


def _create_default_vault() -> Path | None:
    """在标准位置创建默认 vault

    Returns:
        vault 路径或 None（如果创建失败）
    """
    home = Path.home()
    vault_path = home / "Obsidian"

    try:
        vault_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created default vault at {vault_path}")

        # 补全知识库结构
        result = _ensure_knowledge_structure(vault_path)
        if result["error"]:
            logger.warning(f"Failed to create knowledge structure: {result['error']}")
            return None

        return vault_path

    except Exception as e:
        logger.exception(f"Failed to create default vault: {e}")
        return None



# ============================================================================
# 工具主类
# ============================================================================

class ObsidianLocateTool(Tool):
    """Obsidian Vault 定位与初始化工具"""

    name = "obsidian_locate_and_setup"
    description = "定位和初始化 Obsidian vault，支持 Windows/macOS/Linux"
    risk_level = ToolRiskLevel.MEDIUM

    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    async def execute(self, **kwargs: Any) -> dict:
        """执行工具"""
        # 占位符，下个 task 实现
        return {
            "success": False,
            "error": "Not implemented",
            "vaults": [],
            "primary_vault": None,
        }
