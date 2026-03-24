---
name: union-search-plus
description: 这是一个“统一多平台搜索执行 skill”。当需要跨多个平台搜索、补充更多来源、搜索社交媒体/社区/开发者平台内容，或在主链结果不足时扩大覆盖面时使用。它负责执行多平台搜索、规范化输出、保留可用来源，并在部分平台失败时继续返回结果。
metadata:
  sensenova-claw:
    requires:
      bins:
        - python3
        - bash
---

# union-search-plus（统一多平台搜索执行）

这是一个“多平台搜索执行 skill”，不是研究编排 skill。

它的职责是：

- 执行跨平台、跨来源的搜索
- 按搜索分组或指定平台扩展来源覆盖面
- 将多平台结果整理为统一结构
- 在部分平台失败时保留可用结果并说明限制
- 为上层 research、搜索或报告流程提供更丰富的证据池

它不负责：

- 判断用户需求是否属于复杂 research
- 规划研究问题、确认研究范围
- 生成完整研究大纲
- 最终整合成结论报告

这些属于 `research-union` 或上层 agent 的职责。

## 何时使用

以下场景优先使用本技能：

- 用户明确要求“多平台搜索”“全网补充来源”“扩大搜索覆盖面”
- 需要搜索社交媒体、社区、开发者平台、图片或其他非单一搜索引擎来源
- 普通主链搜索结果不足，需要补充更多来源
- 需要按 group 或指定平台执行搜索，而不是只依赖单一来源

以下场景通常不要使用本技能：

- 单点事实查询，普通搜索已经足够
- 只需要一个网页摘要或几个链接
- 需要完整研究流程、用户确认和最终报告整合
- 本地文件或现有上下文已足够回答问题

## 使用方式

本技能支持两类常见用法。

### 1. 直接多平台搜索

适合：

- 用户明确要求跨平台搜索
- 用户指定某类来源或平台
- 需要从开发者社区、社交媒体、通用搜索引擎等多个渠道收集结果

执行原则：

- 按查询主题选择合适的 group 或平台
- 优先使用最贴近问题的来源，而不是盲目全量搜索
- 如果用户明确要求更大覆盖面，再扩大到更多 group 或更多平台

### 2. 作为补充搜索来源

适合：

- 主链结果来源不足
- 主链结果覆盖面不足
- 主链缺少某类来源，例如社媒、开发者平台、社区讨论

在这种用法下，本技能常被 `research-union` 调用，用来补充来源，而不是替代 research 编排。

## 执行原则

### 来源选择

- 优先按问题类型选择合适的 group 或平台
- 不要默认一上来就执行最大范围搜索
- 只有在结果明显不足、用户明确要求、或上层流程需要扩大覆盖时，才继续扩展范围

### 失败降级

- 某个平台失败，不等于整个搜索失败
- 保留成功平台的结果
- 在输出中说明哪些平台失败、哪些结果可用
- 不要把“平台失败”误写成“没有相关信息”

### 输出整理

- 结果应统一为标准结构
- 保留最关键字段：`title`、`link`、`source`
- 若可用，补充 `snippet`、`provider`、`group`
- 若脚本输出了原始文件或原始响应路径，也应保留，便于后续追溯

## 推荐执行流程

### 场景 A：直接搜索

1. 理解用户想要哪类来源
2. 选择最合适的 group 或平台
3. 执行搜索
4. 统一去重、整理结果
5. 返回结构化结果，并说明覆盖范围与限制

### 场景 B：补充来源

1. 读取主链已有结果
2. 判断缺的是哪类来源或覆盖面
3. 选择合适的 group 或平台补充搜索
4. 合并、去重、重排结果
5. 返回补充后的统一结果

## 可调用脚本

### 统一搜索入口

```bash
python3 .sensenova-claw/skills/union-search-plus/scripts/union_search_plus.py \
  "用户问题" \
  --group preferred \
  --limit 5 \
  --timeout 60
```

如需更大覆盖面，可调整 group、limit 或 timeout。

### 覆盖度评估

若当前场景是“补充来源”，可先评估已有结果是否不足：

```bash
python3 .sensenova-claw/skills/union-search-plus/scripts/assess_coverage.py \
  --input /tmp/primary_results.json \
  --query "用户问题" \
  --min-sources 3 \
  --min-topic-coverage 0.45 \
  --min-valid-evidence 6
```

### 结果合并

```bash
python3 .sensenova-claw/skills/union-search-plus/scripts/merge_search_results.py \
  --primary /tmp/primary_results.json \
  --supplement /tmp/union_results.json \
  --query "用户问题" \
  --output /tmp/merged_results.json
```

## 输出规范

本技能的最终结果建议包含：

- `query`
- `summary`
- `items`

如有更多上下文，建议补充：

- `group`
- `platforms`
- `failed_platforms`
- `raw_response_paths`

每个 item 至少应包含：

- `title`
- `link`
- `source`

若可用，补充：

- `snippet`
- `provider`
- `_source_platform`

## 与 `research-union` 的关系

- `research-union`：负责复杂 research 的规划、确认、执行编排和报告
- `union-search-plus`：负责多平台搜索执行、补充来源和结果整理

如果任务是“完整调研”，优先让 `research-union` 决定何时调用本技能。
如果任务是“直接跨平台搜一轮”，则可以直接使用本技能。

## 禁止事项

- 不要把本技能当成 research 规划器
- 不要把多平台搜索结果直接当成已验证事实
- 不要因为部分平台失败就丢弃全部结果
- 不要在单点事实问题上默认走多平台大范围搜索
- 不要省略结果来源字段

## 执行检查清单

结束前确认：

- 是否明确了这是“直接多平台搜索”还是“补充来源”
- 是否按问题类型选择了合适的 group 或平台
- 是否保留了关键来源字段
- 是否对失败平台做了限制说明
- 是否将结果整理成统一结构，便于上层继续使用
