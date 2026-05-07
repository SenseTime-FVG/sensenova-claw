# 360 搜索

360 搜索引擎（so.com），通过网页抓取获取结果，无需 API Key。

## 使用方式

```bash
python scripts/so360/so360_no_api.py "人工智能" -m 10
```

## 参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `query` | 搜索关键词（必填） | — |
| `-m/--max-results` | 最大结果数 | 10 |
| `--proxy` | 代理地址 | 无 |
| `--json` | JSON 格式输出 | 否 |

## 输出字段

| 字段 | 说明 |
|------|------|
| `title` | 结果标题 |
| `href` | 链接地址 |
| `body` | 摘要内容 |
| `engine` | 引擎标识 (`so360`) |

## 编程调用

```python
from scripts.so360.so360_no_api import search_so360
results = search_so360("人工智能", max_results=10)
```
