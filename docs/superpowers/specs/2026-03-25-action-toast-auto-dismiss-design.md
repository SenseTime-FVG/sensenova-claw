# Action Toast 自动消失设计

## 背景

当前 `action-toast` 用于承载 `tool_confirmation`、`user_question` 等需要用户关注的提示。现状是这类 toast 只支持手动关闭或等待服务端 `resolved` 事件收口，没有任何超时回收逻辑，因此会长期停留在页面右上角，影响后续交互。

## 目标

- 待用户处理的 `action-toast` 在显示 60 秒后自动从界面消失。
- 自动消失仅影响右上角浮层，不影响通知中心中的持久化卡片。
- 已进入 `pending` 的 toast 不走自动消失逻辑，仍等待服务端最终结果。
- 已收到 `resolved` 的 toast 继续按现有逻辑立即关闭。

## 方案

### 方案一：在 `NotificationProvider` 统一管理 toast 生命周期

在 provider 中为 `actionToasts` 增加超时清理逻辑，按 `createdAtMs` 计算剩余时间，仅对“未 `pending` 且未 `resolved` 的浮层”注册 60 秒定时器。定时器触发时仅移除对应 toast，不修改通知卡片状态。

优点：

- 生命周期集中管理，和 `pushCard` / `markCardPending` / `resolveCard` 的状态流保持一致。
- 不依赖单个 `ActionToastItem` 的挂载时机，避免列表补位或重渲染导致重复计时。
- 更容易在 provider 层做统一清理，减少内存泄漏风险。

缺点：

- 需要在 provider 中增加一段 effect 和 timer 管理代码。

### 方案二：在 `ActionToastItem` 中逐项计时

每个 toast 组件挂载时启动 60 秒定时器，到点后调用 `onDismiss`。

优点：

- 改动表面上更局部。

缺点：

- toast 列表裁剪、重排或重新挂载时容易重复创建定时器。
- 行为更依赖渲染细节，不利于后续维护。

## 结论

采用方案一，在 `NotificationProvider` 统一处理超时回收。

## 测试策略

- 增加前端回归测试，覆盖“toast 出现后 60 秒自动消失”的行为。
- 断言通知卡片仍然保留，说明只是浮层收口，不是把交互直接判定为完成。
- 保留现有 `resolved` 收口测试，确保新的超时逻辑不影响已有行为。
