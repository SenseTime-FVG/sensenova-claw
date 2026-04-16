# 今日头条搜索

今日头条（字节跳动新闻资讯平台）搜索，通过网页抓取获取结果，无需 API Key。

## 使用方式

```bash
python scripts/toutiao/toutiao_no_api.py "人工智能" -m 10
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
| `engine` | 引擎标识 (`toutiao`) |

## 编程调用

```python
from scripts.toutiao.toutiao_no_api import search_toutiao
results = search_toutiao("人工智能", max_results=10)
```
