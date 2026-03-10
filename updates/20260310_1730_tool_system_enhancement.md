# 工具系统增强更新

**日期**: 2026-03-10 17:30
**依据**: docs/16_tool_system_enhancement.md

---

## 变更概述

根据工具系统增强 PRD，完成三项改进：结果截断统一、write_file 增强、工具权限管理。

---

## 一、工具结果截断统一 (P0)

### 改动文件
- `backend/app/runtime/workers/tool_worker.py` — `_truncate_result` 方法
- `backend/app/tools/builtin.py` — `FetchUrlTool.execute`
- `backend/app/core/config.py` — DEFAULT_CONFIG

### 改动内容
1. **ToolRuntime 层截断阈值**：从 `16000 * 3` 字符改为配置可控，默认 `8000 * 3` 字符
   - 新增配置项 `tools.result_truncation.max_tokens`（默认 8000）
   - 新增配置项 `tools.result_truncation.save_dir`（默认 "workspace"）
   - 截断提示文案改为 `[内容已截断] 完整结果已保存到: {file_path}`

2. **FetchUrlTool 内存保护**：
   - 配置项 `tools.fetch_url.max_size_mb` 重命名为 `tools.fetch_url.max_response_mb`
   - 默认阈值从 5MB 调整到 10MB（仅作 OOM 防线）
   - 工具层不再关心 token 限制，由 ToolRuntime 统一截断

### 两层截断职责分工
| 层次 | 位置 | 目的 | 阈值 |
|------|------|------|------|
| 内存保护 | FetchUrlTool 内部 | 防止 OOM | 10MB |
| Token 截断 | ToolSessionWorker | 控制传给 LLM 的文本长度 | 8000 tokens |

---

## 二、write_file 增强 (P0)

### 改动文件
- `backend/app/tools/builtin.py` — `WriteFileTool`

### 改动内容
1. 新增 `mode=insert` 模式，支持 `start_line` 和 `end_line` 参数
2. 返回值新增 `mode` 字段

### 模式说明
| 模式 | 参数 | 行为 |
|------|------|------|
| `write`（默认） | 无 | 全量覆盖 |
| `append` | 无 | 追加到文件末尾 |
| `insert` | `start_line` | 纯插入，原内容下移 |
| `insert` | `start_line` + `end_line` | 替换 [start_line, end_line] 范围 |

### 边界处理
- 文件不存在时 `insert` 模式等同于 `write`
- `start_line` 从 1 开始
- `end_line` 包含在替换范围内

---

## 三、工具权限管理 (P1)

### 改动文件
- `backend/app/tools/base.py` — 新增 `ToolRiskLevel` 枚举，`Tool` 基类新增 `risk_level` 属性
- `backend/app/tools/builtin.py` — 各工具设置风险等级
- `backend/app/events/types.py` — 新增 `TOOL_CONFIRMATION_REQUESTED` / `TOOL_CONFIRMATION_RESPONSE`
- `backend/app/runtime/workers/tool_worker.py` — 新增权限确认机制
- `backend/app/core/config.py` — 新增 `tools.permission` 配置段

### 风险等级分配
| 工具名 | 风险等级 | 理由 |
|--------|---------|------|
| `serper_search` | LOW | 只读，无副作用 |
| `fetch_url` | LOW | 只读，无副作用 |
| `read_file` | LOW | 只读，无副作用 |
| `write_file` | MEDIUM | 写文件，有副作用但可控 |
| `bash_command` | HIGH | 执行任意命令，风险最高 |

### 确认流程
1. `ToolSessionWorker._handle_tool_requested` 找到工具后调用 `_needs_confirmation(tool)`
2. 若需要确认，调用 `_request_confirmation(event, tool)`：
   - 发布 `tool.confirmation_requested` 事件（含工具参数、风险等级、提示消息）
   - 通过 `asyncio.Event` 挂起等待用户响应
3. 用户通过 `tool.confirmation_response` 事件回复（`approved: bool`）
4. `_handle_confirmation_response` 唤醒挂起的任务
5. 超时自动拒绝（默认 60 秒）
6. 拒绝时向 LLM 返回 "用户拒绝执行该工具"

### 配置项（默认关闭）
```yaml
tools:
  permission:
    enabled: false
    auto_approve_levels: ["low"]
    confirmation_timeout: 60
```

---

## 四、新增测试

### 文件
- `backend/tests/test_tool_system.py` — 20 个测试用例

### 测试覆盖
| 类别 | 数量 | 覆盖内容 |
|------|------|---------|
| 风险等级 | 5 | 5 个内置工具的风险等级验证 |
| write_file | 6 | write/append/insert/replace/不存在/默认模式 |
| 截断 | 2 | 短结果不截断、长结果截断 |
| 权限管理 | 7 | 开关、各风险等级判断、确认响应/拒绝 |

### 测试结果
```
20 passed in 0.89s
```

---

## 五、配置变更汇总

```yaml
# 新增/变更的配置项
tools:
  fetch_url:
    max_response_mb: 10          # 原 max_size_mb: 5，重命名 + 调整阈值

  result_truncation:             # 新增
    max_tokens: 8000
    save_dir: "workspace"

  permission:                    # 新增
    enabled: false
    auto_approve_levels: ["low"]
    confirmation_timeout: 60
```
