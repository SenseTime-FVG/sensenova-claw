# 集思录搜索

集思录（jisilu.cn）金融投资数据搜索，通过网页抓取获取可转债、基金等金融信息，无需 API Key。

## 使用方式

```bash
python scripts/jisilu/jisilu_no_api.py "可转债" -m 10
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
| `engine` | 引擎标识 (`jisilu`) |

## 编程调用

```python
from scripts.jisilu.jisilu_no_api import search_jisilu
results = search_jisilu("可转债", max_results=10)
```
