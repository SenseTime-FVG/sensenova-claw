# Chat Markdown 渲染设计文档

- 日期：2026-03-19
- 状态：Draft（已完成用户对设计分节确认）
- 关联需求：前端聊天区统一支持 `user / assistant / tool / system` 四类消息的增强版 Markdown 渲染；禁止原始 HTML。

## 1. 背景与目标

当前前端聊天区的消息正文仍按纯文本直接渲染，像粗体、列表、代码块、表格、任务列表等 Markdown 内容无法以结构化样式展示，影响对话可读性，也削弱了工具输出和模型回复的表达能力。

结合现状与用户确认，本次目标如下：

1. 为 `user / assistant / tool / system` 四类消息统一支持增强版 Markdown。
2. 支持 GFM 常用能力：表格、任务列表、删除线、自动链接。
3. 禁止原始 HTML 渲染，避免聊天内容带来 XSS 与样式污染风险。
4. 保持现有 JSON 查看器能力不变，结构化数据不误渲染为 Markdown。
5. 保留长文本折叠体验，避免超长消息破坏聊天布局。

## 2. 范围与非目标

### 2.1 范围内

1. 前端聊天消息展示层支持 Markdown 渲染。
2. `tool` 消息正文支持 Markdown。
3. `toolInfo.arguments` 与 `toolInfo.result` 中的普通字符串支持 Markdown。
4. 为 Markdown 内容补齐聊天场景样式。
5. 补充单元/页面回归与 Playwright e2e 覆盖。

### 2.2 非目标（YAGNI）

1. 不修改后端消息协议与 WebSocket 事件结构。
2. 不支持消息正文中的原始 HTML 渲染。
3. 不在本次需求中引入代码高亮、复制按钮、Mermaid、LaTeX 等扩展能力。
4. 不重构整个聊天 UI 样式系统。

## 3. 方案对比与选型

### 方案 A：直接在 `MessageBubble` 内联 Markdown 渲染

- 做法：将当前 `{message.content}` 直接替换为 Markdown 组件，并在 `tool` 分支重复接入。
- 优点：改动最少，上手最快。
- 缺点：普通消息、工具消息、折叠区字符串内容会出现重复逻辑，后续扩展代码高亮或链接策略时维护成本高。

### 方案 B（采用）：抽象公共 `MarkdownRenderer` 组件

- 做法：新增统一渲染组件，封装 Markdown 解析、GFM 配置、安全策略和样式映射，再由聊天消息及工具折叠区共同复用。
- 优点：职责清晰、复用性好、后续演进成本低。
- 缺点：相比方案 A 多一层整理工作。

### 方案 C：一次性建设完整富文本渲染层

- 做法：除 Markdown 外，同时加入代码高亮、复制按钮、富块扩展与更多交互。
- 优点：能力上限最高。
- 缺点：超出当前需求，测试和样式成本显著增加。

结论：采用方案 B，以最小必要抽象满足当前需求，并为后续增强保留清晰扩展点。

## 4. 目标架构与职责边界

### 4.1 组件职责

1. `MarkdownRenderer`
- 负责解析 Markdown 文本。
- 负责开启 GFM 增强能力。
- 负责禁用原始 HTML。
- 负责统一输出聊天场景样式。

2. `MessageBubble`
- 负责按消息角色选择展示结构。
- 负责将 `message.content` 接入 `MarkdownRenderer`。
- 负责 `tool` 消息正文与附加信息展示。

3. `CollapsibleContent`
- 负责长文本折叠/展开行为。
- 负责在字符串内容展开后以 Markdown 方式渲染。

4. `JsonViewer`
- 负责展示 JSON 或可解析为 JSON 的结构化内容。
- 明确不参与 Markdown 渲染，避免结构数据被错误格式化。

### 4.2 边界原则

1. 后端仍只传输纯字符串消息，展示语义由前端决定。
2. “结构化内容”优先走 JSON 查看器，“自然语言字符串”走 Markdown。
3. Markdown 渲染只负责展示，不执行 HTML，不承担数据转换职责。
4. 长文本折叠能力优先保留，避免为了 Markdown 而破坏现有消息区交互。

## 5. 数据流与渲染规则

### 5.1 消息协议

不修改现有前端消息结构，继续沿用：

```python
from typing import Any, Literal, Optional

MessageRole = Literal["user", "assistant", "tool", "system"]


class ToolInfo:
    name: str
    arguments: dict[str, Any] | str
    result: Optional[Any]
    success: Optional[bool]
    error: Optional[str]
    status: Literal["running", "completed"]


class Message:
    id: str
    role: MessageRole
    content: str
    timestamp: int
    toolInfo: Optional[ToolInfo]
```

### 5.2 渲染规则

1. `user / assistant / system`
- `message.content` 统一按 Markdown 渲染。

2. `tool`
- `message.content` 按 Markdown 渲染。
- `toolInfo.arguments`
  - 若为 JSON 或可解析 JSON 的字符串，继续走 `JsonViewer`
  - 若为普通字符串，走支持折叠的 Markdown 渲染
- `toolInfo.result`
  - 若为错误文本，按普通文本或 Markdown 安全展示
  - 若为 JSON 或可解析 JSON 的字符串，继续走 `JsonViewer`
  - 若为普通字符串，走支持折叠的 Markdown 渲染

3. 长文本
- 保留现有折叠逻辑。
- 收起状态可继续使用纯文本摘要或截断预览。
- 展开状态必须按 Markdown 渲染完整内容。

## 6. Markdown 能力与安全策略

### 6.1 支持能力

本次按“增强版 Markdown”落地，包含：

1. 标题
2. 粗体、斜体、删除线
3. 有序/无序列表
4. 引用块
5. 行内代码与代码块
6. 链接与自动链接
7. 表格
8. 任务列表

### 6.2 安全策略

1. 不启用原始 HTML 渲染。
2. 不使用 `dangerouslySetInnerHTML` 直接灌入消息内容。
3. 对外链统一增加安全属性（如新窗口打开时的 `rel` 保护）。
4. Markdown 解析失败时回退为普通文本显示，不阻断消息渲染。

### 6.3 样式策略

新增或复用一组聊天 Markdown 样式类，覆盖：

1. 标题间距与字号层级
2. 列表缩进与项目符号
3. 代码块背景、滚动与换行策略
4. 表格边框、单元格间距与溢出滚动
5. 引用块边框与前景色
6. 链接颜色与 hover 状态

目标是让 Markdown 在聊天气泡中“可读但不过度像文档页”，不破坏当前对话式布局。

## 7. 组件改造设计

### 7.1 `MarkdownRenderer`

建议新增公共组件，例如：

- 路径：`sensenova_claw/app/web/components/chat/MarkdownRenderer.tsx`

职责：

1. 接收 `content: string`
2. 接收可选样式变体参数（如普通消息、工具折叠区）
3. 统一配置 Markdown 解析能力与安全规则
4. 输出语义化 DOM，便于 e2e 断言

### 7.2 `MessageBubble`

改造方向：

1. 普通消息分支不再直接输出纯文本，改为 `MarkdownRenderer`
2. `tool` 消息正文改为 `MarkdownRenderer`
3. `ToolInfoDisplay` 保持现有结构，但将普通字符串内容切到 Markdown 渲染链路

### 7.3 `CollapsibleContent`

改造方向：

1. 保留 `isExpanded` 与长度判断逻辑
2. 收起态继续使用简短文本预览，避免在未展开时渲染大段复杂 DOM
3. 展开态将原始字符串交给 `MarkdownRenderer`

这样既能保留性能与布局稳定性，也能在真正查看详情时获得 Markdown 效果。

## 8. 异常处理与回退

1. 空内容
- 渲染为空容器或空字符串，不抛出错误。

2. Markdown 解析异常
- 回退为纯文本展示，并记录前端控制台错误或开发日志。

3. 超长字符串
- 保留折叠，避免一次性渲染过长 DOM。

4. JSON 与 Markdown 冲突
- 优先按 JSON 检测；命中后不再尝试 Markdown。

5. 原始 HTML
- 视作普通文本内容显示，不转换为 DOM 节点。

## 9. 测试设计

### 9.1 前端组件/页面回归

至少覆盖以下场景：

1. `**bold**` 渲染为加粗文本
2. 三反引号代码块渲染为 `pre > code`
3. 表格渲染为 `table`
4. 任务列表渲染为复选框样式列表
5. 原始 HTML 不会变成真实可执行节点
6. `tool` 消息正文支持 Markdown
7. `toolInfo.arguments/result` 的普通字符串支持 Markdown
8. `toolInfo.arguments/result` 的 JSON 内容仍显示为 JSON 查看器

### 9.2 Playwright e2e

至少覆盖以下聊天链路：

1. 模拟一条带 Markdown 的普通消息，断言页面出现语义化节点而非原始 Markdown 标记
2. 模拟一条 `tool` 消息，展开参数或结果后确认 Markdown 生效
3. 验证原始 HTML 标签不会被当作真实元素插入页面

### 9.3 回归关注点

1. 现有消息滚动到底部行为不回归
2. 长文本折叠/展开行为不回归
3. 现有 JSON 查看器行为不回归

## 10. 验收标准

1. 聊天区 `user / assistant / tool / system` 四类消息都可以显示增强版 Markdown。
2. 表格、任务列表、代码块等 GFM 常用能力可见且样式可读。
3. 原始 HTML 不会被执行或渲染为真实 HTML 结构。
4. `toolInfo` 中 JSON 内容仍按 JSON 查看器展示。
5. 长文本消息仍支持折叠/展开。
6. 前端回归测试与 Playwright e2e 覆盖新增行为。

## 11. 伪代码（Python 风格）

```python
from typing import Any, Literal, Optional


RenderVariant = Literal["bubble", "tool-detail"]


class MarkdownRenderer:
    def render(self, content: str, variant: RenderVariant = "bubble") -> Any:
        # 作用：将 Markdown 字符串渲染为安全的前端节点
        # 可能调用：react-markdown、remark-gfm 等前端渲染库
        # 约束：不允许原始 HTML 生效
        pass


class JsonViewer:
    def render(self, data: Any) -> Any:
        # 作用：展示结构化 JSON 数据
        # 约束：仅用于结构化内容，不负责 Markdown 渲染
        pass


class CollapsibleContent:
    def render(self, content: str, max_length: int = 500) -> Any:
        # 作用：控制长文本的折叠与展开
        # 行为：收起时显示摘要；展开时调用 MarkdownRenderer.render
        pass


class ToolInfoDisplay:
    def render_arguments(self, arguments: Any) -> Any:
        # 作用：根据内容类型在 JsonViewer 与 MarkdownRenderer 间分流
        # 规则：JSON 优先，其次普通字符串 Markdown
        pass

    def render_result(self, result: Any, error: Optional[str] = None) -> Any:
        # 作用：展示工具执行结果或错误
        # 规则：error 直接显示；JSON 走 JsonViewer；普通字符串走 MarkdownRenderer
        pass


class MessageBubble:
    def render(self, message: Message) -> Any:
        # 作用：按消息角色渲染聊天气泡
        # 规则：user/assistant/system/tool 的正文统一走 MarkdownRenderer
        # 规则：tool 的结构化附加信息由 ToolInfoDisplay 负责
        pass
```
