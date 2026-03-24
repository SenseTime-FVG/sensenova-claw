# 项目重命名设计：sensenova-claw → sensenova-claw

**日期**: 2026-03-24
**状态**: 已批准

## 背景

GitHub 仓库已从 `SenseTime-FVG/sensenova-claw` 重命名为 `SenseTime-FVG/sensenova-claw`。需要将代码库中所有 "sensenova-claw" 相关引用同步更新。

## 命名映射

| 场景 | 当前 | 目标 |
|------|------|------|
| Python 包名 | `sensenova-claw` | `sensenova_claw` |
| CLI 命令 | `sensenova-claw` | `sensenova-claw` |
| 用户运行时目录 | `~/.sensenova-claw/` | `~/.sensenova-claw/` |
| 环境变量前缀 | `AGENTOS_*` | `SENSENOVA_CLAW_*` |
| UI 显示名称 | `Sensenova-Claw` | `Sensenova-Claw` |
| Cookie 名 | `sensenova_claw_token` | `sensenova_claw_token` |
| 数据库文件 | `sensenova-claw.db` | `sensenova-claw.db` |
| 前端包名 | `sensenova-claw-frontend` | `sensenova-claw-frontend` |
| WhatsApp Bridge 包名 | `sensenova-claw-whatsapp-bridge` | `sensenova-claw-whatsapp-bridge` |
| Skill 元数据 key | `metadata["sensenova-claw"]` | `metadata["sensenova-claw"]` |
| Keyring service_name | `"sensenova-claw"` | `"sensenova-claw"` |
| GitHub URL | `github.com/SenseTime-FVG/sensenova-claw` | `github.com/SenseTime-FVG/sensenova-claw` |

## 方案

采用一次性批量替换方案（方案 A）：不做向后兼容，一刀切全改。

## 影响范围

- **Python imports**: 902 处，261 个文件
- **环境变量**: 250+ 处
- **前端代码**: 85 处，48 个文件
- **测试文件**: 1037 处
- **文档**: 606 处
- **配置/脚本**: ~60 处
- **GitHub URL**: 6 处

## 执行步骤

### Step 1: 目录重命名与删除

```bash
git mv sensenova_claw/ sensenova_claw/
git mv .sensenova-claw/ .sensenova-claw/
rm -rf docs_raw/
```

### Step 2: 字符串批量替换

按长度降序替换，避免子串误替换。**关键规则：`.py` 文件中 `sensenova-claw` 一律替换为 `sensenova_claw`（下划线），其他文件替换为 `sensenova-claw`（连字符）。**

#### Phase 2a: 精确匹配规则（全局，所有文件类型）

| 顺序 | 查找 | 替换为 | 说明 |
|------|------|--------|------|
| 1 | `SENSENOVA_CLAW_REPO_BRANCH` | `SENSENOVA_CLAW_REPO_BRANCH` | 环境变量 |
| 2 | `SENSENOVA_CLAW_REPO_URL` | `SENSENOVA_CLAW_REPO_URL` | 环境变量 |
| 3 | `SENSENOVA_CLAW_REPO_REF` | `SENSENOVA_CLAW_REPO_REF` | 环境变量 |
| 4 | `SENSENOVA_CLAW_DEBUG_LLM` | `SENSENOVA_CLAW_DEBUG_LLM` | 环境变量 |
| 5 | `SENSENOVA_CLAW_TOKEN` | `SENSENOVA_CLAW_TOKEN` | 环境变量 |
| 6 | `SENSENOVA_CLAW_HOME` | `SENSENOVA_CLAW_HOME` | 环境变量 |
| 7 | `sensenova_claw_frontend` | `sensenova_claw_frontend` | 包名变体 |
| 8 | `sensenova_claw_token` | `sensenova_claw_token` | Cookie/Token 名 |
| 9 | `sensenova_claw_home` | `sensenova_claw_home` | Python 变量（含复合名如 `resolve_sensenova_claw_home`） |
| 10 | `sensenova-claw-frontend` | `sensenova-claw-frontend` | 前端包名 |
| 11 | `sensenova-claw-whatsapp-bridge` | `sensenova-claw-whatsapp-bridge` | WhatsApp Bridge 包名 |
| 12 | `#sensenova-claw-workdir:` | `#sensenova-claw-workdir:` | 前端链接前缀 |
| 13 | `#sensenova-claw-file:` | `#sensenova-claw-file:` | 前端链接前缀 |
| 14 | `sensenova-claw:open-slide-preview` | `sensenova-claw:open-slide-preview` | 前端自定义事件 |
| 15 | `from sensenova_claw` | `from sensenova_claw` | Python import |
| 16 | `import sensenova_claw` | `import sensenova_claw` | Python import |
| 17 | `sensenova_claw.app.main` | `sensenova_claw.app.main` | 模块引用（脚本/配置） |
| 18 | `sensenova_claw.app.gateway` | `sensenova_claw.app.gateway` | 模块引用（脚本/配置） |
| 19 | `.sensenova-claw` | `.sensenova-claw` | 运行时目录路径 |
| 20 | `sensenova-claw.db` | `sensenova-claw.db` | 数据库文件名 |
| 21 | `Sensenova-Claw` | `Sensenova-Claw` | 显示名称 |

#### Phase 2b: 兜底规则（按文件类型分流）

| 顺序 | 查找 | 替换为 | 范围 |
|------|------|--------|------|
| 22 | `sensenova-claw` | `sensenova_claw` | 仅 `.py` 文件 |
| 23 | `sensenova-claw` | `sensenova-claw` | 所有其他文本文件 |

**替换范围**: 所有文本文件（.py, .ts, .tsx, .yml, .yaml, .json, .sh, .ps1, .bat, .md, .toml, .cfg）
**排除**: `uv.lock`, `package-lock.json`, `node_modules/`, `.git/`, 二进制文件

### Step 3: 特殊文件手动检查

- **pyproject.toml**: `name = "sensenova-claw"`, entry point `sensenova-claw = "sensenova_claw.app.main:main"`
- **package.json (根)**: `"name": "sensenova-claw"`, 脚本路径更新
- **package.json (前端)**: `"name": "sensenova-claw-frontend"`
- **package.json (WhatsApp Bridge)**: `"name": "sensenova-claw-whatsapp-bridge"`
- **.gitignore**: 路径从 `sensenova_claw/` 更新为 `sensenova_claw/`
- **AGENTS.md**: 所有 agent 描述中的引用
- **argparse prog**: `main.py` 中 `prog="sensenova-claw"` → `prog="sensenova-claw"`

### Step 4: 重新生成锁文件

```bash
uv sync
cd sensenova_claw/app/web && npm install
```

### Step 5: 验证

1. `grep -r "sensenova-claw"` 确认无遗漏（排除 lock 文件、node_modules、.git）
2. `grep -rn "sensenova-claw" --include="*.py"` — **确认 Python 文件中无连字符版本**（全应为下划线）
3. `python3 -c "import sensenova_claw"` 验证包可导入
4. `python3 -m pytest tests/unit/ -q` 跑单元测试
5. 手动启动 `npm run dev` 验证运行

## 不改的内容

- `uv.lock`、`package-lock.json` — 自动生成，重新 sync 后更新
- 测试中用 "Sensenova-Claw" 作为纯文本测试数据（如搜索 query）的地方
- 二进制文件（图片等）

## 额外操作

- 删除 `docs_raw/` 目录（该目录为原始用户文档，大量引用旧名称且不再维护）
- 更新 `CLAUDE.md` 中的项目描述、命令示例、文件路径

## 风险

| 风险 | 应对 |
|------|------|
| Python 文件中误用连字符产生语法错误 | Phase 2b 按文件类型分流；验证步骤 2 专门检查 |
| 替换误伤含 "sensenova-claw" 子串的第三方内容 | 替换后 grep + 人工审查 diff |
| lock 文件重新生成引入依赖变更 | 与 rename 分开关注 |
| 替换顺序错误导致双重替换 | 严格按长度降序，每条规则只执行一次 |
| keyring service_name 变更导致旧 secret 不可访问 | 不兼容策略，用户需重新配置 |
| 已部署环境的 `SENSENOVA_CLAW_HOME` 环境变量失效 | 不兼容策略，用户需更新 shell profile |
