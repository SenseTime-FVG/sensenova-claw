# PPT Skills 重构设计

## 1. 目标与约束

本次迭代只重构 `.sensenova-claw/skills` 中的 PPT 技能体系，不修改 Sensenova-Claw 运行时代码。

目标如下：

1. 将旧的“大一统 `pptx` skill”重构为新的 `ppt-*` superpower 体系。
2. 默认采用“快速优先”路径，避免生成一套 PPT 时出现过长流程。
3. 同时保留 `B + C` 级别的中断、介入和继续推进能力：
   - `B`：关键工件级可独立生成、替换、重跑。
   - `C`：页面级、图片槽位级可按需单独修复。
4. `style-spec.json` 必须为默认必产工件，用于稳定设计一致性和设计丰富度。
5. `storyboard.json` 必须为默认必产工件，并提供固定 schema，供前端阶段性展示和局部修改。
6. 讲稿能力纳入体系，但当前版本作为可选交付物。

当前稳定交付物仍是 HTML slides，而不是 `.pptx` 文件。未来若要支持 `.pptx` 导出，应增加独立 skill，而不是重新把总控 skill 做大。

---

## 2. 旧体系问题分析

旧体系已经覆盖了若干有效能力：信息收集、风格提取、大纲生成、图片选择、HTML 生成。但主要问题不在单点能力，而在编排方式。

### 2.1 总控 skill 过重

旧 `pptx` 同时承担了：

- 任务理解
- 信息规划
- brief 汇总
- 风格抽取调度
- 大纲调度
- 图片调度
- HTML 调度
- 阶段闸门与结果说明

职责边界过大，导致：

- 中途打断后难以恢复
- 局部返工时只能“再跑一次整套”
- 很难把阶段性结果稳定展示给前端

### 2.2 前后阶段只停留在文档层

旧设计文档里已经描述了：

- 输入汇总
- 内容完整性判断
- 后续流程规划
- 文档解析
- 模板拆解
- 页面检查
- 模板/偏好沉淀

但这些阶段没有真正成为可独立调用的 skill，导致“设计文档中的流程”和“实际 skills 能做的事”之间存在断层。

### 2.3 上传文件的职责混杂

用户上传的输入至少有三种生态位：

- 内容素材
- 风格参考
- 模板参考

旧体系没有把这三类职责显式拆开。结果是：

- 后续 `style`、`outline`、`html` 都在消费混杂输入
- 同一个文件的“内容价值”和“设计价值”没有被分别利用
- 很难决定某个文件应该驱动哪条后续链路

### 2.4 `style` 不是中心工件

旧体系中 `ppt-style-extract` 是一个子阶段，但不是整个系统的设计控制面。

这会带来两个直接问题：

1. 页面之间的风格一致性不稳定，容易退化成模型“临场发挥的一致性”。
2. 如果不提前建立设计共识，模型会优先保内容正确，最终页面就会走向单一、保守、简陋。

### 2.5 `outline` 不足以承担前端契约

旧 `outline` 更像内部生成产物，不是前端阶段展示的稳定对象。它缺少：

- 固定 schema 版本
- 页面叙事角色
- 观众收获点
- 局部未解决项
- 讲述意图

因此它很难同时承担：

- 前端大纲展示
- 用户局部修改
- 后续页面生成输入
- 局部返工锚点

### 2.6 流程默认串行到底

旧体系默认以“从输入一路跑到 HTML”组织，适合一次性批处理，不适合：

- 用户先看阶段成果再决定是否继续
- 用户只改第 3 页
- 用户只替换某个图片槽位
- 图片阶段局部失败，但其他页面仍可先推进

---

## 3. 新体系的设计原则

### 3.1 统一入口，分层执行

新体系只保留一个默认入口 `ppt-superpower`，负责：

- 判断当前任务类型
- 判断已有工件是否可复用
- 决定运行模式
- 决定下一步最值得生成的工件

### 3.2 围绕工件组织，而不是围绕抽象步骤组织

新的核心思路是“工件优先”。

用户中断、前端展示、局部返工、继续推进，都应该围绕以下对象展开：

- `task-pack.json`
- `style-spec.json`
- `storyboard.json`
- `asset-plan.json`
- `speaker-notes.json`
- `pages/page_XX.html`

### 3.3 默认短路径，按需下钻

默认路径只生成最关键的工件，不把所有输入都解析到最细。

只有命中触发器时，才下钻到：

- 页面级
- 图片槽位级
- 风格局部增强
- 叙事局部修正

### 3.4 `style-spec` 是设计控制面

`style-spec.json` 不是附属文件，而是全 deck 的设计控制面。它必须解决：

- 每页为何属于同一套 deck
- 页面类型如何变化但不失统一
- 如何避免“能用但丑”的安全产出

### 3.5 `storyboard` 是前端契约

`storyboard.json` 是默认必产，并承担双重职责：

- 页面叙事和页面生成的控制面
- 前端阶段展示和局部编辑的稳定契约
- research 的消费层；把可上页的 claim、evidence 和缺口显式落到页面级对象

### 3.6 上传文件必须先分类

只要有文件、链接、截图、模板输入，就应先做 `ppt-source-analysis`，把来源拆成：

- `content_source`
- `style_reference`
- `template_reference`
- `mixed_source`

这样后续每个 skill 才知道自己该消费哪部分输入。

### 3.7 结果必须落在自包含 deck 目录

新体系不能把中间结果直接散落在 agent 根目录或当前工作目录顶层。

总规则：

- 优先使用用户明确指定的输出目录
- 如果是在已有 deck 上继续修改，复用原有目录
- 否则自动创建新的 `deck_dir`
- `deck_dir` 名称使用 `query概述 + 时间戳`
- `deck_dir` 是本轮任务的 canonical 输出根目录
- 后续 skill 只能直接复制这个值，不要手写、缩写、翻译或重拼目录名
- 创建 `deck_dir` 后立即创建 `pages/` 与 `images/`

所有工件都必须落在同一个 `deck_dir` 中，例如：

- `task-pack.json`
- `style-spec.json`
- `storyboard.json`
- `asset-plan.json`
- `image_search_results.json`
- `image_selection.json`
- `pages/page_XX.html`
- `images/...`
- `review.md`

### 3.8 阶段性结果回显是默认交互

长链路 PPT 任务不能一旦开始就持续沉默。除了产出工件，还必须持续给用户最小但有用的进度感知。

总原则：

- `fast` 也要有简短阶段回显，但默认非阻塞，不要求用户每步确认。
- `guided` 除了阶段回显，还要在关键停点明确等待用户确认。
- `surgical` 的回显必须说明当前只改哪个页面、槽位或控制面，避免用户误以为会重跑整套。
- 回显内容优先包含：当前阶段、已产出工件、未解决项、下一步。
- 搜图下载、逐页 HTML、整套 review、导出 PPTX 这类明显耗时阶段，可以补 1 条进行中反馈，但不能刷屏。
- 依赖缺失、路径不一致、下载失败、页面失败等异常要立即回显，不允许静默跳过。

### 3.9 正文页内容诊断维度

后续实验统一使用以下审计词汇：

- 论点密度
- 证据密度
- 结构密度
- 视觉承载密度
- 空白感

当前优先实现方案 1，采用强约束渲染契约；可选补层包括预置装饰模板库和后置抛光补层。

---

## 4. 新 Skill 体系

### 4.1 顶层总控

#### `ppt-superpower`

唯一默认入口。

负责：

- 先确定或复用本次任务的 `deck_dir`
- 识别任务类型：新建整套、继续已有成果、局部修改、只产出中间工件
- 决定运行模式：`fast / guided / surgical`
- 决定下一步生成哪个工件
- 判断哪些已有工件可复用

### 4.2 关键工件 skills

#### `ppt-source-analysis`

负责输入来源分类，产出 `source-map.json`。

#### `ppt-task-pack`

负责统一记录任务目标、页数、受众、语言、限制、交付物、输出目录、推荐路径、`research_required`、`content_gap_assessment`、`research_needs` 和 `风格意图`，产出 `task-pack.json`。
在实验 1 中，`ppt-task-pack` 不只是任务收敛层，也是内容控制面：要先把内容缺口评估清楚，再决定 research 是否值得执行。

#### `ppt-research-pack`

负责内容研究和内容补充。它必须先读取 `task-pack.json`，并且只在 `task-pack.json.research_required` 为真时才执行，产出 `research-pack.md` 或 `research-pack.json`。
上传报告、事实数据案例、长文档这些输入都要先交给 `ppt-task-pack` 消化，它们只是 `research_required` 的信号，不是绕过 `task-pack` 的独立入口。
research 不是摘要，而是“可上页内容池”。
pageworthy chunks 是 storyboard 的上游输入。

#### `ppt-template-pack`

负责模板拆解和模板约束提取，产出 `template-pack.json`。

#### `ppt-style-spec`

负责 deck 级设计语言，产出 `style-spec.json`。默认必产。
它必须优先理解用户需求，再把 `task-pack.json` 中的 `风格意图` 转成可执行的设计语法；只有在风格信号不足时，才允许退到 `商务` 或 `海报` 这两种兜底。
这里的“可执行”不是多写几个形容词，而是要产出 variant 级页面壳子映射，例如 `variant_key`、`layout_shell`、`header_strategy`，不要只按 `page_type` 粗分。
同时要给出 `svg_motif_library` 这类可直接绘制的装饰元素库，让背景和前景的插画感不是停留在文字描述。
对装饰层的当前实现策略采用“强约束渲染契约”，不是只描述气质，而是给出可直接落地的 motif 配方。
这里的 `插画感` 只影响装饰层与组件皮肤，不应被误用成“所有视觉都改成插画、无需真实图片”。
正文 / 内容页不能把 `background_motif_recipe` 留空，也不要只给一个角落里的小图标；至少要有一个大面积或跨边缘的背景 motif 配方。真实图片也不能替代背景装饰配方。

#### `ppt-storyboard`

负责分页叙事和前端契约，产出 `storyboard.json`。默认必产。
storyboard 是 research 的消费层，不允许只把 research 主题词重新改写成页面摘要；每页必须能说明主 claim 和 evidence 从哪里来。
如果 research 里存在缺口、证据不足或待确认项，必须在页面级 `content_blocks[].unresolved_gaps` 或页级未解决项里显式保留，不要静默吞掉。
其中每页的 `style_variant` 必须直接引用 `style-spec.json` 中已声明的 variant 映射，不要把它写成宽泛形容词。
`asset_requirements` 也不能只写模糊槽位名；要带上 `svg-illustration`、`svg-icon`、`real-photo`、`qr-placeholder` 这类类型提示。
资产类型判断必须先看页面语义。如果页面要呈现人物、产品、空间、场景、活动现场、作品样张或环境氛围，默认应规划为 `real-photo`；`插画感` 只影响装饰语法，不要因为风格里有插画感，就把整套 deck 的图片需求都改成 `svg-illustration`。

#### `ppt-asset-plan`

负责图片与视觉资产规划，产出 `asset-plan.json`，必要时同时落地 `image_search_results.json`、`image_selection.json` 和 `images/`，并在下载前先创建 `deck_dir/images`。
它只应为真实图片槽位走搜图与下载；可直接绘制的图标或插画应标记为 `draw-inline-svg`，不要强行走搜图下载。
如果 `asset_requirements` 写得过轻，但 `visual_requirements` 或页面语义明显指向真实图片，资产规划阶段应补出对应的 `real-photo` 槽位，不要静默接受“整套都只有 SVG”。

#### `ppt-page-html`

负责按页生成 `pages/page_XX.html`。
每个 `storyboard.json.pages[n]` 都必须对应一个单独的页面文件，不允许把整套 deck 拼成单个 HTML，同时必须忠实消费 `style-spec.json` 和已经下载成功的本地图片，并继续遵守 `1280x720` 固定画布、16:9 比例和页脚安全区约束。
不要编写 Python 脚本来批量生成页面；必须逐页直接生成最终 HTML，不要先写生成器脚本再批量产出页面。
页面实现时必须显式消费 `background_system`、`foreground_motifs`、`component_skins`、`density_rules`、`page_type_variants`；不要只做纯色背景 + 普通白卡片，除非 `style-spec` 明确要求极简。
生成时应优先按 `style_variant` 映射页面壳子，不要把多个不同 `style_variant` 页面重新压成同一种安全模板。
图标、装饰性元素、可直接绘制的插画应使用内联 SVG 落地；只有真实照片、二维码、用户专有素材缺失时才允许 placeholder。
不要把图标画成 placeholder。
可见标题必须放在 `#ct` 内，或放在单独的 `#header` 容器内；不要把 `.header` 当作 `#bg` 和 `#ct` 之间的裸兄弟节点，否则很容易被内容层盖住。
非极简页面必须至少 1 层背景装饰，且至少 1 处前景装饰；如果只有纯色或渐变背景，应视为未完成。
背景装饰层必须是用户可感知的视觉层，不能退化成极小角标或几乎不可见的弱纹理。
正文 / 内容页即使有真实图片，也不能把照片当成背景装饰层的替代。
根据 recipe 落地的背景 motif 元素必须带 `data-layer="bg-motif"`；前景 motif 元素必须带 `data-layer="fg-motif"`；每个 motif 还要带 `data-motif-key`，让 review 和导出前校验可以核对。真实图片或主视觉照片不能替代这些标记。
同时，页面必须逐项消费 `storyboard.json.pages[n].asset_requirements`，不要用一个通用 motif 替代不同页面的具体资产要求；如果页面要求 `real-photo`，不要改画成 SVG 小图标。
在生成前，消费前必须先确认 `task-pack.json`、`style-spec.json`、`storyboard.json` 以及相关 `asset-plan.json` 真实存在且可读；如果目标文件不存在、目录不一致或关键字段缺失，先补齐依赖，不要猜测。

#### `ppt-speaker-notes`

负责生成逐页讲稿，产出 `speaker-notes.json` 或 `speaker-notes.md`。当前为可选交付物。

#### `ppt-review`

负责整套结果审查，产出 `review.md` 或 `review.json`。
review 不是口头总结，必须写回工件；并且必须写出 `review.md` 或 `review.json`，检查是否满足页级 `asset_requirements`、如果要求真实图片却只落了 SVG 或 placeholder、以及装饰层是否真的成立。审查时必须直接读取页面 HTML，不要只根据模型自述；如果 style-spec recipe 要求某个 motif，就要在页面里找到对应的 `data-motif-key`。同时必须核对标题元素是否放在 `#ct` 或 `#header`，不要把仅存在于源码但被层级盖住的标题判成通过；如果 `.header` 落在 `#ct` 外面，应视为标题不可见。没有 `review.md` 或 `review.json` 时，不得继续导出。

### 4.3 局部修复 skills

这些 skill 不进入默认快路径，只有触发器命中时才使用：

- `ppt-page-plan`
- `ppt-page-assets`
- `ppt-page-polish`
- `ppt-style-refine`
- `ppt-story-refine`

### 4.4 技能清单速览

流程图可以由使用方按需要自行绘制；这里保留技能清单表，明确每个 skill 的职责和用户可见反馈点。

| Skill | 类型 | 触发时机 | 主要输入 | 主要产物 | 用户回显 |
| --- | --- | --- | --- | --- | --- |
| `ppt-superpower` | 总控入口 | 用户提出整套生成、继续已有 deck、局部修改、阶段确认时 | 用户 query、上传文件、已有 deck 工件 | `deck_dir`、mode、下一步 skill 选择 | 首条消息说明目标 / mode / `deck_dir` / 第一步；后续统一要求各阶段给 `开始反馈`、`完成反馈`、必要时给 `进行中反馈` 或 `阻塞反馈` |
| `ppt-source-analysis` | 来源分析 | 有报告、网页、截图、模板、已有 deck 等上传来源时 | 原始文件、链接、截图 | `source-map.json` | 回显识别出的来源角色、限制和推荐 `下一步` |
| `ppt-task-pack` | 任务收敛 | 新建 deck、重新明确页数、受众、语言、交付物时 | 用户目标、来源分析结果、输出要求 | `task-pack.json` | 回显主题、页数、mode、`deck_dir`、`research_required` 和关键假设 |
| `ppt-research-pack` | 研究补充 | `task-pack.json.research_required` 为真，且 task-pack 仍有内容缺口时 | `task-pack.json`、来源材料、检索结果 | `research-pack.md` / `research-pack.json` | 回显核心结论、不确定性和 `下一步` |
| `ppt-template-pack` | 模板拆解 | 用户提供模板 deck、参考版式或样页时 | 模板文件、参考页面、`task-pack.json` | `template-pack.json` | 回显识别出的布局规则、组件约束和可复用范围 |
| `ppt-style-spec` | 设计控制面 | 默认必产；明确 deck 级设计语言时 | `task-pack.json`、模板约束、风格参考 | `style-spec.json` | 回显设计主题、风格关键词、主色 / 字体方向和 `下一步` |
| `ppt-storyboard` | 叙事控制面 | 默认必产；确定分页结构与前端契约时 | `task-pack.json`、`style-spec.json`、`research-pack` | `storyboard.json` | 回显页数、章节结构、未解决项；`guided` 下提示用户先审阅 |
| `ppt-asset-plan` | 资产规划 | 页面存在图片、背景、图标等视觉资产缺口时 | `task-pack.json`、`storyboard.json`、可选 `style-spec.json` | `asset-plan.json`、`image_search_results.json`、`image_selection.json`、`images/` | 回显待补槽位数、下载进度、成功落地数量、未解决槽位和 `下一步` |
| `ppt-page-html` | 页面生成 | 需要按页落地 HTML 或局部重做页面时 | `task-pack.json`、`style-spec.json`、`storyboard.json`、`asset-plan.json` | `pages/page_XX.html` | 回显当前页范围、进度、已生成页数、保留的占位或残留问题 |
| `ppt-speaker-notes` | 讲稿生成 | 用户要求讲稿、备注页、演讲词时 | `storyboard.json`、页面 HTML | `speaker-notes.json` / `speaker-notes.md` | 回显讲稿覆盖页数、语气方向和 `下一步` |
| `ppt-review` | 结果审查 | 页面生成后统一检查叙事、风格、页面质量和资产状态时 | `task-pack.json`、`style-spec.json`、`storyboard.json`、页面与资产 | `review.md` / `review.json` | 回显总体结论、问题数量、建议下钻 skill 和是否可直接交付 |
| `ppt-page-plan` | 单页规划修复 | 只改某一页结构、布局意图或内容块时 | 指定页规划、`storyboard.json`、用户反馈 | 单页规划更新 | 回显锁定的 `page_id`、影响范围和 `下一步` |
| `ppt-page-assets` | 单页资产修复 | 只换某页或某槽位的图片 / 图标 / 背景时 | 指定页、`asset-plan.json`、`storyboard.json` | 单页资产更新与本地图片 | 回显锁定槽位、资产替换结果、未解决项和 `下一步` |
| `ppt-page-polish` | 单页视觉抛光 | 单页结构基本正确，但视觉质量需要微调时 | 指定页 HTML、`style-spec.json`、用户反馈 | 抛光后的单页 HTML | 回显本页抛光目标、已做调整和残留问题 |
| `ppt-style-refine` | 全局风格修复 | 全局风格方向对，但品牌感、变化度或一致性不足时 | `style-spec.json`、若干页面 HTML、用户反馈 | 更新后的 `style-spec.json` | 回显增强了哪些全局规则、影响哪些页面类型和 `下一步` |
| `ppt-story-refine` | 叙事修正 | 故事线、章节顺序、页数分配需要调整时 | `storyboard.json`、`task-pack.json`、用户反馈 | 更新后的 `storyboard.json` | 回显调整后的故事线、影响页数和 `下一步` |
| `ppt-export-pptx` | 导出交付 | 页面和 review 基本就绪，需要导出最终 PPTX 时 | `deck_dir`、`pages/page_XX.html`、可选 `style-spec.json` / `storyboard.json` | `<deck_dir>/<目录名>.pptx` | 回显导出开始、处理页数、失败页数、输出路径和 `下一步` |

---

## 5. 核心工件模型

### 5.1 必产工件

默认必产：

- `task-pack.json`
- `style-spec.json`
- `storyboard.json`

原因：

- `task-pack` 提供统一任务边界
- `style-spec` 提供统一设计语言
- `storyboard` 提供统一叙事与前端契约
- 三者共同固定 `deck_dir`、设计控制面和页面控制面，保证 deck 可继续演进
- `task-pack.json` 还负责显式标记 `research_required`，作为是否进入 `ppt-research-pack` 的唯一门控输入

### 5.2 可选工件

按需产出：

- `source-map.json`
- `research-pack.md` / `research-pack.json`
- `template-pack.json`
- `asset-plan.json`
- `image_search_results.json`
- `image_selection.json`
- `speaker-notes.json` / `speaker-notes.md`
- `review.md` / `review.json`

### 5.3 `task-pack.json`

建议最小结构：

```python
from typing import Literal

Mode = Literal["fast", "guided", "surgical"]
OutputPolicy = Literal["user-provided", "reuse-existing", "auto-generated"]

class TaskPack:
    schema_version: str
    topic: str
    language: str
    audience: str
    goal: str
    total_pages: int
    mode: Mode
    deliverables: list[str]
    must_have_sections: list[str]
    constraints: list[str]
    known_gaps: list[str]
    content_gap_assessment: list[str]
    research_required: bool
    research_needs: list["ResearchNeed"]
    available_sources: list[str]
    style_intent: "StyleIntent"
    deck_dir: str
    output_policy: OutputPolicy


class StyleIntent:
    scenario: str
    audience_signal: str
    tone: list[str]
    industry_context: str
    explicit_style_preference: str | None


class ResearchNeed:
    topic: str
    reason: str
    scope: list[str]
    priority: str
```

要求：

- `风格意图` 必须先从用户 query 中抽取，至少覆盖 `场景`、`气质`、`行业语境` 和显式风格偏好
- 如果用户已经明确给出风格偏好、品牌语气、参考图或模板方向，必须在 `task-pack.json` 中显式记录，供后续 `style-spec` 优先消费
- `deck_dir` 必须被显式记录，并作为后续 skill 的统一输出目录
- 它是唯一可信的 canonical 输出根目录
- 后续 skill 只能直接复制这个值，不要手写、缩写、翻译或重拼目录名
- 如果用户未指定目录，`deck_dir` 使用 `query概述 + 时间戳` 自动创建
- 不允许把工件散落写到 agent 根目录
- `known_gaps` 保留“当前已知但尚未补齐的问题清单”角色，记录用户未提供的信息、待确认项和缺失材料
- `content_gap_assessment` 负责显式记录当前内容缺什么、为什么缺、会阻塞什么
- `content_gap_assessment` 负责更结构化的判断，用来解释这些缺口为什么会触发 research 或影响后续内容决策
- 避免两个字段看起来重复：`known_gaps` 记录现象，`content_gap_assessment` 记录判断
- `research_required` 由 `task-pack.json` 自己判断并显式记录
- `research_needs` 负责把 research topic、reason、scope、priority 写成稳定输入
- 不允许在 `task-pack` 之前做外部 research 决策

### 5.4 `style-spec.json`

建议最小结构：

```python
class StyleSpec:
    schema_version: str
    design_theme: str
    design_keywords: list[str]
    visual_archetype: str
    fallback_archetype: str
    color_roles: list["ColorRole"]
    typography: "TypographySpec"
    background_system: list[str]
    foreground_motifs: list[str]
    svg_motif_library: list["SvgMotif"]
    component_skins: list[str]
    density_rules: list[str]
    page_type_variants: list["PageTypeVariant"]
    page_type_principles: list["PageTypePrinciple"]
    component_tone: list[str]
    diversity_rules: list[str]
    anti_patterns: list[str]


class ColorRole:
    role: str
    hex: str
    usage: str


class TypographySpec:
    title_font: str
    body_font: str
    title_weight: str
    body_line_height: float


class PageTypePrinciple:
    page_type: str
    visual_goal: str
    allowed_variants: list[str]


class PageTypeVariant:
    variant_key: str
    page_type: str
    layout_shell: str
    header_strategy: str
    background_strategy: str
    foreground_strategy: str
    required_svg_motifs: list[str]
    background_motif_recipe: list["MotifPlacement"]
    foreground_motif_recipe: list["MotifPlacement"]
    component_strategy: str


class SvgMotif:
    motif_key: str
    usage_layer: str
    drawing_hint: str
    palette_binding: list[str]


class MotifPlacement:
    motif_key: str
    placement_hint: str
    density_hint: str
    opacity_hint: str
```

要求：

- `style-spec.json` 为默认必产
- 它是设计控制面
- 必须先读取 `task-pack.json`
- 必须优先理解用户需求，再决定具体风格方向
- `visual_archetype` 表示根据用户需求推断出的主风格；只有在风格信号不足时，`fallback_archetype` 才允许取 `商务` 或 `海报`
- 输出路径必须严格为 `${deck_dir}/style-spec.json`
- 不要手写、缩写、翻译或重拼目录名
- 必须包含 `background_system`、`foreground_motifs`、`component_skins`、`density_rules`、`page_type_variants`
- 必须包含“页面类型视觉原则”
- 必须包含“禁用项”或等价反模式
- 后续 `ppt-storyboard` 与 `ppt-page-html` 必须显式消费它

补充要求：

- `background_system` 要明确背景层次、渐变、纹理、几何层、光晕或分区底纹，避免页面退回纯色底
- `foreground_motifs` 要明确角标、编号块、导视线、强调框、标签等前景装饰语法
- 背景和前景都要给出可绘制的装饰元素，不要只停留在文字描述
- `svg_motif_library` 要列出可直接绘制的装饰元素或插画母题，供后续页面生成直接消费
- `component_skins` 要明确卡片、数据面板、表格、引言块、图表容器的皮肤规则
- `density_rules` 要明确哪些页面允许更浓、哪些页面必须更克制
- `page_type_variants` 要明确封面页、分析页、结论页、风险页等页面如何变化而不失统一
- `page_type_variants` 不要只按 `page_type` 粗分；要能覆盖 `style_variant`
- 每个 variant 都应提供 `variant_key`、`layout_shell`、`header_strategy` 等可执行字段，避免只剩形容词风格
- 每个 variant 都应带 `required_svg_motifs`
- 每个 variant 还应带 `background_motif_recipe`、`foreground_motif_recipe`、`placement_hint`、`density_hint`
- 正文 / 内容页不能把 `background_motif_recipe` 留空
- 正文 / 内容页不要只给一个角落里的小图标
- 正文 / 内容页至少要有一个大面积或跨边缘的背景 motif 配方
- 真实图片也不能替代背景装饰配方
- 不要只写“有叶片感”这类抽象描述

### 5.5 `storyboard.json`

`storyboard.json` 是默认必产，同时也是前端契约工件。

建议固定 schema：

```python
from typing import Literal

Mode = Literal["fast", "guided", "surgical"]

class Storyboard:
    schema_version: str
    ppt_title: str
    language: str
    total_pages: int
    mode: Mode
    pages: list["StoryboardPage"]


class StoryboardPage:
    page_id: str
    page_number: int
    title: str
    page_type: str
    section: str
    narrative_role: str
    audience_takeaway: str
    layout_intent: str
    style_variant: str
    content_blocks: list["ContentBlock"]
    visual_requirements: list[str]
    data_requirements: list[str]
    asset_requirements: list[str]
    unresolved_issues: list[str]
    presenter_intent: str


class ContentBlock:
    block_id: str
    heading: str
    summary: str
    source_claim_ids: list[str]
    source_evidence_ids: list[str]
    unresolved_gaps: list[str]
```

设计要求：

- storyboard 是 research 的消费层
- 消费前必须先确认依赖文件真实存在且可读
- 如果目标文件不存在、路径不一致或关键字段缺失，先补齐依赖，不要猜测
- 页数必须与 `task-pack.json` 对齐
- 内容语言必须默认与用户 query 保持一致
- 允许前端稳定渲染页面列表
- 允许后续 skill 基于 `page_id` 做局部重写
- 不允许只拿 research 主题词重新写一遍
- 每页必须能说明主 claim 和 evidence 从哪里来
- 每个 `ContentBlock` 都必须显式记录 `source_claim_ids` 与 `source_evidence_ids`
- 缺证据时要显式记录 `unresolved_gaps`
- `style_variant` 必须直接引用 `style-spec.json` 中已声明的 variant 映射
- `style_variant` 不要把它写成宽泛形容词；后续 `ppt-page-html` 可直接按 variant 落地
- `asset_requirements` 不要只写模糊的槽位名，应带 `svg-illustration`、`svg-icon`、`real-photo`、`qr-placeholder` 这类类型提示
- `presenter_intent` 只提供轻量讲述意图，不承担完整讲稿职责

### 5.6 `asset-plan.json`

建议最小结构：

```python
class AssetPlan:
    schema_version: str
    deck_dir: str
    slots: list["AssetSlot"]


class AssetSlot:
    page_id: str
    page_title: str
    slot_id: str
    purpose: str
    asset_kind: str
    render_strategy: str
    source_caption: str
    query: str
    selected: bool
    selected_image: "SelectedImage | None"
    rejected_candidates: list["RejectedCandidate"]
    status: str
    reason: str


class SelectedImage:
    title: str
    image_url: str
    local_path: str
    source_page: str
    source_domain: str


class RejectedCandidate:
    image_url: str
    rejection_stage: str
    reason: str
```

要求：

- 消费前必须先确认依赖文件真实存在且可读
- 如果目标文件不存在、路径不一致或关键字段缺失，先补齐依赖，不要猜测
- 必须保留 `image_search_results.json`，记录 query 与原始候选
- 必须保留 `image_selection.json`，记录最终选择与拒绝原因
- 选图流程必须可审计，不能让“筛选过程”在重构后消失
- `asset-plan.json` 中必须显式区分 `real-photo`、`svg-illustration`、`svg-icon`、`qr-placeholder`
- `real-photo` 应走 `download-local`
- 不要为可直接绘制的图标或插画走搜图下载
- 如果 `asset_requirements` 写得过轻，但页面语义明显要求人物、产品、场景或活动现场图片，应补出对应的 `real-photo` 槽位
- 必须先下载验证，再做最终选择
- 优先落地本地图片
- 本地文件不存在时必须显式标记 `unresolved`
- 最终选中的图片必须来自下载成功的本地文件
- 不允许把远程 URL 伪装成最终本地资产

### 5.7 `speaker-notes.json`

讲稿是可选交付物。

建议结构：

```python
class SpeakerNotes:
    schema_version: str
    language: str
    notes: list["SpeakerNotePage"]


class SpeakerNotePage:
    page_id: str
    page_title: str
    opening: str
    key_points: list[str]
    transition: str
    caution: list[str]
```

---

## 6. 默认运行路径

### 6.1 快速优先

无上传文件时的最小路径：

主路径从 `deck_dir -> task-pack -> research(按需) -> style-spec -> storyboard` 开始。

1. `ppt-task-pack`
2. 如 `task-pack.json.research_required` 为真且仍有内容缺口，则进入 `ppt-research-pack`
3. `ppt-style-spec`
4. `ppt-storyboard`
5. 如存在 `real-photo` 槽位，或页面语义明显需要人物 / 产品 / 场景图片，则先进入 `ppt-asset-plan`
6. `ppt-page-html`
7. `ppt-review`

有上传文件时的常规路径：

主路径从 `deck_dir -> task-pack -> research(按需) -> style-spec -> storyboard` 开始。

1. `ppt-source-analysis`
2. `ppt-task-pack`
3. 如 `task-pack.json.research_required` 为真且仍有内容缺口，则进入 `ppt-research-pack`
4. `ppt-style-spec`
5. `ppt-storyboard`
6. 如存在 `real-photo` 槽位，或页面语义明显需要人物 / 产品 / 场景图片，则先进入 `ppt-asset-plan`
7. `ppt-page-html`
8. `ppt-review`

### 6.2 按需插入

仅在命中触发器时插入：

- `ppt-research-pack`
- `ppt-template-pack`
- `ppt-asset-plan`
- `ppt-speaker-notes`

### 6.3 运行模式

#### `fast`

默认模式。

- 只生成必要工件
- 优先尽快得到整套结果
- 只在必要时下钻
- 必须给用户简短阶段回显，但默认非阻塞
- 除非触发阻塞条件，否则每次回显后自动进入 `下一步`

#### `guided`

用于希望逐步查看中间产物的场景。

- 如果用户说“先看大纲”“先确认大纲”“先看风格和大纲”或“确认后再生成”，必须进入 `guided`
- 在用户确认前，不要直接生成 `pages/page_XX.html`
- 不要只返回一段自由文本大纲，应展示已落盘的结构化工件
- 更稳定地产出中间工件
- 更适合前端阶段性确认
- 完成关键工件后必须明确提示用户现在可查看什么，以及确认后的 `下一步`

#### `surgical`

用于局部修复。

- 不重跑整套
- 只改指定页面、指定槽位、指定风格或叙事局部
- 阶段回显必须点明当前锁定的 `page_id`、`slot_id` 或被修改工件范围

### 6.4 阶段回显协议

建议所有阶段回显都遵循同一最小结构：

```python
from typing import Literal

FeedbackStatus = Literal[
    "started",
    "in_progress",
    "completed",
    "blocked",
    "awaiting_confirmation",
]


class StageFeedback:
    stage: str
    status: FeedbackStatus
    scope: str
    artifacts: list[str]
    highlights: list[str]
    unresolved: list[str]
    next_step: str
```

执行要求：

- 第一条反馈必须说明目标、mode、`deck_dir` 和第一步。
- 每个关键阶段至少有一条 `开始反馈` 和一条 `完成反馈`。
- 搜图、逐页 HTML、review、导出 PPTX 允许补一条 `进行中反馈`，但不要刷屏。
- 遇到缺依赖、路径错误、下载失败、导出失败时，要立即发 `阻塞反馈`。
- `guided` 在等待用户决策时使用 `awaiting_confirmation` 语义，并明确告诉用户当前停在哪个工件。

---

## 7. 上传文件分析策略

`ppt-source-analysis` 必须先做来源分类。

### 7.1 内容素材

如报告、文档、网页、说明材料。

作用：

- 提供事实、论点、章节信息
- 先进入 `ppt-task-pack`，由 `task-pack.json.research_required` 决定是否进入 `ppt-research-pack`
- 上传报告、主题涉及事实 / 数据 / 案例、长文档整理等都只是 `task-pack` 判断 `research_required` 的信号
- 上传报告、事实数据案例和长文档只是 `task-pack` 计算 `research_required` 的信号

### 7.2 风格参考

如参考 PPT、设计图、截图、海报。

作用：

- 提供配色、气质、排版语气
- 进入 `ppt-style-spec`

### 7.3 模板参考

如已有 deck、页面样例、版式模板。

作用：

- 提供结构、布局、组件约束
- 进入 `ppt-template-pack`

### 7.4 混合来源

同一个文件可能同时具备：

- 内容价值
- 风格价值
- 模板价值

因此 `source-map.json` 必须允许 `mixed_source`，而不是强制一对一归类。

---

## 8. 讲稿策略

讲稿能力保留，但当前版本作为可选交付物。

### 8.1 为什么不直接塞进 `storyboard`

如果把完整讲稿直接写入 `storyboard.json`，会带来三个问题：

1. 前端契约会变重
2. 页面结构一改，讲稿也会跟着整份重写
3. `storyboard` 会从控制面膨胀成内容大容器

### 8.2 当前策略

- `storyboard.json` 只保留 `presenter_intent`
- 完整讲稿由 `ppt-speaker-notes` 生成

### 8.3 默认触发条件

只有以下情况才默认生成讲稿：

- 用户明确要求讲稿
- 场景是汇报、路演、培训、答辩、演讲
- `task-pack.json` 把讲稿列为交付物

---

## 9. 触发器设计

### 9.1 任务级触发器

- 用户目标不清晰
- 存在上传文件、链接、模板、截图
- 内容不足，需要补充研究
- 主题涉及真实事实
- 用户明确要求先看中间工件

### 9.2 页面级触发器

- 用户只改某一页
- review 发现某页结构失衡
- 某页内容溢出或过空
- 某页风格漂移
- 某页页面类型不合适

### 9.3 槽位级触发器

- 某个图片槽位未解决
- 某个图片槽位下载失败
- 用户只想替换 hero 图或背景图

---

## 10. 与旧能力的关系

新体系不保留旧 skill 名称，也不做薄封装转发。

但需要继承旧体系中已经验证有效的限制与经验：

- 页面默认语言与用户 query 保持一致
- 页面生成使用 `1280x720` 画布
- 图片优先本地化，不直接依赖远程链接
- 图片检索必须保留候选、筛选理由和下载记录
- 图片选择阶段必须记录 unresolved 状态
- 创建 `deck_dir` 后应立即创建 `pages/` 与 `images/`
- HTML 页面必须保留页脚安全区
- HTML 页面应保持严格的 16:9 / `1280x720` 画布
- 右下角 `160px x 60px` 必须保留给页码
- HTML 不应因为重构而退回通用默认样式
- 叙事结构应与目标页数保持一致
- 风格应区分 deck 级规则与页面局部装饰

---

## 11. 测试与评测用例

### 11.1 契约测试

本次重构至少要有以下契约测试：

1. 新 `ppt-*` skill 集合存在
2. 旧 `ppt-image-selection / ppt-html-gen` 可以保留作参考文档，但 `ppt-superpower` 不得回退调用它们
3. `ppt-superpower` 明确声明 `fast / guided / surgical` 与 `deck_dir`，并要求初始化 `pages/` / `images/`
4. `ppt-style-spec` 明确声明默认必产、设计控制面、页面类型视觉原则、禁用项
5. `ppt-storyboard` 明确包含固定 schema 字段
6. `ppt-asset-plan` 明确保留搜图候选、筛选记录、本地下载结果，并在下载前先创建 `deck_dir/images`，同时区分 `real-photo` 与可直接绘制的 SVG 资产
7. `ppt-page-html` 明确消费 `style-spec.json` 与本地图片，不退回通用默认样式，同时恢复严格的 `1280x720` / 页脚安全区约束，并禁止通过 Python 生成器脚本批量产出页面；优先按 `style_variant` 映射页面壳子，并用内联 SVG 落地图标与装饰性插画；非极简页面若只有纯色或渐变背景则视为未完成
   并且按 recipe 落地的背景 / 前景 motif 必须带 `data-layer="bg-motif"`、`data-layer="fg-motif"` 与 `data-motif-key`，让 review 和导出前校验可以核对；真实图片或主视觉照片不能替代这些标记
8. `ppt-speaker-notes` 明确标注可选交付物
9. 设计文档中的术语与新 skill 体系一致
10. `ppt-superpower` 与关键子 skill 明确声明阶段回显协议，避免长链路静默执行
11. 设计文档明确 `fast / guided / surgical` 的交互反馈差异与 `StageFeedback` 结构

### 11.2 场景测试矩阵

#### 用例 1：无上传文件，简单中文主题

期望：

- `deck_dir -> task-pack -> research(按需) -> style-spec -> storyboard`
- 走 `fast`
- 生成 `task-pack.json`
- 生成 `style-spec.json`
- 生成 `storyboard.json`

#### 用例 2：上传报告作为内容素材

期望：

- 在 `source-map.json` 中识别为 `content_source`
- 先进入 `ppt-task-pack`
- 由 `task-pack.json.research_required` 决定是否进入 `ppt-research-pack`

#### 用例 3：上传参考图作为风格参考

期望：

- 识别为 `style_reference`
- `style-spec.json` 不再只是保守空壳

#### 用例 4：上传模板 deck

期望：

- 识别为 `template_reference`
- 进入 `ppt-template-pack`

#### 用例 5：同一文件同时承担内容和风格作用

期望：

- 识别为 `mixed_source`

#### 用例 6：用户只要求先看风格和大纲

期望：

- 流程停在 `style-spec.json` 与 `storyboard.json`
- 必须进入 `guided`
- 不要直接生成 `pages/page_XX.html`
- 不要只返回一段自由文本大纲

#### 用例 7：前端阶段性展示

期望：

- `storyboard.json` 可稳定渲染页面列表、块摘要和未解决项

#### 用例 8：用户只改第 3 页

期望：

- 进入 `surgical`
- 只触发页面级 skill

#### 用例 9：某个图片槽位下载失败

期望：

- 只标记该槽位 unresolved
- 其他页面继续生成

#### 用例 10：长链路默认阶段回显

期望：

- `fast` 也会在关键阶段给出简短 `开始反馈` / `完成反馈`
- `guided` 会在关键停点显式等待用户确认
- 搜图、逐页 HTML、review、导出 PPTX 可补 1 条 `进行中反馈`
- 遇到阻塞时会立刻告诉用户卡点和 `下一步`

#### 用例 10：用户要求讲稿

期望：

- 生成 `speaker-notes.json` 或 `speaker-notes.md`
- 不污染 `storyboard.json` 的前端契约

### 11.3 设计优化回归 query 草案

以下用例用于观察“是否先理解用户需求，再生成匹配风格”，以及页面是否真正具备更丰富的背景层、前景装饰和组件皮肤。这里先保留可直接修改的 query 草案，后续可按需要继续细化。

#### 草案 1：高端珠宝限定系列发布

Query：

`帮我做一份“月光与潮汐”珠宝限定系列发布的PPT，给买手店和媒体看。希望高级、克制、精致，有一点戏剧感和材质感，但不要做成普通奢侈品商务介绍。需要有系列灵感、主打款式、材质工艺、目标客群、陈列建议、传播主视觉方向。`

#### 草案 2：山野观察营·秋季亲子自然教育项目

Query：

`帮我做一份“山野观察营·秋季亲子自然教育项目”的PPT，给家长和学校合作方看。希望温暖、自然、有手作感和一点插画感，能吸引孩子，但不能幼稚。需要有课程亮点、导师介绍、每日节奏、安全机制、报名方式。`

#### 草案 3：冷萃乌龙气泡茶新品发布

Query：

`帮我做一份“冷萃乌龙气泡茶新品发布”的PPT，给渠道商和媒体预热。希望年轻、明亮、有点包装设计感，页面要有活力，适合现场大屏展示。需要有品牌概念、新品卖点、目标人群、陈列建议、传播海报方向。`

#### 草案 4：小米汽车城市巡展提案

Query：

`帮我做一份“小米汽车城市巡展提案”的PPT，给商场渠道和品牌合作方看。希望有速度感、科技感和高级感，但不要做成泛蓝色科技模板。需要有巡展主题、主打亮点、体验动线、场景布置、传播话题。`

#### 草案 5：故宫夜游文化体验升级方案

Query：

`帮我做一份“故宫夜游文化体验升级方案”的PPT，给文旅合作方和策展团队看。希望有东方秩序、宫廷质感和当代设计感，不要做成普通旅游宣传册。需要有项目定位、体验章节、空间氛围、文创联动、传播建议。`

#### 草案 6：多模态大模型能力介绍

Query：

`帮我做一份“多模态大模型能力介绍”的PPT，给产品经理和售前团队看。希望专业、现代、信息密度高，但页面不能枯燥。需要有模型定位、核心能力、典型场景、效果对比、部署方式。`

---

## 12. 实施范围

本轮实施范围：

- 重写 `docs/ppt-skills/design.md`
- 全量替换 `.sensenova-claw/skills` 下当前 PPT skills
- 新增契约测试，验证新体系边界

本轮不做：

- Sensenova-Claw 运行时代码改造
- 新的 `.pptx` 导出实现
- 前端渲染逻辑改造
