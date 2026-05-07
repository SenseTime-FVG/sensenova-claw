# 微博搜索

通过 TikHub API 搜索微博内容，支持高级过滤和排序。

**需要 API Key：** `TIKHUB_TOKEN` 环境变量

## 使用方式

```bash
python scripts/weibo/tikhub_weibo_search.py "人工智能" --limit 10
```

## 参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `keyword` | 搜索关键词（位置参数或 `--keyword`） | — |
| `--token` | TikHub API Token | 环境变量 `TIKHUB_TOKEN` |
| `--search-type` | 搜索类型 (`hot`/`normal`) | 无 |
| `--include-type` | 内容类型过滤 (`pic`/`video`) | 无 |
| `--timescope` | 时间范围（如 `2024-01-01:2024-12-31`） | 无 |
| `--page` | 页码 | 1 |
| `--limit` | 结果数量限制 | 无 |
| `--host` | API 主机地址 | `api.tikhub.io` |
| `--timeout` | 请求超时（秒） | 30 |
| `--pretty` | 格式化 JSON 输出 | 否 |
| `--env-file` | 自定义 .env 文件路径 | 无 |

## 输出字段

| 字段 | 说明 |
|------|------|
| `text` | 微博内容 |
| `user` | 用户信息（昵称、粉丝数等） |
| `reposts_count` | 转发数 |
| `comments_count` | 评论数 |
| `attitudes_count` | 点赞数 |
| `pics` | 图片列表 |
| `created_at` | 发布时间 |

## 响应存档

原始 API 响应自动保存到 `responses/` 目录，同时生成过滤后的精简版本。

## 编程调用

```python
from scripts.weibo.tikhub_weibo_search import main
# 通过命令行参数调用
```
