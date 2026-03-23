# 用户偏好设置下拉菜单 — 设计文档

## 概述

点击顶部导航栏头像弹出下拉菜单，包含用户信息、快捷外观设置和操作入口。偏好持久化到 localStorage，通过动态修改 CSS 变量实现即时主题切换。

## 交互结构

下拉菜单分三个区域，从上到下依次为：

### 1. 用户信息区
- 头像 + 用户名显示
- 分隔线

### 2. 快捷设置区

**主题色（Accent Color）**
- 6 个预设色板圆点，横排排列，点击即时切换
- 当前选中的色板有外圈 ring 指示
- 预设色板：

| 名称 | 色相 | Light HSL | Dark HSL |
|------|------|-----------|----------|
| 青绿 Teal | 172 | `hsl(172, 66%, 40%)` | `hsl(172, 60%, 48%)` |
| 靛蓝 Indigo | 234 | `hsl(234, 89%, 60%)` | `hsl(234, 80%, 66%)` |
| 琥珀 Amber | 38 | `hsl(38, 92%, 50%)` | `hsl(38, 90%, 56%)` |
| 玫瑰 Rose | 347 | `hsl(347, 77%, 50%)` | `hsl(347, 70%, 58%)` |
| 紫罗兰 Violet | 263 | `hsl(263, 70%, 58%)` | `hsl(263, 65%, 65%)` |
| 石板蓝 Slate | 215 | `hsl(215, 20%, 40%)` | `hsl(215, 18%, 52%)` |

**外观模式（Appearance）**
- 三个 icon 按钮：☀ 浅色 / 🌙 深色 / 💻 跟随系统
- 复用已有 next-themes 的 `setTheme()`

**字号大小（Font Size）**
- 三档文字按钮：紧凑(12px) / 标准(13px) / 舒适(14px)
- 修改 `body` 的 `font-size` CSS 变量

**面板圆角（Panel Radius）**
- 两档：圆润(14px) / 方正(6px)
- 修改 `--panel-radius` 和 `--radius` CSS 变量

### 3. 操作区
- "设置" — 跳转 `/settings` 页面（已有的 LLM 配置页）
- "登出" — 调用 `useAuth().logout()`

## 技术实现

### 新建文件

1. **`contexts/UserPreferencesContext.tsx`**
   - `UserPreferences` 接口：`{ accentColor, fontSize, panelRadius }`
   - 默认值：`{ accentColor: 'teal', fontSize: 'standard', panelRadius: 'rounded' }`
   - 从 `localStorage` key `sensenova-claw-user-prefs` 读取/写入
   - 提供 `useUserPreferences()` hook
   - `useEffect` 中监听偏好变化，动态修改 `document.documentElement.style` 上的 CSS 变量

2. **`components/layout/UserDropdown.tsx`**
   - 使用 Radix `DropdownMenu` 组件
   - 内部分三个 `DropdownMenuGroup`，用 `DropdownMenuSeparator` 分隔
   - 主题色用 6 个圆形 `<button>` 实现，不用 DropdownMenuItem
   - 外观模式用 `useTheme()` from next-themes
   - 字号和圆角用 `useUserPreferences()`

### 修改文件

3. **`components/layout/DashboardLayout.tsx`**
   - 将 Avatar 包裹在 `DropdownMenuTrigger` 中
   - 引入 `UserDropdown` 组件

4. **`app/layout.tsx`**
   - 在 provider 树中加入 `UserPreferencesProvider`

5. **`app/globals.css`**
   - 每个预设色板定义对应的 CSS 变量覆盖集合（通过 JS 动态设置，不需额外 CSS class）

### CSS 变量映射

当用户选择一个主题色时，`UserPreferencesContext` 的 effect 会设置：
- `--primary` / `--primary-foreground`
- `--ring`
- `--sidebar-primary` / `--sidebar-primary-foreground`
- `--sidebar-ring`
- `--chart-1`

深色模式下使用对应的 dark 值。通过监听 `next-themes` 的 theme 变化来切换。

### 持久化

```typescript
interface UserPreferences {
  accentColor: 'teal' | 'indigo' | 'amber' | 'rose' | 'violet' | 'slate';
  fontSize: 'compact' | 'standard' | 'comfortable';
  panelRadius: 'rounded' | 'sharp';
}
```

存储到 `localStorage` key `sensenova-claw-user-prefs`，JSON 序列化。

## 不在范围内

- 用户头像上传/修改
- 语言切换（当前固定中文）
- 键盘快捷键配置
- 通知偏好设置
