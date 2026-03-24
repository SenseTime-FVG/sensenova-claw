---
name: ppt-page-html
description: 当需要根据 style-spec、storyboard 和 asset-plan 逐页生成 HTML 幻灯片，并严格遵守页面尺寸、本地图片和布局安全规则时使用。
---

# PPT HTML 页面生成

## 目标

根据 `style-spec.json`、`storyboard.json`、可选的 `asset-plan.json` 逐页生成 `pages/page_XX.html`。

每个 `storyboard.json.pages[n]` 都必须对应一个单独的 HTML 文件。

如果 `task-pack.json` 已记录 `deck_dir`，则所有 HTML 也必须写回该目录下的 `pages/`。

## 用户回显要求

- `开始反馈`：说明当前要生成哪些页面、会写入哪个 `pages/` 目录。
- `进行中反馈`：如果需要连续生成多页，可补 1 条进度更新，说明已完成页数或当前页范围。
- `完成反馈`：总结已生成的页面文件数量、是否保留了占位或未解决项，以及 `下一步`。
- 如果某页因为依赖缺失、资产缺失或布局冲突无法完成，必须立即告诉用户具体页码和卡点，不要静默跳过。

## 前置检查

- 消费前必须先确认 `task-pack.json`、`style-spec.json`、`storyboard.json` 以及要用到的 `asset-plan.json` 真实存在且可读。
- 如果目标文件不存在、落在错误目录、或与 `task-pack.json.deck_dir` 不一致，先停下并补齐依赖，不要猜测。

## 硬性规则

- 优先消费本地图片路径
- 不要直接把远程 URL 写进最终页面
- 用户可见文本默认与用户 query 语言保持一致
- 每页必须单独输出为一个 HTML 文件
- 不要输出单个包含整套 deck 的 HTML

### 固定画布

- 页面尺寸必须严格为 `1280x720`
- 不允许出现滚动条
- 所有内容必须完整落在视区内
- 缩放逻辑只能放在最外层容器，不能放在内容元素上

### 布局实现

- 只能用 Flexbox 或 CSS Grid 做对齐
- 不要用 `mt-auto`、`flex-grow` 或 `flex: 1` 伪造间距
- 不要用 `position: absolute + transform: translate(...)` 布局流式内容
- 图片和图表区域要靠明确尺寸控制，不能靠空 div 挤空间

### 页脚安全区

- 右下角 `160px x 60px` 必须保留给页码
- 任何内容都不能覆盖这块区域
- 页码必须放在 `<div id="footer">`
- 页脚必须带有等价于 `position: absolute; right: 40px; bottom: 20px;` 的内联定位

## 输出契约

- 按 `page_number` 顺序落盘到 `pages/page_XX.html`
- 一页对应一个文件，不拼成单个总 HTML
- 如果只重做局部页面，也只覆盖对应的页面文件

## 页面结构约束

HTML 必须保留这些层级：

- `.wrapper`
- `#bg`
- `#ct`
- `#footer`
- `#bg` 和 `#ct` 都必须铺满整页

## 风格执行规则

- 必须先读取并忠实消费 `style-spec.json` 的真实字段，不要只抓几个宽泛关键词后重新发明一套样式。
- 如果局部字段不完整，应从已有 `style-spec.json` 中做兼容推导，不要退回通用默认样式。
- 必须延续 deck 级的配色、字体、背景层次、卡片语法和装饰方向，不能因为实现方便把页面做成另一套模板。
- 局部重做页面时，也必须与同 deck 其他页面保持同一视觉系统。

## 资源规则

- 如果 `asset-plan.json` 中某个槽位 `selected=False`，需要保留明确占位或替代方案。
- 如果 `local_path` 存在，应优先引用本地相对路径。
- 如果 `asset-plan.json` 已经给出成功下载的本地图片，最终 HTML 必须显式消费该槽位，不能静默忽略。
- 如果图片还未就绪，必须保留明确占位，并把预期视觉与页面语义对应起来。
- 图片、图表、表格应与 `storyboard.json` 的页面意图一致。

## 质量原则

- 忠实消费 `style-spec.json`
- 忠实消费 `storyboard.json`
- 同一套 deck 中既要统一，也要避免页面完全重复
- 不要为了“简洁”擅自删掉关键内容
- 不要因为实现方便弱化原有风格层次、背景氛围或版式张力
- 对存在资产需求的页面，不能静默忽略图片槽位
