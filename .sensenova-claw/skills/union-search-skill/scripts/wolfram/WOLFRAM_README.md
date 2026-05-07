# Wolfram Alpha 搜索

Wolfram Alpha 计算知识引擎，通过网页抓取获取结果，无需 API Key。

> 注意：需要代理才能访问（`REQUIRES_PROXY = True`）。Wolfram Alpha 返回的是计算结果而非网页链接，`href` 字段可能为空。

## 使用方式

```bash
python scripts/wolfram/wolfram_no_api.py "integrate x^2" -m 10
```

## 参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `query` | 查询表达式（必填） | — |
| `-m/--max-results` | 最大结果数 | 10 |
| `--proxy` | 代理地址（推荐设置） | 环境变量 `NO_API_KEY_PROXY` |
| `--json` | JSON 格式输出 | 否 |

## 输出字段

| 字段 | 说明 |
|------|------|
| `title` | 结果分类（如 "Result", "Plot"） |
| `href` | 链接地址（通常为空） |
| `body` | 计算结果内容 |
| `engine` | 引擎标识 (`wolfram`) |

## 编程调用

```python
from scripts.wolfram.wolfram_no_api import search_wolfram
results = search_wolfram("integrate x^2", max_results=10, proxy="http://127.0.0.1:7890")
```
