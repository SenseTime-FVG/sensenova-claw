---
name: ppt-review
description: 当需要审查整套 PPT 的叙事完整性、风格执行度、页面质量和局部返工建议，并决定是否进入页面级或槽位级修复时使用。
---

# PPT Review

## 目标

对整套结果做结构化审查，输出继续交付或局部返工建议。

审查结果必须写回 `deck_dir/review.md` 或 `deck_dir/review.json`，不能只在聊天消息里口头总结。

## 用户回显要求

- `开始反馈`：说明正在审查整套 deck，并指出会检查结构、风格、页面质量和资产状态。
- `完成反馈`：给出总体结论、问题数量、推荐下钻 skill 和 `下一步`。
- 如果 review 发现阻塞性交付问题，要在反馈里明确指出不能直接交付的原因，不要只给笼统评价。

## 审查维度

- `task-pack.json` 是否被满足
- `style-spec.json` 是否被忠实执行
- `storyboard.json` 与最终页面是否一致
- 是否满足页级 `asset_requirements`
- 页面之间是否风格漂移
- 单页是否溢出、过空或信息失衡
- 资产计划中的 unresolved 是否需要继续处理
- 是否缺少背景装饰层
- 是否缺少前景装饰层
- 是否只有纯色或渐变背景
- 如果要求真实图片却只落了 SVG 或 placeholder
- 装饰层是否只是很小的角标或极弱纹理，不足以构成真正的背景 / 前景层

## 输出要求

至少给出：

- 总体结论
- 页面级问题列表
- 建议触发的下钻 skill
- 并且必须写出 `review.md` 或 `review.json`

## 关键原则

- 消费前必须先确认 `task-pack.json`、`style-spec.json`、`storyboard.json` 以及已产出的页面文件真实存在且可读。
- 如果目标文件不存在、目录不一致或交付物缺页，先标记缺失依赖，不要猜测。
- 必须直接读取页面 HTML，必要时结合 DOM / CSS 结构核对装饰层，不要只根据模型自述判定通过。
- 必须检查页面里是否存在 `data-layer="bg-motif"` 与 `data-layer="fg-motif"` 这类装饰层证据。
- 如果 style-spec recipe 要求某个 motif，就要在页面里找到对应的 `data-motif-key`。
- 必须检查标题元素是否放在 `#ct` 或 `#header`。
- 不要把仅存在于源码但被层级盖住的标题判成通过；如果 `.header` 落在 `#ct` 外面，应视为标题不可见。
- 能局部修复的问题，不要整套推倒重来。
- 如果只是某页问题，应转到 `ppt-page-plan`、`ppt-page-polish` 或 `ppt-page-assets`。
- 如果是全局设计问题，应转到 `ppt-style-refine`。
- 如果是叙事节奏问题，应转到 `ppt-story-refine`。
- 如果页面只有纯色或渐变背景，且缺少背景装饰层或前景装饰层，不能直接交付。
- 如果页面要求真实图片却只落了 SVG 或 placeholder，不能直接交付。
- 如果没有 `review.md` 或 `review.json`，后续不要直接进入导出。
