# 下载器

基于 yt-dlp 的视频/音频下载工具，可从搜索结果 JSON 中提取 URL 并批量下载。

**依赖：** `pip install yt-dlp`

## 功能

- 从搜索结果 JSON 文件中自动提取可下载 URL
- 支持 YouTube、Bilibili、抖音等平台
- 支持视频下载和纯音频提取
- 支持代理、Cookie、dry-run 模式

## 编程调用

```python
from scripts.downloader.yt_dlp_downloader import (
    collect_urls_from_search_output,
    build_download_candidates,
    run_yt_dlp_download,
)

# 从搜索结果 JSON 提取 URL
urls = collect_urls_from_search_output("responses/youtube_results.json")

# 构建下载候选
candidates = build_download_candidates(urls)

# 执行下载
run_yt_dlp_download(
    candidates,
    output_dir="downloads/",
    audio_only=False,
    proxy=None,
)
```

## 配置

| 环境变量 | 说明 |
|----------|------|
| `YTDLP_COOKIES_FILE` | YouTube Cookie 文件路径（可选） |

## 注意事项

- 此模块为库函数，没有独立的 CLI 入口
- 默认下载超时 1 小时
- 支持 `--select` 索引过滤和 `--limit` 限制下载数量
