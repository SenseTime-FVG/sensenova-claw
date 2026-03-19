

# docs_raw 文档

** docs_raw目录下的文档是用户直接构造的docs，不要修改这部分内容 **

docs下的文档是模型生成的，你可以修改docs下的文档


# 文档伪代码格式
使用python格式伪代码
以下是示例
```python
from typing import Any, Literal, Optional

Json = dict[str, Any]

Role = Literal["user", "assistant", "tool", "system"]

class Message:
    role: Role
    content: str
    meta: Optional[Json]  # e.g. { toolName, toolCallId, traceId }
    ts: Optional[int]


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool):
        # 注明函数的作用
        # 注明函数可能会调用哪些外部模块的函数
        # 注意不需要写具体的实现，用文字描述主要功能
        pass
```



# 代码要求

dev阶段，你必须记录后端系统完整的日志，以便于检查错误，例如DEBUG level下，保存每次LLM调用的输入

最好能够一键启动，例如 npm run dev 能够同时启动前端和后端


# 测试

写完代码之后必须完成对应的测试

如果需要api配置可以向用户询问

如果有新增功能，需要针对性的写好e2e测试用例，确保功能被激活使用并且没有bug

对于后端，你必须要进行完整的e2e测试，即对后端的api模拟用户输入进行测试，例如输入"帮我搜索英超联赛最近3年的冠亚军分别是什么球队"，并观察完整的日志和最终结果。

对于前端，你需要编写playwright脚本，启动无头浏览器，完整模拟用户的输入，并观察每一步的结果

e2e测试需要使用真实api_key进行真实测试，如果缺少api_key，像用户发出请求

# python运行和python包管理

使用uv工具来安装和配置python package

python的运行先conda activate base, 再uv run python xxx.py


# 其他

使用中文写注释和文档

先思考再行动

遇到外部资料，先使用search/browse等工具获取相关信息再行动


如果用户需求是根据指定文档更新代码，你需要全面考虑需要更新哪些代码/文档/测试


# 自动生成的Notes

你可以修改这个这部分内容，但是不要更改上面的内容

每次你执行完成任务之后，需要总结成功和失败的经验，并选择会对后续任务有帮助的内容保存在这里

### 2026-03-05 任务复盘

成功经验：
- 后端事件驱动链路（`ui.user_input -> llm -> tool -> agent.step_completed`）可以通过集成测试稳定跑通，并且 DEBUG 日志中已包含 `LLM call input`，便于排查问题。
- 一键启动脚本 `scripts/dev.sh` 已支持端口检查、配置提示、进程联动退出；根目录 `npm run dev` 可以统一启动前后端。
- 在当前环境中，`sqlite3` 比 `aiosqlite` 更稳定；仓储层切换为 `sqlite3` 后，启动与测试阻塞问题消失。

失败/风险经验：
- 当前环境缺少 `uv`，且 `python` 命令不存在（仅有 `python3`），脚本必须显式使用 `python3`。
- 当前环境运行 Playwright Chromium 缺少系统库（如 `libatk-1.0.so.0`），`npx playwright install --with-deps` 需要 sudo 密码，无法自动完成，导致前端 e2e 无法在本机执行。
- 当前环境对 `localhost` 访问存在限制，基于真实端口的后端 e2e不稳定；优先使用进程内事件流集成测试验证后端逻辑。

### 2026-03-05 真实API回归补充

成功经验：
- 在越权网络环境下，`api.uniapi.io` 和 `google.serper.dev` 都可连通，真实调用可以跑到“LLM首轮 + 多个 Serper 工具并发执行”。  

失败/风险经验：
- 当前后端在第二次 `chat.completions` 请求中，会把上一轮 assistant 的 `tool_calls` 以 `{id,name,arguments}` 回传，但缺少 `tool_calls[*].type=\"function\"`，导致 OpenAI 兼容网关返回 `400 invalid_value`。  
- `scripts/dev.sh` 启动后端时工作目录在 `backend/`，默认不会读取仓库根目录 `config.yml`；需要显式同步配置或调整配置加载路径。

### 2026-03-05 Bug修复补充

成功经验：
- 对 OpenAI provider 增加消息归一化后，真实链路可通过：首轮 LLM -> 工具并发 -> 二轮 LLM -> `agent.step_completed`。  
- `tool` 消息携带 `tool_call_id` 后，上下文关联更稳定，兼容网关不会因字段缺失拒绝请求。  

风险提醒：
- 真实链路下模型输出不稳定，前端 e2e 断言不应依赖固定文案；建议断言事件类型或结构化字段。

### 2026-03-05 配置与前端回归补充

成功经验：
- 仅在仓库根目录 `config.yml` 配置 `OPENAI_API_KEY`/`SERPER_API_KEY` 时，配置加载应自动将 `agent.provider` 切到 `openai`，否则前端 e2e 会误跑 `mock` provider。  
- 当 `agent.default_model` 未显式配置时，按当前 provider 自动回填默认模型（如 `openai -> gpt-4o-mini`）可避免 provider 与 model 不匹配。  
- Playwright 断言改为“WebSocket 已连接 + 用户消息已回显 + 出现非用户响应气泡”后，对真实 API 返回波动更稳健。  

失败/风险经验：
- `npm run test:backend:e2e` 依赖 `pytest` 可执行文件，当前环境不存在该命令；需要使用 `python3 -m pytest` 或改脚本兼容。  

### 2026-03-07 CLI 交互修复补充

成功经验：
- `asyncio` 场景下仅在 `Prompt.ask` 外层捕获 `KeyboardInterrupt` 不够，需额外注册 `SIGINT` 处理器并在主循环兜底捕获，才能避免连续 `Ctrl+C` 直接退出。
- 将命令输入统一做 `strip()` 后再分派，可稳定识别 ` / ` 与 `/quit`，避免因为前后空白导致命令失效。
- 将输入分派提炼为纯函数（`parse_user_input`）后，可用轻量单测快速覆盖 `/` 菜单、`/quit` 退出和未知命令行为。

失败/风险经验：
- 当前环境运行 `uv` 默认缓存目录 `~/.cache/uv` 可能无权限，需要显式设置 `UV_CACHE_DIR=/tmp/uv_cache`。
- 若本地未同步 dev 依赖，`uv run python -m pytest` 会报 `No module named pytest`，需先执行 `uv sync --extra dev`。

### 2026-03-07 CLI 即时命令菜单补充

成功经验：
- 终端若使用按行读取（如 `Prompt.ask`），`/` 命令天然需要回车；要实现“按下 `/` 立即弹菜单”，需要切到逐字符读取（raw mode）。
- 通过 `termios + tty.setraw` 在“输入缓冲为空且按下 `/`”时直接返回命令动作，可实现无需回车的命令菜单触发。
- 将“是否触发即时菜单”抽成纯函数（`should_trigger_menu_on_keypress`）后，能用单测稳定覆盖该交互规则。

失败/风险经验：
- `termios` 仅适用于类 Unix 终端；非 TTY/不支持环境需保留按行读取降级路径，避免脚本不可用。

### 2026-03-14 测试审查补充

成功经验：
- `tests/` 已是当前唯一有效的 pytest 根目录；对外脚本若继续引用旧 `test/`/`backend/` 结构，会直接造成“脚本存在但不覆盖真实测试”的假象，需尽快收敛到 `tests/`。
- 为 agent 核心链路单独补一个进程内 e2e 用例最有效：验证“首轮 `llm.call_requested` -> `tool.call_requested/result` -> 二轮 `llm.call_requested` -> `agent.step_completed`”，同时断言第二轮消息里确实带有 assistant `tool_calls` 与 tool 结果消息。
- 在当前受限环境下，测试脚本默认优先使用 `python3 -m pytest` 比自动走 `uv run` 更稳；若确实需要 `uv`，应显式开启并设置 `UV_CACHE_DIR=/tmp/uv_cache`。

失败/风险经验：
- `tests/e2e/run_e2e.py` 虽能做真实 API 回归，但它是手动脚本，不会被 `pytest tests/e2e/` 自动覆盖；核心链路断言不能只放在这个脚本里。
- 真实 API 回归仍依赖网络与 API key；当前本机只能稳定验证 mock provider 的完整编排链路，不能在无密钥/无网络条件下宣称真实 provider 已回归。

### 2026-03-17 WhatsApp Channel 核心接入补充

成功经验：
- 新 channel 接入可直接复用 `wecom` 的测试结构：先补 `config/plugin/channel/e2e` 四层测试，再落生产代码，能快速把“模块不存在”推进到“完整链路通过”。
- WhatsApp 这类外部 IM 渠道，最好把“AgentOS channel 逻辑”和“底层 runtime/协议 bridge”拆开；`channel.py` 只负责会话映射、策略和事件桥接，后续替换真实 runtime 不需要重写业务层。
- 进程内 e2e 里若要验证 DEBUG 日志，必须显式把 `system.agentos_home` 指到测试临时目录；否则日志默认写到 `~/.agentos/logs`，在受限环境下容易触发权限问题。

失败/风险经验：
- 当前仓库的 WhatsApp 接入只完成了核心 channel 层与 bridge 抽象，默认 `LocalBridgeStub` 还不具备真实 WhatsApp Web 收发能力；不能把“测试链路通过”误判为“生产可扫码可收发”。
- Python 生态缺少像 `openclaw` 所用 runtime 那样成熟稳定的 WhatsApp Web 实现，真实 bridge 落地前必须继续评估依赖、登录态存储和浏览器/协议兼容性。

### 2026-03-17 WhatsApp Sidecar 补充

成功经验：
- 对“Python 主体 + Node sidecar”这类跨语言接入，先用假 sidecar 脚本把 NDJSON 协议层测通最有效；这样能在不依赖真实 Node/Baileys 的情况下先验证子进程、响应匹配、超时和事件分发。
- 当前安装的 `@whiskeysockets/baileys` 导出是命名导出 `makeWASocket`，不是默认导出；接 runtime 前最好先用 `node -e "import(...)"` 打印实际导出，避免在启动链路里盲猜 API。
- sidecar 入口应做到“未收到 `start` 前不导入重依赖”，这样即使未扫码或未联网，也能先跑通 `booting -> 接收命令` 的最小自检。

失败/风险经验：
- 即使 `npm install` 成功、`start/status/stop` 自检通过，也只能说明 Baileys 能被加载并初始化 socket，不能替代真实扫码与消息收发验证。
- `fetchLatestWaWebVersion` 这类可能访问网络的 Baileys API 不适合作为第一版启动必需路径；最小实现优先避免在 `start` 期间引入额外网络依赖。

### 2026-03-18 WhatsApp 登录页补充

成功经验：
- 对“全前端任意页面未授权即跳转”的需求，最稳的落点是 `ProtectedRoute` 这类全局保护层，而不是逐页加判断；后端只需提供一个统一的 WhatsApp 状态接口。
- 若二维码最终展示在前端，最简单的链路是 sidecar 直接把 QR 转成 `data URL`，前端只渲染 `<img>`，避免额外引入前端二维码生成依赖。
- 为 `gateway` API 增加 `whatsapp/status` 这种单点状态端点后，前端 Guard 和独立登录页都能复用同一份数据结构，逻辑更容易收敛。

失败/风险经验：
- 当前 Playwright 配置会联动启动整套 `npm run dev`，在受限环境下后端 watch 模式可能直接因为系统权限失败，导致前端 e2e 不是页面逻辑失败而是基础设施失败。
- `next build` 在当前环境会因为 `next/font` 访问 Google Fonts 失败而中断；这种网络型失败不能误判为新页面或跳转逻辑本身有语法问题。

### 2026-03-17 Telegram Channel 接入补充

成功经验：
- `python-telegram-bot` 适合作为 Telegram 第一版接入 SDK：`Update.de_json`、`Bot.get_updates`、`Bot.send_message` 足以支撑 polling/webhook、topic 回复和文本消息桥接。
- Telegram channel 可以继续复用 `wecom/whatsapp` 的结构化接入方式：`config/plugin/channel/runtime/models + unit/e2e`，先把测试补齐，再落生产代码，推进很稳。
- 进程内 e2e 仍然是验证这类 IM channel 的最高性价比手段；通过 fake runtime 注入真实样式的入站消息，能稳定覆盖 `USER_INPUT -> mock LLM -> AGENT_STEP_COMPLETED -> 出站回复` 全链路。

失败/风险经验：
- 当前环境下 `uv sync` 与 `uv pip install` 都可能在 Rust `system-configuration` 层 panic，不能假设 `uv` 一定可用；若必须安装新依赖，需要准备降级到 `pip` 并申请越权网络。
- `python-telegram-bot` 的对象反序列化要求比裸 JSON 严格，例如 `User` 需要 `first_name`、`PhotoSize` 需要 `file_unique_id/width/height`；测试数据必须按 SDK 的真实字段构造，否则会在 `de_json` 阶段失败。

### 2026-03-18 Feishu 插件发现补充

成功经验：
- 插件注册表若要发现 channel 插件，必须扫描实际落盘位置；当前仓库的内置 channel 插件都在 `agentos.adapters.channels.<name>.plugin`，只扫 `agentos.adapters.plugins` 会导致 Gateway 完全无感知。
- 对“Web 端没显示某 channel”这类问题，先跑 `PluginRegistry.load_plugins()` 的最小单测最有效，能直接区分“前端展示问题”和“后端根本没注册”。
- 插件发现修复后，顺手把 `feishu/wecom/telegram/whatsapp` 的发现断言集中到单测里，能防止后续新 channel 再被扫描逻辑漏掉。

失败/风险经验：
- `config_api.update_config_sections()` 当前只会重载 `config.data`，不会热注册/反注册 channel 插件；用户在 Web 里改完 `plugins.feishu` 后仍需要重启后端，不能误以为“保存成功”就代表运行时已接入。
- 部分飞书插件单测的工具数量断言容易随默认工具开关漂移；这类测试应断言工具名集合，不要把实现细节硬编码成固定数量。

### 2026-03-18 企微官方 SDK 移植补充

成功经验：
- 当用户不希望依赖外部安装包时，可以把第三方 SDK 源码整体移植到仓库内部，再由 `tool_client.py` 做一层包装；对这类“协议 SDK + 业务 channel”接入，保留 upstream 文件结构最利于后续继续对照更新。
- `WecomToolClient` 采用可注入的 `client_factory` 与 `options_cls` 后，能在不连接真实 WebSocket 的情况下稳定覆盖“创建 SDK client、注册 `message.text` 回调、调用 `send_message` 发 Markdown”这些关键行为。
- 企微文本帧目前可以稳定从 `body.text.content`、`body.chatid`、`body.chattype`、`body.from.userid` 和 `headers.req_id` 提取入站消息，缺失时再用回退逻辑兜底。

失败/风险经验：
- 仅移植 SDK 源码不等于可运行，运行依赖如 `pyee`、`aiohttp`、`cryptography` 仍需同步补到 `pyproject.toml` 并安装，否则内部 `sdk/__init__.py` 一 import 就会失败。
- 企微 e2e 若调用 `setup_logging()`，必须显式把 `system.agentos_home` 指向测试临时目录；否则日志会默认落到 `~/.agentos/logs`，在当前环境下容易直接因权限问题失败。

### 2026-03-18 搜索工具扩展补充

成功经验：
- 为多个外部搜索工具统一输出结构（`provider/query/items`）最省心，Agent 侧和测试侧都无需为 Brave、Baidu、Tavily 分别写特殊分支。
- 对需要 API key 的外部搜索工具，在 `ToolRegistry.as_llm_tools()` 中按 provider 动态过滤非常有效：`mock` provider 保留工具便于链路测试，真实 provider 则自动隐藏未配置 key 的工具，能显著减少模型误调用空工具。
- `httpx.AsyncClient` 用 `AsyncMock + __aenter__/__aexit__` 包装后，工具级 HTTP 契约测试可稳定覆盖请求头、请求体和响应映射，不需要真实网络。

失败/风险经验：
- 当前环境下真实 `gemini` 进程内 e2e 仍不稳定：`serper_search` 返回 `403 Forbidden` 后，模型会回退到多次 `bash_command` 探测，最终超时，说明“真实 provider 回归”不能只看工具注册是否成功，还要验证外部 key 的真实性和可用性。
- 新增的 `tests/e2e/test_live_search_tools.py` 只有在对应 `BRAVE_SEARCH_API_KEY`、`BAIDU_APPBUILDER_API_KEY`、`TAVILY_API_KEY` 配置后才会真正执行；无 key 场景下会全部 skip，不能误判为真实回归已完成。

### 2026-03-18 前端重连恢复补充

成功经验：
- `/chat` 页面使用的是独立 WebSocket 状态机，不走 `WebSocketContext`；排查“服务重启后首次访问卡住、刷新恢复”时必须直接看 `agentos/app/web/app/chat/page.tsx`。
- 仅修自动重连不够，重连成功后还要补拉 session 列表，并对当前 session 发 `load_session` 重新绑定 WebSocket，否则历史会话后续回复仍可能收不到。
- Playwright 回归测试里如果要模拟业务 WebSocket，必须只拦截 `localhost:8000/ws` 这一条连接并保留 Next dev 的 HMR WebSocket；否则页面会因为开发态连接被破坏而卡在认证/加载阶段。
- 对根入口 `/?token=...`，真正可靠的统一方式不是只改 `app/page.tsx`，而是让 `AuthProvider` 在根路径检测到 token 后立刻跳到 `/chat?...`；否则 `AuthProvider` 可能先把根路径里的 token 清掉，导致页面组件读到的 query 已经不完整。

失败/风险经验：
- `switchSession` 只做 HTTP 拉历史不能恢复事件投递；后端真正的 session-to-websocket 绑定发生在 `create_session`/`load_session` 这类 WS 消息里，不补这一层前端看起来“打开了会话”，实际收不到后续事件。
- 当前前端全量构建仍存在与本次改动无关的既有类型错误：`agentos/app/web/components/ThemeProvider.tsx` 依赖 `next-themes/dist/types`，`npm run build` 会在该文件失败，因此不能把这次任务表述为“整个前端构建通过”。

### 2026-03-19 WhatsApp 405 调试补充

成功经验：
- 对照参考实现时，先抓 sidecar 的实时事件序列比只看聚合后的 `/api/gateway/whatsapp/status` 更有效；`connected to WA -> attempting registration -> 405` 直接说明问题发生在注册握手阶段，而不是前端 QR 展示层。
- `openclaw` 的 WhatsApp runtime 关键不只是在 `makeWASocket`，还包括 `fetchLatestBaileysVersion`、`makeCacheableSignalKeyStore(state.keys, logger)` 和更接近真实客户端的 `browser` 标识；这些参数差异足以影响“能连上 WA 但拿不到 QR”的行为。
- 给 Node sidecar 增加 `node:test` 级单测，并把 Baileys loader 做成可注入后，可以在不触网的情况下精确验证 socket 构造参数，适合这类跨语言 runtime 调试。

失败/风险经验：
- 仅清理 `auth_dir` 不足以解决持续 `405`；如果 socket 构造参数和参考实现有偏差，WhatsApp 仍可能在 `attempting registration` 后直接拒绝会话且不下发 QR。
- 当前受限执行环境里的网络结果不能直接代表用户本机终端；像 DNS/WS 这类结论必须优先以用户实际启动 sidecar 的终端输出为准。

### 2026-03-19 WhatsApp 入站消息补充

成功经验：
- 当用户反馈“已登录但不回复消息”时，先判断是“出站失败”还是“根本没入站”；日志里完全没有 `agentos.adapters.channels.whatsapp` 相关记录时，优先怀疑 sidecar 的 `messages.upsert` 抽取逻辑。
- 真实 WhatsApp 文本消息经常包在 `ephemeralMessage`、`viewOnceMessageV2`、`editedMessage` 这类 wrapper 里；只读最外层 `conversation/extendedTextMessage` 很容易导致消息被静默忽略。
- 对这类协议层问题，给 Node sidecar 补一层 `node:test` 用例最有效：直接构造 `messages.upsert` 事件，断言是否发出了 `type=message`，比从 Python 侧反推更快。

失败/风险经验：
- 即使 channel/e2e 都通过，如果 sidecar 的文本解包逻辑过窄，生产环境仍会表现为“登录正常但没有任何回复”；进程内 e2e 不能替代真实协议样本覆盖。

### 2026-03-19 WhatsApp Self Chat 补充

成功经验：
- 对 WhatsApp Web 而言，“自己给自己发消息”在 Baileys 里会表现为 `fromMe=true`，但这不一定代表“机器人自己的出站回执”；是否放行必须结合 `sock.user.id` 和 `remoteJid/participant` 一起判定。
- 最稳的策略是只放开“当前登录账号的 self chat 私聊”这一类 `fromMe=true`，其它 `fromMe=true` 继续忽略，这样能支持自聊触发，同时避免把机器人回复再次吃回去形成回环。
- 这类协议行为非常适合用 Node 侧最小单测锁定：一条 self chat `fromMe=true` 应产出 `message`，一条非 self chat `fromMe=true` 必须继续被忽略。

失败/风险经验：
- 仅凭 `fromMe=true` 或仅凭 `remoteJid` 都不足以判断 self chat；像 `@lid` 这类回执/同步消息也可能带 `fromMe=true`，放开过宽会直接引入重复触发或消息回环。

### 2026-03-19 WhatsApp 408 重连补充

成功经验：
- `WebSocket Error (Opening handshake has timed out) | statusCode=408` 更像瞬时连接失败，而不是登录态损坏；这种场景应保留 `auth_dir` 做有限次数自动重连，不要走 `401/405` 的清缓存分支。
- 把 `restartDelayMs` 和 `reconnectDelayMs` 做成可注入参数后，Node 侧重连/重启测试可以在 0ms 延迟下稳定跑通，不需要为测试等待真实超时。

失败/风险经验：
- `408` 如果不单独处理，运行时会停在 `closed`，用户感知就是“偶尔自己掉线”；这类问题不是业务逻辑 bug，而是连接恢复策略缺失。
