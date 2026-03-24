---
name: ppt-page-assets
description: 当只需要修复某一页或某个槽位的图片、插图、图标或背景资产，而其他页面无需重算时使用。
---

# PPT 单页资产修复

## 目标

针对单页或单槽位更新 `asset-plan.json`，必要时重新生成：

- `image_search_results.json`
- `image_selection.json`
- 对应的本地图片文件

所有修复结果仍必须落回同一个 `deck_dir`。

## 适用场景

- 只换封面图
- 只换第 5 页 hero 图
- 某个槽位下载失败
- 某张图与页面语义不符

## 关键原则

- 消费前必须先确认 `task-pack.json`、`asset-plan.json` 以及相关 `storyboard.json` 真实存在且可读。
- 如果目标文件不存在、槽位记录缺失或本地路径失效，先补齐依赖，不要猜测。
- 优先保留其他槽位和页面不变。
- 更新后必须保持本地路径可读。
- 单页修复也必须保留搜图候选、筛选理由和下载结果，不能只留下最后一张图。
- 如果前一批候选全部失败，应重新搜索并覆盖对应槽位的 `image_search_results.json` / `image_selection.json` 记录。
- 不要跳过筛选过程，直接手工指定一张远程图片结束任务。
- 不要把失败的远程 URL 标成已完成。
