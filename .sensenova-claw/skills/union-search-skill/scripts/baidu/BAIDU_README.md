# 百度搜索

提供两种百度搜索方式：无需 API Key 的网页抓取版本，以及基于百度千帆 API 的版本。

## 搜索方式

### 1. 无需 API Key（网页抓取）

通过抓取百度搜索页面获取结果，无需任何凭据。

```bash
python scripts/baidu/baidu_no_api.py "人工智能" -m 10
```

**参数：**

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `query` | 搜索关键词（必填） | — |
| `-m/--max-results` | 最大结果数 | 10 |
| `--proxy` | 代理地址 | 无 |
| `--json` | JSON 格式输出 | 否 |

### 2. 百度千帆 API

使用百度千帆大模型平台的搜索 API，返回更结构化的结果。

```bash
python scripts/baidu/baidu_search.py "人工智能" -l 10
```

**环境变量：** `BAIDU_QIANFAN_API_KEY`（bce-v3 格式）

**参数：**

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `query` | 搜索关键词（必填） | — |
| `-l/--limit` | 返回结果数量（最大 50） | 10 |
| `--key` | 手动指定 API Key | 无 |
| `--json` | JSON 格式输出 | 否 |

## 输出字段

### 无需 API Key 版

| 字段 | 说明 |
|------|------|
| `title` | 结果标题 |
| `href` | 链接地址 |
| `body` | 摘要内容 |
| `engine` | 引擎标识 (`baidu`) |

### 千帆 API 版

| 字段 | 说明 |
|------|------|
| `title` | 结果标题 |
| `url` | 链接地址 |
| `description` | 内容描述 |
| `date` | 发布日期 |
| `type` | 结果类型 |
| `score` | 重排分数 |

## 编程调用

```python
# 无需 API Key
from scripts.baidu.baidu_no_api import search_baidu
results = search_baidu("人工智能", max_results=10)

# 千帆 API
from scripts.baidu.baidu_search import BaiduSearch
client = BaiduSearch(api_key="your-key")
results = client.search("人工智能", limit=10)
```
