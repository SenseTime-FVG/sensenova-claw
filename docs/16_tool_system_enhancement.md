# 工具系统增强 PRD

## 背景

当前工具系统存在三个待改进点：

1. **缺少权限管理**：所有工具（包括 `bash_command` 等高风险工具）无需用户确认即可执行，存在安全风险。
2. **结果截断不统一**：全局截断阈值为 16000 tokens，`fetch_url` 工具内部又有独立的 `max_size_mb` 截断逻辑，策略分散且阈值偏高。
3. **write_file 功能不足**：仅支持全量覆盖或追加写入，无法从指定行号开始插入或替换内容。

## 目标

- 实现工具权限分级，高风险工具执行前需用户确认
- 统一工具结果截断策略，阈值降至 8000 tokens，明确两层截断的职责分工
- 增强 `write_file` 工具，支持按行号范围写入（插入和替换）

---

## 一、工具权限管理

### 1.1 权限分级

```python
from enum import Enum

class ToolRiskLevel(Enum):
    LOW = "low"           # 只读操作，无副作用
    MEDIUM = "medium"     # 有副作用但可控
    HIGH = "high"         # 高风险操作，需用户确认
```

### 1.2 工具风险等级分配

| 工具名 | 风险等级 | 理由 |
|--------|---------|------|
| `serper_search` | LOW | 只读，无副作用 |
| `fetch_url` | LOW | 只读，无副作用 |
| `read_file` | LOW | 只读，无副作用 |
| `write_file` | MEDIUM | 写文件，有副作用但可控 |
| `bash_command` | HIGH | 执行任意命令，风险最高 |

### 1.3 确认事件定义

```python
TOOL_CONFIRMATION_REQUESTED = "tool.confirmation_requested"
TOOL_CONFIRMATION_RESPONSE = "tool.confirmation_response"
```

#### tool.confirmation_requested

```python
{
    "tool_call_id": str,
    "tool_name": str,
    "arguments": dict,      # 工具参数（供用户查看）
    "risk_level": str,       # 风险等级
    "message": str           # 确认提示消息
}
```

#### tool.confirmation_response

```python
{
    "tool_call_id": str,
    "approved": bool,        # 用户是否批准
    "reason": str            # 拒绝理由（可选）
}
```

### 1.4 权限确认的状态管理方案

事件驱动架构中不能同步 await 一个未来事件，需要显式的挂起/唤醒机制：

```python
class ToolRuntime:
    # 挂起中的确认请求：tool_call_id → asyncio.Event
    _pending_confirmations: dict[str, asyncio.Event] = {}
    # 确认结果缓存：tool_call_id → bool
    _confirmation_results: dict[str, bool] = {}

    async def _handle_tool_requested(self, event: EventEnvelope) -> None:
        tool = self.registry.get(tool_name)

        if self._needs_confirmation(tool):
            approved = await self._request_confirmation(event, tool)
            if not approved:
                # 发布拒绝结果给 AgentRuntime
                await self._publish_tool_result(event, result="用户拒绝执行该工具", success=False)
                return

        # 正常执行工具
        await self._execute_tool(event, tool)

    async def _request_confirmation(self, event: EventEnvelope, tool: Tool) -> bool:
        """发布确认请求并挂起等待，超时自动拒绝"""
        tool_call_id = event.payload["tool_call_id"]
        wait_event = asyncio.Event()
        self._pending_confirmations[tool_call_id] = wait_event

        # 发布确认请求事件
        await self.publisher.publish(EventEnvelope(
            type=TOOL_CONFIRMATION_REQUESTED,
            payload={...}
        ))

        # 挂起等待，超时自动拒绝
        timeout = config.get("tools.permission.confirmation_timeout", 60)
        try:
            await asyncio.wait_for(wait_event.wait(), timeout=timeout)
            return self._confirmation_results.pop(tool_call_id, False)
        except asyncio.TimeoutError:
            return False
        finally:
            self._pending_confirmations.pop(tool_call_id, None)

    async def _handle_confirmation_response(self, event: EventEnvelope) -> None:
        """处理用户确认响应，唤醒挂起的任务"""
        tool_call_id = event.payload["tool_call_id"]
        approved = event.payload.get("approved", False)

        self._confirmation_results[tool_call_id] = approved
        wait_event = self._pending_confirmations.get(tool_call_id)
        if wait_event:
            wait_event.set()  # 唤醒挂起的 _request_confirmation

    def _needs_confirmation(self, tool: Tool) -> bool:
        """判断工具是否需要用户确认"""
        if not config.get("tools.permission.enabled", False):
            return False
        auto_levels = config.get("tools.permission.auto_approve_levels", ["low"])
        return tool.risk_level.value not in auto_levels
```

### 1.5 前端/客户端适配

- **Web 前端**：在消息流中插入确认卡片，用户点击"允许"/"拒绝"
- **CLI/TUI**：在终端中提示用户输入 y/n
- **超时处理**：确认请求超过 60 秒未响应，默认拒绝执行，并向 LLM 返回"用户拒绝"

### 1.6 配置项

```yaml
tools:
  permission:
    enabled: true                    # 是否启用权限管理
    auto_approve_levels: ["low"]     # 自动批准的风险等级
    confirmation_timeout: 60         # 确认超时时间（秒）
```

---

## 二、工具结果截断统一

### 2.1 当前问题

- ToolRuntime 全局截断阈值为 ~16000 tokens（`16000 * 3` 字符）
- `fetch_url` 工具内部有独立的 `max_size_mb` 截断逻辑
- 两层截断策略不一致，维护成本高

### 2.2 两层截断的职责分工

截断需要区分两个不同层次的关注点：

| 层次 | 位置 | 目的 | 阈值 |
|------|------|------|------|
| **内存保护** | 工具层（各 Tool 内部） | 防止 OOM，限制原始数据加载量 | 按数据类型各自设置（如 HTTP 响应 10MB） |
| **Token 截断** | ToolRuntime 层 | 控制传给 LLM 的文本长度 | 统一 8000 tokens |

> **设计决策**：不能完全移除工具层的截断。以 `fetch_url` 为例，如果目标网页是 100MB，
> `httpx.response.text` 会先将完整内容加载到内存，然后才走到 ToolRuntime 的 token 截断。
> 工具层的 `max_size_mb` 是 OOM 防线，必须保留。

### 2.3 目标方案

```python
class ToolRuntime:
    def _truncate_result(self, result: Any, session_id: str, tool_call_id: str) -> Any:
        """Token 截断：统一控制传给 LLM 的结果长度"""
        result_str = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)

        max_tokens = config.get("tools.result_truncation.max_tokens", 8000)
        max_chars = max_tokens * 3  # 粗略估算：1 token ≈ 3 字符

        if len(result_str) <= max_chars:
            return result

        # 保存完整结果到 <workspace>/<session_id>/tool_result_<id>.txt
        file_path = self._save_full_result(result_str, session_id, tool_call_id)

        truncated = result_str[:max_chars]
        truncated += f"\n\n[内容已截断] 完整结果已保存到: {file_path}"
        return truncated


class FetchUrlTool(Tool):
    async def execute(self, **kwargs) -> Any:
        # 内存保护截断：限制 HTTP 响应体大小，防止 OOM
        max_size = int(config.get("tools.fetch_url.max_response_mb", 10) * 1024 * 1024)
        # ...获取网页内容...
        if len(text) > max_size:
            text = text[:max_size]
        # 返回原始内容，由 ToolRuntime 做 token 截断
        return {"url": str(resp.url), "status_code": resp.status_code, "content": text}
```

### 2.4 涉及改动

```python
# ToolRuntime._truncate_result
# - 阈值从 16000*3 改为 config 可配置，默认 8000*3
# - 方法签名和保存逻辑不变

# FetchUrlTool.execute
# - max_size_mb 从截断手段改为 OOM 防护（阈值从 5MB 调整到 10MB）
# - 工具层不再关心 token 限制

# 配置文件
# - tools.fetch_url.max_size_mb 重命名为 tools.fetch_url.max_response_mb（语义更清晰）
# - 新增 tools.result_truncation.max_tokens 配置项
```

### 2.5 配置项

```yaml
tools:
  result_truncation:
    max_tokens: 8000                 # Token 截断阈值（ToolRuntime 层）
    save_dir: "workspace"            # 完整结果保存目录

  fetch_url:
    max_response_mb: 10              # 内存保护：HTTP 响应体上限（工具层 OOM 防线）
    timeout: 15
```

---

## 三、write_file 工具增强

### 3.1 当前参数

```python
class WriteFileTool(Tool):
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {"type": "string"},
            "content": {"type": "string"},
            "mode": {"type": "string", "enum": ["write", "append"]},
        },
        "required": ["file_path", "content"],
    }
```

### 3.2 新增 start_line / end_line 参数

```python
class WriteFileTool(Tool):
    name = "write_file"
    description = "写入文本文件，支持全量覆盖、追加、插入、或替换指定行范围"
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "文件路径"},
            "content": {"type": "string", "description": "要写入的内容"},
            "mode": {
                "type": "string",
                "enum": ["write", "append", "insert"],
                "default": "write",
                "description": "write=覆盖全文, append=追加到末尾, insert=在start_line处插入或替换"
            },
            "start_line": {
                "type": "integer",
                "description": "起始行号（从1开始），仅 mode=insert 时有效"
            },
            "end_line": {
                "type": "integer",
                "description": "结束行号（包含），仅 mode=insert 时有效。"
                               "省略时为纯插入（原内容下移）；"
                               "指定时替换 start_line 到 end_line 的内容"
            },
        },
        "required": ["file_path", "content"],
    }
```

### 3.3 执行逻辑

```python
class WriteFileTool(Tool):
    async def execute(self, **kwargs) -> Any:
        file_path = Path(kwargs["file_path"])
        file_path.parent.mkdir(parents=True, exist_ok=True)
        content = str(kwargs.get("content", ""))
        mode = str(kwargs.get("mode", "write"))
        start_line = kwargs.get("start_line")
        end_line = kwargs.get("end_line")

        if mode == "append":
            # 追加到文件末尾
            with file_path.open("a", encoding="utf-8") as f:
                f.write(content)

        elif mode == "insert" and start_line is not None:
            if not file_path.exists():
                # 文件不存在时等同于 write
                file_path.write_text(content, encoding="utf-8")
            else:
                lines = file_path.read_text(encoding="utf-8").splitlines(keepends=True)
                idx = max(start_line - 1, 0)
                new_lines = content.splitlines(keepends=True)

                if end_line is not None:
                    # 替换模式：删除 [start_line, end_line] 范围的行，插入新内容
                    end_idx = min(end_line, len(lines))
                    lines[idx:end_idx] = new_lines
                else:
                    # 纯插入模式：在 start_line 之前插入，原内容下移
                    lines[idx:idx] = new_lines

                file_path.write_text("".join(lines), encoding="utf-8")

        else:
            # 默认全量覆盖
            file_path.write_text(content, encoding="utf-8")

        return {"success": True, "file_path": str(file_path), "size": len(content), "mode": mode}
```

### 3.4 使用示例

```python
# 全量覆盖（默认行为，不变）
{"file_path": "config.yaml", "content": "key: value\n"}

# 追加到末尾（不变）
{"file_path": "log.txt", "content": "new line\n", "mode": "append"}

# 纯插入：在第10行之前插入2行，原第10行及后续下移
{"file_path": "main.py", "content": "import os\nimport sys\n", "mode": "insert", "start_line": 10}

# 替换：将第5~8行替换为新内容
{"file_path": "config.yaml", "content": "new_key: new_value\n", "mode": "insert", "start_line": 5, "end_line": 8}
```

---

## 四、实施优先级

| 优先级 | 改动项 | 影响范围 | 复杂度 |
|--------|--------|---------|--------|
| P0 | 结果截断统一（8000 tokens） | ToolRuntime, FetchUrlTool | 低 |
| P0 | write_file 增强 | WriteFileTool | 低 |
| P1 | 工具权限管理 | ToolRuntime, Gateway, 前端, CLI/TUI | 高 |

---

## 五、验证要点

### 截断统一

- 工具返回超过 8000 tokens 的结果时，自动截断并保存完整结果到文件
- `fetch_url` 获取大页面时，工具层做内存保护（10MB），ToolRuntime 层做 token 截断（8000）
- 截断后的结果尾部包含文件路径提示
- `fetch_url` 获取超过 10MB 的页面时不会 OOM

### write_file 增强

- `mode=write`：行为不变，全量覆盖
- `mode=append`：行为不变，追加写入
- `mode=insert` + `start_line`（无 end_line）：纯插入，原内容下移
- `mode=insert` + `start_line` + `end_line`：替换指定行范围
- 文件不存在时 `insert` 模式等同于 `write`
- `start_line` 超出文件行数时追加到末尾

### 权限管理

- `bash_command` 执行前向用户发送确认请求
- 用户批准后正常执行
- 用户拒绝或超时后返回拒绝结果给 LLM（LLM 可据此调整策略）
- LOW 风险工具不触发确认流程
- 权限管理可通过配置关闭
- 并发场景下多个 HIGH 工具的确认互不干扰
