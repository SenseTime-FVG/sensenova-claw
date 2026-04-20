# 贡献指南

感谢你对 Sensenova-Claw 的关注！我们欢迎任何形式的贡献——Bug 报告、功能建议、文档改进、代码提交。

## 快速开始

### 环境要求

- Python ≥ 3.12
- Node.js ≥ 18
- [uv](https://docs.astral.sh/uv/) (Python 包管理)
- npm (Node.js 包管理)

### 搭建开发环境

```bash
# 1. Fork 并克隆仓库
git clone https://github.com/<你的用户名>/sensenova-claw.git
cd sensenova-claw

# 2. 安装 Python 依赖（含开发工具）
uv sync --extra dev

# 3. 安装 Node.js 依赖
npm install

# 4. 复制示例配置
cp config_example.yml ~/.sensenova-claw/config.yml
# 编辑 config.yml，填入你的 API Key

# 5. 启动开发服务
npm run dev
```

启动后访问 `http://localhost:3000` 即可看到 Web 界面。

## 贡献流程

### 1. 选择或创建 Issue

- 浏览 [Issues](https://github.com/SenseTime-FVG/sensenova-claw/issues) 找到你感兴趣的任务
- 带有 `good first issue` 标签的适合新贡献者
- 如果你想做的事情还没有对应 Issue，请先创建一个，描述你的想法

### 2. 创建分支

从 `dev` 分支创建你的功能分支：

```bash
git checkout dev
git pull origin dev
git checkout -b <分支名>
```

**分支命名规范**：

| 类型 | 格式 | 示例 |
|------|------|------|
| 新功能 | `feat/<描述>` | `feat/streaming-response` |
| Bug 修复 | `fix/<描述>` | `fix/websocket-reconnect` |
| 文档 | `docs/<描述>` | `docs/api-reference` |
| 重构 | `refactor/<描述>` | `refactor/event-bus` |

### 3. 开发与测试

编写代码后，确保测试通过：

```bash
# 单元测试
npm run test:unit

# 后端 e2e 测试（需要 API Key）
npm run test:e2e

# 前端 e2e 测试（需要 Playwright 浏览器）
npm run test:web:e2e

# 全部测试
npm run test
```

### 4. 提交代码

我们使用 [Conventional Commits](https://www.conventionalcommits.org/) 规范，提交信息使用中文描述：

```
<type>(<scope>): <描述>
```

**Type**：

| Type | 用途 |
|------|------|
| `feat` | 新功能 |
| `fix` | Bug 修复 |
| `docs` | 文档变更 |
| `refactor` | 重构（不改变功能） |
| `test` | 测试相关 |
| `ci` | CI/CD 配置 |
| `chore` | 构建、依赖等杂项 |

**Scope**（可选）：`frontend`、`backend`、`cli`、`config`、`tools`、`skills` 等。

**示例**：

```
feat(frontend): 侧边栏支持双击重命名对话标题
fix(backend): 添加会话重命名 PATCH /api/sessions/{session_id}/title 端点
docs: 补齐搜索 skill 缺失的 README
ci: 自动更新 latest tag 跟随 dev 分支
```

### 5. 提交 Pull Request

- 向 `dev` 分支提交 PR（不要直接提交到 `main`）
- PR 标题遵循 Conventional Commits 格式
- 在描述中说明：
  - **做了什么**：简要描述改动内容
  - **为什么**：解释改动的动机或关联的 Issue（`Closes #123`）
  - **如何测试**：说明如何验证你的改动

**PR 模板**：

```markdown
## 改动说明

简要描述你的改动。

## 关联 Issue

Closes #

## 测试方式

- [ ] 单元测试通过
- [ ] e2e 测试通过（如涉及）
- [ ] 手动验证（描述步骤）
```

## 代码规范

### Python

- 注释和文档使用**中文**
- 遵循 PEP 8 风格
- 使用 type hints
- 异步代码使用 `async/await`（项目基于 asyncio）

### TypeScript / React

- 前端位于 `sensenova_claw/app/web/`
- 使用 Next.js 14 App Router
- 组件使用函数式写法 + Hooks

### 测试

- 新功能必须编写测试
- 后端测试放在 `tests/` 对应子目录（`unit/`、`integration/`、`e2e/`）
- 前端 e2e 测试放在 `sensenova_claw/app/web/e2e/`
- e2e 测试使用真实 API Key，通过 `config.yml` 配置

### 架构原则

- 所有模块通过 **EventBus** 解耦通信，避免直接依赖
- 通过 `session_id` 做会话级隔离
- 新工具在 `sensenova_claw/capabilities/tools/` 中实现，继承 `BaseTool`
- 新 LLM Provider 在 `sensenova_claw/adapters/llm/providers/` 中实现，继承 `LLMProvider`
- 新 Channel 在 `sensenova_claw/adapters/channels/` 中实现

## 项目结构

关键目录说明：

```
sensenova_claw/
├── kernel/              # 内核层：事件总线、运行时编排、调度
├── capabilities/        # 能力层：Agent、工具、Skills、记忆
├── adapters/            # 适配层：LLM、渠道、存储、插件
├── interfaces/          # 接口层：REST API、WebSocket
├── platform/            # 平台层：配置、日志、安全
└── app/                 # 应用层：Gateway、CLI、Web 前端

tests/                   # 测试
docs/                    # 技术文档
```

详细架构说明见 [README](README.md#️-architecture) 和 `docs/architecture/`。

## 报告 Bug

请在 [Issues](https://github.com/SenseTime-FVG/sensenova-claw/issues/new) 中提交，包含以下信息：

1. **环境**：操作系统、Python 版本、Node.js 版本
2. **复现步骤**：尽量提供最小复现路径
3. **预期行为** vs **实际行为**
4. **日志/截图**：如有报错，附上相关日志（开发模式下有 DEBUG 日志）

## 功能建议

欢迎在 Issues 中提出功能建议，请描述：

1. **使用场景**：你希望解决什么问题
2. **期望方案**：你设想的解决方式
3. **替代方案**：是否考虑过其他实现方式

## 许可证

提交贡献即表示你同意将代码以 [MIT License](LICENSE) 授权。
