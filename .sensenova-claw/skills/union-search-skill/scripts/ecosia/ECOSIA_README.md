# Ecosia 搜索

Ecosia 环保搜索引擎，通过网页抓取获取结果，无需 API Key。

> 注意：需要代理才能访问（`REQUIRES_PROXY = True`）

## 使用方式

```bash
python scripts/ecosia/ecosia_no_api.py "renewable energy" -m 10
```

## 参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `query` | 搜索关键词（必填） | — |
| `-m/--max-results` | 最大结果数 | 10 |
| `--proxy` | 代理地址（推荐设置） | 环境变量 `NO_API_KEY_PROXY` |
| `--json` | JSON 格式输出 | 否 |

## 输出字段

| 字段 | 说明 |
|------|------|
| `title` | 结果标题 |
| `href` | 链接地址 |
| `body` | 摘要内容 |
| `engine` | 引擎标识 (`ecosia`) |

## 编程调用

```python
from scripts.ecosia.ecosia_no_api import search_ecosia
results = search_ecosia("renewable energy", max_results=10, proxy="http://127.0.0.1:7890")
```
