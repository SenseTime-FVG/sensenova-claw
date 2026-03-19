

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

### 2026-03-17 ask_user 收尾补充

成功经验：
- ask_user 闭环建议采用“双轨验证”：`pytest` 进程内 e2e 固化事件链（`question_asked -> question_answered -> step_completed`），再补一个独立真实 API 脚本验证线上 provider 行为。
- 前端 Playwright 用例将 mock websocket 回归与真实 API 回归拆分后更稳；真实 API 用例通过 `ENABLE_REAL_API_E2E=1` 门控，默认不会误触发慢测。
- 回归脚本保留关键事件打印（含 `question_id`、answer payload）后，排查 ToolSessionWorker 的等待/恢复逻辑明显更高效。

失败/风险经验：
- 当前环境运行 Playwright Chromium 仍缺系统库（`libnspr4.so`）；`npx playwright install --with-deps chromium` 需要 sudo 密码，未授权时无法完成前端浏览器级 e2e。
- 本地网络权限与沙箱能力会影响真实 API 回归；出现 DNS/连接异常时需在越权网络下复跑，避免把环境问题误判为功能缺陷。

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
- `ask_user` 需要区分“工具外层超时”和“ask_user 内层等待超时”：仅在 `ToolSessionWorker` 中把 `ask_user` 默认超时提升到 `300s`，才能避免用户输入过程中被 15 秒通用超时提前打断。
- `TimeoutError` 常见空字符串，错误链路统一采用 `str(exc).strip() or type(exc).__name__` 后，前端错误提示可稳定显示为 `TimeoutError`，不再退回 `Unknown Error`。
- 在 `chat/session` 两个页面都加 `session_id` 过滤，可以避免其他会话的 `turn_completed/error` 事件误关闭当前 `ask_user` 弹窗。

失败/风险经验：
- 前端 Playwright 在当前环境仍受系统库限制（缺 `libnspr4.so`），即使越权运行也无法启动 Chromium；`npx playwright install --with-deps chromium` 需要 sudo 密码，未授权时无法完成浏览器级回归。
- `tests/e2e/run_e2e.py` 的 `setup_services(provider=\"mock\")` 仍存在被本地 `config.yml` 实际 provider 覆盖的风险；ask_user 进程内 e2e 需在用例中显式固定 `agent.model`/`llm.default_model` 为 `mock` 才稳定。

### 2026-03-18 chat 跨窗口 ask_user 修复补充

成功经验：
- `WebSocketChannel.send_event` 对 `USER_QUESTION_ASKED/USER_QUESTION_ANSWERED` 做连接级广播后，前端无需先切换会话也能收到跨 session 的 `ask_user` 事件。
- 为 `USER_QUESTION_ANSWERED` 增加下行映射事件（`user_question_answered_event`）后，多窗口可用 `question_id` 做状态收敛，避免“一个窗口已回答、另一个窗口仍挂弹窗”。
- `user_input` 在携带已有 `session_id` 时补做 `gateway.bind_session + channel.bind_session`，能稳定修复“旧会话发消息后收不到后续事件”的问题；对应 `tests/unit/test_gateway_ws_endpoint_ask_user.py` 可直接回归。

失败/风险经验：
- 当前环境 `next build` 仅返回泛化的 “Build failed because of webpack errors”，无具体堆栈；前端编译问题排查应优先结合本地 IDE/CI 日志而非仅依赖该环境终端输出。
- Playwright 仍受系统库缺失影响（`libnspr4.so`），即使越权执行测试命令也无法启动 Chromium，浏览器级 e2e 结果不能在本机作为通过依据。
- `tests/e2e/test_gateway_integration.py` 在默认 `AGENTOS_HOME` 下会写到只读路径（`/home/languilin/.agentos/logs`）导致失败；需要显式设置可写 `AGENTOS_HOME` 后再跑。

### 2026-03-18 子会话继承 channel 绑定补充

成功经验：
- 在 `Gateway._dispatch_event` 中做“按 `parent_session_id` 递归查找已绑定祖先 + 命中后缓存绑定”，可以最小改动修复 `send_message` 子会话事件无法路由到前端的问题，且不会影响已绑定会话的常规路径。
- `/sessions/[id]` 页面处理 ask_user 时，必须保存 `sourceSessionId` 并在 `user_question_answered` 回传时使用来源 session；否则跨会话提问场景会持续超时。
- WebSocket 监听 effect 去除 `pendingQuestion` 依赖后，避免了问答状态变更导致的重复重连和潜在丢事件。

失败/风险经验：
- 当前环境缺少 `pytest` 运行时（`python3 -m pytest` 报 `No module named pytest`），后端新增测试只能先做静态校验，需在完整依赖环境复跑。
- 当前环境执行 Playwright 仍缺浏览器二进制（`chrome-headless-shell` 不存在），即使越权可启动流程也无法完成浏览器级断言。
- `next build` 在本机会停在 `Linting and checking validity of types ...` 且无进一步堆栈，需在 CI 或本地完整 Node 环境结合日志排查。

### 2026-03-19 skills prompt 注入补充

成功经验：
- skills 只注入 `name/description/location` 时，模型未必会主动读取正文；在 system prompt 中增加一条极简 `Skill Usage` 规则，明确“匹配到 skill 后先读对应 `SKILL.md`”，效果更稳定。
- 将 skills 列表从自由文本改为 `<available_skills><skill><name><description><location>` 结构后，测试断言和后续字段扩展都更直接。
- 当前仓库虽缺少全局 `pytest`，但可稳定使用 `.venv/bin/python -m pytest` 跑本地回归，适合作为受限环境下的默认验证方式。

失败/风险经验：
- 仅替换标签格式而不补“命中后去读 `SKILL.md`”的协议指令，收益有限；真正影响模型行为的是规则和结构一起改。

### 2026-03-19 email-agent 工具接入补充

成功经验：
- Agent 侧 `tools` 白名单与全局 `ToolRegistry` 注册缺一不可；仅修改 `.agentos/agents/<id>/config.yml` 不会让未注册工具自动可用。
- 对预置 Agent 配置做回归时，直接用仓库内真实 `.agentos/agents/<id>/config.yml` 构造 `AgentRegistry` 断言，比复制一份测试夹具更能防止配置漂移。
- 当前环境执行 pytest 应优先使用 `.venv/bin/python -m pytest`；系统 `python3` 缺少 `pytest`，直接调用会误判为测试无法运行。

失败/风险经验：
- 邮件工具虽然注册后会暴露给运行时，但真实可用性仍依赖 `tools.email.enabled` 及 SMTP/IMAP 凭据；仅单元测试通过不能代表邮件链路已完成真实回归。
