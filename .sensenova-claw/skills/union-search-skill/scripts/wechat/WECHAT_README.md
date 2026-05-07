# 微信公众号搜索

通过搜狗微信搜索（weixin.sogou.com）抓取微信公众号文章，无需 API Key。

## 使用方式

```bash
python scripts/wechat/wechat_no_api.py "人工智能" -m 10
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
| `title` | 文章标题 |
| `href` | 文章链接 |
| `body` | 摘要内容 |
| `engine` | 引擎标识 (`wechat`) |

## 编程调用

```python
from scripts.wechat.wechat_no_api import search_wechat
results = search_wechat("人工智能", max_results=10)
```
