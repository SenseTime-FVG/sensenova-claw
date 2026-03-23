'use client';

import { useRouter } from 'next/navigation';
import { useTheme } from 'next-themes';
import {
  Sun, Moon, Monitor,
  Settings, LogOut,
  Check,
  Type,
  RectangleHorizontal,
} from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { cn } from '@/lib/utils';
import { useAuth } from '@/contexts/AuthContext';
import {
  useUserPreferences,
  ACCENT_COLORS,
  type AccentColor,
  type FontSize,
  type PanelRadius,
} from '@/contexts/UserPreferencesContext';

// ── 主题色选择器 ──

function AccentColorPicker() {
  const { prefs, setAccentColor } = useUserPreferences();
  const colors = Object.entries(ACCENT_COLORS) as [AccentColor, typeof ACCENT_COLORS[AccentColor]][];

  return (
    <div className="px-2 py-2">
      <span className="text-[10px] font-semibold text-muted-foreground/70 uppercase tracking-wider px-1">
        主题色
      </span>
      <div className="flex items-center gap-2 mt-2 px-1">
        {colors.map(([key, def]) => {
          const isActive = prefs.accentColor === key;
          return (
            <button
              key={key}
              type="button"
              title={def.label}
              onClick={() => setAccentColor(key)}
              className={cn(
                'w-6 h-6 rounded-full transition-all duration-150 shrink-0',
                'hover:scale-110 active:scale-95',
                isActive && 'ring-2 ring-offset-2 ring-offset-background',
              )}
              style={{
                backgroundColor: def.light,
                ...(isActive ? { boxShadow: `0 0 0 2px var(--background), 0 0 0 4px ${def.light}` } : {}),
              }}
            >
              {isActive && (
                <Check className="w-3 h-3 mx-auto" style={{ color: def.lightForeground }} />
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ── 外观模式切换 ──

function AppearancePicker() {
  const { theme, setTheme } = useTheme();

  const modes = [
    { key: 'light', icon: Sun, label: '浅色' },
    { key: 'dark', icon: Moon, label: '深色' },
    { key: 'system', icon: Monitor, label: '系统' },
  ] as const;

  return (
    <div className="px-2 py-2">
      <span className="text-[10px] font-semibold text-muted-foreground/70 uppercase tracking-wider px-1">
        外观
      </span>
      <div className="flex items-center gap-1 mt-2 px-1">
        {modes.map(({ key, icon: Icon, label }) => (
          <button
            key={key}
            type="button"
            onClick={() => setTheme(key)}
            className={cn(
              'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-150',
              theme === key
                ? 'bg-primary/10 text-primary'
                : 'text-muted-foreground hover:text-foreground hover:bg-muted/60',
            )}
          >
            <Icon className="w-3.5 h-3.5" />
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}

// ── 字号选择 ──

function FontSizePicker() {
  const { prefs, setFontSize } = useUserPreferences();

  const sizes: { key: FontSize; label: string }[] = [
    { key: 'compact', label: '紧凑' },
    { key: 'standard', label: '标准' },
    { key: 'comfortable', label: '舒适' },
  ];

  return (
    <div className="px-2 py-2">
      <div className="flex items-center gap-1.5 px-1 mb-2">
        <Type className="w-3 h-3 text-muted-foreground/60" />
        <span className="text-[10px] font-semibold text-muted-foreground/70 uppercase tracking-wider">
          字号
        </span>
      </div>
      <div className="flex items-center gap-1 px-1">
        {sizes.map(({ key, label }) => (
          <button
            key={key}
            type="button"
            onClick={() => setFontSize(key)}
            className={cn(
              'px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-150',
              prefs.fontSize === key
                ? 'bg-primary/10 text-primary'
                : 'text-muted-foreground hover:text-foreground hover:bg-muted/60',
            )}
          >
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}

// ── 圆角选择 ──

function RadiusPicker() {
  const { prefs, setPanelRadius } = useUserPreferences();

  const options: { key: PanelRadius; label: string }[] = [
    { key: 'rounded', label: '圆润' },
    { key: 'sharp', label: '方正' },
  ];

  return (
    <div className="px-2 py-2">
      <div className="flex items-center gap-1.5 px-1 mb-2">
        <RectangleHorizontal className="w-3 h-3 text-muted-foreground/60" />
        <span className="text-[10px] font-semibold text-muted-foreground/70 uppercase tracking-wider">
          圆角
        </span>
      </div>
      <div className="flex items-center gap-1 px-1">
        {options.map(({ key, label }) => (
          <button
            key={key}
            type="button"
            onClick={() => setPanelRadius(key)}
            className={cn(
              'px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-150',
              prefs.panelRadius === key
                ? 'bg-primary/10 text-primary'
                : 'text-muted-foreground hover:text-foreground hover:bg-muted/60',
            )}
          >
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}

// ── 主组件 ──

export function UserDropdown() {
  const router = useRouter();
  const { logout } = useAuth();

  const handleLogout = async () => {
    await logout();
    router.push('/login');
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button type="button" className="focus:outline-none">
          <Avatar className="h-7 w-7 cursor-pointer ring-2 ring-border/30 hover:ring-primary/30 transition-all">
            <AvatarImage src="/icon.png" alt="AgentOS" />
            <AvatarFallback className="text-[10px] font-semibold bg-muted">AO</AvatarFallback>
          </Avatar>
        </button>
      </DropdownMenuTrigger>

      <DropdownMenuContent align="end" className="w-72" sideOffset={8}>
        {/* 用户信息区 */}
        <DropdownMenuLabel className="font-normal px-3 py-2.5">
          <div className="flex items-center gap-2.5">
            <Avatar className="h-8 w-8">
              <AvatarImage src="/icon.png" alt="AgentOS" />
              <AvatarFallback className="text-xs font-semibold bg-muted">AO</AvatarFallback>
            </Avatar>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold truncate">AgentOS</p>
              <p className="text-[11px] text-muted-foreground truncate">AI Agent 工作平台</p>
            </div>
          </div>
        </DropdownMenuLabel>

        <DropdownMenuSeparator />

        {/* 快捷设置区 */}
        <DropdownMenuGroup>
          <AccentColorPicker />
          <AppearancePicker />
          <FontSizePicker />
          <RadiusPicker />
        </DropdownMenuGroup>

        <DropdownMenuSeparator />

        {/* 操作区 */}
        <DropdownMenuGroup>
          <DropdownMenuItem
            onClick={() => router.push('/settings')}
            className="gap-2 px-3 py-2 cursor-pointer"
          >
            <Settings className="w-4 h-4 text-muted-foreground" />
            <span>设置</span>
          </DropdownMenuItem>
          <DropdownMenuItem
            onClick={handleLogout}
            className="gap-2 px-3 py-2 cursor-pointer text-destructive focus:text-destructive"
          >
            <LogOut className="w-4 h-4" />
            <span>登出</span>
          </DropdownMenuItem>
        </DropdownMenuGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
