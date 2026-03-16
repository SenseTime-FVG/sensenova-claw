# Multi-Agent Team 架构图 & 信息流转图

## 1. 架构总览

```mermaid
graph TB
    subgraph 用户层["用户层 (Interfaces)"]
        WebUI["Web UI<br/>(Next.js)"]
        TUI["TUI Client"]
        CLI["CLI Client"]
    end

    subgraph 接入层["接入层 (Gateway)"]
        GW["Gateway"]
        WSC["WebSocketChannel"]
        TUIC["TUIChannel"]
        CLIC["CLIChannel"]
    end

    subgraph 事件层["事件总线 (Event Bus)"]
        PUB["PublicEventBus<br/>(全局事件流)"]
        BR["BusRouter<br/>(session 路由)"]
        PB1["PrivateEventBus<br/>Session A"]
        PB2["PrivateEventBus<br/>Session B"]
        PB3["PrivateEventBus<br/>子 Session C<br/>(delegate)"]
    end

    subgraph 运行时层["运行时层 (Runtime)"]
        AR["AgentRuntime<br/>(per-session worker)"]
        LR["LLMRuntime<br/>(per-session worker)"]
        TR["ToolRuntime<br/>(per-session worker)"]
        DR["DelegateRuntime<br/><b>全局单例</b><br/>Team 调度 & 跨 session 协调"]
        TTR["TitleRuntime<br/>(全局)"]
    end

    subgraph 能力层["能力层 (Capabilities)"]
        subgraph Tools
            DT["DelegateTool<br/>(name='delegate')"]
            BT["BashTool"]
            ST["SerperTool"]
            FT["FetchTool"]
            RW["Read/WriteTool"]
        end
        subgraph Agents
            AREG["AgentRegistry"]
            AC1["AgentConfig<br/>research-agent"]
            AC2["AgentConfig<br/>writer-agent"]
        end
        subgraph Teams["Teams (新增)"]
            TREG["TeamRegistry"]
            TC1["TeamConfig<br/>research-team<br/>strategy: leader"]
        end
    end

    subgraph 适配层["适配层 (Adapters)"]
        LLM["LLM Providers<br/>OpenAI / Anthropic / Gemini"]
        DB["Repository<br/>(SQLite)"]
    end

    WebUI --> WSC
    TUI --> TUIC
    CLI --> CLIC
    WSC --> GW
    TUIC --> GW
    CLIC --> GW
    GW <--> PUB
    PUB <--> BR
    BR --> PB1
    BR --> PB2
    BR --> PB3
    PB1 --> AR
    PB2 --> AR
    PB3 --> AR
    AR --> LR
    LR --> TR
    PUB --> DR
    PUB --> TTR
    TR --> DT
    DT -.->|"Team 委派"| DR
    DT -.->|"Agent 同步委派"| PUB
    DR -.->|"spawn 子 session"| PUB
    AREG --> AC1
    AREG --> AC2
    TREG --> TC1
    LR --> LLM
    AR --> DB
    DR --> DB

    style DR fill:#ff9,stroke:#f90,stroke-width:3px
    style Teams fill:#ffe,stroke:#f90,stroke-width:2px
    style DT fill:#ff9,stroke:#f90,stroke-width:2px
```

## 2. 组件关系图

```mermaid
graph LR
    subgraph 入口["Tool 入口"]
        DT["DelegateTool<br/>name='delegate'"]
    end

    subgraph 路由["路由判断"]
        R{"target_id<br/>是 Agent<br/>还是 Team?"}
    end

    subgraph Agent委派["Agent 直接委派"]
        AS["现有同步路径<br/>_delegate_to_agent_sync()"]
    end

    subgraph Team委派["Team 委派 (新增)"]
        DR["DelegateRuntime"]
        subgraph 策略["调度策略"]
            LS["Leader 策略<br/>Leader 自行编排成员"]
            PS["Parallel 策略<br/>成员并行执行"]
            PPS["Pipeline 策略<br/>成员串行执行"]
        end
    end

    subgraph 子Session["子 Session"]
        CS1["子 Session 1<br/>(PrivateEventBus + Workers)"]
        CS2["子 Session 2<br/>(PrivateEventBus + Workers)"]
        CS3["子 Session N<br/>(PrivateEventBus + Workers)"]
    end

    DT --> R
    R -->|"Agent + sync"| AS
    R -->|"Team / async"| DR
    AS --> CS1
    DR --> LS
    DR --> PS
    DR --> PPS
    LS --> CS1
    PS --> CS1
    PS --> CS2
    PS --> CS3
    PPS -->|"step 1"| CS1
    PPS -->|"step 2"| CS2

    style DR fill:#ff9,stroke:#f90,stroke-width:2px
    style 策略 fill:#ffe,stroke:#f90
```

## 3. 信息流转 — 同步委派（Agent → Agent）

```mermaid
sequenceDiagram
    participant User as 用户
    participant GW as Gateway
    participant PUB as PublicEventBus
    participant BR as BusRouter
    participant PB_A as PrivateEventBus<br/>Session A
    participant AW_A as AgentWorker A
    participant LW_A as LLMWorker A
    participant TW_A as ToolWorker A
    participant DT as DelegateTool
    participant PB_B as PrivateEventBus<br/>Session B (子)
    participant AW_B as AgentWorker B
    participant LW_B as LLMWorker B

    User->>GW: 发送消息
    GW->>PUB: USER_INPUT (session_id=A)
    PUB->>BR: 路由
    BR->>PB_A: deliver
    PB_A->>AW_A: USER_INPUT
    AW_A->>PB_A: AGENT_STEP_STARTED
    AW_A->>PB_A: LLM_CALL_REQUESTED

    PB_A->>PUB: forward
    PUB->>BR: 路由
    BR->>PB_A: deliver
    PB_A->>LW_A: LLM_CALL_REQUESTED
    LW_A-->>LW_A: 调用 LLM API
    LW_A->>PB_A: LLM_CALL_RESULT (tool_calls: delegate)

    PB_A->>AW_A: LLM_CALL_RESULT
    AW_A->>PB_A: TOOL_CALL_REQUESTED (delegate)

    PB_A->>TW_A: TOOL_CALL_REQUESTED
    TW_A->>DT: execute(target_id="agent2", task="...")

    Note over DT: 路由判断: Agent + sync<br/>→ 走现有同步路径

    DT->>PUB: USER_INPUT (session_id=B)
    PUB->>BR: 首次见 session B → 创建 Workers
    BR->>PB_B: deliver
    PB_B->>AW_B: USER_INPUT

    AW_B->>PB_B: LLM_CALL_REQUESTED
    PB_B->>LW_B: LLM_CALL_REQUESTED
    LW_B-->>LW_B: 调用 LLM API
    LW_B->>PB_B: LLM_CALL_RESULT

    PB_B->>AW_B: LLM_CALL_RESULT
    AW_B->>PB_B: AGENT_STEP_COMPLETED

    PB_B->>PUB: forward AGENT_STEP_COMPLETED
    PUB-->>DT: 监听到子 session 完成

    DT->>TW_A: 返回 tool_result
    TW_A->>PB_A: TOOL_CALL_RESULT

    PB_A->>AW_A: TOOL_CALL_RESULT
    AW_A->>PB_A: LLM_CALL_REQUESTED (含 tool_result)
    Note over LW_A: 第二轮 LLM 调用

    LW_A->>PB_A: LLM_CALL_RESULT (final)
    AW_A->>PB_A: AGENT_STEP_COMPLETED

    PB_A->>PUB: forward
    PUB->>GW: 路由到 Channel
    GW->>User: 返回最终响应
```

## 4. 信息流转 — Team 委派（Leader 策略）

```mermaid
sequenceDiagram
    participant AW_A as AgentWorker A<br/>(父 Agent)
    participant DT as DelegateTool
    participant PUB as PublicEventBus
    participant DR as DelegateRuntime
    participant BR as BusRouter
    participant AW_L as AgentWorker L<br/>(Leader)
    participant AW_M1 as AgentWorker M1<br/>(成员1)
    participant AW_M2 as AgentWorker M2<br/>(成员2)

    AW_A->>DT: delegate(target="research-team")
    Note over DT: 路由: TeamRegistry → Team<br/>发布 DELEGATE_REQUESTED

    DT->>PUB: AGENT_DELEGATE_REQUESTED
    DT-->>DT: 订阅 PUB，等待 DELEGATE_COMPLETED

    PUB->>DR: AGENT_DELEGATE_REQUESTED
    Note over DR: 识别 Team, strategy=leader<br/>启动 asyncio.Task

    DR->>PUB: AGENT_DELEGATE_STARTED
    DR->>PUB: USER_INPUT (Leader session, 增强任务)
    PUB->>BR: 创建 Leader session Workers
    BR->>AW_L: USER_INPUT

    Note over AW_L: Leader LLM 分析任务<br/>决定分配子任务

    AW_L->>DT: delegate(target="member1", task="子任务1")
    DT->>PUB: USER_INPUT (M1 session)
    PUB->>BR: 创建 M1 Workers
    BR->>AW_M1: USER_INPUT

    AW_L->>DT: delegate(target="member2", task="子任务2")
    DT->>PUB: USER_INPUT (M2 session)
    PUB->>BR: 创建 M2 Workers
    BR->>AW_M2: USER_INPUT

    par 并行执行
        AW_M1-->>AW_M1: LLM + Tools
        AW_M2-->>AW_M2: LLM + Tools
    end

    AW_M1->>PUB: AGENT_STEP_COMPLETED (M1 结果)
    PUB-->>AW_L: tool_result (M1)

    AW_M2->>PUB: AGENT_STEP_COMPLETED (M2 结果)
    PUB-->>AW_L: tool_result (M2)

    Note over AW_L: 汇总成员结果

    AW_L->>PUB: AGENT_STEP_COMPLETED (Leader 汇总结果)

    PUB->>DR: AGENT_STEP_COMPLETED (Leader session)
    DR->>PUB: AGENT_DELEGATE_COMPLETED (最终结果)

    PUB-->>DT: 收到 DELEGATE_COMPLETED
    DT->>AW_A: 返回 Team 最终结果
```

## 5. 信息流转 — Team 委派（Parallel 策略）

```mermaid
sequenceDiagram
    participant AW_A as AgentWorker A<br/>(父 Agent)
    participant DT as DelegateTool
    participant PUB as PublicEventBus
    participant DR as DelegateRuntime
    participant AW_M1 as AgentWorker M1
    participant AW_M2 as AgentWorker M2
    participant AW_M3 as AgentWorker M3

    AW_A->>DT: delegate(target="team-x")
    DT->>PUB: AGENT_DELEGATE_REQUESTED
    DT-->>DT: 等待 DELEGATE_COMPLETED

    PUB->>DR: AGENT_DELEGATE_REQUESTED
    Note over DR: strategy=parallel<br/>启动 asyncio.Task

    par 并行 Spawn
        DR->>PUB: USER_INPUT → M1 session
        DR->>PUB: USER_INPUT → M2 session
        DR->>PUB: USER_INPUT → M3 session
    end

    par 并行执行
        AW_M1-->>AW_M1: LLM + Tools
        AW_M2-->>AW_M2: LLM + Tools
        AW_M3-->>AW_M3: LLM + Tools
    end

    AW_M1->>PUB: AGENT_STEP_COMPLETED
    PUB->>DR: 子 delegation 完成 (M1)

    AW_M2->>PUB: AGENT_STEP_COMPLETED
    PUB->>DR: 子 delegation 完成 (M2)

    AW_M3->>PUB: AGENT_STEP_COMPLETED
    PUB->>DR: 子 delegation 完成 (M3)

    Note over DR: 全部完成 → 汇总结果

    DR->>PUB: AGENT_DELEGATE_COMPLETED (汇总结果)
    PUB-->>DT: 收到 DELEGATE_COMPLETED
    DT->>AW_A: 返回合并结果
```

## 6. 信息流转 — Team 委派（Pipeline 策略）

```mermaid
sequenceDiagram
    participant AW_A as AgentWorker A<br/>(父 Agent)
    participant DT as DelegateTool
    participant PUB as PublicEventBus
    participant DR as DelegateRuntime
    participant AW_S1 as AgentWorker<br/>Step1 (搜索)
    participant AW_S2 as AgentWorker<br/>Step2 (分析)
    participant AW_S3 as AgentWorker<br/>Step3 (撰写)

    AW_A->>DT: delegate(target="pipeline-team")
    DT->>PUB: AGENT_DELEGATE_REQUESTED
    DT-->>DT: 等待 DELEGATE_COMPLETED

    PUB->>DR: AGENT_DELEGATE_REQUESTED
    Note over DR: strategy=pipeline<br/>启动 asyncio.Task

    DR->>PUB: USER_INPUT → Step1 (原始任务)
    AW_S1-->>AW_S1: 执行搜索任务
    AW_S1->>PUB: AGENT_STEP_COMPLETED (搜索结果)
    PUB->>DR: Step1 完成

    Note over DR: 将 Step1 结果<br/>作为 Step2 输入

    DR->>PUB: USER_INPUT → Step2 (搜索结果 + 继续处理)
    AW_S2-->>AW_S2: 执行分析任务
    AW_S2->>PUB: AGENT_STEP_COMPLETED (分析结果)
    PUB->>DR: Step2 完成

    Note over DR: 将 Step2 结果<br/>作为 Step3 输入

    DR->>PUB: USER_INPUT → Step3 (分析结果 + 继续处理)
    AW_S3-->>AW_S3: 执行撰写任务
    AW_S3->>PUB: AGENT_STEP_COMPLETED (最终文章)
    PUB->>DR: Step3 完成

    DR->>PUB: AGENT_DELEGATE_COMPLETED (最终文章)
    PUB-->>DT: 收到 DELEGATE_COMPLETED
    DT->>AW_A: 返回最终结果
```

## 7. 异步委派信息流

```mermaid
sequenceDiagram
    participant AW_A as AgentWorker A
    participant DT as DelegateTool
    participant PUB as PublicEventBus
    participant DR as DelegateRuntime
    participant AW_B as AgentWorker B (子)
    participant Inbox as Delegation Inbox<br/>(AgentWorker A)

    AW_A->>DT: delegate(target="agent2", mode="async")
    DT->>PUB: AGENT_DELEGATE_REQUESTED
    DT->>AW_A: 立即返回 {delegation_id, status: "dispatched"}

    Note over AW_A: 继续执行其他操作...<br/>（不阻塞）

    PUB->>DR: AGENT_DELEGATE_REQUESTED
    DR->>PUB: USER_INPUT → 子 session

    AW_B-->>AW_B: 执行中...

    Note over AW_A: Agent A 此时可能在<br/>处理其他 tool 或 LLM 调用

    AW_B->>PUB: AGENT_STEP_COMPLETED
    PUB->>DR: 子 session 完成
    DR->>PUB: AGENT_DELEGATE_COMPLETED

    PUB->>Inbox: 存入 inbox (completed)

    Note over Inbox: 等待 Agent A<br/>下一轮 LLM 调用前

    Inbox->>AW_A: 注入 [Delegation Updates]<br/>role: system

    Note over AW_A: LLM 看到更新后<br/>自主决定如何处理
```

## 8. 完整层次关系

```mermaid
graph TD
    subgraph 用户请求
        U["用户输入"]
    end

    subgraph 主Session["主 Session (depth=0)"]
        A1["Agent1 (Orchestrator)"]
    end

    subgraph 委派层1["委派层 (depth=1)"]
        A2["Agent2<br/>(直接委派)"]
        T1["Team: research-team<br/>(Team 委派)"]
    end

    subgraph Team内部["Team 内部 (depth=1→2)"]
        Leader["Leader Agent<br/>(研究员)"]
        M1["Member: writer-agent<br/>(depth=2)"]
        M2["Member: reviewer-agent<br/>(depth=2)"]
    end

    subgraph 深层委派["深层委派 (depth=2)"]
        A3["Agent3<br/>(Agent2 继续委派)"]
    end

    U --> A1
    A1 -->|"delegate(agent2, sync)"| A2
    A1 -->|"delegate(research-team, sync)"| T1
    T1 -->|"leader 策略"| Leader
    Leader -->|"delegate(writer)"| M1
    Leader -->|"delegate(reviewer)"| M2
    A2 -->|"delegate(agent3)"| A3

    A3 -.->|"depth=2 < max=3 ✓"| A3
    M1 -.->|"depth=2 < max=3 ✓<br/>但可用预算仅 1 层"| M1

    style T1 fill:#ff9,stroke:#f90,stroke-width:2px
    style Leader fill:#ffe,stroke:#f90
    style M1 fill:#ffe,stroke:#f90
    style M2 fill:#ffe,stroke:#f90
```
