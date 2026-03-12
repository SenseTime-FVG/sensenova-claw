# Feishu Skills 接入配置

**日期**: 2026-03-11 00:10

---

## 变更概述

1. **新功能**：SkillRegistry 支持通过 `skills.extra_dirs` 配置加载额外目录下的 Skills
2. **配置更新**：在 `config.yml` 中接入飞书 4 个 Skills（feishu-doc、feishu-wiki、feishu-drive、feishu-perm）

---

## 一、背景

飞书相关的 Skills 定义文件位于 `backend/app/skills/feishu/` 目录下，包含 4 个子 Skill：

| Skill 名称 | 用途 | SKILL.md 路径 |
|---|---|---|
| `feishu-doc` | 飞书文档读写（读取/写入/追加/创建/Block 操作/表格/图片） | `feishu/feishu-doc/SKILL.md` |
| `feishu-wiki` | 飞书知识库导航（空间/节点/创建/移动/重命名） | `feishu/feishu-wiki/SKILL.md` |
| `feishu-drive` | 飞书云空间文件管理（列表/创建文件夹/移动/删除） | `feishu/feishu-drive/SKILL.md` |
| `feishu-perm` | 飞书权限管理（协作者列表/添加/移除） | `feishu/feishu-perm/SKILL.md` |

此前 `SkillRegistry` 仅从用户目录（`~/.agentos/skills`）和工作区目录加载 Skills，无法扫描项目内置的 Skill 目录。

---

## 二、修改内容

### 2.1 config.yml — 添加 Skills 配置段

```yaml
skills:
  extra_dirs:
    - D:\code\agentos\backend\app\skills\feishu
  entries:
    feishu-doc:
      enabled: true
    feishu-wiki:
      enabled: true
    feishu-drive:
      enabled: true
    feishu-perm:
      enabled: true
```

- `extra_dirs`：额外的 Skill 扫描目录列表，SkillRegistry 会递归查找其中的 `SKILL.md` 文件
- `entries`：逐个 Skill 的启用/禁用开关，默认 `enabled: true`

### 2.2 SkillRegistry — 支持 extra_dirs

**文件**: `backend/app/skills/registry.py`

在 `load_skills()` 方法末尾增加对 `extra_dirs` 的遍历：

```python
# 加载 extra_dirs 中配置的额外 skill 目录
extra_dirs = config.get("skills", {}).get("extra_dirs", [])
for dir_path in extra_dirs:
    p = Path(dir_path)
    if p.exists():
        self._load_from_dir(p, config)
```

加载顺序：用户目录 → 工作区目录 → extra_dirs（后加载的同名 Skill 会覆盖先前的）。

### 2.3 DEFAULT_CONFIG — 添加 extra_dirs 默认值

**文件**: `backend/app/core/config.py`

```python
"skills": {
    "extra_dirs": [],   # 新增
    "entries": {},
},
```

---

## 三、影响范围

| 文件 | 改动 |
|------|------|
| `config.yml` | 添加 `skills` 配置段（extra_dirs + entries） |
| `backend/app/skills/registry.py` | `load_skills()` 增加 extra_dirs 遍历逻辑 |
| `backend/app/core/config.py` | `DEFAULT_CONFIG.skills` 添加 `extra_dirs` 默认空列表 |

- `main.py` 无需修改，`skill_registry.load_skills(config.data)` 已传入完整配置
- 对原有 Skills 加载逻辑无影响，extra_dirs 默认为空列表

---

## 四、飞书 Skills 功能速览

### feishu-doc
单工具 `feishu_doc`，通过 `action` 参数区分操作：read / write / append / create / list_blocks / get_block / update_block / delete_block / create_table / write_table_cells / create_table_with_values / upload_image / upload_file

### feishu-wiki
单工具 `feishu_wiki`：spaces / nodes / get / create / move / rename。与 `feishu_doc` 配合使用——Wiki 负责导航，Doc 负责内容读写。

### feishu-drive
单工具 `feishu_drive`：list / info / create_folder / move / delete。注意：Bot 无根目录，需用户先共享文件夹。

### feishu-perm
单工具 `feishu_perm`：list / add / remove。默认禁用（`enabled: false`），此次配置中显式启用。
