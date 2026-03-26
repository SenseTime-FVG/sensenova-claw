

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
- WhatsApp 这类外部 IM 渠道，最好把“Sensenova-Claw channel 逻辑”和“底层 runtime/协议 bridge”拆开；`channel.py` 只负责会话映射、策略和事件桥接，后续替换真实 runtime 不需要重写业务层。
- 进程内 e2e 里若要验证 DEBUG 日志，必须显式把 `system.sensenova_claw_home` 指到测试临时目录；否则日志默认写到 `~/.sensenova-claw/logs`，在受限环境下容易触发权限问题。

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

### 2026-03-17 Telegram Channel 接入补充

成功经验：
- `python-telegram-bot` 适合作为 Telegram 第一版接入 SDK：`Update.de_json`、`Bot.get_updates`、`Bot.send_message` 足以支撑 polling/webhook、topic 回复和文本消息桥接。
- Telegram channel 可以继续复用 `wecom/whatsapp` 的结构化接入方式：`config/plugin/channel/runtime/models + unit/e2e`，先把测试补齐，再落生产代码，推进很稳。
- 进程内 e2e 仍然是验证这类 IM channel 的最高性价比手段；通过 fake runtime 注入真实样式的入站消息，能稳定覆盖 `USER_INPUT -> mock LLM -> AGENT_STEP_COMPLETED -> 出站回复` 全链路。

失败/风险经验：
- 当前环境下 `uv sync` 与 `uv pip install` 都可能在 Rust `system-configuration` 层 panic，不能假设 `uv` 一定可用；若必须安装新依赖，需要准备降级到 `pip` 并申请越权网络。
- `python-telegram-bot` 的对象反序列化要求比裸 JSON 严格，例如 `User` 需要 `first_name`、`PhotoSize` 需要 `file_unique_id/width/height`；测试数据必须按 SDK 的真实字段构造，否则会在 `de_json` 阶段失败。

### 2026-03-17 ask_user 收尾补充

成功经验：
- ask_user 闭环建议采用“双轨验证”：`pytest` 进程内 e2e 固化事件链（`question_asked -> question_answered -> step_completed`），再补一个独立真实 API 脚本验证线上 provider 行为。
- 前端 Playwright 用例将 mock websocket 回归与真实 API 回归拆分后更稳；真实 API 用例通过 `ENABLE_REAL_API_E2E=1` 门控，默认不会误触发慢测。
- 回归脚本保留关键事件打印（含 `question_id`、answer payload）后，排查 ToolSessionWorker 的等待/恢复逻辑明显更高效。

失败/风险经验：
- 当前环境运行 Playwright Chromium 仍缺系统库（`libnspr4.so`）；`npx playwright install --with-deps chromium` 需要 sudo 密码，未授权时无法完成前端浏览器级 e2e。
- 本地网络权限与沙箱能力会影响真实 API 回归；出现 DNS/连接异常时需在越权网络下复跑，避免把环境问题误判为功能缺陷。

### 2026-03-18 WhatsApp 登录页补充

成功经验：
- 对“全前端任意页面未授权即跳转”的需求，最稳的落点是 `ProtectedRoute` 这类全局保护层，而不是逐页加判断；后端只需提供一个统一的 WhatsApp 状态接口。
- 若二维码最终展示在前端，最简单的链路是 sidecar 直接把 QR 转成 `data URL`，前端只渲染 `<img>`，避免额外引入前端二维码生成依赖。
- 为 `gateway` API 增加 `whatsapp/status` 这种单点状态端点后，前端 Guard 和独立登录页都能复用同一份数据结构，逻辑更容易收敛。

失败/风险经验：
- 当前 Playwright 配置会联动启动整套 `npm run dev`，在受限环境下后端 watch 模式可能直接因为系统权限失败，导致前端 e2e 不是页面逻辑失败而是基础设施失败。
- `next build` 在当前环境会因为 `next/font` 访问 Google Fonts 失败而中断；这种网络型失败不能误判为新页面或跳转逻辑本身有语法问题。

### 2026-03-18 Feishu 插件发现补充

成功经验：
- 插件注册表若要发现 channel 插件，必须扫描实际落盘位置；当前仓库的内置 channel 插件都在 `sensenova-claw.adapters.channels.<name>.plugin`，只扫 `sensenova-claw.adapters.plugins` 会导致 Gateway 完全无感知。
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
- 企微 e2e 若调用 `setup_logging()`，必须显式把 `system.sensenova_claw_home` 指向测试临时目录；否则日志会默认落到 `~/.sensenova-claw/logs`，在当前环境下容易直接因权限问题失败。

### 2026-03-18 搜索工具扩展补充

成功经验：
- 为多个外部搜索工具统一输出结构（`provider/query/items`）最省心，Agent 侧和测试侧都无需为 Brave、Baidu、Tavily 分别写特殊分支。
- 对需要 API key 的外部搜索工具，在 `ToolRegistry.as_llm_tools()` 中按 provider 动态过滤非常有效：`mock` provider 保留工具便于链路测试，真实 provider 则自动隐藏未配置 key 的工具，能显著减少模型误调用空工具。
- `httpx.AsyncClient` 用 `AsyncMock + __aenter__/__aexit__` 包装后，工具级 HTTP 契约测试可稳定覆盖请求头、请求体和响应映射，不需要真实网络。

失败/风险经验：
- 当前环境下真实 `gemini` 进程内 e2e 仍不稳定：`serper_search` 返回 `403 Forbidden` 后，模型会回退到多次 `bash_command` 探测，最终超时，说明“真实 provider 回归”不能只看工具注册是否成功，还要验证外部 key 的真实性和可用性。
- 新增的 `tests/e2e/test_live_search_tools.py` 只有在对应 `BRAVE_SEARCH_API_KEY`、`BAIDU_APPBUILDER_API_KEY`、`TAVILY_API_KEY` 配置后才会真正执行；无 key 场景下会全部 skip，不能误判为真实回归已完成。

### 2026-03-18 ask_user 超时稳态修复补充

成功经验：
- `ask_user` 需要区分”工具外层超时”和”ask_user 内层等待超时”：仅在 `ToolSessionWorker` 中把 `ask_user` 默认超时提升到 `300s`，才能避免用户输入过程中被 15 秒通用超时提前打断。
- `TimeoutError` 常见空字符串，错误链路统一采用 `str(exc).strip() or type(exc).__name__` 后，前端错误提示可稳定显示为 `TimeoutError`，不再退回 `Unknown Error`。
- 在 `chat/session` 两个页面都加 `session_id` 过滤，可以避免其他会话的 `turn_completed/error` 事件误关闭当前 `ask_user` 弹窗。

失败/风险经验：
- 前端 Playwright 在当前环境仍受系统库限制（缺 `libnspr4.so`），即使越权运行也无法启动 Chromium；`npx playwright install --with-deps chromium` 需要 sudo 密码，未授权时无法完成浏览器级回归。
- `tests/e2e/run_e2e.py` 的 `setup_services(provider=\”mock\”)` 仍存在被本地 `config.yml` 实际 provider 覆盖的风险；ask_user 进程内 e2e 需在用例中显式固定 `agent.model`/`llm.default_model` 为 `mock` 才稳定。

### 2026-03-18 chat 跨窗口 ask_user 修复补充

成功经验：
- `WebSocketChannel.send_event` 对 `USER_QUESTION_ASKED/USER_QUESTION_ANSWERED` 做连接级广播后，前端无需先切换会话也能收到跨 session 的 `ask_user` 事件。
- 为 `USER_QUESTION_ANSWERED` 增加下行映射事件（`user_question_answered_event`）后，多窗口可用 `question_id` 做状态收敛，避免”一个窗口已回答、另一个窗口仍挂弹窗”。
- `user_input` 在携带已有 `session_id` 时补做 `gateway.bind_session + channel.bind_session`，能稳定修复”旧会话发消息后收不到后续事件”的问题；对应 `tests/unit/test_gateway_ws_endpoint_ask_user.py` 可直接回归。

失败/风险经验：
- 当前环境 `next build` 仅返回泛化的 “Build failed because of webpack errors”，无具体堆栈；前端编译问题排查应优先结合本地 IDE/CI 日志而非仅依赖该环境终端输出。
- Playwright 仍受系统库缺失影响（`libnspr4.so`），即使越权执行测试命令也无法启动 Chromium，浏览器级 e2e 结果不能在本机作为通过依据。
- `tests/e2e/test_gateway_integration.py` 在默认 `SENSENOVA_CLAW_HOME` 下会写到只读路径（`/home/languilin/.sensenova-claw/logs`）导致失败；需要显式设置可写 `SENSENOVA_CLAW_HOME` 后再跑。

### 2026-03-18 子会话继承 channel 绑定补充

成功经验：
- 在 `Gateway._dispatch_event` 中做”按 `parent_session_id` 递归查找已绑定祖先 + 命中后缓存绑定”，可以最小改动修复 `send_message` 子会话事件无法路由到前端的问题，且不会影响已绑定会话的常规路径。
- `/sessions/[id]` 页面处理 ask_user 时，必须保存 `sourceSessionId` 并在 `user_question_answered` 回传时使用来源 session；否则跨会话提问场景会持续超时。
- WebSocket 监听 effect 去除 `pendingQuestion` 依赖后，避免了问答状态变更导致的重复重连和潜在丢事件。

失败/风险经验：
- 当前环境缺少 `pytest` 运行时（`python3 -m pytest` 报 `No module named pytest`），后端新增测试只能先做静态校验，需在完整依赖环境复跑。
- 当前环境执行 Playwright 仍缺浏览器二进制（`chrome-headless-shell` 不存在），即使越权可启动流程也无法完成浏览器级断言。
- `next build` 在本机会停在 `Linting and checking validity of types ...` 且无进一步堆栈，需在 CI 或本地完整 Node 环境结合日志排查。

### 2026-03-19 skills prompt 注入补充

成功经验：
- skills 只注入 `name/description/location` 时，模型未必会主动读取正文；在 system prompt 中增加一条极简 `Skill Usage` 规则，明确”匹配到 skill 后先读对应 `SKILL.md`”，效果更稳定。
- 将 skills 列表从自由文本改为 `<available_skills><skill><name><description><location>` 结构后，测试断言和后续字段扩展都更直接。
- 当前仓库虽缺少全局 `pytest`，但可稳定使用 `.venv/bin/python -m pytest` 跑本地回归，适合作为受限环境下的默认验证方式。

失败/风险经验：
- 仅替换标签格式而不补”命中后去读 `SKILL.md`”的协议指令，收益有限；真正影响模型行为的是规则和结构一起改。

### 2026-03-19 email-agent 工具接入补充

成功经验：
- Agent 侧 `tools` 白名单与全局 `ToolRegistry` 注册缺一不可；仅修改 `.sensenova-claw/agents/<id>/config.yml` 不会让未注册工具自动可用。
- 对预置 Agent 配置做回归时，直接用仓库内真实 `.sensenova-claw/agents/<id>/config.yml` 构造 `AgentRegistry` 断言，比复制一份测试夹具更能防止配置漂移。
- 当前环境执行 pytest 应优先使用 `.venv/bin/python -m pytest`；系统 `python3` 缺少 `pytest`，直接调用会误判为测试无法运行。

失败/风险经验：
- 邮件工具虽然注册后会暴露给运行时，但真实可用性仍依赖 `tools.email.enabled` 及 SMTP/IMAP 凭据；仅单元测试通过不能代表邮件链路已完成真实回归。

### 2026-03-18 前端重连恢复补充

成功经验：
- `/chat` 页面使用的是独立 WebSocket 状态机，不走 `WebSocketContext`；排查”服务重启后首次访问卡住、刷新恢复”时必须直接看 `sensenova_claw/app/web/app/chat/page.tsx`。
- 仅修自动重连不够，重连成功后还要补拉 session 列表，并对当前 session 发 `load_session` 重新绑定 WebSocket，否则历史会话后续回复仍可能收不到。
- Playwright 回归测试里如果要模拟业务 WebSocket，必须只拦截 `localhost:8000/ws` 这一条连接并保留 Next dev 的 HMR WebSocket；否则页面会因为开发态连接被破坏而卡在认证/加载阶段。
- 对根入口 `/?token=...`，真正可靠的统一方式不是只改 `app/page.tsx`，而是让 `AuthProvider` 在根路径检测到 token 后立刻跳到 `/chat?...`；否则 `AuthProvider` 可能先把根路径里的 token 清掉，导致页面组件读到的 query 已经不完整。

失败/风险经验：
- `switchSession` 只做 HTTP 拉历史不能恢复事件投递；后端真正的 session-to-websocket 绑定发生在 `create_session`/`load_session` 这类 WS 消息里，不补这一层前端看起来”打开了会话”，实际收不到后续事件。
- 当前前端全量构建仍存在与本次改动无关的既有类型错误：`sensenova_claw/app/web/components/ThemeProvider.tsx` 依赖 `next-themes/dist/types`，`npm run build` 会在该文件失败，因此不能把这次任务表述为”整个前端构建通过”。

失败/风险经验：
- `npm run test:backend:e2e` 依赖 `pytest` 可执行文件，当前环境不存在该命令；需要使用 `python3 -m pytest` 或改脚本兼容。  

### 2026-03-18 Cron/通知/API Key 面板补充

成功经验：
- 将 `config.yml` 持久化逻辑抽到 `sensenova_claw/interfaces/http/config_store.py` 后，`config_api`、`tools` API key 管理和 `notification_api` 都能复用同一套“保留未知顶层字段 + 热重载”的写回路径，避免多处手写 YAML 合并逻辑。
- 通知系统最稳的落点是事件总线：`NotificationService -> notification.push / notification.session -> WebSocketChannel -> 前端 NotificationProvider`，这样浏览器 toast、浏览器原生通知和会话内系统消息可以共享同一份 payload。
- Cron UI 若直接复用 `CronRuntime` + `Repository.list_cron_runs()`，后端不需要新增第二套调度业务逻辑；前端只需要围绕 `/api/cron/jobs` 与 `/api/cron/jobs/{id}/runs` 做 CRUD 和历史面板即可。

失败/风险经验：
- 当前环境里 `python3 -m pytest` 仍不可用，验证新后端接口时要继续使用 `UV_CACHE_DIR=/tmp/uv_cache uv run python -m pytest ...`。
- 当前前端类型检查仍会先卡在既有问题 `sensenova_claw/app/web/components/ThemeProvider.tsx` 的 `next-themes/dist/types` 导入上；即使新页面本身通过，仓库级 `npx tsc --noEmit` / `npm run build` 也不能直接作为“本次改动失败”的依据。

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
- 当用户反馈“已登录但不回复消息”时，先判断是“出站失败”还是“根本没入站”；日志里完全没有 `sensenova-claw.adapters.channels.whatsapp` 相关记录时，优先怀疑 sidecar 的 `messages.upsert` 抽取逻辑。
- 真实 WhatsApp 文本消息经常包在 `ephemeralMessage`、`viewOnceMessageV2`、`editedMessage` 这类 wrapper 里；只读最外层 `conversation/extendedTextMessage` 很容易导致消息被静默忽略。
- 对这类协议层问题，给 Node sidecar 补一层 `node:test` 用例最有效：直接构造 `messages.upsert` 事件，断言是否发出了 `type=message`，比从 Python 侧反推更快。

失败/风险经验：
- 即使 channel/e2e 都通过，如果 sidecar 的文本解包逻辑过窄，生产环境仍会表现为“登录正常但没有任何回复”；进程内 e2e 不能替代真实协议样本覆盖。

### 2026-03-20 Gateway Channel 失败态补充

成功经验：
- `/api/gateway/channels` 适合做统一状态汇总层；优先读取 channel 自身、`_runtime`、`_client` 上的 `_sensenova-claw_status`，前端就不需要分别理解 `feishu/telegram/wecom` 的内部实现。
- `/gateway` 的失败态展示可以完全复用 WhatsApp 现有红色视觉 token，只需新增 `status === "failed"` 分支，避免再为每个 channel 做单独样式。
- Playwright 若只验证前端页面渲染，最好绕开仓库默认 `webServer`，单独启动 `sensenova_claw/app/web` 的 `next dev` 并用最小配置执行；否则容易被后端 `uv` 启动链路干扰。

失败/风险经验：
- 当前环境下默认 Playwright 配置会经过根目录 `npm run dev`，而这条链路里的 `uv` 可能 panic；前端页面级回归不能假设默认配置一定可用。
- macOS 沙箱下直接启动 Chromium 可能报 `bootstrap_check_in ... Permission denied (1100)`；浏览器级 e2e 需要越权执行。

### 2026-03-20 WhatsApp ask_user 出站补充

成功经验：
- 当日志停在 `tool.call_requested(ask_user) -> user.question_asked`，而前端能看到问题、IM 渠道没有收到时，优先检查对应 channel 的 `event_filter()` 是否订阅了 `USER_QUESTION_ASKED`，以及 `send_event()` 是否有实际下发逻辑。
- 对这类 channel 断点，最有效的红绿验证不是先跑整套 e2e，而是直接构造最小 `send_event(EventEnvelope(type=USER_QUESTION_ASKED,...))` 进程内脚本；可以快速区分“事件没订阅”与“底层发送失败”。
- WhatsApp channel 订阅并转发 `user.question_asked` 后，`ask_user` 的澄清问题就能像普通回复一样发回原始 `chat_jid`，避免出现“Web 会话显示已提问，但用户侧完全无感知”的假象。

失败/风险经验：
- 仅凭前端 session 出现气泡，不能推断外部 IM 已收到消息；前端可能是 WebSocket 广播收到了 `user.question_asked`，而 channel 因未订阅该事件完全没有出站动作。
- 当前环境 `.venv` 缺少 `pytest`，`uv run python -m pytest` 又可能在 macOS 上因 `system-configuration` panic；验证新增测试时要准备进程内脚本兜底，不能把测试工具故障误判为业务修复失败。

### 2026-03-20 IM Channel ask_user 对齐补充

成功经验：
- 对多 IM channel 做相同行为补齐时，最稳的检查清单就是两项：`event_filter()` 是否包含 `USER_QUESTION_ASKED`，`send_event()` 是否把 `payload.question` 走到统一 `_send_reply()`；漏任一项都会出现“前端看得到、外部渠道收不到”。
- Telegram、WeCom、Feishu 这三类实现虽然底层发送接口不同，但 `ask_user` 出站都可以复用同一条最小规则：“收到 `USER_QUESTION_ASKED` 就原样发送 question 文本”，不需要单独设计新事件或新模板。
- 在 `pytest` 不可用时，单个进程内脚本同时验证多个 channel 的 `send_event + event_filter`，是做跨渠道回归的高性价比手段。

失败/风险经验：
- WeCom 之前没有显式 `event_filter()`，默认 `None` 看起来“像是全订阅”，但如果 `send_event()` 不处理 `USER_QUESTION_ASKED`，实际效果仍然是静默丢弃；不能只看订阅层，不看分发层。

### 2026-03-24 Workbench ask_user 输入修复补充

成功经验：
- 工作台 `/chat` 的 `ask_user` 不只是“输入框被禁用”问题，还要检查主输入框提交路径是否会把自由文本映射成 `user_question_answered`；只解锁输入框但仍发送普通 `user_input`，后端 `ask_user` 仍会一直挂起。
- `ChatSessionContext` 已经暴露了 `activeInteraction/sendQuestionAnswer`，在聊天页直接复用这条能力，比重新造一套 `ask_user` 提交协议更稳，改动也更小。

失败/风险经验：
- `sensenova_claw/app/web/e2e/ask-user.spec.ts` 当前夹具陈旧，至少有三类问题会干扰业务回归：鉴权会落到登录页、mock WebSocket 会影响 Next dev HMR、旧断言仍假设 `/chat` 使用 `ask-user-dialog` 弹窗而不是通知卡片。
- 对 `/chat` 做 Playwright 回归时，若直接全局替换 `window.WebSocket`，必须只拦截业务 `localhost:8000/ws`，并保留 Next dev/HMR 所需的 `addEventListener/removeEventListener`；否则页面会先 client-side exception，根本到不了业务断言。

### 2026-03-24 WhatsApp sidecar 入口路径兼容补充

成功经验：
- 当 WhatsApp 状态接口显示 `WhatsApp sidecar command timed out: start` 时，先看 `~/.sensenova-claw/logs/system.log` 里的 sidecar `stderr`，可以快速区分“协议启动慢”和“Node 入口文件根本不存在”；这次真实根因是 `MODULE_NOT_FOUND`。
- `plugins.whatsapp.bridge.entry` 的历史配置可能混入仓库目录名 `sensenova-claw/...`，而真实 Python 包路径是 `sensenova_claw/...`；在 `WhatsAppConfig._normalize_bridge_entry()` 里兼容这类连字符路径，比只依赖用户手动改配置更稳。
- 用一个最小单测锁定 `bridge.entry` 的归一化行为最有效：先让 `sensenova-claw/.../index.mjs` 明确失败，再做最小修复转绿，能避免把问题误判成 sidecar 超时参数不足。

失败/风险经验：
- 当前 `SidecarBridgeClient.start()` 在 sidecar 进程启动即崩溃时，对外仍只会表现为 `start` 超时；若后续还要提升可观测性，可以考虑把“子进程已退出 + 最近 stderr”直接折叠进异常信息，避免用户只看到泛化 timeout。

### 2026-03-24 WhatsApp sidecar 语法错误补充

成功经验：
- 当 `start` 超时在修正入口路径后仍存在，必须继续看 sidecar `stderr`，这次根因是 Node 在加载 `runtime.mjs` 时直接抛了 `SyntaxError: Invalid left-hand side in assignment`，并非 Baileys 启动卡住。
- JavaScript 内部私有挂载字段如果想保留“项目名前缀”，不要写成 `sock._sensenova-clawXxx` 这种带 `-` 的点属性；应统一改成字符串常量 + `sock[KEY]` 访问，既合法又便于复用。
- `node --test sensenova_claw/adapters/plugins/whatsapp/bridge/tests/runtime.test.mjs` 很适合做 sidecar 第一层红绿验证；模块级语法错误会在这里秒暴露，比等 Python 侧 30 秒超时高效得多。

失败/风险经验：
- Python 侧当前仍把“sidecar 进程启动后立即语法崩溃”包装成 `TimeoutError`，如果只看 `channel.py` 堆栈而不追 `stderr`，很容易误判成超时参数需要调大。

### 2026-03-24 WhatsApp 登录页瞬时错误态补充

成功经验：
- WhatsApp 扫码后的 `515 restart required after pairing` 属于预期中的瞬时重连，不应在登录页当成真正失败态展示；前端应把 `connecting/restarting/reconnecting/refreshing_qr` 这类状态视为过渡态。
- 登录页渲染错误卡时，除了 `lastError` 外，还要结合 `authorized/state/lastQrDataUrl` 一起判断；仅凭 `lastError` 很容易把“历史错误”误显示成“当前失败”。
- 给 Playwright 加一个 `state=restarting + lastError` 的最小用例很有价值，即使本机浏览器受沙箱限制暂时跑不起来，也能把预期行为固化在测试文件里，方便后续在可运行环境回归。

失败/风险经验：
- 当前 macOS 受限环境下 Playwright Chromium 仍会因 `bootstrap_check_in ... Permission denied (1100)` 无法启动，前端浏览器级断言不能在本机作为是否修复成功的唯一依据。

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

### 2026-03-19 Cron 通知扩展补充

成功经验：
- 对“聊天会话消息”“浏览器 Notification API”“后端桌面原生通知”三种提醒方式，复用统一的 `NotificationService` 和 `Notification.metadata` 最稳，不需要为 cron 单独再造一套路由协议。
- `delivery.mode="none"` 与 `delivery.session_id` 可以拆开理解：前者控制“是否写回聊天消息”，后者可继续作为浏览器通知的会话路由范围，这样从聊天里创建的 cron 能精准回到原会话标签页。
- 浏览器 toast 和浏览器原生 Notification API 必须分离控制；否则所有 websocket 通知都会误触发系统级浏览器提醒，无法体现“browser channel 是显式选择”的语义。

失败/风险经验：
- `CronRuntime.update_job()` 如果漏掉 `delivery` 字段赋值，API 层构造出的提醒配置会悄悄丢失，表现成“创建能用、编辑失效”的隐蔽 bug。
- `exclude_unset=True` 下前端显式发送的 `null` 与“字段未传”是两种语义；定时任务提醒配置更新时，必须用哨兵值区分“保留原 session”与“明确清空 session”。

### 2026-03-19 Cron 面板与手动触发补充

成功经验：
- `DialogContent` 基础组件自带 `sm:max-w-sm`，业务页如果只追加 `max-w-3xl` 并不能稳定覆盖响应式宽度；需要显式使用 `sm:max-w-*`/`lg:max-w-*` 才能真正修复大屏弹窗过窄的问题。
- 手动触发 cron 不能只是简单复用 `_execute_job()`；还要在运行后重新 `arm_timer`，否则启用状态任务的下一次调度可能不会按新的 `next_run_at_ms` 重新挂表。
- 禁用状态下的手动执行要单独处理 `next_run_at_ms`，否则任务会因为一次“Run Now”被意外重新排入自动调度。

失败/风险经验：
- 如果“Run Now”复用历史面板逻辑但不拆出独立的 `fetchRuns()`，触发成功后刷新展开行很容易误走“toggle 后收起”的分支，表现成用户刚手动执行，历史面板反而消失。

### 2026-03-19 Cron 原生通知开关补充

成功经验：
- “任务级显式通知渠道”和“全局默认通知渠道”要分开处理；像 cron job 上勾选 `native`/`browser` 这种明确请求，不应该再被默认配置里的 `notification.native.enabled=false` 静默拦截。

失败/风险经验：
- 如果 `NotificationService.resolve_channels()` 对显式 `channels=[...]` 仍套用全局子开关过滤，用户界面会表现成“明明勾选了 native，但什么都没发生”，而且排查时容易误以为是 `notify-send` 或系统桌面环境本身有问题。

### 2026-03-19 WhatsApp typingIndicator 配置补充

成功经验：
- 对“新增插件配置”这类改动，不能只停在 Python `config.py`；像 WhatsApp 这种 `Python channel + Node sidecar` 架构，配置需要贯穿 `config -> bridge_client -> start payload -> runtime.sendText` 才真正生效。
- 这类出站行为最适合用 Node 侧单测锁死顺序：直接断言 `sendPresenceUpdate("composing")` 是否在 `sendMessage()` 之前触发，能快速验证默认行为和 `none` 分支。
- 文档示例里的路径要同步到当前真实插件目录；否则用户很容易按旧的 `channels/whatsapp` 路径安装 sidecar，导致配置看起来正确但运行时走错目录。

失败/风险经验：
- 如果 runtime 里原本没有发送 typing/composing，仅增加 `typingIndicator` 配置不会有任何实际效果；要先确认当前 sidecar 的真实出站行为，再决定是”增加开关”还是”同时补行为 + 开关”。
- 当前环境里 `python3 -m pytest` 仍不可用，验证新后端接口时要继续使用 `UV_CACHE_DIR=/tmp/uv_cache uv run python -m pytest ...`。
- 当前前端类型检查仍会先卡在既有问题 `sensenova_claw/app/web/components/ThemeProvider.tsx` 的 `next-themes/dist/types` 导入上；即使新页面本身通过，仓库级 `npx tsc --noEmit` / `npm run build` 也不能直接作为”本次改动失败”的依据。

### 2026-03-19 Chat Markdown 设计补充

成功经验：
- 聊天区 Markdown 改造最稳的边界是”字符串走 Markdown、结构化内容走 JSON 查看器”，这样 `toolInfo.arguments/result` 不会因为富文本改造破坏原有结构化阅读体验。
- 在设计阶段就明确”增强版 Markdown + 禁止原始 HTML + 保留折叠逻辑”，能显著减少后续实现时的安全分歧与交互返工。
- 将通用渲染能力收敛为独立 `MarkdownRenderer` 组件，比在 `MessageBubble` 和工具详情区分别内联渲染更利于后续扩展代码高亮、链接策略与统一样式。

失败/风险经验：
- 当前会话环境没有可直接调用的 spec reviewer 子代理能力，设计文档阶段需要显式说明该限制，并以人工自检作为退化方案，避免误称已完成完整的 spec review loop。

### 2026-03-19 Chat Markdown 计划补充

成功经验：
- 当前前端同时存在共享 `components/chat/MessageBubble.tsx` 与页面内联 `MessageBubble`（`/chat`、`/sessions/[id]`）两套路径；实施计划里优先共享 `MarkdownRenderer` 和内容分流工具，而不是直接做大规模 UI 合并，能更符合 YAGNI。
- 对 Markdown 能力做前端回归时，优先新增 mock WebSocket 的 Playwright 用例比依赖真实模型输出更稳，断言 `h1/table/pre code` 等语义化节点也比断言文案本身更抗波动。

失败/风险经验：
- `docs/superpowers/` 当前被 `.gitignore` 忽略，后续如果需要把 spec/plan 正式纳入版本库，必须显式 `git add -f`，否则容易误以为文件已保存但实际上不会进入提交。

### 2026-03-19 Chat Markdown 执行补充

成功经验：
- `react-markdown` v10 不接受直接传 `className` 到根组件；最稳的写法是在外层包一层容器，再让 `ReactMarkdown` 只负责内容节点渲染。
- `/chat` 页面实时 websocket 链路中的 `tool_result` 消息并不带 `toolInfo`，如果只按 `msg.role === “tool” && msg.toolInfo` 分支渲染，会把工具结果误走到 assistant 展示路径；需要单独补一个”无 `toolInfo` 的 tool 消息”分支。
- 把 `isJsonLike/stringifyContent/previewText` 抽到共享工具后，共享消息组件、`/chat` 和 `/sessions/[id]` 三处展示层可以统一”JSON 优先，其余走 Markdown”的规则，减少分叉。

失败/风险经验：
- 当前环境浏览器级 Playwright 仍缺系统库 `libnspr4.so`，即使越权能拉起 web server，也会在 Chromium 启动阶段失败；这类前端 e2e 结果不能作为功能缺陷依据，只能记录为环境阻塞。
- `npx tsc --noEmit` 与 `next build` 仍会先被仓库既有问题 `components/ThemeProvider.tsx` 的 `next-themes/dist/types` 导入挡住；验证时必须区分”本次新增错误已清零”和”仓库老错误仍在”。

### 2026-03-20 MinerU 渠道选择 Skill 设计补充

成功经验：
- 对”保留旧 skill + 新增选择型 skill”的需求，先把”是否改旧 skill””是否包含网页””结果是否统一落盘”三条边界问清，再写 spec，能明显减少后续实现分叉。
- 使用官方 `mineru-open-api` CLI 的方案时，skill 文档最重要的不是安装说明，而是把”每次先 ask_user 选渠道、免费失败不自动切换、输出目录固定到 workspace”这几个行为约束写死。
- 对这类远程 API CLI，资源要求说明应基于官方产品形态谨慎表述为”通常较轻量”，不要虚构 CPU/内存硬指标。
- 若需求要求”CLI 未安装时由 skill 负责安装”，实现上不能把该 skill 用 `metadata.sensenova-claw.requires.bins` 做硬门控隐藏；否则 skill 在缺失 CLI 时不会被发现，也就无法触发安装流程。

失败/风险经验：
- 当前会话环境没有可调用的 spec reviewer 子代理能力；设计文档阶段只能采用人工自检退化方案，并需要在产物里显式注明，避免误称已完成完整 reviewer loop。
- `docs/superpowers/specs/` 受 `.gitignore` 影响，后续提交 spec 时要记得 `git add -f`，否则文件会留在工作区但不会进入提交。

### 2026-03-19 Agents 删除入口补充

成功经验：
- `/agents` 这种”卡片主体可导航 + 局部危险操作”的列表页，删除按钮最好从外层 `Link` 里拆出来，并配独立确认弹窗；否则删除点击容易被页面跳转吞掉。
- 当前环境可以跑前端浏览器级 e2e，但需要同时满足两个条件：`localhost:3000` 上已有可复用前端服务，以及提前把 Playwright 浏览器安装到可写目录（如 `PLAYWRIGHT_BROWSERS_PATH=/tmp/pw-browsers`）。

失败/风险经验：
- 仓库级 `npx tsc --noEmit` 仍会先命中既有问题：`sensenova_claw/app/web/components/ThemeProvider.tsx` 无法解析 `next-themes/dist/types`；验证这类页面级改动时，不能把这个历史错误误记为本次回归失败。

### 2026-03-19 Sessions 删除补充

成功经验：
- session 删除如果要同时清理数据库和 `~/.sensenova-claw/agents/{agent_id}/sessions/{session_id}.jsonl`，最简洁的落点是新增独立 `sessions` HTTP router：先通过 `repo.get_session_meta()` 解析 `agent_id`，再调用 `gateway.delete_session()` 删库解绑，最后删 JSONL 文件。
- `/sessions` 这种”整行可点击跳详情”的表格，删除按钮必须放在独立操作列里，并在 `onClick` 里显式 `stopPropagation()`；否则按钮会和行级跳转冲突。

失败/风险经验：
- 当前环境下 `uv run python -m pytest` 仍可能因为 Rust `system-configuration` panic 直接失败；针对性后端单测优先改用 `python3 -m pytest` 更稳。

### 2026-03-19 Sessions 批量删除补充

成功经验：
- “全选当前页面”和”全选当前筛选的所有结果”必须拆成两套选择语义：前者由前端直接维护 `selectedSessionIds`，后者则进入独立 `filtered_all` 选择模式，真正删除时把当前 `search_term + status` 交给后端匹配，语义才不会混淆。
- 对这类”平时不显示复选框”的列表页，单独加一个”选择”切换按钮最稳；进入选择模式后再展示复选框和批量操作条，退出时统一清空选择状态，可以显著减少误操作。

失败/风险经验：
- 如果”全选当前筛选的所有结果”只是把当前前端已加载列表全勾上，看起来像实现了需求，实际会漏删未加载命中的结果；这类需求必须由后端按筛选条件执行。

### 2026-03-19 安装脚本与发布流补充

成功经验：
- `uv tool install --from .` 会把包复制进独立 tool 环境；当安装目录仓库更新或本地 hotfix 未重新注册命令时，`sensenova-claw` 可能继续跑旧版代码。改为 `uv tool install --editable --from . --force sensenova-claw` 后，CLI 会直接跟随安装目录源码。
- 安装脚本支持 `SENSENOVA_CLAW_REPO_REF`（兼容旧 `SENSENOVA_CLAW_REPO_BRANCH`）后，发布验证、tag 回滚和灰度安装都更直接，不必修改脚本正文。
- 给安装脚本补”文本契约测试”很划算：直接断言 shell / PowerShell 脚本里存在 `--editable` 与 `REPO_REF` 覆盖逻辑，能防止回归。

失败/风险经验：
- 仅修运行时代码里的 `WEB_DIR` 解析不够；如果全局 `sensenova-claw` 仍是非 editable 安装，用户依然可能继续执行到旧 CLI。
- 安装脚本默认仍拉取 `dev`；若某个修复只在特性分支、未合并到 `dev` 或未打 tag，外部一键安装仍拿不到修复，发布时必须同步合并或显式指定 `SENSENOVA_CLAW_REPO_REF`。

### 2026-03-20 办公 Team 覆盖评估补充

成功经验：
- 办公 team 当前主链路是清晰的：`office-main` 负责编排，`search-agent / ppt-agent / data-analyst / doc-organizer / email-agent` 负责专业任务；`can_send_message_to` 为空在运行时代表”可发给所有启用 agent”，不是禁用协作。
- 根配置里 `serper_search` 与飞书插件都已开启，搜索调研与飞书文档读写更接近”当前可用能力”，不只是设计文档里的预留项。
- PPT 体系现在应按”HTML slides 工件流”理解，不是原生 `.pptx`；评估办公覆盖时，把它归类为”汇报材料生成”更准确。

失败/风险经验：
- `send_message` 会受 `max_send_depth` 约束；当前 `ppt-agent / data-analyst / doc-organizer / email-agent / search-agent` 都配置为 `1`，这意味着子 agent 会话里基本无法再继续新建子会话，设计文档里的”subagent 互相委托”在现配置下并不稳。
- `doc-organizer` 配置里写的是 `feishu-wiki` / `feishu-drive`，但实际工具名是 `feishu_wiki` / `feishu_drive`；由于 prompt 注入按精确工具名过滤，这两项能力可能实现了却不会正确暴露给模型。
- 运行时实际加载的 skills 比配置声明少：`paddleocr-doc-parsing`、`openai-whisper-api`、`mineru-document-extractor-choice` 等并未都进入默认 skill 注册表，扫描 PDF / OCR / 音频转写场景不能按 prompt 文案直接视为已覆盖。
- `tools.email.enabled=true` 不等于邮件可用；如果 `EMAIL_USERNAME` / `EMAIL_PASSWORD` 没有实际注入，邮件工具会在运行时直接报”配置不完整”。
- 当前权限配置只自动放行 `low`；而 `send_message`、`write_file`、`feishu_doc`、`send_email`、`download_attachment`、`cron_manage` 等常见办公动作都是 `medium` 或更高，真实体验更像”半自动办公助手”而不是全自动流水线。

### 2026-03-22 提交与验证补充

成功经验：
- 当前 sandbox 下，`git add` / `git commit` 会因 `.git/index.lock` 写入受限失败；直接按越权权限重跑对应 git 命令，是完成提交最稳的路径。
- 当工作区混有 `.sensenova-claw/sess_*`、`.sensenova-claw/agent2agent_*`、`.sensenova-claw/data/*.db-journal` 这类运行产物时，优先用 `git add -u` 再显式添加新增目录，比 `git add -A` 更安全，能避免把临时文件误带进提交。
- 提交前把验证拆成小粒度更高效：先用 `py_compile` 覆盖语法，再分别跑 `tests/unit/test_cron_models.py`、`tests/unit/test_gateway.py`、`tests/unit/test_cron_delivery.py`，证据更清晰。

失败/风险经验：
- `tests/integration/test_send_message_tool.py:36` 当前存在语法错误，pytest 会在收集阶段直接中断；验证 `send_message` 相关改动时，不能把这个现有问题误判为新回归。
- `tests/unit/test_cron_api.py::test_create_list_get_update_delete_cron_job` 在当前环境会长时间卡住；后续验证需要单独加超时隔离，避免整批测试假性悬挂。

### 2026-03-23 Proactive Agent Prompt 重写补充

成功经验：
- `AGENTS.md` 在当前仓库里更适合作为”角色规范与行为边界”文档，而不是运行时配置清单；真正生效的工具和委派权限仍应以 `config.yml` / `config.json` 为准。
- 对这类会被”用户直聊 + runtime 自动触发”双入口调用的 agent，`SYSTEM_PROMPT.md` 先区分”入口类型”，再区分”任务管理 / 任务执行”两种模式，最容易把行为写稳。
- `proactive-agent` 这类角色最适合”强执行 + 低噪音 + 混合委派”：简单任务自己做，复杂工作流再调专业 agent，能同时减少空转和职责重叠。
- prompt-only 改动也值得跑最贴边的轻量回归；`tests/unit/test_agent_registry.py` 能快速验证 agent prompt 文件加载链路未被破坏。

失败/风险经验：
- 如果在 `AGENTS.md` 里继续硬编码 `tools`、`can_delegate_to` 之类清单，文案很容易和真实运行时配置漂移，后续维护成本会越来越高。
- 强执行型 prompt 如果不显式加入”无重要变化时保持简洁””不要为了显得主动而主动”等约束，很容易把主动推送写成高频、低信息量的噪音输出。

### 2026-03-24 Uvicorn 关闭噪音补充

成功经验：
- 当堆栈同时出现 `uvicorn.server.capture_signals -> signal.raise_signal(...) -> asyncio.runners._on_sigint -> KeyboardInterrupt`，并伴随 `starlette`/`uvicorn.lifespan.on.receive_queue.get()` 的 `CancelledError` 时，优先判断为”收到 SIGINT/SIGTERM 后的关闭链路”，不应先怀疑业务代码抛异常。
- 判断是否是业务层 shutdown 真失败，最直接的方法是看堆栈里是否落到项目自己的 `lifespan finally` 清理代码；如果只有框架内部 `receive()`/`capture_signals()`，通常只是退出时的噪音日志。
- 根目录 `npm run dev` 实际会走 `agentos.app.main` 的父进程监管逻辑；当前端退出、父进程收到 `Ctrl+C`，或 IDE 停止按钮终止父进程时，父进程会反向 `terminate()` 后端，后端打印这类信号关闭堆栈是符合预期的。

失败/风险经验：
- `uvicorn --reload` 会让”父进程/重载进程/工作进程”的信号传播更绕；如果只盯着后端最后那条 `CancelledError`，很容易误判为服务内部 bug，而忽略真正先退出的是前端、父进程或外层进程管理器。

### 2026-03-20 飞书 Wiki token 兼容修复补充

成功经验：
- `lark-oapi 1.5.3` 的 `Client` 已不再暴露 `_token_manager`；排查这类 SDK 漂移问题时，直接读当前 `.venv` 里的包源码比猜测文档更快，能马上确认真实可用入口是 `TokenManager.get_self_tenant_token(client._config)`。
- 对兼容性修复，保留“旧路径优先、新路径兜底”最稳：既兼容历史 `_token_manager` 形态，也兼容新版只有 `_config` 的 `Client`。
- 当前环境即使缺少 `pytest`，也可以先用最小复现脚本验证红灯（复现 `AttributeError`），再用最小脚本验证绿灯，避免在环境问题下盲改。

失败/风险经验：
- 当前仓库 `.venv` 未安装 `pytest`，而 `uv run --extra dev ...` 在本机会触发 Rust `system-configuration` panic；新增测试文件后不能直接宣称已完成 pytest 回归，需要在完整依赖环境补跑。

### 2026-03-20 飞书 api_tool 接口兼容补充

成功经验：
- 当某个旧能力决定下线但配置接口要兼容保留时，最稳做法不是删配置，而是统一清理“描述/注释/测试”三处语义，让运行时能力和对外声明一致。
- 对“保留接口但不生效”的约束，补一条回归测试直接断言 `api_tool.enabled=True` 时也不会注册 `feishu_api`，能防止后续有人误恢复半套旧逻辑。

失败/风险经验：
- 当前环境仍缺少 `pytest`，这类轻量修复只能先用内联断言脚本和 `py_compile` 做最小验证；正式 pytest 回归仍要在完整依赖环境补跑。

### 2026-03-20 飞书 ask_user 文本闭环补充

成功经验：
- 对 IM 渠道补 `ask_user`，第一版先做“待回答问题存在时，下一条文本优先解释为回答”最稳；不需要先引入按钮卡片回调，也能把 `USER_QUESTION_ASKED -> USER_QUESTION_ANSWERED` 主链路接通。
- 渠道侧最小状态就是 `session_id -> question_id`；收到回答后立刻清理状态，后续消息自然回到普通 `USER_INPUT` 流，不容易和日常对话串台。
- 这类闭环最关键的回归测试是两条：一条断言回答消息被转成 `USER_QUESTION_ANSWERED`，一条断言回答完成后下一条消息重新走 `USER_INPUT`。

失败/风险经验：
- 当前飞书第一版只支持文本回答，不校验 `options/multi_select` 合法性，也不支持飞书按钮/多选卡片交互；如果后续需要更强约束，必须补事件回调与结构化解析。

### 2026-03-20 多渠道 ask_user 闭环补充

成功经验：
- `telegram/wecom/whatsapp` 可以直接复用飞书的最小闭环模式：各自 channel 内维护 `pending_questions`，在入站消息路径优先分流成 `USER_QUESTION_ANSWERED`，实现一致且改动面小。
- 对多渠道并行补同一行为时，测试也要成对补齐：每个 channel 都应同时覆盖“回答优先分流”和“回答后恢复普通 `USER_INPUT`”，否则很容易只在一个渠道上闭环。
- 渠道层实现保持“无待回答问题时完全不改原路径”，最利于控制回归范围；完整跑 `telegram/wecom/wecom_outbound/whatsapp` 四组单测能快速验证这一点。

失败/风险经验：
- 文本闭环虽然统一了，但仍然只是“下一条文本即回答”；`options/multi_select` 的结构化校验、取消操作和按钮回调在三个渠道上都还没落。

### 2026-03-20 chat think 展示补充

成功经验：
- 对“模型把思考内容包在 `<think>...</think>` 里”的前端支持，最稳的做法是“双通道”：非流式/历史消息直接解析正文里的 `<think>` 标签，流式阶段额外消费 `llm_result.reasoning_details`，这样历史回放和实时展示都能覆盖。
- `/chat` 里如果要避免 `llm_result` 与 `turn_completed` 产生重复 assistant 气泡，消息结构里需要显式保存 `turnId`，并在上下文层做 upsert，而不是每次都 append。
- Playwright 在 Next dev 下 mock 全局 `WebSocket` 时，替身必须补上 `addEventListener/removeEventListener`，并且只把业务 `/ws` 连接暴露成 `__mockWs`；否则很容易误打到 HMR socket，导致测试看起来“事件没生效”。

失败/风险经验：
- 当前 `/chat` 页面的 mock e2e 不能再只靠 `localStorage access_token`；实际鉴权链路依赖 `sensenova_claw_token` cookie 和 `/api/auth/status`、`/api/config/llm-status`，漏掉任一项都会让页面停在登录/配置检查流程，导致断言偏离真实问题。

### 2026-03-21 Secret Store 接入补充

成功经验：
- 为通用 secret 机制先落 `SecretStore + SecretRef + SecretRegistry` 三层最稳，后续把 `Config` 解析和 `config_store` 持久化都接到同一抽象上，比在各 API 里散落 `if api_key` 判断更可控。
- `persist_path_updates()` 这类统一写回入口非常适合承接 secret 逻辑；在这里把 `cfg._secret_store` 回填好，能顺手修复“写入后 reload 读不回 secret”的问题。
- `/api/config/sections` 一旦开始返回脱敏结构，前端设置页必须同步改成“secret 元数据 + draft/touched”双轨状态；否则保存全量 provider 配置时会把原有 secret 误清空。
- 明文迁移能力最适合做成独立迁移器（扫描 raw config 的叶子路径，再按 `SecretRegistry` 过滤）；这样 HTTP API 和 CLI 命令都能复用同一份迁移逻辑，行为不会分叉。

失败/风险经验：
- 当前环境下 `python3 -m pytest` 可用，但 `.venv/bin/python -m pytest` 不一定有 `pytest`；回归命令优先直接用系统 `python3 -m pytest` 更稳。
- `npx tsc --noEmit -p sensenova_claw/app/web/tsconfig.json` 在本环境没有及时返回有效结果，前端静态类型回归不能在这次任务里作为通过依据；需要在本地完整 Node/Next 环境继续确认。
- 虽然已接入 `python-keyring` 抽象并把默认 store 指向 `KeyringSecretStore`，但真实 keyring backend 可用性仍取决于宿主机环境；当前只完成了进程内/注入式测试，未做真实系统 keyring e2e。
- 全局 `config = Config()` 这类模块级初始化一旦遇到用户本机已有 `${secret:...}` 配置，会在 import 时就触发 secret 解析；默认 store 不可用时必须先走 `is_available()` 兜底，否则测试导入阶段就会直接崩。

### 2026-03-21 LLM 管理页补充

成功经验：
- 对“新增独立管理页但不改后端协议”的需求，直接复用 `/api/config/sections` 的 `llm.providers/models/default_model` 最稳；前端只需做一次 `provider -> models[]` 视图映射，就能实现按 provider 管理 llm。
- 若 Playwright 默认配置会联动根目录 `npm run dev`，而根脚本又依赖 `uv`，优先复用仓库里无 `webServer` 的备用配置（如 `playwright.gateway.config.ts`）配合手动启动前端服务，可避开与当前任务无关的启动链问题。
- 在当前 macOS 受限环境里，前端浏览器级 e2e 往往需要“两段式验证”：先越权启动 `next dev` 监听端口，再越权运行 `npx playwright test` 启动 Chromium；两者任一不放开，都会被误判成页面功能失败。

失败/风险经验：
- 对 provider / llm “重命名”这类 key 级编辑，若输入框直接绑定对象 key，测试和实现都容易受重新渲染影响；当前实现虽然可用，但后续若要增强交互稳定性，可考虑引入 draft state 再在 blur/submit 时提交 rename。

### 2026-03-21 LLM 管理页折叠与 secret 删除补充

成功经验：
- 对 secret-aware 配置写回，`persist_path_updates()` 在处理空字符串时不能无条件 `delete()`；先检查原始配置值是否真的是 secret ref，再决定是否删 secret，才能兼容 `mock.api_key=''` 这类普通空值路径。
- provider 折叠卡片的头部最好拆成“左侧 toggle 按钮 + 右侧操作按钮”，不要把删除按钮嵌进整卡 toggle 按钮里；否则 HTML 语义和浏览器点击行为都容易出问题。
- 这类“后端写回 + 前端交互”组合修复，最稳的回归组合是“一条 pytest 单测锁 secret 删除条件 + 一条 Playwright 用例锁 UI 折叠与保存主流程”。

失败/风险经验：
- 即使前端 payload 看起来合理，secret store 后端的删除语义也可能更严格；像 keyring 删除不存在条目会报错，这类行为必须在仓库内抽象层显式兜底，不能假设底层实现天然幂等。

### 2026-03-21 通用 secret reveal 补充

成功经验：
- 对“默认掩码、按需展示真实值”的需求，首屏接口不应直接下发真实 secret；新增受保护的通用 `/api/config/secret?path=...` 并限制到 `is_secret_path(path)`，前端点击眼睛后再按需读取，安全边界和复用性都更好。
- reveal 接口直接返回 `config.get(path)` 的解析结果最省事，能同时兼容 secret ref、环境变量和明文配置，不需要前端关心底层来源。
- 前端 secret 输入框若需要“默认显示 `******` 但又保留未修改状态”，最稳的是把“展示值”和“真实 draft”分开：未 touch 且未 reveal 时显示 `******`，点击眼睛后再把真实值拉进本地状态，但继续保持 `api_key_touched=false`，这样保存时不会误把原 secret 全量回传。

失败/风险经验：
- 当前 `test_config_api.py` 在本机直接运行会受全局 `~/.sensenova-claw/config.yml` 影响；涉及 `config_api` 的 pytest 回归在本环境应显式用临时 `HOME` 隔离，避免导入阶段误读真实 secret 配置。

### 2026-03-21 LLM 管理页 mock 回传补充

成功经验：
- 像 `/llms` 这种“只管理用户可见子集”的页面，保存时不应把隐藏保留项（如 `mock` provider/model）一并全量回传；按页面实际可编辑集合组 payload，更符合职责边界，也能避开历史脏配置触发的副作用。
- 当后端采用 dotted-path merge 写配置时，前端省略未编辑字段通常比回传默认值更安全；缺失字段会保留原配置，而“默认值回传”可能意外触发 secret 删除、覆盖或热重载副作用。

失败/风险经验：
- 即使后端已经对 secret 删除做了保护，只要前端还在无意义地回传 `mock.api_key=''`，用户历史配置若存在异常状态仍可能触发问题；这类 bug 需要同时检查前后端边界，而不是只修一侧。

### 2026-03-21 Secret 删除幂等补充

成功经验：
- 清空 secret 字段时，`config_store` 不应把“底层 secret 已缺失”视为致命错误；即使 `delete()` 失败，也应继续把 config 中的该字段置空并完成保存，这样历史脏状态才能被自愈。
- 对这类问题，最有效的单测是直接构造“raw config 仍是 secret ref，但 secret store.delete() 抛错”的场景；它比只测普通空值或正常 delete 更贴近真实用户故障。

失败/风险经验：
- 仅依赖前端不回传某些字段不够稳；一旦用户浏览器缓存了旧前端，或历史配置里已存在异常 secret ref，后端仍会再次踩到删除异常。对 secret 清空链路，后端必须保证幂等。

### 2026-03-24 Secret 文件回退补充

成功经验：
- 把“keyring 主存储”和“本地 `secret.yml` 回退存储”拆成 `FallbackSecretStore(primary, fallback)` 最稳，`Config`、`ConfigManager`、迁移与 reveal API 都不需要改调用协议。
- 回退文件用单个 YAML 扁平映射 `{ref: value}` 最省事，直接复用现有 secret ref（如 `sensenova_claw/llm.providers.openai.api_key`）作为 key，避免路径编码和目录散落问题。
- `get()` 不能只在 keyring 抛错时回退；当历史写入曾回退到文件、而当前 keyring 恢复但查不到值时，也需要在 primary 返回空值时继续查 fallback，才能真正读回旧 secret。

失败/风险经验：
- 文档里“keyring 不可用时降级为明文写 config.yml”的旧口径容易过时；现在行为改成落到 `~/.sensenova-claw/data/secret/secret.yml` 后，配置与安全文档必须一起更新，否则会误导排查。

### 2026-03-21 LLM 编辑态补充

成功经验：
- 对“单项编辑 + 编辑所有配置”这类页面，最稳的前端模型是三层状态：服务端基线 state、单项 draft、全局 draft。这样单项取消不会污染其他项，全局取消也能直接回滚整页。
- 单项保存和全量保存最好在后端分两条路：局部接口处理 provider/model 改名联动，全量接口继续复用 `/api/config/sections`；否则前端很容易在“看起来局部保存”时误覆盖整份配置。
- Playwright 对这类交互最有效的断言不是文案，而是“默认 disabled -> 点击编辑后 editable -> 保存命中特定局部接口 -> 编辑所有命中全量接口”。

失败/风险经验：
- 单项保存后如果页面会重新加载配置，现有折叠态通常会被重置；测试和交互都要考虑“保存后需要重新展开才能继续操作”，否则很容易把页面重载误判成元素消失 bug。

### 2026-03-21 Setup 动态模型列表补充

成功经验：
- setup 页如果要支持不同 OpenAI 兼容厂商的专用模型发现逻辑，前端请求 `/api/config/list-models` 时必须透传具体 `provider key`（如 `minimax`），不能统一压成 `openai`；否则后端新增的 provider 分支永远不会被命中。
- 对“动态模型列表取回后仍无法继续”的问题，要同时检查显示逻辑和按钮禁用逻辑；当前 setup 页曾用 `selectedProvider.models.length` 控制 `测试连接/完成配置`，会把“远端已成功返回模型但预设为空”的场景错误判成必须手填模型。
- 这类 setup 向导问题最适合补一条 Playwright 回归：直接 mock `/llm-presets` 与 `/list-models`，断言请求体里的 `provider` 和最终渲染的模型列表，能同时锁住根因和用户可见行为。

失败/风险经验：
- Playwright 浏览器安装路径必须与测试运行时的 `PLAYWRIGHT_BROWSERS_PATH` 保持一致；只执行 `npx playwright install chromium` 而不带同样的环境变量，测试仍会报“Executable doesn't exist”。

### 2026-03-22 Mini-App Workspace 补充

成功经验：
- 复用现有 `custom_pages` 入口比另起一套 `miniapps` 路由更稳：列表/导航无需重做，只要在后端把 page 元数据升级成“工作区 + builder + agent + runs”结构，前端 portal 和 `/features/[slug]` 就能平滑演进。
- 专属 Agent 的工作目录最好直接落在 `SENSENOVA_CLAW_HOME/workdir/{agent_id}/miniapps/{slug}/app`；这样既能继续复用 `/api/files/workdir/...` 静态服务，又能让 Agent 通过默认 workdir 直接改页面文件，不需要额外路径映射。
- 对页面内交互回传，最省心的协议是 iframe 里统一使用 `window.Sensenova-ClawMiniApp.emit(action, payload)`，外层页面通过 `postMessage -> /api/custom-pages/{slug}/interactions -> gateway.send_user_input` 转给 Agent；这条链路用进程内 mock provider e2e 很容易稳定锁住。
- ACP 第一版不必一次做全，先实现 `initialize -> session/new -> session/prompt` 的最小 stdio JSON-RPC 客户端，再把通知原样落到 run logs，已经足够给 Claude Code / Codex 预留标准接入点。

失败/风险经验：
- 当前用户本机配置若在 `agents.default` 下仍保留 `system_prompt`，真实后端启动会在 `AgentRegistry.load_from_config()` 阶段直接报错；这会影响 Playwright 这类需要自动拉起 web server 的回归，不能误判成 mini-app 页面本身失败。
- 本机 Playwright 仍缺浏览器可执行文件（`chrome-headless-shell` 不存在）；即使 spec 已能被 `--list` 识别，真正浏览器级回归仍需要先执行 `npx playwright install` 并满足系统库依赖。
- 前端仓库级 `tsc` 目前仍被既有依赖问题阻塞（如 `rehype-highlight`、`@tailwindcss/typography`、`MessageList` 旧 props 错误）；新增页面若要做类型回归，需用 grep 过滤新增文件，不能把全仓历史问题算到本次改动上。

### 2026-03-22 Playwright 认证与浏览器路径补充

成功经验：
- 当后端 token 每次启动都会刷新时，前端 e2e 不要硬编码旧 token；更稳的做法是让用例先走一次真实 `/login -> verify-token -> router.push` 流程，或在 URL 中带 token 并 mock `verify-token`。
- Playwright 若在 dev 模式下 mock `WebSocket`，必须只拦截业务 `ws://localhost:8000/ws`，保留 Next HMR 自己的 websocket；否则会因为 `websocket.addEventListener is not a function` 直接触发客户端异常页。
- `DashboardLayout` 会联动挂载 `GlobalFilePanel`，进入页面时会自动请求 `api/files/roots`；这类全局面板接口若未 mock，`authFetch` 命中真实后端 401 后会把页面重定向回 `/login`，很容易误判成主页面逻辑失败。
- Playwright 配置里加入本机已安装浏览器的显式路径候选（如 `chrome-headless-shell` 的绝对路径）很有效，能避免浏览器安装在非默认 cache 目录时重复卡在 “Executable doesn't exist”。

失败/风险经验：
- Playwright strict mode 很容易把“页面可见”误判成失败：像 `Language Coach`、`sess_miniapp` 这类文本如果同时出现在导航、标题和状态徽标中，断言必须收窄到明确 locator，否则会被多匹配阻塞。

### 2026-03-22 Mini-App 专属 Agent 继承补充

成功经验：
- 当前 `AgentConfig` 已不再保存 `provider` 字段，而是仅保存 `model`，provider 由运行时根据 `llm.models` 动态解析；派生新 agent 时应只继承 `model/temperature/max_tokens/extra_body/tools/skills/workdir` 等真实字段。
- 对这类“线上 500 + 明确 traceback”的修复，直接复跑 `tests/unit/test_custom_pages_api.py` 最有效，因为它本身就覆盖了“创建 mini-app 并生成专属 agent”的主路径。

失败/风险经验：
- 旧思维里继续读取 `base_agent.provider` 会在真实创建工作区时直接报 `AttributeError`，哪怕 UI、路由和工作区文件生成逻辑都正确；这类问题属于配置模型漂移，新增 capability 时必须先对齐当前 dataclass 定义。

### 2026-03-22 Mini-App 通用化与 ACP 超时补充

成功经验：
- 用户举“语言学习”这类例子时，不应顺手把该业务做成平台内置模板；更稳的做法是保持 builtin 生成器输出通用 workspace 壳体，把具体内容和工作流留给未来用户需求与 Agent 决定。
- 将 ACP timeout 拆成 `startup_timeout_seconds` 和 `request_timeout_seconds` 很关键：初始化/建会话可以短，真正的 `session/prompt` 生成必须显著更长，否则 coding agent 极易在生成中途误超时。
- 用一个极小的 `ACPClient` 单测直接锁住方法级 timeout 最省心；只需要 monkeypatch `call()`，就能验证 `initialize/new_session/prompt` 各自用了什么超时值。

失败/风险经验：
- 只改文档或前端文案不够；如果后端仍保留按关键词识别“语言学习”并走专用模板分支，平台语义还是会被悄悄拉向某个垂直场景，必须把实际生成逻辑一起改回通用模式。

### 2026-03-22 Mini-App 动作分流补充

成功经验：
- mini-app 不应把所有按钮和表单都转给 Agent；在宿主页维护一层 `local/server/agent` 动作路由最稳，页面高频交互可继续像普通应用一样本地执行，只有少数需要判断或改造的动作才进入 Agent。
- 页面桥接协议最好同时提供 `emit()`、`emitTo()` 和 `configureActionRouting()`：页面可以只声明动作和 payload，把默认路由和按 action 覆盖规则交给宿主页解释，后续复用现有页面时改造成本更低。
- 后端把 `POST /api/custom-pages/{slug}/actions` 统一做成入口也更清晰：`server` 目标只记日志不建会话，`agent` 目标复用既有 interaction 链路，测试可以稳定断言“server 不创建 session、agent 才创建 session”。
- Playwright 对这类分流功能的最佳断言是“三段式”：`local` 不发请求，`server` 命中新 actions 接口但不切会话，`agent` 命中新 actions 接口且返回并切到新 session。

失败/风险经验：
- 浏览器 e2e 里把中文直接塞进内联 iframe HTML payload 容易触发编码噪音，导致断言看到乱码；这类测试数据最好优先用 ASCII，避免把编码问题误判成动作路由失败。
- Playwright strict mode 下，如果同时存在“动作路由日志”和“动作事件日志”，用宽泛正则断言 action 名会命中多处文本；应收窄到完整事件文案或更具体的 locator。

### 2026-03-23 ACP 设置页补充

成功经验：
- mini-app ACP 配置最适合直接挂在现有 `config_api / config_manager / /settings` 链路上，不需要再造单独接口；只要把 `miniapps` 加进 `/api/config/sections` 默认返回集合，前端就能和 LLM 配置一起统一保存。
- ACP 的 `args` 和 `env` 在前端用 “JSON textarea + 保存前校验” 很实用；相比动态 key-value 表单，实现更轻，且能完整覆盖 CLI 参数数组和环境变量对象两类结构。
- 设置页 e2e 最稳的方式仍是直接 mock `window.fetch`：返回 `/api/config/sections` 初值，捕获 `PUT /api/config/sections` 请求体，最后断言 `miniapps.default_builder` 与 `miniapps.acp.*` 是否按用户输入写回。

失败/风险经验：
- 设置页这类信息密集页面很容易出现同名文案多处复用；Playwright 若直接 `getByText('Mini-App Builder')`，strict mode 会因为统计卡片和 section 标题重复而失败，断言应优先锁到具体输入控件或唯一容器。

### 2026-03-23 ACP 导航入口补充

成功经验：
- 仅实现 `/settings` 页面不够，如果不把它挂进 `DashboardNav.adminNavItems`，用户在“管理”分组里根本发现不了；这类后台配置页必须和 `Tools`、`Skills` 一样进入统一的管理子导航。
- `DashboardLayout` 里的 `ADMIN_PATHS` 也要同步补上新路由，否则虽然能打开页面，但还会带着右侧文件面板，和其他管理页的布局不一致。

### 2026-03-23 ACP 路由迁移与 Codex Bridge 补充

成功经验：
- 把 ACP 正式入口迁到 `/acp` 时，最省心的做法是“新增 `/acp` 页面 + Next redirect 把 `/settings` 指过去”，这样新旧链接都能兼容，且不需要大规模搬运页面代码。
- 当前本机 `codex` CLI 暴露的是 `exec` / `mcp-server` / `app-server`，不是 Sensenova-Claw builder 直接使用的 ACP 子集；要“自动用 Codex”，最务实的方案是加一个很薄的 `codex_acp_bridge`，把 `initialize/session/new/session/prompt` 转成一次 `codex exec`。
- 对这类 bridge，优先把协议层和命令构造抽成纯函数最有效；单测只 mock runner，不依赖真实 Codex 登录态，也能稳定锁住 session 生命周期和最终返回格式。

失败/风险经验：
- 不能简单把 `miniapps.acp.command=codex` 当成可用配置写给用户；在当前安装版本下这会直接协议不匹配，必须明确区分 MCP/app-server 与 Sensenova-Claw 当前 ACP builder 的差异。

### 2026-03-23 官方 codex-acp 适配器补充

成功经验：
- 用户给出 `zed-industries/codex-acp` 后，应优先切回官方适配器推荐，而不是继续把自定义 bridge 当主路径；Sensenova-Claw 当前 ACP client 本身已经能直接对接这个适配器。
- 当前 Linux x64 环境下，`npx @zed-industries/codex-acp` 单独执行会因为 optional binary 包缺失失败，但 `npx -y -p @zed-industries/codex-acp -p @zed-industries/codex-acp-linux-x64 codex-acp --help` 可以正常启动，适合作为无需预安装的通用配置。
- 当 `~/.sensenova-claw/config.yml` 尚无 `miniapps` 段时，直接补入 `default_builder: acp` 和 `codex-acp` 启动参数风险较低，且能让新 workspace 默认走 Codex。
- 用真实后端创建一条 `builder_type=acp` 的 mini-app 很有必要；只有这样才能确认官方 `codex-acp` 不只是能启动，而是真的会把页面文件写到 `~/.sensenova-claw/workdir/.../app/` 并让 run 状态最终变成 `completed`。
- 真实 ACP 生成是长任务，排查时不要只看首轮 API 返回的 `queued/running`；应同时检查 `custom_pages_runs/<slug>.json` 的日志流和工作区文件是否持续变化，避免把“仍在生成中”误判成“协议卡死”。

失败/风险经验：
- npm 主包版本与平台二进制包版本可能暂时不同步；仅凭 `npx 包名` 失败，不能立刻判断官方适配器不可用，先检查 optionalDependencies 和平台包安装方式。

### 2026-03-23 Mini-App 构建消息流补充

成功经验：
- 对 workspace 右侧 Agent 面板这类 UI，若要展示 ACP/builder 生成过程，优先把 build run 日志转成“只读聊天转录”更稳，不要硬把构建日志塞进真实聊天 session；这样不会污染后续用户会话，也不依赖 Gateway 事件桥再造一遍。
- `ACP agent_message_chunk` / `ACP agent_thought_chunk` 适合在前端按连续 chunk 聚合成 assistant 消息与思考块；只要在遇到普通系统日志时 flush，一页里就能同时看到“构建状态 + builder 输出 + 思考过程”。
- 这类前端功能的 e2e 最稳方式是把“构建中 -> 刷新 -> 已就绪 -> 页面动作分流”串成同一条 Playwright 场景；复用同一套登录和全局 mock，比拆成第二条独立用例更不容易被鉴权状态机和全局布局请求干扰。

失败/风险经验：
- 单独为“构建消息流”再开一条浏览器用例时，若它和主用例走的认证初始化路径稍有不同，就很容易被 `ProtectedRoute` 重定向回 `/login`；这类页面测试应优先复用已经验证稳定的认证入口，而不是在第二条用例里重新发明一套登录前置。

### 2026-03-23 Mini-App ACP 工具事件卡片补充

成功经验：
- 若前端需要把 ACP `tool_call` 渲染成结构化卡片，后端 run log 最好直接保留 `sessionUpdate + status + title` 三要素；像 `ACP tool_call [completed]: Edit app.js` 这种格式，前端无需额外上下文就能稳定解析出标题和状态。
- 构建消息流里 assistant chunk 和 tool_call 是两种不同语义，前端聚合时要在遇到 tool/system 日志前先 flush assistant draft；否则工具卡片会被错误并入上一条 assistant 消息。
- 给工具卡片补 `data-testid` 后，Playwright 可以直接断言“标题 + 状态”是否出现，明显比匹配整段日志文本更稳。

失败/风险经验：
- 前端把普通消息数组重构成 union item（chat/tool）后，像 `messages.length` 这种旧变量名很容易残留并只在运行期暴露；这类重构完成后要优先跑一次真实浏览器回归，而不只看 TypeScript 静态检查。

### 2026-03-23 Mini-App 悬浮工作区布局补充

成功经验：
- 对“主舞台优先”的 workspace 页面，最稳的实现不是在现有右栏上加收起逻辑，而是明确拆成两种布局态：未 pin 时只有中间主舞台，聊天窗作为绝对定位浮窗；pin 后再切回 `ResizablePanelGroup` 的固定右栏。
- 浮动 tabs 和信息卡片若覆盖在预览上层，容器必须先 `pointer-events-none`，再让真实卡片恢复 `pointer-events-auto`；否则即使视觉上透明，也会把 iframe 内点击全部挡住。
- `workspace` 页签下的浮动信息卡片更适合放在舞台底部，顶部只保留轻量 tabs；否则用户最容易点击到的首屏按钮区域会被状态卡片压住。
- Playwright 覆盖这类交互时，建议把“默认悬浮按钮 -> 展开浮窗 -> pin 成右栏 -> 继续操作 preview”串成同一条场景，这样最容易发现布局切换后的真实遮挡问题。

### 2026-03-23 Mini-App 浮动按钮显隐补充

成功经验：
- 这类悬浮页签不应强行维持“始终有一个选中项”；把状态从 `WorkspaceTab` 放宽到 `WorkspaceTab | null`，再用统一 `toggleOverlayTab()` 处理“点击当前按钮即收起”，实现最直接也最不容易漏分支。
- Playwright 对显隐切换最好直接断言 `toBeHidden()`，这样能发现“视觉上像收起了，但其实仍在页面上拦截事件”的问题。
### 2026-03-22 dev 合并到 wdh/dev 补充

成功经验：
- 当用户要求“只在 `wdh/dev` 上操作”时，可以用 detached worktree 基于 `dev` 先做只读验证，再回到当前分支执行合并；这样既不污染 `dev` 分支，也能在合并前确认 `dev` 本身是否已经带着失败用例。
- 处理冲突时，`config_api` 这类配置写回入口应优先保留 `ConfigManager` 单入口实现；否则容易绕开 secret 路径处理、内存热重载和 `CONFIG_UPDATED` 事件发布。
- 这次最有效的回归组合是“后端定向 pytest + 进程内 e2e + 前端关键 Playwright”。仅看 merge 是否成功不够，必须同时验证 `test_config_api / test_agent_worker / test_agent_config`、`test_agent_llm_core_flow` 和 `setup-model-list/chat-markdown`。

失败/风险经验：
- `dev` 上的失败不一定来自当前改动；这次先在 detached worktree 跑测试，就提前暴露了 `tests/unit/test_agent_worker.py` 对本机模型配置的脆弱依赖，以及 `AgentConfig.provider` 已删除但运行时代码仍直接访问的兼容性问题。
- Playwright 不能并行复用同一个 `webServer.port=3000` 配置直接起两套服务；并发跑多个 spec 容易报 `Address already in use`，这类前端回归在当前仓库更适合串行执行或拆分端口。

### 2026-03-22 WhatsApp 启动超时补充

成功经验：
- 对可选 channel，启动失败不应直接拖垮 FastAPI lifespan；像 WhatsApp sidecar 这类外部子进程超时，更稳的策略是 channel 自己记录 `state=error/last_error`，让主服务继续启动，状态页再暴露失败原因。
- 这类问题最有效的 TDD 用例不是去模拟完整 sidecar，而是让 fake bridge 的 `start()` 直接抛 `TimeoutError`，断言 `WhatsAppChannel.start()` 不再向上抛异常且会写入运行时错误状态。

失败/风险经验：
- 当前 sidecar 的 `start` 命令响应时机仍依赖 Node runtime 完成一段真实初始化；在网络慢、Baileys 初始化卡住或登录态异常时，`start` 仍可能超时。当前修复解决的是“主服务被带崩”，不是“WhatsApp 一定能成功连上”。

### 2026-03-22 WhatsApp 版本探测卡顿补充

成功经验：
- 真实日志如果稳定停在 `auth state loaded` 之后、`socket created` 之前，优先怀疑 `fetchLatestBaileysVersion()` 这类启动期远端探测，而不是扫码或 Python sidecar 协议本身。
- 给 sidecar runtime 增加“版本探测超时回退到内置版本”的兜底后，`start` 可以继续完成 socket 创建；这类修复最适合用 `node:test` 直接把 `fetchLatestBaileysVersion` mock 成永不返回，再断言 `runtime.start()` 仍会在短时间内返回并使用 fallback version。

失败/风险经验：
- 当前沙箱环境直接跑 `python3 -m sensenova_claw.app.main run --no-frontend` 仍可能被 `watchfiles` 权限拦住（`[Errno 1] Operation not permitted`）；这种失败不能用来判断 WhatsApp 启动逻辑是否仍有 bug，需优先看单测和用户本机真实启动日志。

### 2026-03-22 WhatsApp 自聊 protocolMessage 补充

成功经验：
- “给自己发 WhatsApp 纯文本”在真实设备上不一定走 `conversation`/`extendedTextMessage`；这次样本最外层是 `protocolMessage`，如果 sidecar 只解常规 wrapper，就会持续出现 `messages.upsert received` 但 `ignored: no text content`。
- 对这类协议兼容问题，最稳的流程是先在 `runtime.test.mjs` 补失败样本，再在 `unwrapMessage()` 中按最小范围扩展 wrapper；这次补 `protocolMessage.editedMessage.message` 后，自聊文本即可进入现有提取链。
- 在 `no text content` 的 debug 日志中带上 `protocol_type`，后续能更快区分“真空消息”还是“漏解某种 protocol wrapper”。

失败/风险经验：
- 仅覆盖“self chat + conversation”这种理想化测试不够；真实 WhatsApp 多设备/自聊场景的消息结构会漂移，自聊链路必须保留协议级样本测试。

### 2026-03-22 LLM 默认模型编辑补充

成功经验：
- `/llms` 页面采用“单项编辑 + 编辑所有配置”双模式时，`default_model` 也必须进入同一套编辑状态机；否则顶部卡片会变成唯一不能单项编辑的配置项。
- `default_model` 这类单字段更新，单独提供 `PUT /api/config/llm/default-model` 比复用整份 `llm` section 保存更稳，前后端都更容易保持“只更新当前一项”的语义。
- Playwright 对顶部配置卡片最有效的断言顺序是“默认禁用 -> 编辑后可改 -> 取消恢复 -> 保存发单独请求”，这样能同时覆盖 UI 状态切换与接口契约。

失败/风险经验：
- 当前环境跑 Playwright 需要同时满足两件事：浏览器具备越权启动权限，且 `http://localhost:3000` 上已有 Next dev 进程；缺任一条件都会失败，但报错表象不同，容易误判到页面逻辑。

### 2026-03-23 LLM 配置状态判定补充

成功经验：
- `llm-status` 这类“是否已配置”接口不应只按字符串字面值判断；若配置支持 `${secret:...}`，就必须结合 secret store 解析后再判空，否则前端会把已登录用户错误重定向到 `/setup`。
- 将 secret 解析能力收敛到 `check_llm_configured(..., secret_store=...)` 这一层最稳，Web 接口和 CLI 启动提示共用同一规则，避免状态判断分叉。
- 对配置判定问题，最小高价值测试是三类：普通 `${ENV}` 占位符、`${secret:...}` 且 secret 为空、`${secret:...}` 且 secret 有值。

失败/风险经验：
- 当前环境仍无法直接跑 pytest：`.venv` 缺少 `pytest`，`uv run python -m pytest` 又会在 `system-configuration` 依赖层 panic；完成修改后需要至少补做 `python3` 级函数断言和 `py_compile` 校验，并在完整依赖环境复跑正式单测。

### 2026-03-23 /agents 创建模型下拉补充

成功经验：
- `/agents` 创建弹窗与 `/agents/[id]` 编辑页若都需要模型列表，最省事的做法是统一复用 `/api/config/sections` 中的 `llm.models/default_model`，前端直接按 key 生成下拉，无需新增专门接口。
- 这类“把输入框改成选择框”的前端改动，最高价值的 Playwright 断言是“默认值来自 `default_model` + 提交请求体带上用户选中的 model”，比只看界面上出现选项更能锁住真实行为。
- 当前仓库跑前端 e2e 时，若 `playwright.config.ts` 的 `webServer.command` 会触发根目录 `npm run dev`，可以先保证 3000 端口已有服务，再用 `reuseExistingServer` 跳过那条启动链，避免把 `uv` 环境问题误判成页面失败。

失败/风险经验：
- 在当前环境下直接跑根目录联动启动仍可能触发 `uv` 的缓存权限或 `system-configuration` panic；前端回归若报在 `webServer` 启动阶段，先区分是页面断言失败还是基础启动链失败。

### 2026-03-23 Agent 持久化修复补充

成功经验：
- Agent 重启丢失时，先核对启动期真实加载来源最关键；当前生效来源只有 `config.yml` 的 `agents` 段和 `SENSENOVA_CLAW_HOME/agents/<id>/SYSTEM_PROMPT.md`，没有任何 `config.json` 覆盖层读取逻辑，因此修复应直接写回这两处。
- 对 Agent CRUD，最稳的持久化方式是复用 `ConfigManager.replace("agents", ...)` 做整段写回，同时只修改目标 agent 的记录；这样既能保留其他未知 key，又能触发既有的配置内存刷新与 `CONFIG_UPDATED` 事件。
- Python 3.14 下旧式 `asyncio.get_event_loop().run_until_complete(...)` 很容易在测试 fixture 中直接报错；测试夹具应改成 `asyncio.run(...)` 才能稳定把失败推进到业务断言。

失败/风险经验：
- `tests/e2e/test_agents_preset_api_flow.py` 中“preset-agent 不允许删除”和“写 `config.json` 覆盖层”的假设已经过时；排查 Agent 持久化问题时，不能把旧测试名义上的预期当成当前产品事实。

### 2026-03-23 Qwen 静默回退 Mock 修复补充

成功经验：
- 当日志里已经出现 `llm.call_requested provider=qwen`，但最终回复仍是 `mock` 文案时，优先检查 provider 工厂是否在“显式请求某 provider”时做了静默回退；这类问题不能只看事件 payload，必须沿 `LLMFactory.get_provider()` 实际取到的实例继续追踪。
- 对多 Agent 场景，标题生成链路不能只读全局 `llm.default_model`；应先看 `session -> agent_id -> agent.model`，否则会出现“主回复走 agent 模型、标题却走全局 mock”的错位现象。
- 针对这类配置/编排问题，最小有效回归测试是两条：一条锁住“显式 provider 不可用时返回结构化错误而不是 mock 回复”，另一条锁住“TitleRuntime 按 session agent 模型选 provider/model”。

失败/风险经验：
- `LLMFactory` 改为抛错后，若 `LLMSessionWorker` 在 `try` 外先取 provider，异常会直接炸出 worker，前端收不到统一错误事件；provider 获取也必须纳入同一错误处理分支。

### 2026-03-23 LLM 参数错误友好提示补充

成功经验：
- 对外部 LLM 网关返回的 provider 特定错误（如 DashScope 的 `Range of max_tokens should be [1, 65536]`），最稳的落点是 `LLMSessionWorker` 的统一异常出口：同时生成 `error_code`、`user_message` 和结构化 `context`，再复用现有 `error.raised` / `llm.call_result` / `agent.step_completed` 链路，无需单独开新事件。
- WebSocket 下行如果只传 `message` 不够，最好同时保留 `error_code`、`user_message`、`raw_message`；这样前端能优先显示友好文案，同时保留排查原始错误的能力。
- 前端收到结构化错误后，应优先展示 `user_message`，不要直接把 provider 原始异常前缀成 `Error:`；否则用户看到的仍是低可读性的网关报错字符串。

失败/风险经验：
- 直接在运行时对 `max_tokens` 做硬编码自动截断虽然能临时避错，但会掩盖真实配置问题；若用户更需要可见性而不是静默修复，应改成错误提炼而不是偷偷改请求参数。

### 2026-03-23 max_tokens 越界自动重试补充

成功经验：
- 对 `max_tokens_out_of_range` 这类可机械修复的错误，最稳的是“提示 + 单次重试”组合：先向当前 session 发一条会话内通知，再用解析出的 `limit` 仅重试一次，成功则用户直接拿到正常回复，失败再退回结构化错误链路。
- 这类提示最好复用现有 `notification.session`，而不是新增一套前端事件；WebSocket 已能把它稳定映射成追加到对话框的系统消息，改动最小。
- provider 上限不应硬编码在正常请求路径；更稳的做法是从实际错误文案里提取上限数字（如 `65536`、`196608`），仅对当前请求做临时修复。

失败/风险经验：
- 自动重试必须严格限制为一次；如果不加边界，很容易在 provider 持续报参数错误时形成重复通知或隐藏真实故障。

### 2026-03-23 Chat Agent 切换补充

成功经验：
- 工作台聊天页里，“选中的 agent”和“当前打开的 session”是两套独立状态；排查“明明选了 minimax，实际却走 default”时，先看前端是否真的切换了 `currentSessionId`，不要先怀疑后端 provider 回退。
- 多 agent 会话页在切换左侧 agent 后，需要同步右侧会话上下文：有历史会话时切到该 agent 最近会话，没有历史会话时补建一个新的空会话，否则后续 `user_input` 仍会落到旧 session。
- 这类回归最适合用前端 Playwright 的假 WebSocket 用例固化，直接断言发出的 `create_session.agent_id` 和 `user_input.session_id`，比只看页面上显示的模型名称更可靠。

失败/风险经验：
- 当前环境跑 Playwright 时，仓库默认 `webServer` 会走 `uv run python3 -m sensenova_claw.app.main run`；如果 `uv` 命中缓存权限或 `system-configuration` panic，浏览器级 e2e 会在服务启动前失败，不能误判为页面交互逻辑有问题。

### 2026-03-23 LLM 回退链路补充

成功经验：
- LLM 失败回退规则应集中放在 `LLMSessionWorker`，不要分散在 `LLMFactory` 和调用层各自兜底；否则“provider 不可用”“参数错误”“业务 400”会出现互相覆盖的行为差异。
- `max_tokens` 越界这类错误可以保留“同 provider 截断重试”作为第一层自恢复，但只允许一次；若重试仍失败，再继续走 `当前模型 -> default model -> mock` 的分层回退更清晰。
- 回退提示最好统一写成 `provider:model`，并明确“哪个模型出错、将回退到哪个模型”；这样用户在对话框里就能直接分辨是 agent 选错、provider 故障还是自动降级。

失败/风险经验：
- 单元测试若不显式固定 `config.data["llm"]["default_model"]`，会被开发机本地真实配置污染，导致回退目标漂移；这类测试必须在用例内保存并恢复配置。
### 2026-03-23 Tools API Key 指引补充

成功经验：
- Tools 页的 API key 获取说明是由后端 `TOOL_API_KEY_SPECS` 直接驱动的；要让前端展示更具体的“如何拿 token”，优先补充 `setup_guide/docs_url/example_format`，比在前端硬编码文案更稳。
- 对这类“内容增强但仍需用户可见回归”的改动，后端单测断言关键关键词，前端 Playwright 只断言一个代表性流程即可，维护成本最低。
- 当前环境若已安装独立 `chrome-headless-shell`，可在 `playwright.config.ts` 中加入固定候选路径回退，避免每次测试都依赖 Playwright 自带浏览器缓存。

失败/风险经验：
- 第三方控制台的入口名称会变化，例如 `Dashboard`、`Subscriptions`、`API Keys` 等；文案应写到“足够具体但不强依赖像素级页面布局”，否则后续很容易因供应商改版过时。

### 2026-03-23 Tabs orientation 布局补充

成功经验：
- Radix 这类组件如果运行时依赖 `data-orientation="horizontal"`，Tailwind 选择器必须写成 `data-[orientation=horizontal]:...` 或 `group-data-[orientation=horizontal]/...`；写成 `data-horizontal:` 只会匹配布尔属性，实际不会命中。
- 当页面表现成“tab 栏在左、内容在右”时，先检查根组件是否仍是 `display:flex` 且没有被切成 `flex-col`；这种问题通常是状态类名没生效，不是业务页本身的布局问题。
- 对布局修复，Playwright 最稳的断言不是截图，而是直接比较 `boundingBox`：验证 tablist 的 `y` 在内容上方、`x` 基本对齐即可。

失败/风险经验：
- 同类错误容易同时出现在 `Tabs`、`Separator`、`ScrollArea` 等多个基础组件中；只修单页通常会留下第二处同源问题。

### 2026-03-23 Windows 原生通知修复补充

成功经验：
- Windows 下 `ToastNotificationManager.CreateToastNotifier(appId)` 不能只传任意字符串；若开始菜单里不存在同一 `AppUserModelID` 的快捷方式，PowerShell 即使返回成功，系统通知也可能完全不显示。
- 对 PowerShell 通知脚本，改用 `-EncodedCommand` 比直接 `-Command` 稳定得多，能避免 XML、引号、`$` 和换行内容在通知正文里被二次解析。
- 当前 Windows 环境里，新的通知脚本可真实执行并返回 `0`，同时成功创建 `AppData\\Roaming\\Microsoft\\Windows\\Start Menu\\Programs\\Sensenova-Claw Notifications.lnk`；通知单测可通过 `uv run --extra dev python -m pytest tests/unit/test_notification_service.py` 稳定回归。

失败/风险经验：
- 当前自动化只能确认“脚本执行成功 + 快捷方式落盘 + 返回码正常”，无法直接断言用户桌面一定已经弹出可见通知；最终显示仍受 Windows 通知权限、专注助手和实际交互桌面会话影响。

### 2026-03-23 工作台新建会话 Agent 选择补充

成功经验：
- 工作台底部 selector 切 agent 但继续复用旧 session 的问题，直接在 `ChatSessionContext.sendMessage()` 内比对“当前 session 的 `agent_id`”与“待发送 agent”最稳；不需要新增后端协议，也不会影响已有 `create_session -> session_created -> user_input` 链路。
- 最近对话 `+` 的需求适合直接放在 `LeftNav` 层完成：复用同一份 agent 列表，弹一个轻量 `Dialog` 让用户确认后再 `createSession()`，普通工作台默认 `default`，带 `agentFilter` 的页面默认当前过滤 agent。
- Playwright 用假 `fetch` 和假 `WebSocket` 断言 `load_session/create_session/user_input` 的顺序，非常适合这类前端 session 编排回归；本次两个工作台用例都能在隔离环境下快速跑通。

失败/风险经验：
- 旧前端测试里默认认为 `chat-input`、`send-button` test id 一直存在，但组件实际可能已经漂移；遇到“元素不存在”时先核对测试钩子，不要误判成业务逻辑回归。
- 当前仓库默认 Playwright 配置会联动 `webServer`，在本机可能被 `uv` 缓存权限或 `system-configuration` panic 拖垮；做前端局部回归时，临时改成“直连已启动 3000 服务”的最小配置更稳。

### 2026-03-23 工作台加号重置空白对话补充

成功经验：
- 如果产品期望是“像刚进入工作台那样的新对话窗口，但不提前建 session”，最小实现就是让最近对话 `+` 只调用 `startNewChat()`；右侧会自然回到空白输入态，首条消息再沿用现有惰性建 session 链路。
- 这种行为比“点 `+` 就创建空 session”更稳，也避免用户误触后留下无内容会话；和现有 `sendMessage()` 的惰性创建模型一致。

失败/风险经验：
- 这类交互需求很容易在中途反复变化；如果先把 `+` 绑定到复杂弹窗或预创建逻辑，再回退会造成无谓代码噪音。应优先围绕”是否真的需要立即创建 session”这个核心约束做最小实现。

### 2026-03-23 Discord Channel 插件迁移补充

成功经验：
- 对这类从外部项目迁移的 IM channel，先把范围收敛到“标准消息 channel 能力”最稳：`config/models/runtime/channel/plugin` 五层结构足以承载 DM、群聊 mention、线程路由、`ask_user` 出站和通用 `MessageTool`，不必一开始就卷入 slash command、语音或管理动作。
- `discord.py` 依赖应延迟到 `runtime.start()` 再导入；这样即使本机没装 Discord SDK，插件发现、配置解析、channel 单测和进程内 e2e 仍可稳定执行，不会把“依赖缺失”误判成“插件结构错误”。
- Discord 的会话键最好直接按 `dm:<sender_id> / group:<channel_id> / thread:<thread_id>` 划分；这样与 Telegram topic、WhatsApp group 的思路一致，后续扩展线程绑定或 channel 级功能时不需要重做会话模型。

失败/风险经验：
- `openclaw/extensions/discord` 里的能力远超 Sensenova-Claw 现有 channel 抽象；如果不先明确“只迁移消息渠道闭环”，很容易把 provider runtime、原生命令和复杂 reply delivery 一并带进来，导致首版范围失控。

### 2026-03-23 Gateway 缺依赖插件展示补充

成功经验：
- 对“插件已启用但缺少运行依赖”的场景，最稳的做法不是让 channel 注册后启动失败，而是在 `PluginRegistry` 层保存一份 `plugin_state`，由 `/api/gateway/channels` 把“真实已注册 channel”和“失败但应展示的插件”合并返回。
- `Gateway` 页面如果要展示这类失败态，后端响应里必须直接带 `error` 字段；前端只根据 `status=failed` 上色不够，用户仍然不知道是认证失败、网络失败还是本机没装依赖。
- `stats.totalChannels` 与 channel 列表最好复用同一份合并结果，否则会出现“页面明明有一张失败卡片，但统计仍显示 0 channels”的割裂感。

失败/风险经验：
- 仅在插件 `register()` 里静默跳过依赖缺失，虽然能避免服务启动失败，但会让 `/gateway` 页面完全看不到该 channel，用户体验上等同于“配置没生效”，排查成本仍然很高。

### 2026-03-23 npm install 同步 Python 可选依赖补充

成功经验：
- 对“用户只跑 `npm install`”的仓库，真正的一键安装要落在根目录 `postinstall`，而不是只在 README 里要求用户再手动执行 `uv sync`；当前仓库 `npm install` 已会执行 `scripts/postinstall.sh`，是接入 Python 可选依赖的正确位置。
- Discord 这类 Python channel 依赖如果不放进 `uv sync --extra ...`，用户即使完成 `npm install` 也仍会在 Gateway 里看到“未安装依赖”；把 `--extra discord` 直接合入 postinstall 后，安装体验和用户预期才能对齐。

失败/风险经验：
- 不能把“某个包之前能 import”误判成“npm install 已经覆盖 Python 依赖”；像 `lark_oapi` 这类模块可能只是开发机全局 Python 环境里本来就有，和 npm 安装链路没有关系。

### 2026-03-23 Channel 依赖收敛到默认安装补充

成功经验：
- 如果产品要求是“用户只跑一次 `npm install`”，最稳的方案不是继续堆 `uv sync --extra xxx`，而是把实际需要的 channel Python 依赖直接放进 `pyproject.toml` 的默认 `dependencies`，这样 `postinstall -> uv sync` 就天然覆盖到位。
- 对已经进默认依赖的包，安装脚本应回到最简单的 `uv sync`；否则依赖声明和安装路径会双轨并存，后续很容易继续出现“某包在默认依赖里，脚本却还写着 extra”的漂移。

### 2026-03-23 dev 退出残留子进程补充

成功经验：
- `sensenova-claw run` 用 `uvicorn --reload` 启动时，真正的根因不是某个 channel 卡住，而是当前清理逻辑只 `terminate()` 了父进程，没有回收整个进程组；一旦 reload/watch 或某些 runtime 生成子进程，就会留下孤儿进程继续占端口。
- 对这类“父进程 + watcher + worker”模型，最稳的修法是启动时给每个子进程单独建进程组，退出时按进程组发送 `SIGTERM`，超时再 `SIGKILL`；仅杀父 PID 不足以保证端口释放。
- 用真实子进程测试比 mock 更可靠：让父脚本再 spawn 一个 `sleep` 子进程，然后断言清理函数能把父子一起杀掉，能稳定覆盖这类端口残留问题。

失败/风险经验：
- 仅修 Discord runtime 的异常提示不能解决 `Ctrl+C` 后端口残留；如果 `app/main.py` 仍然按单 PID 清理，换成别的 channel 或热重载路径仍会复现类似问题。

### 2026-03-24 网站图标 500 排查补充

成功经验：
- Next.js App Router 下，`app/icon.png` 会直接生成 `/icon.png` metadata route；如果同时存在 `public/icon.png`，干净启动时首次访问 `/icon.png` 会稳定报 `A conflicting public file and page file was found for path /icon.png`。
- 这类静态资源问题最有效的验证方式是起一个干净的独立 `next dev` 端口后直接 `curl /icon.png`；复用已有 dev 进程时，热更新状态可能会暂时掩盖冲突。
- 对这类“资源路径冲突”回归，使用 `node --test` 做文件级断言成本最低，不依赖浏览器环境，也能稳定卡住 `app/icon.png` 与 `public/icon.png` 的重复落盘。

失败/风险经验：
- 当前仓库把 `.next/` 产物纳入版本管理，调试前端路由时很容易产生大量噪音改动；完成后需要显式回退 `.next/`，只保留真实源码变更。

### 2026-03-24 Proactive Agent Prompt 收敛补充

成功经验：
- 对这类“runtime 自动触发 + 用户直聊”双入口 agent，`SYSTEM_PROMPT.md` 最适合承载硬规则、判断顺序和执行协议，`AGENTS.md` 更适合承载角色边界、默认协作策略和风格偏好；两者分层清楚后，提示词更稳也更容易维护。
- Prompt 文案应尽量贴真实运行时能力来写，例如 proactive 当前稳定支持的是 `time/event` 触发，以及 `list/create/enable/disable/delete` 管理动作；把不存在的“条件触发”“字段级 update”写进 prompt，只会让模型产生幻觉。
- 对这类 prompt-only 改动，跑 `./.venv/bin/python -m pytest tests/unit/test_agent_registry.py` 作为最小回归很高效，能快速确认 `SYSTEM_PROMPT.md` 的加载链路未被破坏。

失败/风险经验：
- 当前 `proactive` 任务虽然支持 `system_prompt_override` 元数据注入，但是否在完整消息构建链路中被最终消费，仍需后续单独核查；不能仅凭字段存在就默认该能力已稳定可用。
### 2026-03-24 setup 跳过按钮补充

成功经验：
- `setup` 页的“跳过，稍后配置”如果只做 `router.push('/')`，会被后续守卫重新拦回；最小可行修法是在前端会话里显式写 `llm_setup_skipped`，并让 `ProtectedRoute` 在当前浏览器会话内跳过 LLM 强制配置检查。
- 登录态刚建立时，`verifyToken()` 与 `AuthProvider` 初始化可能并发，后者会把前者刚设成 `true` 的状态覆盖回 `false`；用 `auth_just_verified` + `verifiedInSessionRef` 兜住这个短暂窗口，能避免“刚验证完 token 就又被打回 /login”。
- Playwright 回归前必须先确认 `reuseExistingServer` 复用的是当前仓库的 dev 进程；这次 3000 端口一度连到另一个仓库 `agentos-dev/.../app/web`，导致浏览器现象与源码完全对不上。最稳的做法是先查端口占用，再跑正式用例。
- 当 `playwright test` 本身被 webServer 复用/残留进程干扰时，先用一次性的 Playwright 脚本直接驱动页面、打印 URL 与 `sessionStorage`，可以快速区分“代码没生效”和“测试基础设施跑偏”。

失败/风险经验：
- 根目录 Playwright 配置会同时拉起前后端，一旦 8000/3000 端口有残留进程，失败现象会混入大量非业务噪音；在这种情况下不能直接把浏览器断言失败等同于页面逻辑失败。
- 当前 `npx tsc --noEmit` 仍会先撞到仓库既有类型问题（如 `app/settings/page.tsx`、`components/chat/MessageList.tsx`、`e2e/miniapp-workspace.spec.ts`），不能把这类全局红灯误判成这次 `setup` 修复引入的新错误。

### 2026-03-24 Secret Skill 接入补充

成功经验：
- 给内置 skill 新增能力时，先补一个“从 `.sensenova-claw/skills` 加载该 skill”的最小单测最有效；可以快速证明失败原因是 skill 缺失，而不是 `SkillRegistry` 扫描路径不对。
- 当前后端 secret 读取与写入不是同一个接口：读取走 `GET /api/config/secret?path=...`，写入应走 `PUT /api/config/sections`，由 `ConfigManager` 自动写入 keyring / fallback secret store 并将 `config.yml` 改写为 `${secret:...}`。
- 适合作为通用桥接 skill 的敏感路径范围，应严格对齐 `platform/secrets/registry.py` 里的注册模式，尤其是 `tools.*.api_key` 与 `llm.providers.*.api_key`，这样像 Brave Search 这类 skill 才能稳定复用。
- 如果希望 skill 自身保留“它依赖哪个 secret 标识”的可追踪信息，最轻量的约定是在目标 skill 目录下维护 `secret.yml`，只写映射不写明文，例如 `OPENAI_API_KEY: secret:openai-whisper-api:OPENAI_API_KEY`；读取时优先查这个文件，写入成功后同步创建或更新它。

失败/风险经验：
- 如果把 secret skill 设计成“任意 path 都可读写”的通用管理器，很容易和后端 `is_secret_path()` 的约束冲突，最终在运行时直接返回 400；文档必须明确只支持已注册敏感路径。

### 2026-03-24 ask_user 提示框溢出补充

成功经验：
- 先确认当前真实渲染链路很关键；`chat` 页 ask_user 已不再走 `QuestionDialog`，而是通过 `NotificationToast` 的 action toast 展示选项，修 UI 前必须先对准现网组件。
- 长选项按钮的稳定修法是组合处理：外层按钮容器加 `flex-wrap`，按钮本身加 `max-w-full`、`whitespace-normal`、`break-all` 和 `text-left`，这样长 URL 与中英文混排都能在卡片内换行。
- 这类布局回归用 Playwright 几何断言最有效：直接比较按钮右边界和 toast 右边界，能避免“文本可见但其实已经溢出”的假通过。

失败/风险经验：
- 旧的 `sensenova_claw/app/web/e2e/ask-user.spec.ts` 仍按已废弃的弹窗交互建模，和当前通知卡片实现已漂移；后续若要维护整套 ask_user 前端回归，应该先统一到现有通知交互模型再扩展断言。

### 2026-03-24 WhatsApp 授权页错误信息补充

成功经验：
- `/api/gateway/whatsapp/status` 已经返回了 `lastError/lastStatusCode/debugMessage/authDir`，如果授权页只展示 `state`，用户会把“可定位的启动失败”误看成泛化 `error`；前端应直接把这些字段展示出来。
- 这类问题的最小修法通常不在 sidecar 或 channel，本质是“后端已有证据但前端没透出”；先核对接口 payload，再决定是否真的要改运行时。

失败/风险经验：
- 当前仓库的 Playwright 默认 `webServer` 仍依赖根目录 `npm run dev`，而这条链路会受 `uv` 缓存权限和 `uv` 自身 panic 影响；前端单用例失败时，必须先区分是页面断言失败还是测试基础设施没起来。

### 2026-03-24 LLM 回退链路补充

成功经验：
- 当回退策略从“当前模型 -> default -> mock”扩展为“当前模型 -> default -> 任意可用 LLM -> mock”时，最稳的落点是集中改 `llm_worker._fallback_targets()`，不要把“找备用模型”的逻辑分散到 `LLMFactory` 或 `AgentWorker`。
- “任意可用 LLM”如果不想引入额外配置，直接按 `llm.models` 的定义顺序扫描、结合 provider `api_key` 可用性判断即可，行为可预测，也方便测试锁定。
- 这类回退改动最适合用 `tests/unit/test_llm_worker.py` 做 TDD：先写“default 失败后应落到第三跳可用模型”的失败用例，再跑整份文件补齐旧断言，能快速识别哪些是新行为，哪些只是历史测试文案过窄。

失败/风险经验：
- 现有 `MockProvider` 的兜底文案并不包含字符串 `mock`，而是“当前没有可用的 LLM...”；如果测试把“回退到 mock”硬编码成断言回复里必须出现 `mock`，会把文案实现细节误当成行为契约。
### 2026-03-24 ACP Wizard 多平台补充

成功经验：
- ACP 多 agent 支持最适合收敛成一个后端 catalog/service：把 `agent 预设`、`平台支持`、`依赖探测`、`安装 recipe`、`推荐 command/args/env` 放在同一份 `ACPWizardService` 中，前端只消费结构化结果即可，避免在 UI 里硬编码平台分支。
- Windows 支持不能只做 `platform == windows`；还要同时处理命令名归一化与真实可执行路径。像 `codex.cmd` / `python.exe` 的配置比对需要去掉扩展名，而安装步骤执行时又必须优先使用实际探测到的二进制路径，否则会出现“向导显示已检测，点击安装却起不来”的假成功。
- `powershell` 相关 recipe 最容易踩坑：探测层应允许 `pwsh` 与 `powershell` 统一归到同一个 installer，执行层再把命令首项替换为实际探测到的路径，这样 Windows PowerShell 和 PowerShell 7 都能覆盖。
- 前端 ACP 设置页做向导时，最稳的交互闭环是“三步走”：`检测 -> 一键安装缺失项 -> 回填推荐配置再统一保存`；把“安装”和“保存 config.yml”拆开后，用户更容易理解当前状态，也便于 Playwright 断言。
- 这类 ACP 预设不要靠记忆猜命令；先对照 ACP 官方 agents 列表和各 CLI 官方文档确认真实入口，再写成预设，能显著减少 `args`/adapter 命名漂移。

失败/风险经验：
- 当前环境执行 `uv run ...` 会把 `uv.lock` 重写成本机镜像源 URL，即使业务代码没变也会产生超大噪音 diff；完成测试后要记得把 `uv.lock` 恢复回仓库版本，再做最终状态检查。

### 2026-03-24 Default Agent 默认模型补充

成功经验：
- 当 `default agent` 看起来“用户没配 model 却仍固定走 mock”时，优先检查 `DEFAULT_CONFIG` 与用户配置的深度合并结果，而不是只盯着 `~/.sensenova-claw/config.yml`；这次根因正是内置默认值里的 `agents.default.model: mock` 被保留下来了。
- 对这类配置继承问题，最高价值的回归测试应直接覆盖“真实 `Config` 加载 + `AgentRegistry.load_from_config()`”链路；仅测 `AgentWorker` 下游现象，不足以锁住错误来源。
- `default agent` 若希望继承全局 `llm.default_model`，最干净的实现不是在运行时特殊判断 `mock`，而是从默认配置源头移除 `agents.default.model`，让缺省值真正表现为“未设置”。

失败/风险经验：
- 如果只修用户配置或手工在本机 `config.yml` 里补 `agents.default.model`，表面上能恢复真实 LLM，但无法阻止其他新环境继续因同一默认值设计再次落回 mock。
### 2026-03-24 edit 工具移植补充

成功经验：
- 文件精确编辑工具最稳的落点是独立模块，而不是继续扩张 `builtin.py`；这次新增 `sensenova_claw/capabilities/tools/edit_tool.py` 后，路径解析、替换校验、diff 生成和恢复逻辑都能独立测试。
- `edit` 的核心契约必须锁死为“`oldText` 恰好命中一次”；把“未命中 / 多次命中 / `_agent_workdir` 相对路径 / post-write recovery”都放进集成测试后，行为边界会清晰很多。
- `openclaw` 的 post-write recovery 很值得保留：当文件已经写成功但 diff/格式化阶段报错时，重新读盘并按最终内容恢复成功结果，可以避免误向用户报告假失败。

失败/风险经验：
- 当前实现虽然兼容了 `old_text/new_text` 与 `old_string/new_string`，但对外主 schema 仍以 `oldText/newText` 为中心；若后续要继续补更多上游兼容别名，需要先核对各 provider 的 tool schema 约束，避免把参数面扩得过宽。

### 2026-03-24 apply_patch 工具移植补充

成功经验：
- `apply_patch` 这类复杂文件变更能力，适合像 `edit` 一样拆成独立模块；把解析、路径解析、更新替换和 summary 输出都放在 `sensenova_claw/capabilities/tools/apply_patch_tool.py` 后，测试与后续演进都更稳。
- 从 `openclaw` 移植时，优先保留补丁格式契约（`*** Begin/End Patch`、`Add/Delete/Update File`、`Move to`、`@@` chunk）而不是生搬硬套它的 sandbox 安全层，能更好地贴合当前仓库的 `_agent_workdir` 工具语义。
- 对这类工具最有效的测试组合是“一个多 hunk 端到端用例 + 一个 `_agent_workdir` 相对路径用例 + 一个非法边界用例 + 一个 `_path_policy` 拦截用例”，既覆盖 happy path，也锁住关键失败态。

失败/风险经验：
- 当前 `apply_patch` 的 `_path_policy` 接入是按已解析的绝对路径做 `check_write`，这和 `PathPolicy` 内部“相对路径默认基于 workspace”语义并不完全一致；若后续要把所有文件工具统一到严格路径策略，需要整体收敛 `read_file/write_file/edit/apply_patch`，不能只单独加强一个。

### 2026-03-24 apply_patch 解析器对齐补充

成功经验：
- 如果目标是“严格对齐上游解析器”，最稳的方法不是口头比对，而是直接把上游 parser 的失败态一个个翻译成测试：非法 hunk header、第二个 update chunk 缺 `@@`、update hunk 非法行、`<<EOF ... EOF` 包裹的 lenient boundary，都应先红后绿。
- `openclaw` 的 parser 有一个关键细节：首个 update chunk 可以省略 `@@`，但后续 chunk 不行；只有把 `allowMissingContext` 这条规则一起移过来，错误行号和报错文案才能真正对齐。
- 对模型友好的做法不是自动兼容错误方言，而是像上游一样在 schema/description 里只展示一种合法格式，并在解析失败时返回带“Valid hunk headers ...”的明确错误。

失败/风险经验：
- 看起来像“第二个 chunk 缺少 `@@`”的补丁，未必真的会分裂成第二个 chunk；像 `+tail` 这种行在上游仍会被视为同一个 chunk 的新增行，测试样例必须先按 parser 规则推演，不然容易把错误归因到实现。

### 2026-03-25 PPT 标题可见层级补充

成功经验：
- PPT 页面里“标题源码存在但浏览器看不见”往往不是内容缺失，而是层级结构错误；最常见的坏结构是把 `.header` 放在 `#bg` 和 `#ct` 之间，随后被 `#ct` 的更高 `z-index` 盖住。
- 这类问题不能只靠 skill 提示语约束，最好同时在 `ppt-page-html`、`ppt-review` 和导出前 guard 三处收口：生成时禁止坏结构，review 时检查标题是否落在 `#ct` 或 `#header`，导出前再做一次硬校验。
- `ppt-export-pptx` 的导出前校验不应只看装饰层证据；`review.md/review.json` 是否存在、是否标记阻塞，也应在 `cli_guards.mjs` 里真实落地，而不是只留在文档里。

失败/风险经验：
- 如果只检查页面里有没有 `<h1>`/`<h2>`，会把“标题在源码里但被层级盖住”的页面误判为通过；标题校验必须结合容器位置，至少区分“在 `#ct` / `#header` 内”和“落在 `#ct` 外的裸 `.header`”。

### 2026-03-26 payload_budget 下游承接补充

成功经验：
- 这类“控制面字段继续下沉”的任务，最稳的推进方式是只在下游 skill 文档和契约测试里扩展职责边界：保留 `task-pack` 的 profile 定义不变，由 `ppt-storyboard` 写页级 `payload_budget`，`ppt-page-html` 消费预算，`ppt-review` 审核预算兑现。
- 先把字符串契约测试补成红灯很有效；像 `每页必须声明页级 payload_budget`、`不允许把应承载 3 块内容的页面退回成一个标题 + 一张大卡片`、`承载不足 / 结构块不足 / 缺少对比或摘要` 这类文案，能直接锁住职责分工和后续回归重点。
- `content_density_profile -> payload_budget` 的解释链最好同时写在设计总览和 `storyboard` 详细 schema 里；只改一处容易让文档看起来“有字段但没来源”或“有原则但没落点”。

失败/风险经验：
- 旧测试里如果曾明确断言“设计文档不应出现 payload_budget”，这类历史约束需要先精确缩小作用域，只保留对上游 skill 的边界限制；否则新任务明明要求文档同步，却会被旧断言误杀。

### 2026-03-26 PPT 默认 guided 回归补充

成功经验：
- 当工作区里的 `.sensenova-claw/skills` 尚未同步到 `~/.sensenova-claw` 时，真实回归不要直接用 home 目录启动服务；最稳的方法是在 `/tmp` 组一个临时 `SENSENOVA_CLAW_HOME`，复用 home 的 `config.yml`/`data/secret`，但把 `agents/skills` 从当前工作区复制进去，这样才能验证“当前代码 + 当前 skill”而不是用户 home 里的旧版本。
- 对默认 `guided` 的真实回归，判断口径不需要等整轮对话完全结束；只要能确认 `task-pack.json`、`research-pack.json`、`style-spec.json`、`storyboard.json` 已落盘，且 `pages/` 仍为空，就足以说明链路停在确认点之前，没有继续进入 `ppt-page-html`。
- 对显式 `fast` 的真实回归，不一定要等到整套 HTML/PPTX 都生成完；只要 `task-pack.json.mode == "fast"`，并且日志或工件证明链路在 `style-spec` 之后自动继续进入 `storyboard`/后续步骤、没有等待用户确认，就可以判定默认 mode 切换逻辑生效。
- 这类长链路真实回归，直接用最小 WebSocket 脚本比依赖 CLI 更稳；可以精确控制 `create_session -> user_input`，并按需观察 `notification.session`、`turn_completed`、`user_question_asked` 等事件。

失败/风险经验：
- 当前 CLI 读取 token 时调用 `read_token_file()` 没有传 `SENSENOVA_CLAW_HOME`，会硬编码回 `Path.home()/.sensenova-claw/token`；只要测试使用临时 home，CLI 就可能因为 token 不匹配直接报 `1008 Invalid or missing token`。在修掉 CLI 之前，临时 home 回归应优先走原生 WebSocket 脚本。
- 即便服务进程设置了临时 `SENSENOVA_CLAW_HOME`，当前实现里仍可能继续读取 home 的某些配置/secret/watcher 路径；因此这套真实回归是“技能与工作目录隔离优先”，不是完全沙箱化的全隔离环境，分析日志时要留意 home 路径残留。
