# Yandex 搜索

通过 SerpAPI 调用 Yandex 搜索引擎，支持语言和地区设置。

**需要 API Key：** `SERPAPI_API_KEY_YANDEX` 或 `SERPAPI_API_KEY` 环境变量

**依赖：** `pip install google-search-results`

## 使用方式

```bash
python scripts/yandex/yandex_search.py "machine learning" -m 10
```

## 参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `query` | 搜索关键词（必填） | — |
| `-m/--max-results` | 最大结果数 | 10 |
| `-p/--page` | 页码 | 1 |
| `--yandex-domain` | Yandex 域名 | `yandex.com` |
| `-l/--lang` | 搜索语言 | `en` |
| `--lr` | 地区代码 | `84` |
| `--api-key` | SerpAPI Key | 环境变量 |
| `--json` | JSON 格式输出 | 否 |
| `--pretty` | 格式化 JSON 输出 | 否 |

## 输出字段

| 字段 | 说明 |
|------|------|
| `title` | 结果标题 |
| `link` | 链接地址 |
| `snippet` | 摘要内容 |
| `position` | 结果排名 |

## 编程调用

```python
from scripts.yandex.yandex_search import YandexSerpApiSearch
client = YandexSerpApiSearch(api_key="your-key")
results = client.search("machine learning", max_results=10)
```
