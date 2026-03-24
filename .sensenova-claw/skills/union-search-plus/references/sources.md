# 来源说明

`union-search-plus` 继承 `union-search-skill` 的多来源聚合能力，采用两级补充策略：

## 第一级：preferred

用于快速补洞，优先低成本、高稳定来源组合。

## 第二级：all

在 preferred 仍不足时启用，覆盖更多来源（可能带来更高噪声与更长耗时）。

## 与主链关系

- 主链：`serper_search + fetch_url`
- 补充链：`union-search-plus`
- 输出：统一去重、统一重排，形成单一证据池
