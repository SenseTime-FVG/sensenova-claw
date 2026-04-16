---
name: ppt-export-pptx
description: 将 deck_dir 中的 HTML 页面导出为可编辑的 PPTX 文件，使用 DOM 解析重建方式生成原生 PPTX 元素（文本框、图片、形状、表格等）。
---

# PPT 导出 PPTX

将已生成的 HTML slides 导出为可编辑的 `.pptx` 文件。

## 目标

- 将 `deck_dir/pages/` 下的所有 `page_*.html` 转换为原生 PPTX 元素。
- 生成的 PPTX 中文本、图片、表格均可编辑。
- 产出文件位于 `${deck_dir}/<目录名>.pptx`。

## 触发条件

- 所有页面 HTML 已生成。
- `review.md` 或 `review.json` 存在且未标记为阻塞。
- motif `data-layer` 标记已就位。
- 必需 `real-photo` 槽位已兑现。

## 输入

- `deck_dir`：必须已存在。若 `pages/` 目录不存在但 `deck_dir` 下直接存在 `page_*.html`，会自动规范化到 `pages/` 中。
- `review.md` 或 `review.json`：默认必须存在且未标记阻塞；使用 `--force` 可降级为警告并继续导出。
- 必须先确认 `review.md` 或 `review.json` 存在。
- `style-spec.json`（可选）：全局配色和字体，用于增强输出质量。
- `storyboard.json`（可选）：PPT 标题，用于增强输出质量。

## 输出

- 成功时 stdout 输出 JSON：`{ success, output, pages, converted, failed, fileSize }`。
- 失败时退出码为 1，错误信息输出到 stderr。
- 生成的 PPTX 文件位于 `${deck_dir}/<目录名>.pptx`。

## 执行规则

### 前置条件检查

导出前默认逐项确认；使用 `--force` 时，阻塞项会降级为警告：

1. `deck_dir` 已存在。若 `pages/` 缺失但根目录下有 `page_*.html`，会自动创建 `pages/` 并移动文件（同时提升相对资源路径一级）。
2. 依赖在首次运行时自动安装（`npm install` + `npx playwright install chromium`），后续运行检测到已安装则跳过。
3. npm 依赖和 Playwright Chromium 已安装（**首次运行时自动安装**，无需手动操作）。
4. `review.md` 或 `review.json` 存在且未标记为阻塞（`--force` 下仅为警告）。
4. 如果 `style-spec.json`/`storyboard.json` 声明了背景或前景 motif recipe，页面 HTML 中最好存在对应的 `data-layer="bg-motif"`、`data-layer="fg-motif"` 与 `data-motif-key` 标记（缺失时按降级模式继续）。
5. 如果 `storyboard.json`/`asset-plan.json` 显示某页仍有必需 `real-photo` 槽位未兑现，或 HTML 中仍保留明显图片 placeholder，默认不得继续导出（`--force` 下仅为警告）。

### 调用方式

通过 `bash_command` 执行：

```bash
node skills/ppt-export-pptx/html_to_pptx.mjs --deck-dir <deck_dir路径>
```

可选参数：
- `--output <文件名>`：输出文件名，默认与 deck_dir 目录名一致（如 `AI_产品发布会_20260318_154500.pptx`），写入 deck_dir 下。
- `--output-dir <目录>`：输出目录，默认与 deck_dir 相同。可指定不同目录，避免写入 deck_dir。
- `--pages-dir <目录>`：HTML 页面所在目录。默认为 `deck_dir/pages/`。当 HTML 不在 `pages/` 子目录下时使用。
- `--force`：强制导出。将 review 缺失/阻塞、标题层级异常、real-photo 未补齐等致命错误降级为警告，继续生成 PPTX。
- `--batch`：批量模式。跳过所有前置条件检查（review、motif、title、real-photo），同时跳过远程图片下载。隐含 `--force`。适用于批量测试场景。

### 转换机制

- 使用 Playwright（headless 模式）渲染 HTML 页面并提取 DOM 布局。
- 自动检测 HTML 画布尺寸（支持 1280×720、1600×900 等任意 16:9 尺寸），不再固定 1280×720。
- 使用 pptxgenjs 生成原生 PPTX 对象（10" × 5.625" 16:9 画布）。
- PPTX 中的文本、图片、表格均可编辑。
- CSS 渐变（linear-gradient / radial-gradient）通过内联 SVG 图片还原视觉效果（pptxgenjs 不支持原生渐变填充）。
- 由于 HTML 使用 Flexbox/Grid 布局，PPTX 元素采用绝对定位，修改内容后不会自动重排。
- 单个页面转换失败不会中断整个流程，会生成空白 slide 保持页码连续。

### 支持的元素

- 文本（标题、正文、列表、富文本格式，含 text-shadow、letter-spacing、line-height）。
- 图片（本地文件；远程 `http/https` 图片会在导出前自动下载到 `deck_dir/images/` 并嵌入；支持 object-fit cover/contain）。
- 背景（纯色、线性渐变、径向渐变、背景图片 + 渐变叠加、多层背景）。
- 渐变填充（linear-gradient / radial-gradient 通过 SVG 图片忠实还原，含 rgba 透明度 stop）。
- div 背景图片（`background-image: url(...)` 在非 `#bg` 元素上也能正确提取嵌入）。
- 表格（含 colspan/rowspan、单元格背景色、边框）。
- SVG（转 base64 嵌入）。
- 容器装饰（边框、圆角、阴影、旋转、透明度）。
- 非对称边框（1-3 条边有边框时用独立线条模拟）。
- 伪元素（`::before` / `::after` 的背景色/背景图提取为合成节点）。
- mask-image 渐变蒙版（通过 SVG overlay 模拟）。
- 页脚（页码）。

### 已知限制

- `mix-blend-mode` 不支持（PPTX 无对应特性）。
- 重复纹理背景（`background-size` 小于元素尺寸的重复 pattern）可能渲染为单个渐变覆盖。
- CSS 动画、transition、hover 等交互效果会丢失。
- 自定义字体需要目标设备已安装对应字体，否则 PowerPoint 会使用 fallback 字体。
- 图片透明度（`opacity < 1` 的图片）通过叠加半透明背景色矩形模拟，效果依赖于背景色匹配度。

### 可选增强

脚本会自动尝试读取以下文件以增强输出质量（非必需）：
- `style-spec.json`：全局配色和字体（用于 PPTX 默认字体设置）。
- `storyboard.json`：PPT 标题（用于 PPTX 文档标题属性）。

### 背景解析策略

slide 背景按以下优先级解析：
1. `#bg` 元素的 CSS `background-image`（图片 + 渐变叠加）。
2. `#bg` 内覆盖 ≥90% 面积的 `<img>` 子元素（提升为 slide 背景图）。
3. `#bg` 的 CSS `background-color`。
4. `.wrapper` 的 CSS 背景（渐变或纯色）。
5. `body` 的 CSS 背景（渐变或纯色）。
6. 白色 `FFFFFF`。

`#bg` 的兄弟 overlay 元素（如 `#bg-image`、`.bg-grid`）通过 `flattenIRToElements` 独立处理，其 `background-image: url(...)` 会被提取为图片元素。

## 用户回显

- **开始反馈**：说明正在把哪个 `deck_dir` 导出成 PPTX，并提示会生成 `<deck_dir>/<目录名>.pptx`。
- **进行中反馈**：如果页面较多或导出明显耗时，可补 1 条进度说明，告知已处理页数或当前阶段。
- **完成反馈**：说明生成的 PPTX 路径、转换页数、失败页数和 `下一步`。
- 如果导出失败、依赖未安装或部分页面转换异常，必须明确告诉用户失败原因和已保留结果。

## 关键原则

- 导出是流水线末端环节，默认必须确保上游审查已通过。
- 没有 `review.md` 或 `review.json`，默认不得直接进入导出；`--force` 可用于紧急生成。
- motif 标记和 real-photo 槽位是硬性前置条件，缺失时默认阻断；`--force` 可用于紧急生成。
- 单页转换失败不中断整体流程，但必须在输出中明确报告。
- 对缺失的本地图片使用透明像素占位，对不存在的背景图片使用纯色 fallback，避免 pptxgenjs 崩溃。

## 禁止事项

- 默认情况下，review 不存在或标记为阻塞时不得执行导出；`--force` 除外。
- 默认情况下，motif `data-layer` 标记缺失时不得继续导出；`--force` 除外。
- 默认情况下，必需 `real-photo` 槽位未兑现或仍有明显 placeholder 时不得继续导出；`--force` 除外。
- 不要在没有 `--force` 的情况下跳过前置条件检查直接执行转换。
