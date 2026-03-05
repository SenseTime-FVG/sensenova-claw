# 开发指南

## 环境准备

### 后端环境

**系统要求**:
- Python 3.12+
- [uv](https://github.com/astral-sh/uv)（Python 包管理工具）

**安装依赖**:
```bash
cd backend
uv sync
```

依赖通过 `pyproject.toml` 管理，新增依赖使用：
```bash
uv add <package>
```

**pyproject.toml 主要依赖**:
```
fastapi
uvicorn[standard]
websockets
pydantic
pyyaml
aiosqlite
httpx
openai
anthropic
```

### 前端环境

**系统要求**:
- Node.js 22
- npm 或 pnpm

**安装依赖**:
```bash
cd frontend
npm install
```


## 项目初始化

### 创建配置文件

```bash
mkdir -p ~/.SenseAssistant
cat > ~/.SenseAssistant/config.yaml << EOF
llm_providers:
  openai:
    api_key: ${OPENAI_API_KEY}
    default_model: gpt-4
  anthropic:
    api_key: ${ANTHROPIC_API_KEY}
    default_model: claude-3-5-sonnet-20241022

tools:
  serper_search:
    api_key: ${SERPER_API_KEY}
EOF
```

### 初始化数据库

```bash
python -m backend.init_db
```

## 启动开发服务器

### 一键启动脚本

项目根目录提供 `scripts/dev.sh`，执行后同时启动前端和后端，并内置以下检查：

```bash
./scripts/dev.sh
```

**脚本需完成的检查项**：

| 检查项 | 说明 |
|--------|------|
| 配置文件存在 | 检查配置文件是否存在，不存在则提示用户创建 |
| 后端端口占用 | 检测后端端口（默认 8000）是否已被占用，占用则报错退出 |
| 前端端口占用 | 检测前端端口（默认 3000）是否已被占用，占用则报错退出 |
| 前后端端口一致性 | 读取配置文件中前端配置的后端地址，与实际后端启动端口比对，不一致则警告 |
| 前后端是否启动成功 |  前后端是否启动成功，如果其中一个失败，则把直接推出，不要有残留进程 |

## 开发工作流

### 1. 添加新的事件类型

**步骤**:
1. 在 `backend/events/types.py` 中定义事件类型常量
2. 在 `backend/events/envelope.py` 中添加 payload 类型定义
3. 更新文档 `docs/02_event_system.md`

### 2. 添加新的工具

**步骤**:
1. 在 `backend/tools/` 下创建新工具文件
2. 继承 `Tool` 基类并实现 `execute` 方法
3. 在 `backend/tools/registry.py` 中注册工具
4. 更新配置文件添加工具配置

**示例**:
```python
from tools.base import Tool

class MyTool(Tool):
    name = "my_tool"
    description = "工具描述"
    parameters = {
        "type": "object",
        "properties": {
            "param1": {"type": "string"}
        },
        "required": ["param1"]
    }

    async def execute(self, param1: str) -> dict:
        # 实现工具逻辑
        return {"result": "success"}
```

### 3. 添加新的 LLM 提供商

**步骤**:
1. 在 `backend/llm/providers/` 下创建新提供商文件
2. 继承 `LLMProvider` 基类
3. 实现 `call` 方法和响应格式转换
4. 在 `backend/llm/factory.py` 中注册提供商

### 4. 修改前端 UI

**步骤**:
1. 在 `frontend/components/` 下创建或修改组件
2. 使用 shadcn/ui 组件库
3. 遵循 VS Code 风格的设计规范
4. 确保响应式设计

## 调试技巧

### 后端调试

**查看事件流**:
```python
# 在 event_bus.py 中添加日志
async def publish(self, event: EventEnvelope):
    logger.debug(f"Publishing event: {event.type}")
    await self.queue.put(event)
```

**查看数据库内容**:
```bash
sqlite3 ~/.SenseAssistant/agentos.db
.tables
SELECT * FROM events ORDER BY timestamp DESC LIMIT 10;
```

### 前端调试

**查看 WebSocket 消息**:
```typescript
ws.onmessage = (event) => {
    const message = JSON.parse(event.data);
    console.log('Received:', message);
    handleMessage(message);
};
```

**React DevTools**:
安装 React DevTools 浏览器扩展查看组件状态。

## 测试

### 后端单元测试

```bash
cd backend
pytest tests/
```

### 前端测试

```bash
cd frontend
npm run test
```

## 常见问题

### WebSocket 连接失败
- 检查后端是否正常运行
- 检查端口是否被占用
- 查看浏览器控制台错误信息

### LLM API 调用失败
- 验证 API Key 是否正确
- 检查网络连接
- 查看后端日志中的错误详情

### 工具执行超时
- 检查工具配置中的 timeout 设置
- 确认命令或操作是否耗时过长
- 查看工具执行日志
