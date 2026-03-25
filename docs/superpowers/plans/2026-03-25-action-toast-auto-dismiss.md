# Action Toast 自动消失 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让待用户处理的 `action-toast` 在 60 秒后自动从界面消失，同时保留通知中心卡片与既有 resolved 收口逻辑。

**Architecture:** 在 `NotificationProvider` 中集中管理 `actionToasts` 的 60 秒超时回收，只移除浮层，不修改通知卡片状态。现有 `pending` 和 `resolved` 流程保持不变，避免引入新的交互歧义。

**Tech Stack:** Next.js 14、React、TypeScript、Playwright

---

## Chunk 1: 回归测试先行

### Task 1: 为 action-toast 自动消失补一个失败用例

**Files:**
- Modify: `sensenova_claw/app/web/e2e/tool-confirmation-resolution.spec.ts`

- [ ] **Step 1: 写失败测试**

在 `tool-confirmation-resolution.spec.ts` 中新增一个用例：
- 发送 `tool_confirmation_requested`
- 断言 `action-toast` 出现
- 快进 60 秒
- 断言 `action-toast` 消失
- 断言通知中心卡片依然存在

- [ ] **Step 2: 运行该测试并确认失败**

Run: `cd sensenova_claw/app/web && PLAYWRIGHT_BROWSERS_PATH=/tmp/pw-browsers npx playwright test e2e/tool-confirmation-resolution.spec.ts --grep "60 秒后自动消失"`

Expected: FAIL，当前 toast 不会自动消失。

## Chunk 2: 最小实现

### Task 2: 在 NotificationProvider 中增加 toast 生命周期管理

**Files:**
- Modify: `sensenova_claw/app/web/components/notification/NotificationProvider.tsx`

- [ ] **Step 3: 写最小实现**

实现要点：
- 增加 `ACTION_TOAST_AUTO_DISMISS_MS = 60_000`
- 为未 `pending` 的 toast 注册剩余时间定时器
- 定时器到点后只移除对应 toast
- effect cleanup 中清理 timer，避免重复注册

- [ ] **Step 4: 运行测试并确认通过**

Run: `cd sensenova_claw/app/web && PLAYWRIGHT_BROWSERS_PATH=/tmp/pw-browsers npx playwright test e2e/tool-confirmation-resolution.spec.ts --grep "60 秒后自动消失"`

Expected: PASS

## Chunk 3: 回归验证与提交

### Task 3: 跑相关回归并提交

**Files:**
- Modify: `docs/superpowers/specs/2026-03-25-action-toast-auto-dismiss-design.md`
- Modify: `docs/superpowers/plans/2026-03-25-action-toast-auto-dismiss.md`

- [ ] **Step 5: 跑相关前端回归**

Run: `cd sensenova_claw/app/web && PLAYWRIGHT_BROWSERS_PATH=/tmp/pw-browsers npx playwright test e2e/tool-confirmation-resolution.spec.ts`

Expected: PASS

- [ ] **Step 6: 提交改动**

```bash
git add -f docs/superpowers/specs/2026-03-25-action-toast-auto-dismiss-design.md docs/superpowers/plans/2026-03-25-action-toast-auto-dismiss.md
git add sensenova_claw/app/web/components/notification/NotificationProvider.tsx sensenova_claw/app/web/e2e/tool-confirmation-resolution.spec.ts
git commit -m "fix: auto dismiss idle action toasts"
```
