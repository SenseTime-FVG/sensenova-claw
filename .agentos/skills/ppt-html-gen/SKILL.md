---
name: ppt-html-gen
description: "根据 outline JSON、单页布局数据、style JSON 和图片选择结果，生成一个或多个 PPT HTML 页面。当任务需要读取 outline.json、style.json、image_selection.json，并在 deck 目录中写出 page_XX.html 时，使用本技能。优先使用已下载到本地的图片文件，而不是远程 URL。"
---

# PPT HTML 生成

你负责生成单页演示 HTML。

当任务已经具备以下输入时，使用本技能：

- 从大纲中拆出的单页 layout
- deck 级风格定义或等价的风格约束
- 可用的图片引用或 `image_selection.json`
- 当前页码和总页数

本技能也适用于这类 delegated subtask 或工作包：

- 根据 `outline.json` 生成全部 HTML 页面
- 读取 `style.json`，输出 `page_01.html` 到 `page_N.html`
- 在指定的 deck 目录里实现整套 PPT 页面

输出必须是 HTML，不要附带解释。

## 核心目标

为 `1280x720` 的演示画布生成视觉质量高且实现安全的单页 HTML。

## 语言规则

- 页面中所有用户可见文本，例如标题、段落、列表、图注、占位说明，默认必须与用户 query 的语言一致。
- 只有当用户明确要求使用另一种语言时，才切换页面文案语言。
- 固定代码字段名、CSS class、HTML id 可以保持英文；但不要在中文 query 下默认生成英文页面文案。

## 所需输入

你应当具备：

- `style`
- `layout`
- `image_selection`、`picture2` 或等价的图片映射
- `current_page`
- `total_pages`

## Style JSON 读取规则

在写任何 HTML 或 CSS 之前，先实际检查 `style.json` 的键结构，再决定如何取值；禁止假设字段名。

- 不要臆测存在 `primary_blue`、`secondary_blue`、`accent_cyan`、`headings`、`body_text` 这类键。
- 如果当前 `style.json` 的结构与你预期不一致，先做兼容映射，再继续生成；不要因为字段名不匹配而退回无关的默认浅色主题。
- 如果必须兜底，兜底值也必须从当前 `style.json` 已有值中推导，保持同一套深浅关系、主辅色关系和字体方向。

当前需要优先兼容的真实 schema 包括：

1. `typography.title_strategy.font_family_css` / `typography.body_strategy.font_family_css`
2. `typography.heading.font_family` / `typography.body.font_family`
3. `typography.headings.family` / `typography.body_text.family`

颜色同样先读实际结构，再做映射；常见来源包括：

1. `color_palette` 为数组：按 `role` 提取主背景、强调色、标题字色、正文色
2. `color_palette.background/accent/text`
3. `color_palette.primary_blue/secondary_blue/...`

如果某个必需样式值仍无法确定，不要静默改成通用白底蓝字；应明确保留与当前 style 最接近的视觉方向。

## 硬性布局规则

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

## 页面结构

HTML 必须遵守双层 wrapper 结构：

- `.wrapper`
- `#bg` 作为背景层
- `#ct` 作为内容层
- `#footer` 作为页码层

`#bg` 和 `#ct` 都必须铺满整页。

## 元素标识规则

每个主要内容元素都应带有：

- 唯一 id，例如 `text_1`、`chart_1`、`table_1`、`svg_1`
- 能描述类型的 class

图表规则：

- 图表容器必须是 `div`
- 在该 `div` 上初始化 ECharts

## 图片与装饰规则

### 外部图片

- 只能使用已提供的图片引用或已筛选通过的图片元数据
- 不要直接使用网络图片
- HTML 中的图片 id 必须和 layout 里的预期图片 id 完全一致
- 如果后处理会补图片地址，就不要在 HTML 中提前写真实 URL
- 如果 `image_selection.json` 中存在 `selected_image.local_path`，必须优先使用该本地路径
- 优先使用 `deck_dir/images/...` 之类的本地相对路径，不要把绝对沙盒路径原样暴露到最终页面里
- 如果只有远程 `image_url` 而没有成功下载的本地文件，不要把远程 URL 直接写入 HTML；应保留图片槽位占位，并在结果中说明该页图片资产未就绪
- 如果页面存在 `needed_pictures`，就必须在最终 HTML 中显式消费这项需求，不能因为布局类型是 `grid`、`timeline`、`two_column`、`three_column`、`closing` 等就静默忽略。
- 如果本地图片下载成功，该页 HTML 必须出现对应的本地图片引用，例如 `images/...`；如果下载失败，则必须保留明确的图片槽位占位，并用 `needed_pictures[].description` 指向预期视觉。
- 即使页面不是典型图文页，也要把图片作为背景模块、侧边卡片、信息插图或 closing hero visual 的一部分来实现，而不是直接删掉。
- 批量生成整套 deck 时，要逐页检查“是否有 `needed_pictures`”“是否有成功下载的本地图片”“最终 HTML 是否真的引用或占位了图片槽位”。

### 装饰图形

- 优先使用 CSS 绘制形状
- 背景图放在 `#bg`
- 背景视觉必须保证文字可读性

### 过滤

- 如果某个图片区域太小，不值得保留，就直接舍弃，不要硬塞

## 图表规则

- 使用 `ECharts` 或 `Frappe Gantt`
- 不要用 Chart.js
- 不要用 `<canvas>` 作为图表容器
- 图表容器必须显式声明宽高

## 文本和表格规则

- 不要在语义上修改、缩减或遗漏 layout 中的文本
- 优先完整保留 layout 中的关键信息，不要为了“页面更空”主动删句子或压缩成短标签
- 通过字号和间距适配来避免溢出
- 表格必须完整显示，不能出现滚动条
- 如果页面信息较多，优先使用更紧凑但仍清晰的排版，而不是擅自砍掉内容

## 输出规则

- 只输出 HTML
- 不要 Markdown 代码块
- 不要自然语言解释

以下 skeleton 可作为基础结构：

```html
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8"/>
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { margin: 0; display: flex; justify-content: center; align-items: center; background: #333; min-height: 100vh; overflow: hidden; }
        .wrapper { width: 1280px; height: 720px; position: relative; overflow: hidden; background: #fff; box-shadow: 0 0 20px rgba(0,0,0,0.5); }
    </style>
</head>
<body>
    <div class="wrapper">
        <div id="bg" style="position: absolute; inset: 0; z-index: 1;"></div>
        <div id="ct" style="position: absolute; inset: 0; z-index: 2; padding: 40px 60px;"></div>
        <div id="footer" class="footer-page" style="position: absolute; right: 40px; bottom: 20px; z-index: 10;">
            1 / N
        </div>
    </div>
    <script>
        // echarts init
    </script>
</body>
</html>
```

## 最终质量要求

- 视觉层级清晰
- 不溢出
- 不碰撞页脚安全区
- 渲染稳定
- 与提供的 style 保持一致
- 与 `image_selection.json` 中的最终图片槽位决策保持一致
- 忠实实现单页 layout 输入
- 当正文页被要求信息更充实时，应优先保住内容密度，再做视觉整理
- 页面中的自然语言内容默认与用户 query 的语言保持一致
- 带 `needed_pictures` 的页面不得出现“图片已成功下载但最终 HTML 完全没有消费该图片”的情况
