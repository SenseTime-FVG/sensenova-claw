---
name: ppt-export-pptx
description: 将 deck_dir 中的 HTML 页面导出为可编辑的 PPTX 文件，使用 DOM 解析重建方式生成原生 PPTX 元素（文本框、图片、形状、表格等）。
---

# PPT Export to PPTX

将已生成的 HTML slides 导出为 `.pptx` 文件。

## 前置条件

1. `deck_dir` 已存在，且 `pages/` 目录下至少有一个 `page_*.html` 文件
2. 依赖已安装（首次使用需执行 `cd .agentos/skills/ppt-export-pptx && npm install`）

## 使用方式

通过 `bash_command` 执行：

```bash
node .agentos/skills/ppt-export-pptx/html_to_pptx.mjs --deck-dir <deck_dir路径>
```

可选参数：
- `--output <文件名>`：输出文件名，默认 `deck.pptx`，写入 deck_dir 下

## 输出

- 成功时 stdout 输出 JSON：`{ success, output, pages, converted, failed, fileSize }`
- 失败时退出码为 1，错误信息输出到 stderr
- 生成的 PPTX 文件位于 `<deck_dir>/deck.pptx`

## 转换说明

- 使用 Playwright（headless 模式）渲染 HTML 页面并提取 DOM 布局
- 使用 pptxgenjs 生成原生 PPTX 对象
- PPTX 中的文本、图片、表格均可编辑
- 由于 HTML 使用 Flexbox/Grid 布局，PPTX 元素采用绝对定位，修改内容后不会自动重排
- 单个页面转换失败不会中断整个流程，会生成空白 slide 保持页码连续

## 支持的元素

- 文本（标题、正文、列表、富文本格式）
- 图片（本地文件）
- 背景（纯色、线性渐变）
- 表格（含 colspan/rowspan）
- SVG（转 base64 嵌入）
- 容器装饰（边框、圆角、阴影）
- 页脚（页码）

## 可选增强

脚本会自动尝试读取以下文件以增强输出质量（非必需）：
- `style-spec.json`：全局配色和字体
- `storyboard.json`：PPT 标题
