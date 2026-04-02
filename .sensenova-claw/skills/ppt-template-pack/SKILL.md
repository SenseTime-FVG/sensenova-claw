---
name: ppt-template-pack
description: 当用户提供已有模板、参考 deck 或页面样例，需要拆解其布局结构、组件规则和设计约束以供后续复用时使用。
---

# PPT 模板包

将用户提供的模板、参考 deck 或页面样例拆解为可复用的布局结构与设计约束。

## 目标

- 产出 `template-pack.json`，明确模板可复用的结构与约束。
- 为 `ppt-style-spec` 提供模板级设计输入，为 `ppt-storyboard` 和 `ppt-page-html` 提供布局复用依据。
- 区分全局规则与局部装饰，避免把偶发设计误判成全 deck 约束。

## 触发条件

- 用户提供了已有模板文件（`.pptx`、`.pdf`、截图等）。
- 用户提供了参考 deck 或页面样例，并希望新 deck 复用其风格或布局。
- 由 `ppt-superpower` 在流水线中按需调度，不是每次都必须执行。

## 输入

- `task-pack.json`：必须先读取，从中取得 `deck_dir` 和任务上下文。
- 用户提供的模板文件、参考 deck 截图或页面样例。

## 输出

- 输出路径：`${deck_dir}/template-pack.json`。
- 不要手写、缩写、翻译或重拼 `deck_dir`。

## 执行规则

### 拆解流程

1. 读取 `task-pack.json`，确认 `deck_dir`。
2. 逐页分析模板或参考 deck，识别其结构化模式。
3. 按页面类型归类，提取可复用的布局规则。
4. 区分全局规则与局部装饰，标注复用范围。
5. 产出 `template-pack.json`。

### 需要识别的内容

- **页面类型分布**：封面、目录、正文、分析、结论等页面的比例和出现位置。
- **布局模式**：栅格结构、分栏比例、内容区域划分、留白策略。
- **组件组织方式**：卡片、面板、数据块、图表容器的排列规律和间距。
- **标题与正文层级**：标题位置、大小层级、正文排版规则、编号/标签体系。
- **图表与图片的放置习惯**：图片尺寸比例、对齐方式、与文字的空间关系。
- **色彩与字体线索**：模板使用的主色、辅助色、字体选择（作为 `ppt-style-spec` 的输入信号）。
- **局部装饰与全局规则的边界**：哪些元素是全局一致的（如页眉页脚、背景纹理），哪些是特定页面的局部装饰。

### 与 `ppt-style-spec` 的集成

- `template-pack.json` 中的色彩、字体、装饰线索应传递给 `ppt-style-spec` 作为设计输入。
- 如果模板已提供明确的设计语言，`ppt-style-spec` 应优先服从模板约束，在模板未覆盖的维度上补充。
- 模板中的布局结构可直接影响 `ppt-style-spec` 的 `page_type_variants`，但 `template-pack` 不直接替代 `style-spec.json`。

### 复用范围判断

- 如果模板只覆盖部分页面类型，明确标注哪些页面可复用、哪些页面需要 `ppt-style-spec` 独立定义。
- 如果模板设计质量参差不齐，标注可信度等级，供下游 skill 选择性采纳。
- 如果模板与用户需求存在冲突（如模板是极简风但用户要求数据密集），必须在产出中显式标注冲突点。

## 数据结构

```python
class TemplatePack:
    schema_version: str
    source_description: str
    page_patterns: list["PagePattern"]
    layout_rules: list[str]
    component_rules: list[str]
    style_constraints: list[str]
    reusable_assets: list[str]
    global_vs_local: list["ScopeAnnotation"]
    conflicts_with_task: list[str]


class PagePattern:
    page_type: str
    layout_description: str
    grid_structure: str
    component_slots: list[str]
    reusable: bool
    notes: str


class ScopeAnnotation:
    element: str
    scope: str       # "global" | "local"
    confidence: str  # "high" | "medium" | "low"
    notes: str
```

## 用户回显

- **开始反馈**：说明正在拆解模板或参考 deck，并指出目标是 `template-pack.json`。
- **完成反馈**：简要概括识别出的布局规则、组件约束和 `下一步`。
- 如果模板只能部分复用，也要在反馈中说明保留范围和限制，不要默认整套照搬。

## 关键原则

- 模板包提供约束，不直接替代 `style-spec.json`。
- 模板中的局部装饰不要误判成全 deck 必须复用的全局规则。
- 模板包可以影响 `ppt-storyboard` 和 `ppt-page-html`，但不负责内容研究。
- 拆解结果必须足够结构化，让下游 skill 可以直接消费，不要只写自由文本描述。

## 禁止事项

- 不要把局部装饰误判成全局规则。
- 不要默认整套照搬模板，必须评估每个部分的复用价值。
- 不要在模板拆解阶段做内容研究或页面叙事编排。
- 不要忽略模板与用户需求之间的冲突，必须显式标注。
- 不要猜测 `deck_dir`，必须从 `task-pack.json` 读取。
