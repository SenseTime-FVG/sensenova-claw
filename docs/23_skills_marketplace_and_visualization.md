# PRD: AgentOS v1.1 — Skills 市场、安装与可视化

> 版本: v1.1 · 日期: 2026-03-12 · 前置: v0.4（Skills 基础）, v1.0（多 Agent）

---

## 1. 核心问题

当前 Skills 通过 system prompt 注入后，用户不知道 Agent 装了什么 Skills、不知道怎么触发。本质是三层缺失：**可发现性**（有什么）、**可理解性**（怎么用）、**可管理性**（怎么管）。

同时 `source = "local"` 同时指代内置和用户自建 skill，语义不清；搜索体验在"已安装"和"市场"之间割裂，用户需要在 ClawHub / Anthropic 之间手动切换搜索。

---

## 2. 分类体系

当前 `local` 应拆分为 `builtin` 和 `workspace`：

| category | 含义 | 可卸载 | 可更新 |
|----------|------|--------|--------|
| **builtin** | 代码内置（`backend/app/skills/` 下） | 否 | 随版本 |
| **workspace** | 用户在工作区手动创建 | 否 | 否 |
| **installed** | 从市场下载，含 `.install.json` | 是 | 是 |

```python
# backend/app/api/skills.py

BUILTIN_SKILLS_DIR = Path(__file__).resolve().parents[1] / "skills"

def _classify_skill(skill: Skill) -> str:
    if skill.install_info:
        return "installed"
    try:
        skill.path.relative_to(BUILTIN_SKILLS_DIR)
        return "builtin"
    except ValueError:
        return "workspace"
```

前端标签色：

```typescript
const categoryConfig = {
  builtin:   { label: '内置',     color: 'bg-emerald-600' },
  workspace: { label: '工作区',   color: 'bg-blue-600' },
  installed: { label: '已安装',   color: 'bg-purple-600' },
  clawhub:   { label: 'ClawHub',  color: 'bg-violet-600' },
  anthropic: { label: 'Anthropic', color: 'bg-orange-600' },
  git:       { label: 'Git',      color: 'bg-gray-600' },
};
```

---

## 3. 统一搜索 API

新增 `GET /api/skills/search`，同时查本地和远程，替代当前分 Tab 搜索。

```python
@router.get("/search")
async def unified_search(q: str, request: Request, sources: str = "all"):
    """统一搜索本地 + 远程市场"""
    skill_registry = request.app.state.skill_registry
    market_service = request.app.state.market_service
    query_lower = q.lower()
    source_list = [s.strip() for s in sources.split(",")] if sources != "all" else []

    # 1. 本地模糊匹配
    local_results = []
    if not source_list or any(s in ("local", "builtin", "workspace", "installed") for s in source_list):
        for skill in skill_registry.get_all():
            if query_lower in skill.name.lower() or query_lower in skill.description.lower():
                local_results.append({
                    "id": f"local:{skill.name}",
                    "name": skill.name,
                    "description": skill.description,
                    "category": _classify_skill(skill),
                    "source": skill.source,
                    "version": skill.version,
                    "enabled": skill_registry.is_enabled(skill.name),
                    "installed": True,
                })

    # 2. 并发搜远程
    remote_results = []
    search_sources = []
    if not source_list or "clawhub" in source_list or sources == "all":
        search_sources.append("clawhub")
    if not source_list or "anthropic" in source_list or sources == "all":
        search_sources.append("anthropic")

    async def _search_one(src: str):
        try:
            result = await market_service.search(src, q, page=1, page_size=10)
            return [{
                "id": item.id, "name": item.name,
                "description": item.description, "category": src,
                "source": src, "version": item.version,
                "author": item.author, "downloads": item.downloads,
                "installed": skill_registry.get(item.name) is not None,
            } for item in result.items]
        except Exception as e:
            logger.warning("搜索 %s 失败: %s", src, e)
            return []

    if search_sources:
        for r in await asyncio.gather(*[_search_one(s) for s in search_sources]):
            remote_results.extend(r)

    return {
        "local_results": local_results,
        "remote_results": remote_results,
        "total_local": len(local_results),
        "total_remote": len(remote_results),
    }
```

前端合并排序：已安装优先，来源 Tab 过滤（全部 / 已安装 / ClawHub / Anthropic）。

---

## 4. 列表 API 增强

`GET /api/skills` 增加 `category`、`dependencies`、`all_deps_met` 字段：

```python
@router.get("")
async def list_skills(request: Request, include_disabled: bool = False):
    skill_registry = request.app.state.skill_registry
    skills = []
    for skill in skill_registry.get_all():
        metadata = _parse_skill_metadata(skill)
        deps = metadata.get("agentos", {}).get("requires", {}).get("bins", [])
        dep_status = {d: shutil.which(d) is not None for d in deps}
        skills.append({
            "id": f"skill-{skill.name}",
            "name": skill.name,
            "description": skill.description or "",
            "category": _classify_skill(skill),
            "enabled": skill_registry.is_enabled(skill.name),
            "source": skill.source,
            "version": skill.version,
            "has_update": False,
            "dependencies": dep_status,
            "all_deps_met": all(dep_status.values()) if dep_status else True,
        })
    return skills

def _parse_skill_metadata(skill: Skill) -> dict:
    try:
        content = (skill.path / "SKILL.md").read_text(encoding="utf-8")
        parts = content.split("---", 2)
        if len(parts) >= 3:
            return yaml.safe_load(parts[1]).get("metadata", {})
    except Exception:
        pass
    return {}
```

---

## 5. 数据模型增强

```python
class SkillSearchItem(BaseModel):
    # 已有字段不变，新增：
    updated_at: str | None = None         # ISO 8601
    dependencies: list[str] | None = None
    tags: list[str] | None = None

class SkillDetail(BaseModel):
    # 已有字段不变，新增：
    updated_at: str | None = None
    dependencies: list[str] | None = None
    readme: str | None = None
```

ClawHub 适配器补 `updated_at=s.get("updatedAt")`。

---

## 6. 安装依赖检查

安装成功后返回依赖状态，前端据此显示警告：

```python
# install 增强（安装成功后追加）
if result.get("ok"):
    skill = skill_registry.get(result["skill_name"])
    if skill:
        metadata = _parse_skill_metadata(skill)
        deps = metadata.get("agentos", {}).get("requires", {}).get("bins", [])
        dep_status = {d: shutil.which(d) is not None for d in deps}
        result["dependencies"] = dep_status
        result["all_deps_met"] = all(dep_status.values()) if dep_status else True
```

前端 toast：依赖全满足 → "安装成功，已自动启用"；缺失 → 警告哪些依赖缺失。

---

## 7. `/agents/[id]/skills` 增强

按 category 分组展示，复用增强版卡片：

```typescript
{['builtin', 'installed', 'workspace'].map(category => {
  const group = filteredSkills.filter(s => s.category === category);
  if (!group.length) return null;
  return (
    <div key={category}>
      <h3>{categoryLabels[category]} ({group.length})</h3>
      {group.map(skill => (
        <AgentSkillCard
          key={skill.name} skill={skill}
          enabled={skillStates[skill.name] ?? true}
          onToggle={v => setSkillStates(p => ({ ...p, [skill.name]: v }))}
        />
      ))}
    </div>
  );
})}
```

启用/禁用三层逻辑：`全局已启用 ∩ AgentConfig 白名单 ∩ Agent 偏好`。全局禁用的灰色不可操作，不在白名单的灰色提示"需在 Agent 配置中添加"。

---

## 8. `/skills` 页面结构

```
┌───────────────────────────────────────────────────┐
│  Skills 管理                                       │
│  🔍 搜索 skills...                        [Git URL]│
│  [全部] [已安装] [ClawHub] [Anthropic]             │
├───────────────────────────────────────────────────┤
│  未搜索时 → 按 category 分组展示已安装列表         │
│  搜索时   → 本地匹配 + 市场结果，已安装排前        │
│  每个卡片: 名称 + [category] + 版本 + 描述         │
│           + author/downloads(远程) + toggle/安装   │
│  点击卡片 → 详情弹窗(SKILL.md + 依赖 + 文件列表)  │
└───────────────────────────────────────────────────┘
```

前端组件树：

```
/skills
  ├── SearchInput + FilterTabs
  ├── InstalledSection (默认) → CategoryGroup → SkillCard
  ├── SearchResults (搜索时) → LocalResults + RemoteResults → SkillCard
  ├── GitUrlInstaller
  └── SkillDetailModal (概览 / SKILL.md / 文件)

/agents/[id] → SkillsTab
  ├── SearchInput + SaveButton
  └── CategoryGroup → AgentSkillCard (轻量版)
```

---

## 9. 实施计划

| 阶段 | 内容 | 工期 | 改动文件 |
|------|------|------|----------|
| **a** | 分类体系 + 列表 API 增强 | 2h | `skills.py`, `registry.py` |
| **b** | 统一搜索 API + 前端搜索重构 | 1d | `skills.py`, `SkillsPage`, `InstalledTab`, `MarketTab` |
| **c** | SkillCard + 详情弹窗增强 | 0.5d | `SkillCard.tsx`, `SkillDetailModal.tsx` |
| **d** | `/agents/[id]/skills` 增强 | 0.5d | `agents/[id]/page.tsx` |
| **e** | 安装依赖检查 | 0.5d | `skills.py`, `MarketTab.tsx` |
| **f** | 数据模型 + 适配器补字段 | 0.5d | `models.py`, `clawhub.py`, `anthropic_market.py` |

**总计 ~3.5 天**。阶段 a 改动极小可立即执行。

---

## 10. 验收标准

| # | 条件 | P |
|---|------|---|
| S1 | `/skills` 按 builtin/workspace/installed 分组展示 | P0 |
| S2 | 统一搜索同时查本地+远程，合并展示 | P0 |
| S3 | 卡片显示名称、描述、来源标签、版本 | P0 |
| S4 | 远程额外显示 author、downloads | P0 |
| S5 | 点击卡片弹详情（SKILL.md 预览） | P0 |
| S6 | 安装/卸载/toggle 正常工作 | P0 |
| S7 | `/agents/[id]/skills` 分类分组 + 增强卡片 | P1 |
| S8 | 安装后返回依赖状态，缺失时 UI 警告 | P1 |
| S9 | 搜索结果已安装优先、来源 Tab 过滤 | P1 |
| S10 | 详情弹窗展示依赖满足状态 | P2 |

---

## 11. 否决方案

| 方案 | 原因 |
|------|------|
| 展示 GitHub Stars | 市场没有统一 star 体系，用 downloads 替代 |
| 合并 `/skills` 和 `/agents/[id]/skills` | 用户意图不同（全局管理 vs Agent 配置） |
| 打字即搜远程市场 | ClawHub 限流 120/min，改为回车触发 |
| Skill 在线编辑器 | workspace files 编辑器已够用 |
| Skill 评分/评论 | 无用户账号体系，市场也无评论 API |

---

## 相关文档

- [13_skills_system.md](./13_skills_system.md) - Skills 系统基础
- [22_multi_agent_and_workflow.md](./22_multi_agent_and_workflow.md) - 多 Agent（Skills 分配）
