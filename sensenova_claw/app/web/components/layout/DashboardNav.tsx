'use client';

import { useCallback, useMemo } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { cn } from '@/lib/utils';
import { Settings, ChevronDown, Zap, Presentation } from 'lucide-react';
import { useCustomPages } from '@/hooks/useCustomPages';
import { useChatSession } from '@/contexts/ChatSessionContext';

const mainNavItems: { path: string; label: string; exact?: boolean; icon?: string }[] = [
  { path: '/', label: '工作台', exact: true },
  { path: '/ppt', label: 'PPT', icon: 'presentation' },
  { path: '/chat', label: '消息' },
  { path: '/office', label: '办公室' },
];

export type SubNavGroup = 'features' | 'admin' | null;

export const builtinFeatureNavItems = [
  { path: '/research', label: '深度研究' },
  { path: '/automation', label: '自动化' },
];

export const adminNavItems = [
  { path: '/agents', label: 'Agents' },
  { path: '/sessions', label: 'Sessions' },
  { path: '/llms', label: 'LLMs' },
  { path: '/gateway', label: 'Gateway' },
  { path: '/tools', label: 'Tools' },
  { path: '/skills', label: 'Skills' },
  { path: '/acp', label: 'ACP' },
];

export function useFeatureNavItems() {
  const { pages } = useCustomPages();
  return useMemo(() => {
    const customItems = pages.map(p => ({
      path: `/features/${p.slug}`,
      label: p.name,
    }));
    return [
      ...builtinFeatureNavItems,
      ...customItems,
      { path: '/create-feature', label: '+ 创建' },
    ];
  }, [pages]);
}

export function DashboardNav({
  className,
  activeGroup,
  onGroupToggle,
  ...props
}: React.HTMLAttributes<HTMLElement> & {
  activeGroup?: SubNavGroup;
  onGroupToggle?: (group: SubNavGroup) => void;
}) {
  const pathname = usePathname();
  const featureNavItems = useFeatureNavItems();
  const { startNewChat } = useChatSession();
  const isActive = (item: { path: string; exact?: boolean }) => {
    if (item.exact) return pathname === item.path;
    return pathname?.startsWith(item.path);
  };

  const isFeatureActive = featureNavItems.some((item) =>
    pathname?.startsWith(item.path)
  );
  const isAdminActive = adminNavItems.some((item) =>
    pathname?.startsWith(item.path)
  );

  const showFeatures = activeGroup === 'features' || isFeatureActive;
  const showAdmin = activeGroup === 'admin' || isAdminActive;

  const handleGroupClick = useCallback(
    (group: 'features' | 'admin') => {
      const isCurrentlyShown =
        group === 'features' ? showFeatures : showAdmin;
      onGroupToggle?.(isCurrentlyShown ? null : group);
    },
    [showFeatures, showAdmin, onGroupToggle]
  );

  return (
    <nav
      className={cn('flex items-center gap-0.5', className)}
      {...props}
    >
      {mainNavItems.map((item) => (
        <Link
          key={item.path}
          href={item.path}
          onClick={() => { if (isActive(item)) startNewChat(); }}
          className={cn(
            'px-3 py-1.5 text-[13px] font-medium rounded-lg transition-all duration-150 flex items-center gap-1.5',
            item.icon === 'presentation' && isActive(item)
              ? 'text-primary bg-primary/10 font-semibold'
              : isActive(item)
                ? 'text-foreground bg-[var(--nav-pill-active)]'
                : 'text-muted-foreground hover:text-foreground hover:bg-[var(--nav-pill-hover)]'
          )}
        >
          {item.icon === 'presentation' && <Presentation className="w-3.5 h-3.5" />}
          {item.label}
        </Link>
      ))}

      {/* 分隔点 */}
      <div className="w-1 h-1 rounded-full bg-border mx-1.5" />

      <button
        onClick={() => handleGroupClick('features')}
        className={cn(
          'px-3 py-1.5 text-[13px] font-medium rounded-lg transition-all duration-150 flex items-center gap-1.5',
          showFeatures
            ? 'text-primary bg-primary/8'
            : 'text-muted-foreground hover:text-foreground hover:bg-[var(--nav-pill-hover)]'
        )}
      >
        <Zap className="h-3.5 w-3.5" />
        功能
        <ChevronDown
          className={cn(
            'h-3 w-3 transition-transform duration-200',
            showFeatures && 'rotate-180'
          )}
        />
      </button>

      <button
        onClick={() => handleGroupClick('admin')}
        className={cn(
          'px-3 py-1.5 text-[13px] font-medium rounded-lg transition-all duration-150 flex items-center gap-1.5',
          showAdmin
            ? 'text-primary bg-primary/8'
            : 'text-muted-foreground hover:text-foreground hover:bg-[var(--nav-pill-hover)]'
        )}
      >
        <Settings className="h-3.5 w-3.5" />
        管理
        <ChevronDown
          className={cn(
            'h-3 w-3 transition-transform duration-200',
            showAdmin && 'rotate-180'
          )}
        />
      </button>
    </nav>
  );
}
