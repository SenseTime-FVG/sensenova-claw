# Skill 市场管理功能 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 AgentOS 能从 ClawHub、Anthropic Plugin Marketplace、Git URL 搜索并安装 skills，在 Web UI 中统一管理，并支持聊天框斜杠命令调用 skill。

**Architecture:** 后端新增 SkillMarketService + Adapter 模式处理多来源搜索/安装/更新。扩展现有 SkillRegistry 支持热重载和启用状态持久化。前端改造 skills 页面为 Tab 式管理界面，聊天框增加斜杠命令补全。

**Tech Stack:** FastAPI + httpx (HTTP 客户端) + asyncio, Next.js 14 + TypeScript

**Spec 文档:** `docs/superpowers/specs/2026-03-12-skill-marketplace-design.md`

---

## File Structure

### 后端新增文件

| 文件 | 职责 |
|------|------|
| `backend/app/skills/models.py` | Pydantic 数据模型（SearchResult, SkillDetail, UpdateInfo, ErrorResponse 等） |
| `backend/app/skills/adapters/base.py` | MarketAdapter 抽象基类 |
| `backend/app/skills/adapters/clawhub.py` | ClawHub 市场适配器 |
| `backend/app/skills/adapters/anthropic_market.py` | Anthropic Plugin Marketplace 适配器 |
| `backend/app/skills/adapters/git_adapter.py` | Git URL 适配器 |
| `backend/app/skills/adapters/__init__.py` | 导出 |
| `backend/app/skills/market_service.py` | SkillMarketService 核心服务 |
| `backend/app/skills/arg_substitutor.py` | $ARGUMENTS 参数替换逻辑 |
| `backend/tests/test_skill_models.py` | 数据模型单测 |
| `backend/tests/test_skill_registry_ext.py` | SkillRegistry 扩展单测 |
| `backend/tests/test_arg_substitutor.py` | 参数替换单测 |
| `backend/tests/test_market_service.py` | SkillMarketService 单测 |
| `backend/tests/test_skill_api.py` | API 端点单测 |

### 后端修改文件

| 文件 | 变更 |
|------|------|
| `backend/app/skills/registry.py` | 扩展 Skill 模型 + SkillRegistry 热重载/启用状态持久化 |
| `backend/app/api/skills.py` | 扩展为完整 CRUD API + 市场搜索 + skill-invoke |
| `backend/app/main.py` | 初始化 SkillMarketService，注册到 app.state |

### 前端新增文件

| 文件 | 职责 |
|------|------|
| `frontend/app/skills/components/InstalledTab.tsx` | 已安装 Tab 组件 |
| `frontend/app/skills/components/MarketTab.tsx` | 市场浏览 Tab 组件 |
| `frontend/app/skills/components/SkillDetailModal.tsx` | Skill 详情弹窗 |
| `frontend/app/skills/components/SkillCard.tsx` | 复用的 Skill 卡片组件 |
| `frontend/components/chat/SlashCommandMenu.tsx` | 聊天斜杠命令补全菜单 |

### 前端修改文件

| 文件 | 变更 |
|------|------|
| `frontend/app/skills/page.tsx` | 改造为 Tab 式页面 |
| `frontend/app/chat/page.tsx` | 集成斜杠命令补全 + skill-invoke 发送 |

---

## Chunk 1: 后端数据模型与 SkillRegistry 扩展

### Task 1: Pydantic 数据模型

**Files:**
- Create: `backend/app/skills/models.py`
- Test: `backend/tests/test_skill_models.py`

- [ ] **Step 1: 编写数据模型测试**

```python
# backend/tests/test_skill_models.py
"""Skill 市场数据模型单测"""
import pytest
from app.skills.models import (
    SkillSearchItem, SearchResult, SkillDetail,
    UpdateInfo, ErrorResponse, InstallRequest, SkillInvokeRequest,
)


def test_search_result_serialization():
    item = SkillSearchItem(
        id="pdf-tool", name="pdf-tool", description="PDF工具",
        author="test", version="1.0.0", downloads=100, source="clawhub",
    )
    result = SearchResult(source="clawhub", total=1, page=1, page_size=20, items=[item])
    d = result.model_dump()
    assert d["total"] == 1
    assert d["items"][0]["id"] == "pdf-tool"


def test_skill_detail_defaults():
    detail = SkillDetail(
        id="x", name="x", description="d",
        skill_md_preview="---\nname: x\n---\nbody", files=["SKILL.md"],
        installed=False,
    )
    assert detail.version is None
    assert detail.author is None


def test_error_response():
    err = ErrorResponse(error="conflict", code="NAME_CONFLICT")
    assert err.ok is False


def test_install_request_clawhub():
    req = InstallRequest(source="clawhub", id="my-skill")
    assert req.repo_url is None


def test_install_request_git():
    req = InstallRequest(source="git", repo_url="https://github.com/u/r")
    assert req.id is None


def test_skill_invoke_request():
    req = SkillInvokeRequest(skill_name="pdf-tool", arguments="file.pdf")
    assert req.skill_name == "pdf-tool"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python3 -m pytest tests/test_skill_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.skills.models'`

- [ ] **Step 3: 实现数据模型**

```python
# backend/app/skills/models.py
"""Skill 市场管理数据模型"""
from __future__ import annotations

from pydantic import BaseModel


class SkillSearchItem(BaseModel):
    id: str
    name: str
    description: str
    author: str | None = None
    version: str | None = None
    downloads: int | None = None
    source: str


class SearchResult(BaseModel):
    source: str
    total: int
    page: int
    page_size: int
    items: list[SkillSearchItem]


class SkillDetail(BaseModel):
    id: str
    name: str
    description: str
    version: str | None = None
    author: str | None = None
    skill_md_preview: str
    files: list[str]
    installed: bool


class UpdateInfo(BaseModel):
    skill_id: str
    current_version: str
    latest_version: str
    changelog: str | None = None


class ErrorResponse(BaseModel):
    ok: bool = False
    error: str
    code: str  # NAME_CONFLICT, INVALID_SKILL, NETWORK_ERROR, INSTALL_FAILED, NOT_FOUND, PERMISSION_DENIED


class InstallRequest(BaseModel):
    source: str  # clawhub, anthropic, git
    id: str | None = None  # 市场 skill id
    repo_url: str | None = None  # git 来源


class SkillInvokeRequest(BaseModel):
    skill_name: str
    arguments: str = ""
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python3 -m pytest tests/test_skill_models.py -v`
Expected: 6 passed

- [ ] **Step 5: 提交**

```bash
git add backend/app/skills/models.py backend/tests/test_skill_models.py
git commit -m "feat(skills): add Pydantic data models for skill marketplace"
```

---

### Task 2: SkillRegistry 扩展 — Skill 模型 + 热重载 + 启用状态持久化

**Files:**
- Modify: `backend/app/skills/registry.py`
- Test: `backend/tests/test_skill_registry_ext.py`

- [ ] **Step 1: 编写 SkillRegistry 扩展测试**

```python
# backend/tests/test_skill_registry_ext.py
"""SkillRegistry 扩展功能单测：install_info、热重载、启用状态持久化"""
import json
import pytest
from pathlib import Path
from app.skills.registry import Skill, SkillRegistry


@pytest.fixture
def tmp_workspace(tmp_path):
    """创建带 SKILL.md 的临时 workspace"""
    skill_dir = tmp_path / "skills" / "test-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: test-skill\ndescription: A test skill\n---\nDo something with $ARGUMENTS"
    )
    return tmp_path


@pytest.fixture
def tmp_skill(tmp_workspace):
    skill_dir = tmp_workspace / "skills" / "test-skill"
    return Skill(
        name="test-skill",
        description="A test skill",
        body="Do something with $ARGUMENTS",
        path=skill_dir,
    )


# --- Skill.install_info ---

def test_install_info_none_when_no_file(tmp_skill):
    assert tmp_skill.install_info is None
    assert tmp_skill.source == "local"
    assert tmp_skill.version is None


def test_install_info_reads_json(tmp_skill):
    info = {"source": "clawhub", "source_id": "test-skill", "version": "1.0.0"}
    (tmp_skill.path / ".install.json").write_text(json.dumps(info))
    assert tmp_skill.install_info["source"] == "clawhub"
    assert tmp_skill.source == "clawhub"
    assert tmp_skill.version == "1.0.0"


# --- SkillRegistry 热重载 ---

def test_register_and_unregister(tmp_skill):
    reg = SkillRegistry()
    reg.register(tmp_skill)
    assert reg.get("test-skill") is not None
    assert reg.unregister("test-skill") is True
    assert reg.get("test-skill") is None
    assert reg.unregister("nonexistent") is False


def test_reload_skill(tmp_workspace):
    reg = SkillRegistry(workspace_dir=tmp_workspace / "skills")
    reg.load_skills({})
    assert reg.get("test-skill") is not None

    # 修改 SKILL.md
    skill_md = tmp_workspace / "skills" / "test-skill" / "SKILL.md"
    skill_md.write_text("---\nname: test-skill\ndescription: Updated desc\n---\nNew body")
    assert reg.reload_skill("test-skill", {}) is True
    assert reg.get("test-skill").description == "Updated desc"

    # 不存在的 skill
    assert reg.reload_skill("nonexistent", {}) is False


# --- 启用状态持久化 ---

def test_skills_state_json_persistence(tmp_workspace):
    state_file = tmp_workspace / "skills_state.json"
    reg = SkillRegistry(workspace_dir=tmp_workspace / "skills", state_file=state_file)
    reg.load_skills({})
    assert reg.get("test-skill") is not None

    # 禁用
    reg.set_enabled("test-skill", False)
    state = json.loads(state_file.read_text())
    assert state["test-skill"]["enabled"] is False

    # 重新加载，应该跳过被禁用的 skill
    reg2 = SkillRegistry(workspace_dir=tmp_workspace / "skills", state_file=state_file)
    reg2.load_skills({})
    assert reg2.get("test-skill") is None

    # 重新启用
    reg2.set_enabled("test-skill", True)
    reg2.load_skills({})
    assert reg2.get("test-skill") is not None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python3 -m pytest tests/test_skill_registry_ext.py -v`
Expected: FAIL — `TypeError` (Skill 缺少 install_info 等属性, SkillRegistry 缺少新参数)

- [ ] **Step 3: 扩展 Skill 模型和 SkillRegistry**

修改 `backend/app/skills/registry.py`：

```python
from __future__ import annotations

import json
import shutil
import yaml
from pathlib import Path
from typing import Any


class Skill:
    def __init__(self, name: str, description: str, body: str, path: Path):
        self.name = name
        self.description = description
        self.body = body
        self.path = path

    @property
    def install_info(self) -> dict | None:
        """读取 .install.json，无则返回 None（本地 skill）"""
        info_path = self.path / ".install.json"
        if info_path.exists():
            try:
                return json.loads(info_path.read_text(encoding="utf-8"))
            except Exception:
                return None
        return None

    @property
    def source(self) -> str:
        info = self.install_info
        return info["source"] if info else "local"

    @property
    def version(self) -> str | None:
        info = self.install_info
        return info.get("version") if info else None


class SkillRegistry:
    def __init__(
        self,
        workspace_dir: Path | None = None,
        user_dir: Path | None = None,
        state_file: Path | None = None,
    ):
        self._skills: dict[str, Skill] = {}
        self._workspace_dir = workspace_dir
        self._user_dir = user_dir or Path.home() / ".agentos" / "skills"
        self._state_file = state_file

    # --- 启用状态持久化 ---

    def _load_state(self) -> dict[str, Any]:
        """读取 skills_state.json"""
        if self._state_file and self._state_file.exists():
            try:
                return json.loads(self._state_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save_state(self, state: dict[str, Any]) -> None:
        """写入 skills_state.json"""
        if self._state_file:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            self._state_file.write_text(
                json.dumps(state, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def set_enabled(self, name: str, enabled: bool) -> None:
        """设置 skill 启用/禁用状态并持久化"""
        state = self._load_state()
        state[name] = {"enabled": enabled}
        self._save_state(state)
        # 运行时立即生效
        if not enabled:
            self._skills.pop(name, None)

    def is_enabled(self, name: str) -> bool:
        """查询 skill 是否启用"""
        state = self._load_state()
        entry = state.get(name, {})
        return entry.get("enabled", True)

    # --- 加载 ---

    def load_skills(self, config: dict[str, Any]) -> None:
        """从用户目录、工作区目录和额外目录加载 skills"""
        self._skills.clear()
        if self._user_dir.exists():
            self._load_from_dir(self._user_dir, config)
        if self._workspace_dir and self._workspace_dir.exists():
            self._load_from_dir(self._workspace_dir, config)
        extra_dirs = config.get("skills", {}).get("extra_dirs", [])
        for dir_path in extra_dirs:
            p = Path(dir_path)
            if p.exists():
                self._load_from_dir(p, config)

    def _load_from_dir(self, base_dir: Path, config: dict[str, Any]) -> None:
        """从目录加载所有 SKILL.md"""
        for skill_md in base_dir.rglob("SKILL.md"):
            skill = self._parse_skill(skill_md)
            if skill and self._should_load(skill, config):
                self._skills[skill.name] = skill

    def _parse_skill(self, skill_path: Path) -> Skill | None:
        """解析 SKILL.md 文件"""
        try:
            content = skill_path.read_text(encoding="utf-8")
            if not content.startswith("---"):
                return None
            parts = content.split("---", 2)
            if len(parts) < 3:
                return None
            frontmatter = yaml.safe_load(parts[1])
            name = frontmatter.get("name")
            description = frontmatter.get("description")
            body = parts[2].strip()
            if not name or not description:
                return None
            return Skill(name, description, body, skill_path.parent)
        except Exception:
            return None

    def _should_load(self, skill: Skill, config: dict[str, Any]) -> bool:
        """检查 skill 是否应该加载（门控）"""
        # 优先读取 skills_state.json
        state = self._load_state()
        state_entry = state.get(skill.name, {})
        if "enabled" in state_entry:
            if not state_entry["enabled"]:
                return False
        else:
            # 其次读取 config.yml
            entries = config.get("skills", {}).get("entries", {})
            skill_config = entries.get(skill.name, {})
            if not skill_config.get("enabled", True):
                return False

        # 检查依赖的二进制文件
        metadata = self._parse_metadata(skill)
        requires = metadata.get("agentos", {}).get("requires", {})
        bins = requires.get("bins", [])
        for bin_name in bins:
            if not shutil.which(bin_name):
                return False
        return True

    def _parse_metadata(self, skill: Skill) -> dict[str, Any]:
        """解析 frontmatter 中的 metadata 字段"""
        try:
            skill_md = skill.path / "SKILL.md"
            content = skill_md.read_text(encoding="utf-8")
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter = yaml.safe_load(parts[1])
                return frontmatter.get("metadata", {})
        except Exception:
            pass
        return {}

    # --- 热重载 ---

    def register(self, skill: Skill) -> None:
        """安装后立即注册，无需重启"""
        self._skills[skill.name] = skill

    def unregister(self, name: str) -> bool:
        """卸载时移除"""
        return self._skills.pop(name, None) is not None

    def reload_skill(self, name: str, config: dict) -> bool:
        """更新后重新解析并替换"""
        skill = self._skills.get(name)
        if not skill:
            return False
        new_skill = self._parse_skill(skill.path / "SKILL.md")
        if new_skill and self._should_load(new_skill, config):
            self._skills[name] = new_skill
            return True
        return False

    # --- 查询 ---

    def get_all(self) -> list[Skill]:
        """获取所有已加载的 skills"""
        return list(self._skills.values())

    def get(self, name: str) -> Skill | None:
        """根据名称获取 skill"""
        return self._skills.get(name)

    def parse_skill(self, skill_path: Path) -> Skill | None:
        """解析 SKILL.md 文件（公开接口，供 SkillMarketService 调用）"""
        return self._parse_skill(skill_path)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python3 -m pytest tests/test_skill_registry_ext.py -v`
Expected: 全部 passed

- [ ] **Step 5: 运行已有 skill 测试确保无回归**

Run: `cd backend && python3 -m pytest tests/test_skill_registry.py -v`
Expected: 全部 passed（已有测试兼容新签名，因为 state_file 默认 None）

- [ ] **Step 6: 提交**

```bash
git add backend/app/skills/registry.py backend/tests/test_skill_registry_ext.py
git commit -m "feat(skills): extend SkillRegistry with hot-reload, enable/disable persistence"
```

---

### Task 3: $ARGUMENTS 参数替换

**Files:**
- Create: `backend/app/skills/arg_substitutor.py`
- Test: `backend/tests/test_arg_substitutor.py`

- [ ] **Step 1: 编写参数替换测试**

```python
# backend/tests/test_arg_substitutor.py
"""$ARGUMENTS 参数替换逻辑单测"""
import pytest
from app.skills.arg_substitutor import substitute_arguments, parse_arguments


class TestParseArguments:
    def test_simple_split(self):
        assert parse_arguments("foo bar baz") == ["foo", "bar", "baz"]

    def test_quoted_string(self):
        assert parse_arguments('foo "bar baz" qux') == ["foo", "bar baz", "qux"]

    def test_single_quoted(self):
        assert parse_arguments("foo 'bar baz' qux") == ["foo", "bar baz", "qux"]

    def test_empty(self):
        assert parse_arguments("") == []

    def test_whitespace_only(self):
        assert parse_arguments("   ") == []


class TestSubstituteArguments:
    def test_arguments_placeholder(self):
        body = "Process $ARGUMENTS now"
        result = substitute_arguments(body, "file.pdf --verbose")
        assert result == "Process file.pdf --verbose now"

    def test_indexed_placeholder(self):
        body = "Convert $ARGUMENTS[0] to $ARGUMENTS[1]"
        result = substitute_arguments(body, "input.pdf markdown")
        assert result == "Convert input.pdf to markdown"

    def test_shorthand_placeholder(self):
        body = "Convert $0 to $1"
        result = substitute_arguments(body, "input.pdf markdown")
        assert result == "Convert input.pdf to markdown"

    def test_no_placeholder_appends(self):
        body = "Do the task"
        result = substitute_arguments(body, "extra args")
        assert result == "Do the task\n\nARGUMENTS: extra args"

    def test_empty_arguments(self):
        body = "Do $ARGUMENTS"
        result = substitute_arguments(body, "")
        assert result == "Do "

    def test_mixed_placeholders(self):
        body = "All: $ARGUMENTS, first: $0, second: $ARGUMENTS[1]"
        result = substitute_arguments(body, 'a "b c"')
        assert result == "All: a \"b c\", first: a, second: b c"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python3 -m pytest tests/test_arg_substitutor.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 实现参数替换**

```python
# backend/app/skills/arg_substitutor.py
"""Skill $ARGUMENTS 参数替换逻辑，兼容 Claude Code Agent Skills 标准"""
from __future__ import annotations

import re
import shlex


def parse_arguments(raw: str) -> list[str]:
    """按空格分割参数，引号内空格保留"""
    raw = raw.strip()
    if not raw:
        return []
    try:
        return shlex.split(raw)
    except ValueError:
        # 引号不匹配时退化为简单分割
        return raw.split()


def substitute_arguments(body: str, raw_args: str) -> str:
    """将 skill body 中的占位符替换为实际参数值

    占位符:
      $ARGUMENTS — 完整参数字符串
      $ARGUMENTS[N] — 第 N 个参数（0-based）
      $N — $ARGUMENTS[N] 的简写
    """
    args = parse_arguments(raw_args)
    has_placeholder = False

    # 替换 $ARGUMENTS[N]
    def _replace_indexed(m: re.Match) -> str:
        nonlocal has_placeholder
        has_placeholder = True
        idx = int(m.group(1))
        return args[idx] if idx < len(args) else ""

    result = re.sub(r"\$ARGUMENTS\[(\d+)\]", _replace_indexed, body)

    # 替换 $ARGUMENTS（完整字符串）
    if "$ARGUMENTS" in result:
        has_placeholder = True
        result = result.replace("$ARGUMENTS", raw_args)

    # 替换 $N 简写（仅匹配独立的 $0, $1 等，不匹配 $ARGUMENTS）
    def _replace_shorthand(m: re.Match) -> str:
        nonlocal has_placeholder
        has_placeholder = True
        idx = int(m.group(1))
        return args[idx] if idx < len(args) else ""

    result = re.sub(r"\$(\d+)(?!\w)", _replace_shorthand, result)

    # 无占位符时追加到末尾
    if not has_placeholder and raw_args.strip():
        result = result.rstrip() + f"\n\nARGUMENTS: {raw_args}"

    return result
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python3 -m pytest tests/test_arg_substitutor.py -v`
Expected: 全部 passed

- [ ] **Step 5: 提交**

```bash
git add backend/app/skills/arg_substitutor.py backend/tests/test_arg_substitutor.py
git commit -m "feat(skills): add argument substitution for slash commands"
```

---

## Chunk 2: Adapter 层 + SkillMarketService

### Task 4: MarketAdapter 抽象基类

**Files:**
- Create: `backend/app/skills/adapters/__init__.py`
- Create: `backend/app/skills/adapters/base.py`

- [ ] **Step 1: 创建 Adapter 基类**

```python
# backend/app/skills/adapters/__init__.py
from .base import MarketAdapter

__all__ = ["MarketAdapter"]
```

> 注意：Adapter 实现（ClawHub、Anthropic、Git）将在 Task 5-7 完成后再更新 `__init__.py` 的导出。

```python
# backend/app/skills/adapters/base.py
"""市场适配器抽象基类"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from app.skills.models import SearchResult, SkillDetail, UpdateInfo


class MarketAdapter(ABC):
    """统一的市场适配器接口"""

    @property
    def supports_search(self) -> bool:
        """该来源是否支持搜索"""
        return True

    @abstractmethod
    async def search(self, query: str, page: int = 1, page_size: int = 20) -> SearchResult:
        """搜索 skill，返回分页结果"""

    @abstractmethod
    async def get_detail(self, skill_id: str) -> SkillDetail:
        """获取 skill 详情"""

    @abstractmethod
    async def download(self, skill_id: str, target_dir: Path) -> Path:
        """下载并解压 skill 到目标目录，返回 skill 路径"""

    @abstractmethod
    async def check_update(self, skill_id: str, current_version: str) -> UpdateInfo | None:
        """检查是否有新版本"""
```

- [ ] **Step 2: 提交**

```bash
git add backend/app/skills/adapters/
git commit -m "feat(skills): add MarketAdapter abstract base class"
```

---

### Task 5: 安装 httpx 依赖 + ClawHub Adapter

**Files:**
- Create: `backend/app/skills/adapters/clawhub.py`

- [ ] **Step 0: 安装 httpx**

Run: `cd backend && uv add httpx`
Expected: httpx 添加到 pyproject.toml 依赖中

- [ ] **Step 1: 实现 ClawHubAdapter**

```python
# backend/app/skills/adapters/clawhub.py
"""ClawHub 市场适配器"""
from __future__ import annotations

import zipfile
import tempfile
import shutil
import logging
from pathlib import Path

import httpx

from app.skills.models import SearchResult, SkillSearchItem, SkillDetail, UpdateInfo
from .base import MarketAdapter

logger = logging.getLogger(__name__)

# ClawHub API 基础地址（可通过配置覆盖）
CLAWHUB_API_BASE = "https://api.clawhub.ai/v1"


class ClawHubAdapter(MarketAdapter):
    def __init__(self, api_base: str = CLAWHUB_API_BASE, timeout: float = 30.0):
        self._api_base = api_base.rstrip("/")
        self._timeout = timeout

    async def search(self, query: str, page: int = 1, page_size: int = 20) -> SearchResult:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                f"{self._api_base}/skills/search",
                params={"q": query, "page": page, "per_page": page_size},
            )
            resp.raise_for_status()
            data = resp.json()

        items = [
            SkillSearchItem(
                id=s.get("slug", s.get("name", "")),
                name=s.get("name", ""),
                description=s.get("description", ""),
                author=s.get("author", {}).get("name"),
                version=s.get("version"),
                downloads=s.get("downloads"),
                source="clawhub",
            )
            for s in data.get("results", [])
        ]
        return SearchResult(
            source="clawhub",
            total=data.get("total", len(items)),
            page=page,
            page_size=page_size,
            items=items,
        )

    async def get_detail(self, skill_id: str) -> SkillDetail:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(f"{self._api_base}/skills/{skill_id}")
            resp.raise_for_status()
            data = resp.json()

        return SkillDetail(
            id=skill_id,
            name=data.get("name", skill_id),
            description=data.get("description", ""),
            version=data.get("version"),
            author=data.get("author", {}).get("name"),
            skill_md_preview=data.get("skill_md", ""),
            files=data.get("files", []),
            installed=False,  # 由 service 层判断
        )

    async def download(self, skill_id: str, target_dir: Path) -> Path:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(f"{self._api_base}/skills/{skill_id}/download")
            resp.raise_for_status()

        # 写入临时文件并解压
        with tempfile.NamedTemporaryFile(suffix=".skill", delete=False) as tmp:
            tmp.write(resp.content)
            tmp_path = Path(tmp.name)

        try:
            with zipfile.ZipFile(tmp_path, "r") as zf:
                # .skill 包内顶层目录即 skill 名
                top_dirs = {n.split("/")[0] for n in zf.namelist() if "/" in n}
                if len(top_dirs) == 1:
                    skill_name = top_dirs.pop()
                else:
                    skill_name = skill_id
                zf.extractall(target_dir)
            return target_dir / skill_name
        finally:
            tmp_path.unlink(missing_ok=True)

    async def check_update(self, skill_id: str, current_version: str) -> UpdateInfo | None:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(f"{self._api_base}/skills/{skill_id}")
                resp.raise_for_status()
                data = resp.json()
            latest = data.get("version")
            if latest and latest != current_version:
                return UpdateInfo(
                    skill_id=skill_id,
                    current_version=current_version,
                    latest_version=latest,
                )
        except Exception:
            logger.warning("检查 ClawHub skill %s 更新失败", skill_id, exc_info=True)
        return None
```

- [ ] **Step 2: 提交**

```bash
git add backend/app/skills/adapters/clawhub.py
git commit -m "feat(skills): add ClawHub market adapter"
```

---

### Task 6: Anthropic Adapter

**Files:**
- Create: `backend/app/skills/adapters/anthropic_market.py`

- [ ] **Step 1: 实现 AnthropicAdapter**

> 注意：Anthropic Plugin Marketplace 的 API 文档尚未完全公开，此实现基于合理推测，结构与 ClawHubAdapter 对称。正式集成时需对接真实 API。

```python
# backend/app/skills/adapters/anthropic_market.py
"""Anthropic Plugin Marketplace 适配器"""
from __future__ import annotations

import zipfile
import tempfile
import logging
from pathlib import Path

import httpx

from app.skills.models import SearchResult, SkillSearchItem, SkillDetail, UpdateInfo
from .base import MarketAdapter

logger = logging.getLogger(__name__)

ANTHROPIC_MARKET_API_BASE = "https://marketplace.claude.com/api/v1"


class AnthropicAdapter(MarketAdapter):
    def __init__(self, api_base: str = ANTHROPIC_MARKET_API_BASE, timeout: float = 30.0):
        self._api_base = api_base.rstrip("/")
        self._timeout = timeout

    async def search(self, query: str, page: int = 1, page_size: int = 20) -> SearchResult:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                f"{self._api_base}/plugins/search",
                params={"q": query, "page": page, "per_page": page_size},
            )
            resp.raise_for_status()
            data = resp.json()

        items = [
            SkillSearchItem(
                id=p.get("id", ""),
                name=p.get("name", ""),
                description=p.get("description", ""),
                author=p.get("author", {}).get("name"),
                version=p.get("version"),
                downloads=p.get("installs"),
                source="anthropic",
            )
            for p in data.get("plugins", [])
        ]
        return SearchResult(
            source="anthropic",
            total=data.get("total", len(items)),
            page=page,
            page_size=page_size,
            items=items,
        )

    async def get_detail(self, skill_id: str) -> SkillDetail:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(f"{self._api_base}/plugins/{skill_id}")
            resp.raise_for_status()
            data = resp.json()

        return SkillDetail(
            id=skill_id,
            name=data.get("name", skill_id),
            description=data.get("description", ""),
            version=data.get("version"),
            author=data.get("author", {}).get("name"),
            skill_md_preview=data.get("skill_md", ""),
            files=data.get("files", []),
            installed=False,
        )

    async def download(self, skill_id: str, target_dir: Path) -> Path:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(f"{self._api_base}/plugins/{skill_id}/download")
            resp.raise_for_status()

        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp.write(resp.content)
            tmp_path = Path(tmp.name)

        try:
            with zipfile.ZipFile(tmp_path, "r") as zf:
                # Anthropic plugin 包内可能有 skills/ 子目录
                names = zf.namelist()
                skill_dirs = [n for n in names if n.endswith("/SKILL.md")]
                if skill_dirs:
                    # 提取 skills 所在顶层目录
                    skill_root = skill_dirs[0].split("/SKILL.md")[0]
                    zf.extractall(target_dir)
                    return target_dir / skill_root
                else:
                    zf.extractall(target_dir)
                    top_dirs = {n.split("/")[0] for n in names if "/" in n}
                    return target_dir / (top_dirs.pop() if len(top_dirs) == 1 else skill_id)
        finally:
            tmp_path.unlink(missing_ok=True)

    async def check_update(self, skill_id: str, current_version: str) -> UpdateInfo | None:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(f"{self._api_base}/plugins/{skill_id}")
                resp.raise_for_status()
                data = resp.json()
            latest = data.get("version")
            if latest and latest != current_version:
                return UpdateInfo(
                    skill_id=skill_id,
                    current_version=current_version,
                    latest_version=latest,
                )
        except Exception:
            logger.warning("检查 Anthropic skill %s 更新失败", skill_id, exc_info=True)
        return None
```

- [ ] **Step 2: 提交**

```bash
git add backend/app/skills/adapters/anthropic_market.py
git commit -m "feat(skills): add Anthropic marketplace adapter"
```

---

### Task 7: Git Adapter

**Files:**
- Create: `backend/app/skills/adapters/git_adapter.py`

- [ ] **Step 1: 实现 GitAdapter**

```python
# backend/app/skills/adapters/git_adapter.py
"""Git URL 适配器 — 从 Git 仓库克隆并提取 skill"""
from __future__ import annotations

import asyncio
import shutil
import tempfile
import logging
from pathlib import Path

from app.skills.models import SearchResult, SkillDetail, UpdateInfo
from .base import MarketAdapter

logger = logging.getLogger(__name__)


class GitAdapter(MarketAdapter):
    @property
    def supports_search(self) -> bool:
        return False

    async def search(self, query: str, page: int = 1, page_size: int = 20) -> SearchResult:
        """Git 来源不支持搜索，返回空结果"""
        return SearchResult(source="git", total=0, page=page, page_size=page_size, items=[])

    async def get_detail(self, skill_id: str) -> SkillDetail:
        """skill_id 即 repo_url，克隆后解析 SKILL.md"""
        tmp_dir = Path(tempfile.mkdtemp())
        try:
            await self._clone(skill_id, tmp_dir)
            skill_md_path = self._find_skill_md(tmp_dir)
            if not skill_md_path:
                raise FileNotFoundError(f"仓库中未找到 SKILL.md: {skill_id}")

            content = skill_md_path.read_text(encoding="utf-8")
            skill_dir = skill_md_path.parent
            files = [
                str(f.relative_to(skill_dir))
                for f in skill_dir.rglob("*")
                if f.is_file() and not f.name.startswith(".")
            ]
            # 解析 frontmatter
            name = skill_dir.name
            description = ""
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    import yaml
                    fm = yaml.safe_load(parts[1]) or {}
                    name = fm.get("name", name)
                    description = fm.get("description", "")

            return SkillDetail(
                id=skill_id,
                name=name,
                description=description,
                skill_md_preview=content,
                files=files,
                installed=False,
            )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    async def download(self, skill_id: str, target_dir: Path) -> Path:
        """skill_id 即 repo_url，克隆到目标目录"""
        tmp_dir = Path(tempfile.mkdtemp())
        try:
            await self._clone(skill_id, tmp_dir)
            skill_md_path = self._find_skill_md(tmp_dir)
            if not skill_md_path:
                raise FileNotFoundError(f"仓库中未找到 SKILL.md: {skill_id}")

            skill_src = skill_md_path.parent
            skill_name = skill_src.name
            skill_dst = target_dir / skill_name

            if skill_dst.exists():
                raise FileExistsError(f"目标目录已存在: {skill_dst}")

            shutil.copytree(skill_src, skill_dst)
            # 删除 .git 目录（如果复制了整个仓库）
            git_dir = skill_dst / ".git"
            if git_dir.exists():
                shutil.rmtree(git_dir)

            return skill_dst
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    async def check_update(self, skill_id: str, current_version: str) -> UpdateInfo | None:
        """Git 来源暂不支持版本更新检测"""
        return None

    async def _clone(self, repo_url: str, dest: Path) -> None:
        """浅克隆仓库"""
        proc = await asyncio.create_subprocess_exec(
            "git", "clone", "--depth", "1", repo_url, str(dest / "repo"),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"git clone 失败: {stderr.decode()}")

    def _find_skill_md(self, base: Path) -> Path | None:
        """在克隆目录中查找 SKILL.md"""
        for p in base.rglob("SKILL.md"):
            return p
        return None
```

- [ ] **Step 2: 提交**

```bash
git add backend/app/skills/adapters/git_adapter.py
git commit -m "feat(skills): add Git URL adapter"
```

- [ ] **Step 3: 更新 adapters/__init__.py 导出所有 Adapter**

```python
# backend/app/skills/adapters/__init__.py
from .base import MarketAdapter
from .clawhub import ClawHubAdapter
from .anthropic_market import AnthropicAdapter
from .git_adapter import GitAdapter

__all__ = ["MarketAdapter", "ClawHubAdapter", "AnthropicAdapter", "GitAdapter"]
```

- [ ] **Step 4: 提交**

```bash
git add backend/app/skills/adapters/__init__.py
git commit -m "feat(skills): export all adapter implementations"
```

---

### Task 8: SkillMarketService

**Files:**
- Create: `backend/app/skills/market_service.py`
- Test: `backend/tests/test_market_service.py`

- [ ] **Step 1: 编写 SkillMarketService 测试**

```python
# backend/tests/test_market_service.py
"""SkillMarketService 核心逻辑单测（使用 mock adapter）"""
import json
import pytest
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from app.skills.market_service import SkillMarketService
from app.skills.models import SearchResult, SkillSearchItem, SkillDetail
from app.skills.registry import SkillRegistry


@pytest.fixture
def tmp_workspace(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    return tmp_path


@pytest.fixture
def registry(tmp_workspace):
    state_file = tmp_workspace / "skills_state.json"
    return SkillRegistry(workspace_dir=tmp_workspace / "skills", state_file=state_file)


@pytest.fixture
def mock_adapter():
    adapter = AsyncMock()
    adapter.supports_search = True
    adapter.search.return_value = SearchResult(
        source="mock", total=1, page=1, page_size=20,
        items=[SkillSearchItem(id="test-skill", name="test-skill", description="Test", source="mock")],
    )
    return adapter


@pytest.fixture
def service(tmp_workspace, registry, mock_adapter):
    svc = SkillMarketService(
        skills_dir=tmp_workspace / "skills",
        skill_registry=registry,
        config={},
    )
    svc._adapters["mock"] = mock_adapter
    return svc


@pytest.mark.asyncio
async def test_search(service, mock_adapter):
    result = await service.search("mock", "test")
    assert result.total == 1
    mock_adapter.search.assert_called_once()


@pytest.mark.asyncio
async def test_install_success(service, mock_adapter, tmp_workspace):
    # mock download: 在目标目录创建 skill
    async def fake_download(skill_id, target_dir):
        skill_dir = target_dir / skill_id
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\nname: test-skill\ndescription: Test\n---\nBody")
        return skill_dir

    mock_adapter.download = AsyncMock(side_effect=fake_download)
    result = await service.install("mock", "test-skill")
    assert result["ok"] is True
    assert result["skill_name"] == "test-skill"
    # 验证 .install.json 被写入
    install_json = tmp_workspace / "skills" / "test-skill" / ".install.json"
    assert install_json.exists()
    info = json.loads(install_json.read_text())
    assert info["source"] == "mock"
    # 验证注册到 registry
    assert service._registry.get("test-skill") is not None


@pytest.mark.asyncio
async def test_install_name_conflict(service, mock_adapter, tmp_workspace):
    # 预先创建同名 skill
    existing = tmp_workspace / "skills" / "test-skill"
    existing.mkdir(parents=True)
    (existing / "SKILL.md").write_text("---\nname: test-skill\ndescription: Old\n---\nOld body")
    service._registry.load_skills({})

    result = await service.install("mock", "test-skill")
    assert result["ok"] is False
    assert result["code"] == "NAME_CONFLICT"


@pytest.mark.asyncio
async def test_uninstall_success(service, mock_adapter, tmp_workspace):
    # 先安装
    async def fake_download(skill_id, target_dir):
        skill_dir = target_dir / skill_id
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\nname: test-skill\ndescription: Test\n---\nBody")
        return skill_dir

    mock_adapter.download = AsyncMock(side_effect=fake_download)
    await service.install("mock", "test-skill")

    result = await service.uninstall("test-skill")
    assert result["ok"] is True
    assert not (tmp_workspace / "skills" / "test-skill").exists()
    assert service._registry.get("test-skill") is None


@pytest.mark.asyncio
async def test_uninstall_local_skill_denied(service, tmp_workspace):
    # 本地 skill（无 .install.json）
    skill_dir = tmp_workspace / "skills" / "local-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: local-skill\ndescription: Local\n---\nBody")
    service._registry.load_skills({})

    result = await service.uninstall("local-skill")
    assert result["ok"] is False
    assert result["code"] == "PERMISSION_DENIED"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python3 -m pytest tests/test_market_service.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 实现 SkillMarketService**

```python
# backend/app/skills/market_service.py
"""Skill 市场管理核心服务"""
from __future__ import annotations

import asyncio
import json
import shutil
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.skills.models import SearchResult, SkillDetail, UpdateInfo
from app.skills.registry import SkillRegistry
from app.skills.adapters.base import MarketAdapter
from app.skills.adapters.clawhub import ClawHubAdapter
from app.skills.adapters.anthropic_market import AnthropicAdapter
from app.skills.adapters.git_adapter import GitAdapter

logger = logging.getLogger(__name__)


class SkillMarketService:
    def __init__(
        self,
        skills_dir: Path,
        skill_registry: SkillRegistry,
        config: dict[str, Any],
    ):
        self._skills_dir = skills_dir
        self._registry = skill_registry
        self._config = config
        self._locks: dict[str, asyncio.Lock] = {}

        # 初始化 adapters
        self._adapters: dict[str, MarketAdapter] = {
            "clawhub": ClawHubAdapter(
                api_base=config.get("skills", {}).get("clawhub_api_base", "https://api.clawhub.ai/v1"),
            ),
            "anthropic": AnthropicAdapter(
                api_base=config.get("skills", {}).get("anthropic_market_api_base", "https://marketplace.claude.com/api/v1"),
            ),
            "git": GitAdapter(),
        }

    def _get_lock(self, name: str) -> asyncio.Lock:
        if name not in self._locks:
            self._locks[name] = asyncio.Lock()
        return self._locks[name]

    def _get_adapter(self, source: str) -> MarketAdapter:
        adapter = self._adapters.get(source)
        if not adapter:
            raise ValueError(f"未知来源: {source}")
        return adapter

    # --- 搜索 ---

    async def search(self, source: str, query: str, page: int = 1, page_size: int = 20) -> SearchResult:
        adapter = self._get_adapter(source)
        return await adapter.search(query, page, page_size)

    async def get_detail(self, source: str, skill_id: str) -> SkillDetail:
        adapter = self._get_adapter(source)
        detail = await adapter.get_detail(skill_id)
        # 检查是否已安装
        detail.installed = self._registry.get(detail.name) is not None
        return detail

    # --- 安装 ---

    async def install(self, source: str, skill_id: str, repo_url: str | None = None) -> dict:
        actual_id = repo_url if source == "git" else skill_id
        if not actual_id:
            return {"ok": False, "error": "缺少 skill_id 或 repo_url", "code": "INSTALL_FAILED"}

        lock = self._get_lock(actual_id)
        async with lock:
            try:
                adapter = self._get_adapter(source)

                # 下载到 skills 目录
                self._skills_dir.mkdir(parents=True, exist_ok=True)
                skill_path = await adapter.download(actual_id, self._skills_dir)

                # 验证 SKILL.md 存在
                skill_md = skill_path / "SKILL.md"
                if not skill_md.exists():
                    shutil.rmtree(skill_path, ignore_errors=True)
                    return {"ok": False, "error": "下载的内容不包含有效 SKILL.md", "code": "INVALID_SKILL"}

                # 解析并检查名称冲突
                parsed = self._registry.parse_skill(skill_md)
                if not parsed:
                    shutil.rmtree(skill_path, ignore_errors=True)
                    return {"ok": False, "error": "SKILL.md 格式无效", "code": "INVALID_SKILL"}

                if self._registry.get(parsed.name):
                    shutil.rmtree(skill_path, ignore_errors=True)
                    return {
                        "ok": False,
                        "error": f"Skill '{parsed.name}' already installed",
                        "code": "NAME_CONFLICT",
                    }

                # 写入 .install.json
                install_info = {
                    "source": source,
                    "source_id": skill_id or "",
                    "version": parsed.version or "0.0.0",
                    "installed_at": datetime.now(timezone.utc).isoformat(),
                    "repo_url": repo_url,
                    "checksum": "",  # v1 暂不计算
                }
                (skill_path / ".install.json").write_text(
                    json.dumps(install_info, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

                # 注册到 registry
                self._registry.register(parsed)
                logger.info("Skill '%s' 安装成功 (source=%s)", parsed.name, source)

                return {"ok": True, "skill_name": parsed.name}

            except FileExistsError:
                return {"ok": False, "error": f"Skill 目录已存在", "code": "NAME_CONFLICT"}
            except Exception as e:
                logger.error("安装 skill 失败: %s", e, exc_info=True)
                return {"ok": False, "error": str(e), "code": "INSTALL_FAILED"}

    # --- 卸载 ---

    async def uninstall(self, skill_name: str) -> dict:
        lock = self._get_lock(skill_name)
        async with lock:
            skill = self._registry.get(skill_name)
            if not skill:
                return {"ok": False, "error": f"Skill '{skill_name}' not found", "code": "NOT_FOUND"}

            # 不允许卸载 local skill
            if skill.source == "local":
                return {"ok": False, "error": "Cannot uninstall local skill", "code": "PERMISSION_DENIED"}

            # 删除目录
            if skill.path.exists():
                shutil.rmtree(skill.path)

            # 从 registry 移除
            self._registry.unregister(skill_name)
            logger.info("Skill '%s' 已卸载", skill_name)
            return {"ok": True}

    # --- 更新检测 ---

    async def check_updates(self) -> list[dict]:
        updates = []
        for skill in self._registry.get_all():
            info = skill.install_info
            if not info:
                continue
            source = info.get("source")
            source_id = info.get("source_id")
            version = info.get("version")
            if not source or not source_id or not version:
                continue
            try:
                adapter = self._get_adapter(source)
                update = await adapter.check_update(source_id, version)
                if update:
                    updates.append({
                        "skill_name": skill.name,
                        "current_version": update.current_version,
                        "latest_version": update.latest_version,
                    })
            except Exception:
                logger.warning("检查 %s 更新失败", skill.name, exc_info=True)
        return updates

    # --- 更新 ---

    async def update(self, skill_name: str) -> dict:
        lock = self._get_lock(skill_name)
        async with lock:
            skill = self._registry.get(skill_name)
            if not skill:
                return {"ok": False, "error": f"Skill '{skill_name}' not found", "code": "NOT_FOUND"}

            info = skill.install_info
            if not info:
                return {"ok": False, "error": "Local skill cannot be updated", "code": "PERMISSION_DENIED"}

            old_version = info.get("version", "unknown")
            source = info["source"]
            source_id = info["source_id"]

            try:
                adapter = self._get_adapter(source)

                # 备份旧目录
                backup_path = skill.path.with_suffix(".bak")
                if backup_path.exists():
                    shutil.rmtree(backup_path)
                skill.path.rename(backup_path)

                try:
                    # 下载新版本
                    new_path = await adapter.download(source_id, self._skills_dir)

                    # 写入 .install.json
                    new_skill_md = new_path / "SKILL.md"
                    parsed = self._registry.parse_skill(new_skill_md)
                    new_version = "unknown"
                    if parsed:
                        # 尝试从市场获取版本号
                        try:
                            detail = await adapter.get_detail(source_id)
                            new_version = detail.version or new_version
                        except Exception:
                            pass

                    install_info = {
                        **info,
                        "version": new_version,
                        "installed_at": datetime.now(timezone.utc).isoformat(),
                    }
                    (new_path / ".install.json").write_text(
                        json.dumps(install_info, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )

                    # 重新注册
                    self._registry.reload_skill(skill_name, self._config)

                    # 删除备份
                    shutil.rmtree(backup_path, ignore_errors=True)

                    return {"ok": True, "old_version": old_version, "new_version": new_version}

                except Exception:
                    # 恢复备份
                    if new_path.exists():
                        shutil.rmtree(new_path, ignore_errors=True)
                    backup_path.rename(skill.path)
                    raise

            except Exception as e:
                logger.error("更新 skill '%s' 失败: %s", skill_name, e, exc_info=True)
                return {"ok": False, "error": str(e), "code": "INSTALL_FAILED"}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python3 -m pytest tests/test_market_service.py -v`
Expected: 全部 passed

- [ ] **Step 5: 提交**

```bash
git add backend/app/skills/market_service.py backend/tests/test_market_service.py
git commit -m "feat(skills): add SkillMarketService with install/uninstall/update"
```

---

## Chunk 3: 后端 API 端点 + main.py 集成

### Task 9: 扩展 Skills API

**Files:**
- Modify: `backend/app/api/skills.py`
- Test: `backend/tests/test_skill_api.py`

- [ ] **Step 1: 编写 API 端点测试**

```python
# backend/tests/test_skill_api.py
"""Skills API 端点单测（使用 TestClient + mock service）"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.skills import router
from app.skills.models import SearchResult, SkillSearchItem
from app.skills.registry import Skill, SkillRegistry


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(router)

    # mock skill_registry
    mock_skill = MagicMock(spec=Skill)
    mock_skill.name = "test-skill"
    mock_skill.description = "Test skill"
    mock_skill.path = "/fake/path"
    mock_skill.source = "local"
    mock_skill.version = None
    mock_skill.install_info = None

    registry = MagicMock(spec=SkillRegistry)
    registry.get_all.return_value = [mock_skill]
    registry.get.return_value = mock_skill
    registry.is_enabled.return_value = True

    app.state.skill_registry = registry
    app.state.config = MagicMock()
    app.state.config.data = {}

    # mock market_service
    market_service = AsyncMock()
    market_service.search.return_value = SearchResult(
        source="clawhub", total=1, page=1, page_size=20,
        items=[SkillSearchItem(id="x", name="x", description="X", source="clawhub")],
    )
    market_service.install.return_value = {"ok": True, "skill_name": "x"}
    market_service.uninstall.return_value = {"ok": True}
    market_service.check_updates.return_value = []
    market_service.update.return_value = {"ok": True, "old_version": "1.0", "new_version": "1.1"}

    app.state.market_service = market_service
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def test_list_skills(client):
    resp = client.get("/api/skills")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "test-skill"
    assert "source" in data[0]
    assert "enabled" in data[0]


def test_market_search(client):
    resp = client.get("/api/skills/market/search?source=clawhub&q=test")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1


def test_install(client):
    resp = client.post("/api/skills/install", json={"source": "clawhub", "id": "x"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_uninstall(client):
    resp = client.delete("/api/skills/test-skill")
    assert resp.status_code == 200


def test_toggle_enabled(client):
    resp = client.patch("/api/skills/test-skill", json={"enabled": False})
    assert resp.status_code == 200


def test_check_updates(client):
    resp = client.post("/api/skills/check-updates")
    assert resp.status_code == 200
    assert "updates" in resp.json()


def test_update_skill(client):
    resp = client.post("/api/skills/test-skill/update")
    assert resp.status_code == 200
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python3 -m pytest tests/test_skill_api.py -v`
Expected: FAIL — 端点不存在

- [ ] **Step 3: 重写 skills API**

```python
# backend/app/api/skills.py
"""Skills API — 列表、市场搜索、安装/卸载/更新、启用/禁用、斜杠命令调用"""
from __future__ import annotations

import uuid
import time
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from app.skills.models import InstallRequest, SkillInvokeRequest
from app.skills.arg_substitutor import substitute_arguments
from app.events.types import USER_INPUT
from app.events.envelope import EventEnvelope

router = APIRouter(prefix="/api/skills", tags=["skills"])


# --- 已安装 Skills ---

@router.get("")
async def list_skills(request: Request):
    """获取所有已加载的 Skills（扩展版，含 source/version/update 信息）"""
    skill_registry = request.app.state.skill_registry
    market_service = request.app.state.market_service
    skills = []
    for skill in skill_registry.get_all():
        info = skill.install_info
        # 判断 category
        if info:
            category = "installed"
        elif skill.source == "local":
            category = "local"
        else:
            category = "builtin"

        skills.append({
            "id": f"skill-{skill.name}",
            "name": skill.name,
            "description": skill.description or "",
            "category": category,
            "enabled": skill_registry.is_enabled(skill.name),
            "path": str(skill.path),
            "source": skill.source,
            "version": skill.version,
            "has_update": False,
            "update_version": None,
        })
    return skills


# --- 启用/禁用 ---

class ToggleRequest(BaseModel):
    enabled: bool

@router.patch("/{skill_name}")
async def toggle_skill(skill_name: str, body: ToggleRequest, request: Request):
    """启用/禁用 skill"""
    registry = request.app.state.skill_registry
    registry.set_enabled(skill_name, body.enabled)
    # 如果重新启用，需要重新加载
    if body.enabled:
        config = request.app.state.config.data if hasattr(request.app.state.config, 'data') else {}
        registry.load_skills(config)
    return {"ok": True, "skill_name": skill_name, "enabled": body.enabled}


# --- 卸载 ---

@router.delete("/{skill_name}")
async def uninstall_skill(skill_name: str, request: Request):
    """卸载已安装的 skill"""
    market_service = request.app.state.market_service
    result = await market_service.uninstall(skill_name)
    if not result.get("ok"):
        status = 403 if result.get("code") == "PERMISSION_DENIED" else 404
        raise HTTPException(status_code=status, detail=result)
    return result


# --- 更新 ---

@router.post("/{skill_name}/update")
async def update_skill(skill_name: str, request: Request):
    """更新已安装的 skill"""
    market_service = request.app.state.market_service
    result = await market_service.update(skill_name)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result)
    return result


# --- 市场搜索 ---

@router.get("/market/search")
async def market_search(source: str, q: str, page: int = 1, page_size: int = 20, request: Request):
    """搜索市场 skills"""
    market_service = request.app.state.market_service
    try:
        result = await market_service.search(source, q, page, page_size)
        return result.model_dump()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail={"error": str(e), "code": "NETWORK_ERROR"})


@router.get("/market/detail")
async def market_detail(source: str, id: str, request: Request):
    """获取市场 skill 详情"""
    market_service = request.app.state.market_service
    try:
        detail = await market_service.get_detail(source, id)
        return detail.model_dump()
    except Exception as e:
        raise HTTPException(status_code=502, detail={"error": str(e), "code": "NETWORK_ERROR"})


# --- 安装 ---

@router.post("/install")
async def install_skill(body: InstallRequest, request: Request):
    """从市场安装 skill"""
    market_service = request.app.state.market_service
    result = await market_service.install(
        source=body.source,
        skill_id=body.id or "",
        repo_url=body.repo_url,
    )
    if not result.get("ok"):
        code = result.get("code", "INSTALL_FAILED")
        status = 409 if code == "NAME_CONFLICT" else 400
        raise HTTPException(status_code=status, detail=result)
    return result


# --- 检查更新 ---

@router.post("/check-updates")
async def check_updates(request: Request):
    """检查所有已安装 skill 的更新"""
    market_service = request.app.state.market_service
    updates = await market_service.check_updates()
    return {"updates": updates}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python3 -m pytest tests/test_skill_api.py -v`
Expected: 全部 passed

- [ ] **Step 5: 提交**

```bash
git add backend/app/api/skills.py backend/tests/test_skill_api.py
git commit -m "feat(skills): expand Skills API with CRUD, market search, install/uninstall"
```

---

### Task 10: Skill Invoke API（斜杠命令）

**Files:**
- Modify: `backend/app/api/skills.py` (追加 skill-invoke 端点)

- [ ] **Step 1: 在 skills.py 末尾追加 invoke 端点**

在 `backend/app/api/skills.py` 文件末尾追加：

```python
# --- 斜杠命令调用 ---

# 注意：此端点挂在 sessions 路径下，需要单独的 router
invoke_router = APIRouter(prefix="/api/sessions", tags=["skills"])

@invoke_router.post("/{session_id}/skill-invoke")
async def invoke_skill(session_id: str, body: SkillInvokeRequest, request: Request):
    """用户显式调用 skill（斜杠命令）"""
    registry = request.app.state.skill_registry
    skill = registry.get(body.skill_name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{body.skill_name}' not found")

    # 参数替换
    rendered = substitute_arguments(skill.body, body.arguments)

    # 发布 user.input 事件
    services = request.app.state.services
    event = EventEnvelope(
        event_id=str(uuid.uuid4()),
        type=USER_INPUT,
        ts=time.time(),
        session_id=session_id,
        source="api",
        payload={
            "content": rendered,
            "type": "skill_invoke",
            "skill_name": body.skill_name,
            "original_input": f"/{body.skill_name} {body.arguments}".strip(),
        },
    )
    await services.publisher.publish(event)
    return {"ok": True, "session_id": session_id, "skill_name": body.skill_name}
```

- [ ] **Step 2: 提交**

```bash
git add backend/app/api/skills.py
git commit -m "feat(skills): add skill-invoke endpoint for slash commands"
```

---

### Task 11: main.py 集成

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: 在 main.py 中初始化 SkillMarketService 并注册 invoke_router**

在 `backend/app/main.py` 的 `lifespan()` 函数中，在 SkillRegistry 初始化之后追加：

```python
    # 初始化 SkillMarketService
    from app.skills.market_service import SkillMarketService
    market_service = SkillMarketService(
        skills_dir=skills_dir,
        skill_registry=skill_registry,
        config=config.data,
    )
    app.state.market_service = market_service
```

在 `lifespan()` 之后注册 `skills_state.json` 路径到 SkillRegistry：

修改 SkillRegistry 初始化行：

```python
    # 原来:
    # skill_registry = SkillRegistry(workspace_dir=skills_dir)
    # 改为:
    state_file = Path(config.get("system.workspace_dir", ".")) / "skills_state.json"
    skill_registry = SkillRegistry(workspace_dir=skills_dir, state_file=state_file)
```

在 `main.py` 约 219 行 `app.include_router(skills.router)` 之后追加：

```python
from app.api.skills import invoke_router
app.include_router(invoke_router)
```

- [ ] **Step 2: 验证后端启动**

Run: `cd backend && python3 main.py`
Expected: 无报错启动，日志中可见 skill 加载信息

- [ ] **Step 3: 提交**

```bash
git add backend/app/main.py
git commit -m "feat(skills): integrate SkillMarketService into app lifecycle"
```

---

## Chunk 4: 前端 — Skills 管理页面

### Task 12: SkillCard 复用组件

**Files:**
- Create: `frontend/app/skills/components/SkillCard.tsx`

- [ ] **Step 1: 实现 SkillCard**

```tsx
// frontend/app/skills/components/SkillCard.tsx
'use client';

interface SkillCardProps {
  name: string;
  description: string;
  source?: string;
  version?: string | null;
  enabled?: boolean;
  hasUpdate?: boolean;
  downloads?: number | null;
  author?: string | null;
  installed?: boolean;
  onToggle?: (enabled: boolean) => void;
  onUninstall?: () => void;
  onUpdate?: () => void;
  onInstall?: () => void;
  onClick?: () => void;
}

const sourceColors: Record<string, string> = {
  clawhub: 'bg-purple-600',
  anthropic: 'bg-orange-600',
  git: 'bg-gray-600',
  local: 'bg-blue-600',
  builtin: 'bg-green-600',
};

export function SkillCard({
  name, description, source, version, enabled, hasUpdate,
  downloads, author, installed,
  onToggle, onUninstall, onUpdate, onInstall, onClick,
}: SkillCardProps) {
  return (
    <div
      className="bg-[#252526] border border-[#2d2d30] rounded p-3 hover:border-[#3e3e42] transition-colors cursor-pointer"
      onClick={onClick}
    >
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[#cccccc] font-medium truncate">{name}</span>
            {source && (
              <span className={`text-[10px] text-white px-1.5 py-0.5 rounded ${sourceColors[source] || 'bg-gray-600'}`}>
                {source}
              </span>
            )}
            {version && (
              <span className="text-[10px] text-[#858585]">v{version}</span>
            )}
          </div>
          <p className="text-sm text-[#858585] line-clamp-2">{description}</p>
          {(author || downloads != null) && (
            <div className="flex items-center gap-3 mt-1 text-xs text-[#6b6b6b]">
              {author && <span>by {author}</span>}
              {downloads != null && <span>{downloads.toLocaleString()} downloads</span>}
            </div>
          )}
        </div>
        <div className="flex items-center gap-2 flex-shrink-0" onClick={e => e.stopPropagation()}>
          {/* 已安装页：启用/禁用 */}
          {onToggle && (
            <button
              className={`text-xs px-2 py-1 rounded ${enabled ? 'bg-green-700 text-green-100' : 'bg-[#3c3c3c] text-[#858585]'}`}
              onClick={() => onToggle(!enabled)}
            >
              {enabled ? '启用' : '禁用'}
            </button>
          )}
          {/* 有更新 */}
          {hasUpdate && onUpdate && (
            <button
              className="text-xs px-2 py-1 rounded bg-[#0e639c] text-white hover:bg-[#1177bb]"
              onClick={onUpdate}
            >
              更新
            </button>
          )}
          {/* 卸载 */}
          {onUninstall && source !== 'local' && source !== 'builtin' && (
            <button
              className="text-xs px-2 py-1 rounded bg-[#3c3c3c] text-[#858585] hover:bg-red-800 hover:text-red-100"
              onClick={onUninstall}
            >
              卸载
            </button>
          )}
          {/* 市场页：安装 */}
          {onInstall && !installed && (
            <button
              className="text-xs px-2 py-1 rounded bg-[#0e639c] text-white hover:bg-[#1177bb]"
              onClick={onInstall}
            >
              安装
            </button>
          )}
          {installed && (
            <span className="text-xs text-green-400">已安装</span>
          )}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 提交**

```bash
git add frontend/app/skills/components/SkillCard.tsx
git commit -m "feat(frontend): add SkillCard reusable component"
```

---

### Task 13: SkillDetailModal 详情弹窗

**Files:**
- Create: `frontend/app/skills/components/SkillDetailModal.tsx`

- [ ] **Step 1: 实现详情弹窗**

```tsx
// frontend/app/skills/components/SkillDetailModal.tsx
'use client';

import { useEffect, useState } from 'react';
import { X, FileText, Folder } from 'lucide-react';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface SkillDetailModalProps {
  source: string;
  skillId: string;
  onClose: () => void;
  onInstall?: () => void;
  onUninstall?: () => void;
  installed?: boolean;
}

interface DetailData {
  name: string;
  description: string;
  version?: string;
  author?: string;
  skill_md_preview: string;
  files: string[];
  installed: boolean;
}

export function SkillDetailModal({
  source, skillId, onClose, onInstall, onUninstall, installed,
}: SkillDetailModalProps) {
  const [detail, setDetail] = useState<DetailData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API_BASE}/api/skills/market/detail?source=${source}&id=${encodeURIComponent(skillId)}`)
      .then(r => r.json())
      .then(setDetail)
      .catch(() => setDetail(null))
      .finally(() => setLoading(false));
  }, [source, skillId]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div
        className="bg-[#1e1e1e] border border-[#2d2d30] rounded-lg w-[640px] max-h-[80vh] flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-[#2d2d30]">
          <div>
            <h2 className="text-lg font-semibold text-[#cccccc]">{detail?.name || skillId}</h2>
            <div className="flex items-center gap-2 mt-1 text-xs text-[#858585]">
              {detail?.author && <span>by {detail.author}</span>}
              {detail?.version && <span>v{detail.version}</span>}
              <span className="text-[10px] bg-purple-600 text-white px-1.5 py-0.5 rounded">{source}</span>
            </div>
          </div>
          <button onClick={onClose} className="text-[#858585] hover:text-[#cccccc]">
            <X size={20} />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-auto p-4 space-y-4">
          {loading ? (
            <div className="text-center text-[#858585] py-8">加载中...</div>
          ) : detail ? (
            <>
              <p className="text-sm text-[#cccccc]">{detail.description}</p>

              {/* SKILL.md 预览 */}
              <div>
                <h3 className="text-sm font-medium text-[#858585] mb-2 flex items-center gap-1">
                  <FileText size={14} /> SKILL.md
                </h3>
                <pre className="bg-[#252526] rounded p-3 text-xs text-[#cccccc] overflow-auto max-h-60 whitespace-pre-wrap">
                  {detail.skill_md_preview}
                </pre>
              </div>

              {/* 文件列表 */}
              {detail.files.length > 0 && (
                <div>
                  <h3 className="text-sm font-medium text-[#858585] mb-2 flex items-center gap-1">
                    <Folder size={14} /> 文件列表
                  </h3>
                  <div className="bg-[#252526] rounded p-2 text-xs text-[#858585] space-y-1">
                    {detail.files.map(f => <div key={f}>{f}</div>)}
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="text-center text-red-400 py-8">加载失败</div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-2 p-4 border-t border-[#2d2d30]">
          {onInstall && !installed && (
            <button
              className="px-4 py-2 text-sm rounded bg-[#0e639c] text-white hover:bg-[#1177bb]"
              onClick={onInstall}
            >
              安装
            </button>
          )}
          {onUninstall && installed && (
            <button
              className="px-4 py-2 text-sm rounded bg-red-800 text-white hover:bg-red-700"
              onClick={onUninstall}
            >
              卸载
            </button>
          )}
          <button
            className="px-4 py-2 text-sm rounded bg-[#3c3c3c] text-[#cccccc] hover:bg-[#4c4c4c]"
            onClick={onClose}
          >
            关闭
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 提交**

```bash
git add frontend/app/skills/components/SkillDetailModal.tsx
git commit -m "feat(frontend): add SkillDetailModal component"
```

---

### Task 14: InstalledTab 组件

**Files:**
- Create: `frontend/app/skills/components/InstalledTab.tsx`

- [ ] **Step 1: 实现已安装 Tab**

```tsx
// frontend/app/skills/components/InstalledTab.tsx
'use client';

import { useState, useEffect, useCallback } from 'react';
import { Search, Loader2 } from 'lucide-react';
import { SkillCard } from './SkillCard';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface InstalledSkill {
  id: string;
  name: string;
  description: string;
  category: string;
  enabled: boolean;
  source: string;
  version: string | null;
  has_update: boolean;
  update_version: string | null;
}

export function InstalledTab() {
  const [skills, setSkills] = useState<InstalledSkill[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');

  const fetchSkills = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/skills`);
      const data = await res.json();
      setSkills(data);
    } catch {
      setSkills([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchSkills(); }, [fetchSkills]);

  // 检查更新
  useEffect(() => {
    fetch(`${API_BASE}/api/skills/check-updates`, { method: 'POST' })
      .then(r => r.json())
      .then(data => {
        const updateMap = new Map(
          (data.updates || []).map((u: any) => [u.skill_name, u.latest_version])
        );
        setSkills(prev => prev.map(s => ({
          ...s,
          has_update: updateMap.has(s.name),
          update_version: (updateMap.get(s.name) as string) || null,
        })));
      })
      .catch(() => {});
  }, []);

  const handleToggle = async (name: string, enabled: boolean) => {
    await fetch(`${API_BASE}/api/skills/${name}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled }),
    });
    fetchSkills();
  };

  const handleUninstall = async (name: string) => {
    if (!confirm(`确定卸载 ${name}？`)) return;
    await fetch(`${API_BASE}/api/skills/${name}`, { method: 'DELETE' });
    fetchSkills();
  };

  const handleUpdate = async (name: string) => {
    await fetch(`${API_BASE}/api/skills/${name}/update`, { method: 'POST' });
    fetchSkills();
  };

  const filtered = skills.filter(s =>
    s.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    s.description.toLowerCase().includes(searchTerm.toLowerCase())
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="animate-spin text-[#858585]" size={32} />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* 搜索 + 统计 */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-[#858585]" size={16} />
          <input
            className="w-full bg-[#3c3c3c] border border-[#2d2d30] rounded pl-9 pr-3 py-2 text-sm text-[#cccccc] placeholder-[#858585] focus:border-[#007acc] focus:outline-none"
            placeholder="搜索已安装的 skills..."
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
          />
        </div>
        <span className="text-sm text-[#858585]">
          共 {skills.length} 个 / 启用 {skills.filter(s => s.enabled).length} 个
        </span>
      </div>

      {/* 列表 */}
      <div className="space-y-2">
        {filtered.length === 0 ? (
          <div className="text-center text-[#858585] py-8">无匹配结果</div>
        ) : (
          filtered.map(skill => (
            <SkillCard
              key={skill.id}
              name={skill.name}
              description={skill.description}
              source={skill.source}
              version={skill.version}
              enabled={skill.enabled}
              hasUpdate={skill.has_update}
              onToggle={enabled => handleToggle(skill.name, enabled)}
              onUninstall={() => handleUninstall(skill.name)}
              onUpdate={() => handleUpdate(skill.name)}
            />
          ))
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 提交**

```bash
git add frontend/app/skills/components/InstalledTab.tsx
git commit -m "feat(frontend): add InstalledTab component"
```

---

### Task 15: MarketTab 组件

**Files:**
- Create: `frontend/app/skills/components/MarketTab.tsx`

- [ ] **Step 1: 实现市场浏览 Tab**

```tsx
// frontend/app/skills/components/MarketTab.tsx
'use client';

import { useState, useCallback } from 'react';
import { Search, Loader2, GitBranch } from 'lucide-react';
import { SkillCard } from './SkillCard';
import { SkillDetailModal } from './SkillDetailModal';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface MarketSkill {
  id: string;
  name: string;
  description: string;
  author: string | null;
  version: string | null;
  downloads: number | null;
  source: string;
}

const SOURCES = ['clawhub', 'anthropic'] as const;

export function MarketTab({ onInstalled }: { onInstalled: () => void }) {
  const [activeSource, setActiveSource] = useState<string>('clawhub');
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<MarketSkill[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [gitUrl, setGitUrl] = useState('');
  const [gitInstalling, setGitInstalling] = useState(false);
  const [detailModal, setDetailModal] = useState<{ source: string; id: string } | null>(null);

  const doSearch = useCallback(async (src: string, q: string, p: number) => {
    if (!q.trim()) return;
    setLoading(true);
    try {
      const res = await fetch(
        `${API_BASE}/api/skills/market/search?source=${src}&q=${encodeURIComponent(q)}&page=${p}&page_size=20`
      );
      const data = await res.json();
      setResults(data.items || []);
      setTotal(data.total || 0);
      setPage(p);
    } catch {
      setResults([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleInstall = async (source: string, id: string) => {
    const res = await fetch(`${API_BASE}/api/skills/install`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source, id }),
    });
    if (res.ok) {
      alert('安装成功');
      onInstalled();
      doSearch(activeSource, query, page); // 刷新状态
    } else {
      const err = await res.json();
      alert(`安装失败: ${err?.detail?.error || '未知错误'}`);
    }
  };

  const handleGitInstall = async () => {
    if (!gitUrl.trim()) return;
    setGitInstalling(true);
    try {
      const res = await fetch(`${API_BASE}/api/skills/install`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source: 'git', repo_url: gitUrl }),
      });
      if (res.ok) {
        alert('安装成功');
        setGitUrl('');
        onInstalled();
      } else {
        const err = await res.json();
        alert(`安装失败: ${err?.detail?.error || '未知错误'}`);
      }
    } finally {
      setGitInstalling(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* 来源切换 */}
      <div className="flex gap-1 bg-[#252526] rounded p-1">
        {SOURCES.map(src => (
          <button
            key={src}
            className={`px-3 py-1.5 text-sm rounded transition-colors ${
              activeSource === src
                ? 'bg-[#0e639c] text-white'
                : 'text-[#858585] hover:text-[#cccccc]'
            }`}
            onClick={() => { setActiveSource(src); setResults([]); }}
          >
            {src === 'clawhub' ? 'ClawHub' : 'Anthropic'}
          </button>
        ))}
        <button
          className={`px-3 py-1.5 text-sm rounded transition-colors flex items-center gap-1 ${
            activeSource === 'git'
              ? 'bg-[#0e639c] text-white'
              : 'text-[#858585] hover:text-[#cccccc]'
          }`}
          onClick={() => { setActiveSource('git'); setResults([]); }}
        >
          <GitBranch size={14} /> Git URL
        </button>
      </div>

      {/* Git URL 输入 */}
      {activeSource === 'git' ? (
        <div className="flex items-center gap-2">
          <input
            className="flex-1 bg-[#3c3c3c] border border-[#2d2d30] rounded px-3 py-2 text-sm text-[#cccccc] placeholder-[#858585] focus:border-[#007acc] focus:outline-none"
            placeholder="https://github.com/user/skill-repo"
            value={gitUrl}
            onChange={e => setGitUrl(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleGitInstall()}
          />
          <button
            className="px-4 py-2 text-sm rounded bg-[#0e639c] text-white hover:bg-[#1177bb] disabled:opacity-50"
            onClick={handleGitInstall}
            disabled={gitInstalling || !gitUrl.trim()}
          >
            {gitInstalling ? '安装中...' : '安装'}
          </button>
        </div>
      ) : (
        <>
          {/* 搜索框 */}
          <div className="flex items-center gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-[#858585]" size={16} />
              <input
                className="w-full bg-[#3c3c3c] border border-[#2d2d30] rounded pl-9 pr-3 py-2 text-sm text-[#cccccc] placeholder-[#858585] focus:border-[#007acc] focus:outline-none"
                placeholder={`在 ${activeSource === 'clawhub' ? 'ClawHub' : 'Anthropic'} 搜索 skills...`}
                value={query}
                onChange={e => setQuery(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && doSearch(activeSource, query, 1)}
              />
            </div>
            <button
              className="px-4 py-2 text-sm rounded bg-[#0e639c] text-white hover:bg-[#1177bb]"
              onClick={() => doSearch(activeSource, query, 1)}
            >
              搜索
            </button>
          </div>

          {/* 结果 */}
          {loading ? (
            <div className="flex items-center justify-center h-32">
              <Loader2 className="animate-spin text-[#858585]" size={24} />
            </div>
          ) : results.length > 0 ? (
            <div className="space-y-2">
              <div className="text-xs text-[#858585]">共 {total} 个结果</div>
              {results.map(skill => (
                <SkillCard
                  key={skill.id}
                  name={skill.name}
                  description={skill.description}
                  source={skill.source}
                  version={skill.version}
                  downloads={skill.downloads}
                  author={skill.author}
                  onInstall={() => handleInstall(skill.source, skill.id)}
                  onClick={() => setDetailModal({ source: skill.source, id: skill.id })}
                />
              ))}
              {/* 分页 */}
              {total > 20 && (
                <div className="flex justify-center gap-2 pt-2">
                  <button
                    className="px-3 py-1 text-xs rounded bg-[#3c3c3c] text-[#cccccc] disabled:opacity-30"
                    disabled={page <= 1}
                    onClick={() => doSearch(activeSource, query, page - 1)}
                  >
                    上一页
                  </button>
                  <span className="text-xs text-[#858585] py-1">第 {page} 页</span>
                  <button
                    className="px-3 py-1 text-xs rounded bg-[#3c3c3c] text-[#cccccc] disabled:opacity-30"
                    disabled={page * 20 >= total}
                    onClick={() => doSearch(activeSource, query, page + 1)}
                  >
                    下一页
                  </button>
                </div>
              )}
            </div>
          ) : query ? (
            <div className="text-center text-[#858585] py-8">无搜索结果，请尝试其他关键词</div>
          ) : (
            <div className="text-center text-[#858585] py-8">输入关键词搜索 skills</div>
          )}
        </>
      )}

      {/* 详情弹窗 */}
      {detailModal && (
        <SkillDetailModal
          source={detailModal.source}
          skillId={detailModal.id}
          onClose={() => setDetailModal(null)}
          onInstall={() => {
            handleInstall(detailModal.source, detailModal.id);
            setDetailModal(null);
          }}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 2: 提交**

```bash
git add frontend/app/skills/components/MarketTab.tsx
git commit -m "feat(frontend): add MarketTab component with search and install"
```

---

### Task 16: 改造 Skills 主页面为 Tab 式

**Files:**
- Modify: `frontend/app/skills/page.tsx`

- [ ] **Step 1: 重写 skills/page.tsx**

```tsx
// frontend/app/skills/page.tsx
'use client';

import { useState, useCallback } from 'react';
import { Sparkles, Package } from 'lucide-react';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { InstalledTab } from './components/InstalledTab';
import { MarketTab } from './components/MarketTab';

type Tab = 'installed' | 'market';

export default function SkillsPage() {
  const [activeTab, setActiveTab] = useState<Tab>('installed');
  const [refreshKey, setRefreshKey] = useState(0);

  const handleInstalled = useCallback(() => {
    // 安装成功后刷新已安装列表
    setRefreshKey(k => k + 1);
  }, []);

  return (
    <DashboardLayout>
      <div className="h-full flex flex-col">
        {/* Header */}
        <div className="bg-[#252526] border-b border-[#2d2d30] p-4">
          <h1 className="text-xl font-semibold text-[#cccccc] mb-3">Skills 管理</h1>
          <div className="flex gap-1">
            <button
              className={`flex items-center gap-1.5 px-3 py-1.5 text-sm rounded transition-colors ${
                activeTab === 'installed'
                  ? 'bg-[#0e639c] text-white'
                  : 'text-[#858585] hover:text-[#cccccc] hover:bg-[#3c3c3c]'
              }`}
              onClick={() => setActiveTab('installed')}
            >
              <Sparkles size={14} /> 已安装
            </button>
            <button
              className={`flex items-center gap-1.5 px-3 py-1.5 text-sm rounded transition-colors ${
                activeTab === 'market'
                  ? 'bg-[#0e639c] text-white'
                  : 'text-[#858585] hover:text-[#cccccc] hover:bg-[#3c3c3c]'
              }`}
              onClick={() => setActiveTab('market')}
            >
              <Package size={14} /> 市场浏览
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto p-4">
          {activeTab === 'installed' ? (
            <InstalledTab key={refreshKey} />
          ) : (
            <MarketTab onInstalled={handleInstalled} />
          )}
        </div>
      </div>
    </DashboardLayout>
  );
}
```

- [ ] **Step 2: 验证前端编译**

Run: `cd frontend && npm run build`
Expected: 编译通过，无类型错误

- [ ] **Step 3: 提交**

```bash
git add frontend/app/skills/page.tsx
git commit -m "feat(frontend): rewrite skills page with Installed/Market tabs"
```

---

## Chunk 5: 聊天斜杠命令补全

### Task 17: SlashCommandMenu 组件

**Files:**
- Create: `frontend/components/chat/SlashCommandMenu.tsx`

- [ ] **Step 1: 实现斜杠命令补全菜单**

```tsx
// frontend/components/chat/SlashCommandMenu.tsx
'use client';

import { useState, useEffect, useRef } from 'react';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface SkillItem {
  name: string;
  description: string;
}

interface SlashCommandMenuProps {
  inputValue: string;
  onSelect: (skillName: string) => void;
  visible: boolean;
}

export function SlashCommandMenu({ inputValue, onSelect, visible }: SlashCommandMenuProps) {
  const [skills, setSkills] = useState<SkillItem[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const menuRef = useRef<HTMLDivElement>(null);

  // 加载已启用的 skills
  useEffect(() => {
    fetch(`${API_BASE}/api/skills`)
      .then(r => r.json())
      .then((data: any[]) => {
        setSkills(
          data
            .filter(s => s.enabled)
            .map(s => ({ name: s.name, description: s.description }))
        );
      })
      .catch(() => setSkills([]));
  }, []);

  // 过滤
  const query = inputValue.startsWith('/') ? inputValue.slice(1).toLowerCase() : '';
  const filtered = skills.filter(s =>
    s.name.toLowerCase().includes(query) || s.description.toLowerCase().includes(query)
  );

  // 重置选中
  useEffect(() => { setSelectedIndex(0); }, [query]);

  if (!visible || filtered.length === 0) return null;

  return (
    <div
      ref={menuRef}
      className="absolute bottom-full left-0 mb-1 w-80 max-h-48 overflow-auto bg-[#252526] border border-[#2d2d30] rounded shadow-lg z-50"
    >
      {filtered.map((skill, i) => (
        <div
          key={skill.name}
          className={`px-3 py-2 cursor-pointer ${
            i === selectedIndex ? 'bg-[#0e639c] text-white' : 'text-[#cccccc] hover:bg-[#3c3c3c]'
          }`}
          onClick={() => onSelect(skill.name)}
          onMouseEnter={() => setSelectedIndex(i)}
        >
          <div className="text-sm font-medium">/{skill.name}</div>
          <div className="text-xs opacity-70 truncate">{skill.description}</div>
        </div>
      ))}
    </div>
  );
}

/**
 * Hook: 在聊天输入框中使用斜杠命令
 * 返回 { showMenu, handleKeyDown, handleSelect }
 */
export function useSlashCommand(
  inputValue: string,
  setInputValue: (v: string) => void,
  onInvoke: (skillName: string, args: string) => void,
) {
  const showMenu = inputValue.startsWith('/') && !inputValue.includes(' ');

  const handleSelect = (skillName: string) => {
    setInputValue(`/${skillName} `);
  };

  const handleSubmit = (text: string): boolean => {
    // 检查是否是斜杠命令
    if (text.startsWith('/')) {
      const parts = text.slice(1).split(/\s+/, 2);
      const skillName = parts[0];
      const args = text.slice(1 + skillName.length).trim();
      if (skillName) {
        onInvoke(skillName, args);
        return true; // 已处理
      }
    }
    return false; // 非斜杠命令，走正常消息发送
  };

  return { showMenu, handleSelect, handleSubmit };
}
```

- [ ] **Step 2: 提交**

```bash
git add frontend/components/chat/SlashCommandMenu.tsx
git commit -m "feat(frontend): add SlashCommandMenu with useSlashCommand hook"
```

---

### Task 18: 集成斜杠命令到聊天页

**Files:**
- Modify: `frontend/app/chat/page.tsx`

- [ ] **Step 1: 在 chat/page.tsx 中集成**

在 chat/page.tsx 中需要做以下修改：

1. 导入组件和 hook：
```tsx
import { SlashCommandMenu, useSlashCommand } from '@/components/chat/SlashCommandMenu';
```

2. 在组件内部，获取 `inputValue` 和 `setInputValue` 后，添加 hook：
```tsx
const handleSkillInvoke = async (skillName: string, args: string) => {
  if (!sessionId) return;
  await fetch(`${API_BASE}/api/sessions/${sessionId}/skill-invoke`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ skill_name: skillName, arguments: args }),
  });
  setInputValue('');
};

const { showMenu, handleSelect, handleSubmit } = useSlashCommand(
  inputValue, setInputValue, handleSkillInvoke,
);
```

3. 在 `handleSend` 函数开头加入拦截：
```tsx
// 在现有 handleSend 函数开头
if (handleSubmit(inputValue)) return;
```

4. 在输入框容器中添加菜单组件（输入框外层的 `relative` 容器内）：
```tsx
<SlashCommandMenu
  inputValue={inputValue}
  onSelect={handleSelect}
  visible={showMenu}
/>
```

> 注意：chat/page.tsx 较大且可能包含复杂的状态管理。实际集成时需要找到正确的位置插入以上代码。具体变量名（如 inputValue、setInputValue、handleSend）需要与现有代码中的实际名称匹配。

- [ ] **Step 2: 验证前端编译**

Run: `cd frontend && npm run build`
Expected: 编译通过

- [ ] **Step 3: 提交**

```bash
git add frontend/app/chat/page.tsx
git commit -m "feat(frontend): integrate slash command into chat input"
```

---

## Chunk 6: 端到端验证

### Task 19: 手动集成验证

- [ ] **Step 1: 启动后端**

Run: `npm run dev:backend`
Expected: 无报错，日志中有 skill 加载信息

- [ ] **Step 2: 验证 API 端点**

```bash
# 列出已安装 skills
curl http://localhost:8000/api/skills | python3 -m json.tool

# 搜索市场（需要网络，可能超时）
curl "http://localhost:8000/api/skills/market/search?source=clawhub&q=pdf" | python3 -m json.tool

# 启用/禁用
curl -X PATCH http://localhost:8000/api/skills/<skill-name> \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

- [ ] **Step 3: 启动前端**

Run: `npm run dev:frontend`
Expected: Skills 页面显示两个 Tab，已安装 Tab 列出当前 skills

- [ ] **Step 4: 验证聊天斜杠命令**

1. 打开聊天页
2. 输入 `/`
3. 确认补全菜单弹出
4. 选择一个 skill，确认自动填充

- [ ] **Step 5: 提交最终验证通过状态**

```bash
git add -A
git commit -m "chore: skill marketplace feature complete"
```
