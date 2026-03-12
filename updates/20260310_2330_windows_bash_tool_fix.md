# Windows 环境 bash_command 工具修复

**日期**: 2026-03-10 23:30

---

## 变更概述

1. **Bug 修复**：`bash_command` 工具在 Windows 上因事件循环不兼容导致所有命令执行失败
2. **改进**：工具执行错误信息补全，避免异常消息为空时丢失诊断信息

---

## 一、问题现象

所有 `bash_command` 工具调用均返回 `success: False`，但错误信息为空：

```
tool.call_result payload={
    'tool_name': 'bash_command',
    'result': '工具执行失败: ',
    'success': False,
    'error': ''
}
```

涉及的命令包括 `cd`、`pwd`、`dir`、`echo "hello"`、`python --version` 等，全部失败。
而 `read_file`、`write_file` 等不依赖子进程的工具正常工作。

---

## 二、根因分析

### 异常堆栈

```
NotImplementedError
  at base_events.py:528  _make_subprocess_transport
  at subprocess.py:211   create_subprocess_shell
  at builtin.py:30       BashCommandTool.execute
```

### 原因

`asyncio.create_subprocess_shell()` 在 Windows 上需要 `ProactorEventLoop`，
但 `uvicorn[standard]` 在 Windows 上使用了 `SelectorEventLoop`，
该事件循环未实现 `_make_subprocess_transport`，直接抛出 `NotImplementedError`。

由于 `str(NotImplementedError())` 返回空字符串，错误信息被"吞掉"了。

---

## 三、修复内容

### 3.1 BashCommandTool 兼容修复

**文件**: `backend/app/tools/builtin.py`

将 `asyncio.create_subprocess_shell` 替换为 `subprocess.run` + `asyncio.to_thread`：

```python
# 修复前（依赖特定事件循环，Windows 下 NotImplementedError）
proc = await asyncio.create_subprocess_shell(
    command, cwd=cwd,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
)
out, err = await proc.communicate()

# 修复后（跨平台兼容，线程池执行不阻塞事件循环）
def _run() -> dict[str, Any]:
    proc = subprocess.run(
        command, cwd=cwd, shell=True,
        capture_output=True, timeout=300,
    )
    return {
        "return_code": proc.returncode,
        "stdout": proc.stdout.decode("utf-8", errors="replace"),
        "stderr": proc.stderr.decode("utf-8", errors="replace"),
    }
return await asyncio.to_thread(_run)
```

**兼容性说明**：
- `subprocess.run(shell=True)` 在 Linux/macOS 调用 `/bin/sh -c`，Windows 调用 `cmd.exe /c`，行为一致
- `asyncio.to_thread()` 是 Python 3.9+ 标准 API，所有平台通用
- 接口和返回值完全不变，对上层调用者透明

### 3.2 错误信息补全

**文件**: `backend/app/runtime/workers/tool_worker.py`

```python
# 修复前：str(NotImplementedError()) 返回空字符串
error = str(exc)

# 修复后：空消息时退而使用异常类名
error = str(exc) or f"{type(exc).__name__}"
```

---

## 四、测试验证

修复后在 Windows 环境测试，之前全部失败的命令均正常返回：

```
>>> BashCommandTool().execute(command='cd')
{'return_code': 0, 'stdout': 'D:\\code\\agentos\\backend\r\n', 'stderr': ''}

>>> BashCommandTool().execute(command='python --version')
{'return_code': 0, 'stdout': 'Python 3.12.11\r\n', 'stderr': ''}

>>> BashCommandTool().execute(command='where python')
{'return_code': 0, 'stdout': 'D:\\code\\agentos\\backend\\.venv\\Scripts\\python.exe\r\n...', 'stderr': ''}

>>> BashCommandTool().execute(command='echo hello')
{'return_code': 0, 'stdout': 'hello\r\n', 'stderr': ''}
```

---

## 五、影响范围

| 文件 | 改动 |
|------|------|
| `backend/app/tools/builtin.py` | BashCommandTool.execute 实现替换 |
| `backend/app/runtime/workers/tool_worker.py` | 异常错误信息补全 |

对 Linux/macOS 无负面影响，行为完全兼容。
