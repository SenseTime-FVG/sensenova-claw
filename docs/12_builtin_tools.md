# 内置工具文档

## 概述

AgentOS 提供了一套内置工具，供 LLM 调用以完成各种任务。所有工具都遵循统一的接口规范，并通过 ToolRegistry 进行管理。

## 工具基类

```python
class Tool:
    name: str                    # 工具名称
    description: str             # 工具描述
    parameters: dict             # JSON Schema 格式的参数定义

    async def execute(self, **kwargs) -> Any:
        """执行工具逻辑"""
        pass
```

## 内置工具列表

### 1. bash_command

执行 Shell 命令。

**参数**:
- `command` (string, required): 要执行的命令
- `working_dir` (string, optional): 工作目录，默认为当前目录

**返回值**:
```python
{
    "return_code": int,      # 返回码，0表示成功
    "stdout": str,           # 标准输出
    "stderr": str            # 标准错误输出
}
```

**超时**: 15秒（可通过配置 `tools.bash_command.timeout` 修改）

**安全提示**: v0.1 版本无沙箱限制，生产环境需要增强安全策略。

---

### 2. serper_search

使用 Serper API 进行网络搜索。

**参数**:
- `q` (string, required): 搜索关键词
- `tbs` (string, optional): 时间过滤，可选值：
  - `h`: 最近1小时
  - `d`: 最近1天
  - `m`: 最近1个月
  - `y`: 最近1年
  - 不传表示任意时间
- `page` (integer, optional): 页码，默认为1

**固定参数**（系统自动注入）:
- `gl`: "cn" - 地区
- `hl`: "zh-cn" - 语言

**返回值**:
```python
{
    "query": str,            # 搜索关键词
    "items": [               # 搜索结果列表
        {
            "title": str,    # 标题
            "link": str,     # 链接
            "snippet": str   # 摘要
        }
    ]
}
```

**配置项**:
- `tools.serper_search.api_key`: Serper API Key（必需）
- `tools.serper_search.timeout`: 超时时间，默认15秒
- `tools.serper_search.max_results`: 最大返回结果数，默认10

**API 示例**:
```python
import httpx

url = "https://google.serper.dev/search"
payload = {
    "q": "apple inc",
    "gl": "cn",
    "hl": "zh-cn",
    "tbs": "qdr:h",  # 可选
    "page": 1
}
headers = {
    "X-API-KEY": "<SERPER_API_KEY>",
    "Content-Type": "application/json"
}
response = httpx.post(url, headers=headers, json=payload)
```

---

### 3. fetch_url

获取指定 URL 的网页内容。

**参数**:
- `url` (string, required): 目标 URL
- `method` (string, optional): HTTP 方法，默认为 "GET"

**返回值**:
```python
{
    "url": str,              # 实际访问的URL（可能重定向）
    "status_code": int,      # HTTP状态码
    "content": str           # 网页内容
}
```

**配置项**:
- `tools.fetch_url.timeout`: 超时时间，默认15秒
- `tools.fetch_url.max_size_mb`: 最大内容大小（MB），默认5MB

**特性**:
- 自动跟随重定向
- 超过最大大小时自动截断

---

### 4. read_file

读取文本文件内容。

**参数**:
- `file_path` (string, required): 文件路径（绝对或相对）
- `encoding` (string, optional): 编码格式，默认 "utf-8"
- `start_line` (integer, optional): 起始行号（从1开始），默认1
- `num_lines` (integer, optional): 读取行数，不传则读取到文件末尾

**返回值**:
```python
{
    "file_path": str,        # 文件路径
    "content": str           # 文件内容
}
```

**使用示例**:
```python
# 读取整个文件
{"file_path": "config.yaml"}

# 读取前10行
{"file_path": "log.txt", "start_line": 1, "num_lines": 10}

# 从第50行开始读取20行
{"file_path": "data.csv", "start_line": 50, "num_lines": 20}
```

---

### 5. write_file

写入文本文件。

**参数**:
- `file_path` (string, required): 文件路径
- `content` (string, required): 要写入的内容
- `mode` (string, optional): 写入模式，可选值：
  - `write`: 覆盖写入（默认）
  - `append`: 追加写入

**返回值**:
```python
{
    "success": bool,         # 是否成功
    "file_path": str,        # 文件路径
    "size": int              # 写入的字节数
}
```

**特性**:
- 自动创建父目录
- 支持覆盖和追加两种模式

---

### 6. search_skill

搜索可用的 Agent Skill。

**参数**:
- `keyword` (string, optional): 搜索关键词，不传则返回全部

**返回值**:
```python
[
    {
        "skill_name": str,       # Skill 名称
        "description": str       # Skill 描述
    }
]
```

**当前可用 Skill**:
- `skill-creator`: 创建技能
- `skill-installer`: 安装技能

---

### 7. load_skill

加载并执行 Agent Skill。

**参数**:
- `skill_name` (string, required): Skill 名称
- `skill_args` (object, optional): Skill 参数

**返回值**:
```python
{
    "success": bool,
    "message": str,
    "skill_name": str,
    "skill_args": dict
}
```

**当前状态**: v0.1 版本为占位实现，返回固定消息 "v0.1 未接入真实技能执行引擎"。

**未来规划**:
- 支持动态加载 Skill 模块
- Skill 参数验证
- Skill 执行沙箱
- Skill 市场和版本管理

---

## 工具执行流程

### 1. 工具调用请求

LLM 返回工具调用时，AgentRuntime 发布 `tool.call_requested` 事件：

```python
{
    "type": "tool.call_requested",
    "payload": {
        "tool_call_id": "call_abc123",
        "tool_name": "bash_command",
        "arguments": {"command": "ls -la"}
    }
}
```

### 2. 工具执行

ToolRuntime 接收事件并执行：

1. 发布 `tool.call_started` 事件
2. 发布 `tool.execution_start` 事件
3. 调用 `Tool.execute(**arguments)`，带超时控制
4. 发布 `tool.execution_end` 事件
5. 发布 `tool.call_completed` 事件

### 3. 结果处理

工具执行结果会：
- 添加到消息历史（role: "tool"）
- 发送给 LLM 进行下一轮推理
- 如果结果超长（>16000 tokens），自动截断并保存到文件

## 超时控制

所有工具都有超时限制，默认15秒。可通过配置文件修改：

```yaml
tools:
  bash_command:
    timeout: 30
  serper_search:
    timeout: 20
```

超时时，工具执行会被取消，返回错误信息。

## 结果截断机制

当工具返回结果过长时（超过约16000 tokens），ToolRuntime 会：

1. 保存完整结果到文件：`<workspace>/<session_id>/tool_result_<id>.txt`
2. 截断结果并附加文件路径提示
3. 将截断后的结果返回给 LLM

这样既避免了 token 超限，又保留了完整数据供后续使用。

## 安全考虑

### v0.1 版本限制

- ❌ 无命令白名单/黑名单
- ❌ 无文件访问权限检查
- ❌ 无资源使用限制
- ❌ 无沙箱执行环境

### 未来增强

- 命令执行沙箱（Docker/Firecracker）
- 文件访问权限控制
- 网络访问白名单
- 资源配额管理（CPU/内存/磁盘）
- 工具调用审计日志

## 扩展自定义工具

### 1. 定义工具类

```python
from app.tools.base import Tool
from typing import Any

class MyCustomTool(Tool):
    name = "my_tool"
    description = "我的自定义工具"
    parameters = {
        "type": "object",
        "properties": {
            "param1": {"type": "string", "description": "参数1"}
        },
        "required": ["param1"]
    }

    async def execute(self, **kwargs: Any) -> Any:
        param1 = kwargs.get("param1")
        # 执行逻辑
        return {"result": f"处理了 {param1}"}
```

### 2. 注册工具

```python
from app.tools.registry import ToolRegistry

registry = ToolRegistry()
registry.register(MyCustomTool())
```

### 3. 配置超时

```yaml
tools:
  my_tool:
    timeout: 20
```

## 总结

内置工具是 AgentOS 的核心能力之一，通过统一的接口和事件驱动机制，实现了灵活的工具调用和结果处理。v0.1 版本提供了7个基础工具，为后续扩展奠定了基础。
