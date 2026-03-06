# TUI 手动测试指南

## 前提条件

确保后端服务已启动：
```bash
# 在项目根目录
npm run dev
```

## 启动 TUI

在新终端中运行：

```bash
cd backend
source ~/miniconda3/bin/activate base
uv run python run_tui.py --port 8000
```

或使用模块方式：
```bash
cd backend
source ~/miniconda3/bin/activate base
uv run python -m app.gateway.channels.tui_channel --port 8000
```

## 测试场景

### 测试1: 工具调用

在TUI中输入：
```
搜索苏超冠军是谁
```

**预期结果：**
- 看到 `Tool: serper_search 执行中...`
- 看到 `Tool: serper_search 完成`
- 看到 Assistant 的回复，包含搜索结果

### 测试2: 多轮对话

继续在TUI中输入：
```
我第一个问题是什么
```

**预期结果：**
- 看到 Assistant 回复，提到之前关于"苏超冠军"的问题

### 测试3: 普通对话

输入：
```
你好，介绍一下你自己
```

**预期结果：**
- 看到 Assistant 的自我介绍

## 界面说明

```
┌─────────────────────────────────────────────────────────┐
│ TUIApp                                                   │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  [15:30:45] User: 搜索苏超冠军是谁                      │
│  [15:30:46] Tool: serper_search 执行中...               │
│  [15:30:48] Tool: serper_search 完成                    │
│  [15:30:50] Assistant: 根据搜索结果...                  │
│                                                          │
├─────────────────────────────────────────────────────────┤
│ > 输入你的问题...                                        │
└─────────────────────────────────────────────────────────┘
```

## 退出 TUI

按 `Ctrl+C` 退出

## 自动化测试

运行自动化测试脚本：
```bash
cd backend
source ~/miniconda3/bin/activate base
uv run python test_tui.py
```

测试脚本会自动执行上述测试场景并输出结果。
