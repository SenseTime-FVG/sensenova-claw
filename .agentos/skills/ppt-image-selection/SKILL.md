---
name: ppt-image-selection
description: "根据 outline.json 中的 needed_pictures，为 PPT 页面执行图片检索、筛选与本地下载。当任务需要基于页面大纲、search caption 和图片候选结果，选出每个图片槽位最合适的图片并将其下载到 deck 目录中时，使用本技能。"
---

# PPT 图片检索与筛选

你负责为 PPT 大纲中的图片槽位查找、筛选并下载合适的候选图片。

这个技能位于 `ppt-outline-gen` 之后、`ppt-html-gen` 之前。

当任务已经具备以下输入时，使用本技能：

- `outline.json`
- deck 目录
- 可选的 `brief.md`
- 可选的 `style.json`

如果大纲中没有 `needed_pictures`，就不要使用本技能。

## 核心目标

围绕 `outline.json` 中的 `needed_pictures`：

1. 为每个图片槽位构造搜图 query
2. 使用 `image_search` 获取候选图片
3. 先把高优先级候选逐张下载并校验
4. 只从下载成功的候选集合中做最终选择
5. 为每个槽位最多保留 1 张最终通过的本地图片
6. 将原始候选和筛选结果保存在 deck 目录中

## 产物要求

本技能的产物必须和 `brief.md`、`style.json`、`outline.json`、最终 `page_XX.html` 保存在同一个 deck 目录中。

至少保存：

- `image_search_results.json`
- `image_selection.json`
- `images/` 目录下的本地图片文件

如果某个图片槽位没有找到合适图片，也必须记录在 `image_selection.json` 中，不能静默丢失。

## 所需输入

你应当具备：

- `outline`
- `deck_dir`

可选输入：

- `brief`
- `style`

## 工作流

总原则：

- 先下载验证，再做最终选择。
- 最终选择只能从下载成功且校验通过的候选集合中产生。
- 不能先选中一个远程 URL 再赌它之后能下载成功。

### 1. 提取待补图片

从 `outline.json` 的每一页中提取 `needed_pictures`。

对每个补图项，至少保留这些上下文字段：

- `page_id`
- `page_title`
- `page_type`
- `picture_id`
- `caption`
- `tag`
- `size`
- 当前页的核心内容摘要

补充语言规则：

- `outline.json` 里的 `caption`、`description`、`tag` 若是中文，就保持中文作为源信息，不要回写成英文。
- 如果为了提升搜图效果需要将中文 caption 改写成英文 query，这只发生在内部搜索 query 层，不要改动大纲原始字段的语言。

### 2. 生成搜图 query

优先直接使用 `caption` 作为主 query。

必要时可追加非常少量上下文词，帮助结果更贴近页面主题，例如：

- 演示主题中的核心实体
- 行业或场景词
- 风格词

规则：

- query 必须保持单意图、短语化
- 不要把整页大纲直接拼进 query
- 不要加入长句、抽象口号或事实断言
- 背景图可以用更宽泛的场景描述，但仍要和页面主题相关
- 可以将中文 caption 转成更适合图片搜索的英文短语，但 `image_selection.json` 中应继续保留原始 caption/tag 的源语言信息

### 3. 调用 `image_search`

对每个图片槽位调用 `image_search` 获取候选结果。

建议保留 top-k 候选，不要在这个阶段过早手工裁掉。

将原始候选按槽位写入 `image_search_results.json`。

推荐结构：

```json
{
  "page3.hero_image": {
    "query": "OpenAI logo official high resolution",
    "results": []
  }
}
```

## 4. 候选筛选与下载优先级

你要判断每张候选图片是否适合当前 PPT 页面。

筛选只看 2 个标准：

1. `search_key_relevance`
2. `outline_relevance`

### 4.1 关键词相关性

判断候选图片是否与 `caption/search_key` 的核心概念相关。

### 4.2 页面大纲相关性

判断候选图片是否与当前页面大纲内容语义相关。

规则：

- 只有当图片和页面完全无关时，才判为不相关
- 如果图片与 `search_key` 明显相关，通常也应视为与页面相关
- 忽略图表字段，只关注页面主题、标题、文本要点和图片槽位用途

### 4.3 候选通过判定

- 只有两个标准都通过，候选图片才算通过
- 任一标准不通过，`final_decision` 必须为不通过

输出理由必须简短具体，尤其要说明不通过原因。

### 4.4 可下载性与稳定性过滤

在进入最终选择前，必须先判断候选图片是否适合作为可落地的本地资产，并按优先级逐张尝试下载。

优先保留：

- 直接指向静态图片资源的 URL
- 常见图片扩展名结尾或明显可下载的 CDN 图片链接
- 来源稳定、无需登录、无需脚本执行即可访问的站点

优先淘汰：

- 社交平台抓取代理、临时预览链接、crawler/lookaside 类链接
- 需要登录、鉴权、重定向链过长或明显依赖页面脚本的资源
- 强水印、明显缩略图、分辨率过低的资源
- 版权或商用风险明显较高的图库预览图

如果一个候选图语义很相关，但下载稳定性很差，也不应作为最终图。

### 4.5 下载验证队列

对每个图片槽位，先形成一个“候选通过列表”，然后按优先级逐张执行下载与校验。

规则：

- 每次只尝试 1 张候选图，下载成功并校验通过后，再决定它是否成为最终图。
- 下载失败、内容失效、文件损坏、尺寸过小、强水印等情况，都应把该候选记入 `rejected_candidates`，并继续尝试下一个候选。
- 如果前一轮候选全部下载失败，再重新搜索，不要把失败 URL 直接带入最终产物。

## 5. 最终选图

每个图片槽位最多保留 1 张最终图片。

优先级：

1. 与槽位语义最贴合
2. 与页面主题最贴合
3. 可直接稳定下载到本地
4. 画面更通用、更适合演示排版
5. 来源更清晰

最终选择规则：

- 这里的“最终图片”只能是已经下载成功并通过校验的本地文件。
- 如果有多个本地成功候选，再从这些成功候选里按语义、排版适配度和来源质量选 1 张。
- 不要把“最喜欢但没下载成功”的远程图标记为 `selected`。

背景图规则：

- 背景图可以更强调氛围和场景
- 只要和页面主题不冲突、可读性可控，就可以保留

## 6. 下载与可用性验证

不要先选中图片，再把远程 `image_url` 交给 HTML 阶段。

必须先把图片下载到 deck 目录下，例如：

- `deck_dir/images/page2_openclaw_logo_concept.png`
- `deck_dir/images/page3_software_architecture_diagram.jpg`

优先使用简单、可审计的命令行下载方式，并且必须带失败退出和超时：

- `curl -L --fail --connect-timeout 10 --max-time 30 --output ... URL`
- 或 `wget -O ... URL`

必要时可通过 `execute_shell_command` 或 `execute_jupyter_code` 执行下载。

规则：

- 必须校验下载命令退出码
- 必须确认本地文件真实存在且非空
- 必须逐张下载，不要把多个候选图拼成一个超长命令后再统一等待
- 如果下载失败，不能继续沿用该 URL；应切换到下一个候选图或重新搜索
- 如果候选图页面能打开但直链无法下载，也算失败，不能当作最终图
- 如果下载后的文件过小、内容不是图片、或明显是失效占位图，也算失败
- 只有下载成功的图片才能写入最终 `image_selection.json`

推荐额外校验：

- 文件扩展名和内容类型基本一致
- 尺寸过小、明显是缩略图、带强水印的图片优先淘汰
- 无法稳定访问的站点链接优先淘汰
- 下载后优先检查文件大小、`file` 结果或等价方式确认其确实是图片

推荐下载策略：

1. 先为每个槽位保留 2-3 个候选图
2. 按优先级逐个尝试下载
3. 只有在成功下载集合里完成最终比较后，才把其中 1 张写成 `selected_image`
4. 如果前 2-3 个候选图都失败，再重新搜索，不要硬用失败 URL

## 7. 输出结构

将筛选结果写入 `image_selection.json`。

每个槽位至少包含：

- `page_id`
- `picture_id`
- `query`
- `tag`
- `selected`
- `selected_image`
- `rejected_candidates`
- `status`
- `reason`

推荐结构：

```json
{
  "page3.hero_image": {
    "page_id": "page3",
    "picture_id": "hero_image",
    "query": "OpenAI logo official high resolution",
    "tag": "主视觉",
    "selected": true,
    "selected_image": {
      "title": "",
      "image_url": "",
      "local_path": "",
      "source_page": "",
      "source_domain": ""
    },
    "rejected_candidates": [],
    "status": "selected",
    "reason": "与页面主题和图片槽位语义一致"
  }
}
```

额外要求：

- `selected_image.local_path` 必须指向 deck 目录下真实存在的本地图片文件。
- 如果某个槽位没有成功下载任何图片，`selected` 必须为 `false`，并用 `status` / `reason` 明确记录失败原因。
- `image_selection.json` 中不得只写“页面 -> 远程图片路径”的简化映射。

如果没有合适图片：

- `selected` 设为 `false`
- `status` 设为 `unresolved`
- `selected_image` 设为 `null`
- 明确写出原因

## 8. 与 HTML 阶段的接口约定

本技能必须把最终通过的图片下载到本地，再交给 HTML 阶段。

因此：

- `selected_image.local_path` 必须是真实可读的本地路径
- `selected_image.image_url` 只作为来源记录，不应再被 HTML 阶段直接消费
- 不要把远程 URL 当成本地图片交付
- 如果所有候选图都无法下载成功，就把该槽位标为 `unresolved`
- HTML 阶段优先消费 `local_path`，而不是 `image_url`

## 最终规则

- 只在大纲确实存在 `needed_pictures` 时运行
- `image_search_results.json` 和 `image_selection.json` 必须写入 deck 目录
- 通过筛选的图片必须下载到 `images/` 子目录
- 每个图片槽位都要有结果记录
- 不要跳过筛选，直接把第一张图当最终图
- 不要把网络图片伪装成本地图片文件
- 不要把下载失败的图片标记成 `selected`
