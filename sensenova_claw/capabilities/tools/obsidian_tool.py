"""Obsidian 笔记集成工具

支持本地和远程（通过 Local REST API 插件）的 Obsidian vault。

远程连接需要在 Obsidian 中安装 Local REST API 插件：
https://github.com/coddingtonbear/obsidian-local-rest-api
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from sensenova_claw.capabilities.tools.base import Tool, ToolRiskLevel
from sensenova_claw.platform.config.config import config


# ============================================================================
# 数据结构
# ============================================================================

@dataclass
class VaultSource:
    """Vault 来源（本地或远程）"""
    name: str
    source_type: str  # "local" 或 "remote"
    path: str | None = None  # 本地路径
    url: str | None = None   # 远程 URL
    api_key: str | None = None  # 远程 API key


# ============================================================================
# 本地 Vault 操作
# ============================================================================

def _detect_obsidian_vaults() -> list[Path]:
    """自动检测常见的 Obsidian vault 位置"""
    home = Path.home()
    candidates = [
        home / "Documents" / "Obsidian",
        home / "Obsidian",
        home / "obsidian",
        home / "Documents" / "obsidian",
        home / "notes",
        home / "Notes",
        home / ".obsidian-vaults",
        # macOS
        home / "Library" / "Mobile Documents" / "iCloud~md~obsidian" / "Documents",
        # Linux 常见位置
        home / "文档" / "Obsidian",
    ]

    vaults: list[Path] = []
    for path in candidates:
        if path.exists() and path.is_dir():
            if (path / ".obsidian").exists():
                vaults.append(path)
            else:
                for subdir in path.iterdir():
                    if subdir.is_dir() and (subdir / ".obsidian").exists():
                        vaults.append(subdir)

    return vaults


def _get_configured_local_vaults() -> list[Path]:
    """从配置文件获取本地 vault 路径"""
    vault_paths = config.get("tools.obsidian.vaults", [])
    if isinstance(vault_paths, str):
        vault_paths = [vault_paths]

    vaults: list[Path] = []
    for p in vault_paths:
        path = Path(p).expanduser()
        if path.exists() and path.is_dir():
            vaults.append(path)

    return vaults


def _get_all_local_vaults() -> list[Path]:
    """获取所有本地 vault"""
    configured = _get_configured_local_vaults()
    if configured:
        return configured
    return _detect_obsidian_vaults()


# ============================================================================
# 远程 Vault 操作 (Obsidian Local REST API)
# ============================================================================

@dataclass
class RemoteVaultConfig:
    """远程 vault 配置"""
    name: str
    url: str
    api_key: str
    timeout: int = 30


def _get_remote_vaults() -> list[RemoteVaultConfig]:
    """从配置文件获取远程 vault 列表"""
    remotes = config.get("tools.obsidian.remote", [])
    if not remotes:
        return []

    result: list[RemoteVaultConfig] = []
    for i, remote in enumerate(remotes):
        if isinstance(remote, dict):
            url = remote.get("url", "")
            api_key = remote.get("api_key", "")
            name = remote.get("name", f"remote-{i+1}")
            timeout = remote.get("timeout", 30)
            if url:
                result.append(RemoteVaultConfig(
                    name=name,
                    url=url.rstrip("/"),
                    api_key=api_key,
                    timeout=timeout,
                ))

    return result


class ObsidianRemoteClient:
    """Obsidian Local REST API 客户端"""

    def __init__(self, cfg: RemoteVaultConfig):
        self.cfg = cfg
        self.base_url = cfg.url
        self.headers = {}
        if cfg.api_key:
            self.headers["Authorization"] = f"Bearer {cfg.api_key}"

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """发送 HTTP 请求"""
        async with httpx.AsyncClient(timeout=self.cfg.timeout) as client:
            url = f"{self.base_url}{path}"
            return await client.request(
                method,
                url,
                headers=self.headers,
                **kwargs,
            )

    async def test_connection(self) -> dict[str, Any]:
        """测试连接"""
        try:
            resp = await self._request("GET", "/")
            if resp.status_code == 200:
                return {"success": True, "status": "connected"}
            return {"success": False, "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def list_files(self, folder: str = "/") -> list[dict[str, Any]]:
        """列出 vault 中的文件"""
        try:
            path = f"/vault/{quote(folder.lstrip('/'), safe='/')}" if folder != "/" else "/vault/"
            resp = await self._request("GET", path)
            if resp.status_code == 200:
                data = resp.json()
                # API 返回 {"files": [...]}
                return data.get("files", [])
            return []
        except Exception:
            return []

    async def read_file(self, file_path: str) -> dict[str, Any]:
        """读取文件内容"""
        try:
            path = f"/vault/{quote(file_path.lstrip('/'), safe='/')}"
            resp = await self._request("GET", path)
            if resp.status_code == 200:
                content = resp.text
                return {"success": True, "content": content}
            return {"success": False, "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def search(self, query: str) -> list[dict[str, Any]]:
        """搜索笔记"""
        try:
            resp = await self._request(
                "POST",
                "/search/simple/",
                json={"query": query},
            )
            if resp.status_code == 200:
                return resp.json()
            return []
        except Exception:
            return []

    async def get_active_file(self) -> dict[str, Any] | None:
        """获取当前活动文件"""
        try:
            resp = await self._request("GET", "/active/")
            if resp.status_code == 200:
                return resp.json()
            return None
        except Exception:
            return None


# ============================================================================
# 通用辅助函数
# ============================================================================

def _parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """解析 YAML frontmatter"""
    if not content.startswith("---"):
        return {}, content

    end_match = re.search(r"\n---\s*\n", content[3:])
    if not end_match:
        return {}, content

    frontmatter_str = content[3:end_match.start() + 3]
    body = content[end_match.end() + 3:]

    metadata: dict[str, Any] = {}
    for line in frontmatter_str.strip().split("\n"):
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if value.startswith("[") and value.endswith("]"):
                value = [v.strip().strip('"\'') for v in value[1:-1].split(",")]
            elif value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]
            metadata[key] = value

    return metadata, body


def _extract_tags(content: str) -> list[str]:
    """提取笔记中的标签"""
    tags = re.findall(r"(?<!\#)\#([a-zA-Z\u4e00-\u9fff][\w\u4e00-\u9fff/\-]*)", content)
    return list(set(tags))


def _extract_links(content: str) -> list[str]:
    """提取笔记中的内部链接"""
    links = re.findall(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", content)
    return list(set(links))


def _get_all_vault_sources() -> list[VaultSource]:
    """获取所有 vault 来源（本地 + 远程）"""
    sources: list[VaultSource] = []

    # 本地 vaults
    for vault in _get_all_local_vaults():
        sources.append(VaultSource(
            name=vault.name,
            source_type="local",
            path=str(vault),
        ))

    # 远程 vaults
    for remote in _get_remote_vaults():
        sources.append(VaultSource(
            name=remote.name,
            source_type="remote",
            url=remote.url,
            api_key=remote.api_key,
        ))

    return sources


# ============================================================================
# 工具实现
# ============================================================================

class ObsidianSearchTool(Tool):
    """搜索 Obsidian 笔记（支持本地和远程）"""

    name = "obsidian_search"
    description = "搜索 Obsidian 笔记库中的笔记。支持本地 vault 和远程 Obsidian（通过 Local REST API）。"
    risk_level = ToolRiskLevel.LOW
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词，会匹配笔记标题和内容"
            },
            "tag": {
                "type": "string",
                "description": "按标签过滤，如 'project' 或 'work/meeting'"
            },
            "folder": {
                "type": "string",
                "description": "限定搜索的文件夹路径"
            },
            "vault": {
                "type": "string",
                "description": "指定 vault 名称（本地或远程）"
            },
            "limit": {
                "type": "integer",
                "description": "返回结果数量上限",
                "default": 20
            }
        },
        "required": []
    }

    async def execute(self, **kwargs: Any) -> Any:
        query = kwargs.get("query", "").lower()
        tag_filter = kwargs.get("tag", "")
        folder_filter = kwargs.get("folder", "")
        vault_filter = kwargs.get("vault", "")
        limit = int(kwargs.get("limit", 20))

        sources = _get_all_vault_sources()

        # 过滤指定 vault
        if vault_filter:
            sources = [s for s in sources if s.name == vault_filter]

        if not sources:
            return {
                "success": False,
                "error": "未找到 Obsidian vault。请配置本地 vault 路径或远程 REST API。",
                "hint": self._get_config_hint()
            }

        results: list[dict[str, Any]] = []
        vault_info: list[dict[str, str]] = []

        for source in sources:
            vault_info.append({"name": source.name, "type": source.source_type})

            if source.source_type == "local":
                local_results = await self._search_local(
                    Path(source.path),
                    query, tag_filter, folder_filter, limit - len(results)
                )
                results.extend(local_results)
            else:
                remote_results = await self._search_remote(
                    source, query, tag_filter, folder_filter, limit - len(results)
                )
                results.extend(remote_results)

            if len(results) >= limit:
                break

        results.sort(key=lambda x: x.get("modified", 0), reverse=True)

        return {
            "success": True,
            "count": len(results),
            "vaults": vault_info,
            "results": results[:limit]
        }

    async def _search_local(
        self,
        vault: Path,
        query: str,
        tag_filter: str,
        folder_filter: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        """搜索本地 vault"""
        results: list[dict[str, Any]] = []
        vault_name = vault.name

        for md_file in vault.rglob("*.md"):
            if ".obsidian" in md_file.parts:
                continue

            rel_path = md_file.relative_to(vault)
            if folder_filter and not str(rel_path).startswith(folder_filter):
                continue

            try:
                content = md_file.read_text(encoding="utf-8")
            except Exception:
                continue

            metadata, body = _parse_frontmatter(content)
            tags = _extract_tags(content)

            if tag_filter:
                if tag_filter not in tags and tag_filter not in metadata.get("tags", []):
                    continue

            title = md_file.stem
            if query:
                if query not in title.lower() and query not in content.lower():
                    continue

            summary = body.strip()[:200].replace("\n", " ")
            if len(body) > 200:
                summary += "..."

            results.append({
                "vault": vault_name,
                "vault_type": "local",
                "path": str(rel_path),
                "title": title,
                "tags": tags,
                "summary": summary,
                "metadata": metadata,
                "modified": md_file.stat().st_mtime,
            })

            if len(results) >= limit:
                break

        return results

    async def _search_remote(
        self,
        source: VaultSource,
        query: str,
        tag_filter: str,
        folder_filter: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        """搜索远程 vault"""
        remote_cfg = RemoteVaultConfig(
            name=source.name,
            url=source.url,
            api_key=source.api_key or "",
        )
        client = ObsidianRemoteClient(remote_cfg)

        results: list[dict[str, Any]] = []

        # 使用 REST API 搜索
        if query:
            search_results = await client.search(query)
            for item in search_results[:limit]:
                file_path = item.get("filename", "")
                if folder_filter and not file_path.startswith(folder_filter):
                    continue

                # 获取文件内容以提取标签
                file_data = await client.read_file(file_path)
                if not file_data.get("success"):
                    continue

                content = file_data.get("content", "")
                metadata, body = _parse_frontmatter(content)
                tags = _extract_tags(content)

                if tag_filter:
                    if tag_filter not in tags and tag_filter not in metadata.get("tags", []):
                        continue

                summary = body.strip()[:200].replace("\n", " ")
                if len(body) > 200:
                    summary += "..."

                results.append({
                    "vault": source.name,
                    "vault_type": "remote",
                    "path": file_path,
                    "title": Path(file_path).stem,
                    "tags": tags,
                    "summary": summary,
                    "metadata": metadata,
                    "matches": item.get("matches", []),
                })

                if len(results) >= limit:
                    break
        else:
            # 无查询时列出文件
            files = await client.list_files(folder_filter or "/")
            for file_path in files[:limit * 2]:  # 多取一些，后面可能过滤
                if not file_path.endswith(".md"):
                    continue

                file_data = await client.read_file(file_path)
                if not file_data.get("success"):
                    continue

                content = file_data.get("content", "")
                metadata, body = _parse_frontmatter(content)
                tags = _extract_tags(content)

                if tag_filter:
                    if tag_filter not in tags and tag_filter not in metadata.get("tags", []):
                        continue

                summary = body.strip()[:200].replace("\n", " ")
                if len(body) > 200:
                    summary += "..."

                results.append({
                    "vault": source.name,
                    "vault_type": "remote",
                    "path": file_path,
                    "title": Path(file_path).stem,
                    "tags": tags,
                    "summary": summary,
                    "metadata": metadata,
                })

                if len(results) >= limit:
                    break

        return results

    def _get_config_hint(self) -> str:
        return """配置示例:
tools:
  obsidian:
    # 本地 vault
    vaults:
      - ~/Documents/MyVault
    # 远程 Obsidian (需安装 Local REST API 插件)
    remote:
      - name: work-vault
        url: http://192.168.1.100:27123
        api_key: your-api-key"""


class ObsidianReadTool(Tool):
    """读取 Obsidian 笔记内容（支持本地和远程）"""

    name = "obsidian_read"
    description = "读取指定 Obsidian 笔记的完整内容。支持本地和远程 vault。"
    risk_level = ToolRiskLevel.LOW
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "笔记路径，如 'folder/note.md' 或 'note'（可省略 .md）"
            },
            "vault": {
                "type": "string",
                "description": "vault 名称（本地或远程）"
            }
        },
        "required": ["path"]
    }

    async def execute(self, **kwargs: Any) -> Any:
        note_path = kwargs.get("path", "")
        vault_name = kwargs.get("vault", "")

        if not note_path:
            return {"success": False, "error": "请指定笔记路径"}

        if not note_path.endswith(".md"):
            note_path += ".md"

        sources = _get_all_vault_sources()

        if vault_name:
            sources = [s for s in sources if s.name == vault_name]
            if not sources:
                return {"success": False, "error": f"未找到 vault: {vault_name}"}

        if not sources:
            return {"success": False, "error": "未找到任何 Obsidian vault"}

        # 依次尝试各 vault
        for source in sources:
            if source.source_type == "local":
                result = await self._read_local(Path(source.path), note_path)
            else:
                result = await self._read_remote(source, note_path)

            if result.get("success"):
                return result

        # 尝试模糊匹配
        search_name = Path(note_path).stem.lower()
        for source in sources:
            if source.source_type == "local":
                result = await self._fuzzy_read_local(Path(source.path), search_name)
                if result.get("success"):
                    result["note"] = f"通过模糊匹配找到"
                    return result

        return {
            "success": False,
            "error": f"未找到笔记: {note_path}",
            "available_vaults": [{"name": s.name, "type": s.source_type} for s in sources]
        }

    async def _read_local(self, vault: Path, note_path: str) -> dict[str, Any]:
        """读取本地笔记"""
        file_path = vault / note_path
        if not file_path.exists():
            return {"success": False}

        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as e:
            return {"success": False, "error": str(e)}

        metadata, body = _parse_frontmatter(content)
        tags = _extract_tags(content)
        links = _extract_links(content)

        return {
            "success": True,
            "vault": vault.name,
            "vault_type": "local",
            "path": note_path,
            "title": file_path.stem,
            "metadata": metadata,
            "tags": tags,
            "links": links,
            "content": body,
            "raw_content": content,
            "modified": file_path.stat().st_mtime,
        }

    async def _fuzzy_read_local(self, vault: Path, search_name: str) -> dict[str, Any]:
        """模糊匹配读取本地笔记"""
        for md_file in vault.rglob("*.md"):
            if ".obsidian" in md_file.parts:
                continue
            if md_file.stem.lower() == search_name:
                try:
                    content = md_file.read_text(encoding="utf-8")
                except Exception:
                    continue

                metadata, body = _parse_frontmatter(content)
                tags = _extract_tags(content)
                links = _extract_links(content)
                rel_path = md_file.relative_to(vault)

                return {
                    "success": True,
                    "vault": vault.name,
                    "vault_type": "local",
                    "path": str(rel_path),
                    "title": md_file.stem,
                    "metadata": metadata,
                    "tags": tags,
                    "links": links,
                    "content": body,
                    "raw_content": content,
                    "modified": md_file.stat().st_mtime,
                }

        return {"success": False}

    async def _read_remote(self, source: VaultSource, note_path: str) -> dict[str, Any]:
        """读取远程笔记"""
        remote_cfg = RemoteVaultConfig(
            name=source.name,
            url=source.url,
            api_key=source.api_key or "",
        )
        client = ObsidianRemoteClient(remote_cfg)

        result = await client.read_file(note_path)
        if not result.get("success"):
            return {"success": False}

        content = result.get("content", "")
        metadata, body = _parse_frontmatter(content)
        tags = _extract_tags(content)
        links = _extract_links(content)

        return {
            "success": True,
            "vault": source.name,
            "vault_type": "remote",
            "path": note_path,
            "title": Path(note_path).stem,
            "metadata": metadata,
            "tags": tags,
            "links": links,
            "content": body,
            "raw_content": content,
        }


class ObsidianListVaultsTool(Tool):
    """列出可用的 Obsidian vaults（本地 + 远程）"""

    name = "obsidian_list_vaults"
    description = "列出所有可用的 Obsidian vault，包括本地检测到的和配置的远程 vault。"
    risk_level = ToolRiskLevel.LOW
    parameters = {
        "type": "object",
        "properties": {
            "test_remote": {
                "type": "boolean",
                "description": "是否测试远程连接状态",
                "default": False
            }
        },
        "required": []
    }

    async def execute(self, **kwargs: Any) -> Any:
        test_remote = kwargs.get("test_remote", False)

        configured_local = _get_configured_local_vaults()
        detected_local = _detect_obsidian_vaults()
        remote_configs = _get_remote_vaults()

        vaults_info: list[dict[str, Any]] = []

        # 本地 vaults
        all_local = list(set(configured_local + detected_local))
        for vault in all_local:
            note_count = 0
            folders: set[str] = set()

            for md_file in vault.rglob("*.md"):
                if ".obsidian" not in md_file.parts:
                    note_count += 1
                    parent = md_file.parent.relative_to(vault)
                    if str(parent) != ".":
                        folders.add(str(parent).split("/")[0])

            vaults_info.append({
                "name": vault.name,
                "type": "local",
                "path": str(vault),
                "note_count": note_count,
                "top_folders": sorted(folders)[:10],
                "source": "configured" if vault in configured_local else "detected",
                "status": "available",
            })

        # 远程 vaults
        for remote in remote_configs:
            info: dict[str, Any] = {
                "name": remote.name,
                "type": "remote",
                "url": remote.url,
                "source": "configured",
            }

            if test_remote:
                client = ObsidianRemoteClient(remote)
                conn_result = await client.test_connection()
                info["status"] = "connected" if conn_result.get("success") else "disconnected"
                if not conn_result.get("success"):
                    info["error"] = conn_result.get("error")
            else:
                info["status"] = "not_tested"

            vaults_info.append(info)

        if not vaults_info:
            return {
                "success": False,
                "error": "未找到任何 Obsidian vault",
                "hint": """配置示例:
tools:
  obsidian:
    vaults:
      - ~/Documents/MyVault
    remote:
      - name: remote-vault
        url: http://192.168.1.100:27123
        api_key: your-api-key"""
            }

        return {
            "success": True,
            "count": len(vaults_info),
            "local_count": len(all_local),
            "remote_count": len(remote_configs),
            "vaults": vaults_info
        }


class ObsidianWriteTool(Tool):
    """写入/创建 Obsidian 笔记（支持本地和远程）"""

    name = "obsidian_write"
    description = "创建或更新 Obsidian 笔记。支持本地和远程 vault。"
    risk_level = ToolRiskLevel.MEDIUM
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "笔记路径，如 'folder/note.md'"
            },
            "content": {
                "type": "string",
                "description": "笔记内容（Markdown 格式）"
            },
            "vault": {
                "type": "string",
                "description": "目标 vault 名称"
            },
            "append": {
                "type": "boolean",
                "description": "是否追加到文件末尾（而非覆盖）",
                "default": False
            }
        },
        "required": ["path", "content"]
    }

    async def execute(self, **kwargs: Any) -> Any:
        note_path = kwargs.get("path", "")
        content = kwargs.get("content", "")
        vault_name = kwargs.get("vault", "")
        append = kwargs.get("append", False)

        if not note_path:
            return {"success": False, "error": "请指定笔记路径"}

        if not note_path.endswith(".md"):
            note_path += ".md"

        sources = _get_all_vault_sources()

        if vault_name:
            sources = [s for s in sources if s.name == vault_name]
            if not sources:
                return {"success": False, "error": f"未找到 vault: {vault_name}"}

        if not sources:
            return {"success": False, "error": "未找到任何 Obsidian vault"}

        # 使用第一个 vault
        source = sources[0]

        if source.source_type == "local":
            return await self._write_local(Path(source.path), note_path, content, append)
        else:
            return await self._write_remote(source, note_path, content, append)

    async def _write_local(
        self,
        vault: Path,
        note_path: str,
        content: str,
        append: bool,
    ) -> dict[str, Any]:
        """写入本地笔记"""
        file_path = vault / note_path
        file_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            if append and file_path.exists():
                existing = file_path.read_text(encoding="utf-8")
                content = existing + "\n" + content

            file_path.write_text(content, encoding="utf-8")
            return {
                "success": True,
                "vault": vault.name,
                "vault_type": "local",
                "path": note_path,
                "action": "appended" if append else "written",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _write_remote(
        self,
        source: VaultSource,
        note_path: str,
        content: str,
        append: bool,
    ) -> dict[str, Any]:
        """写入远程笔记"""
        remote_cfg = RemoteVaultConfig(
            name=source.name,
            url=source.url,
            api_key=source.api_key or "",
        )
        client = ObsidianRemoteClient(remote_cfg)

        try:
            if append:
                # 先读取现有内容
                existing = await client.read_file(note_path)
                if existing.get("success"):
                    content = existing.get("content", "") + "\n" + content

            # 写入
            path = f"/vault/{quote(note_path.lstrip('/'), safe='/')}"
            async with httpx.AsyncClient(timeout=remote_cfg.timeout) as http_client:
                resp = await http_client.put(
                    f"{remote_cfg.url}{path}",
                    headers=client.headers,
                    content=content.encode("utf-8"),
                )

            if resp.status_code in (200, 201, 204):
                return {
                    "success": True,
                    "vault": source.name,
                    "vault_type": "remote",
                    "path": note_path,
                    "action": "appended" if append else "written",
                }
            return {"success": False, "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
