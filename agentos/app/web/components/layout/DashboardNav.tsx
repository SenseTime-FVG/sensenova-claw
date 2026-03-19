'use client';

import { useCallback, useMemo } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { cn } from '@/lib/utils';
import { Settings, ChevronDown, Zap } from 'lucide-react';
import { useCustomPages } from '@/hooks/useCustomPages';
import { useChatSession } from '@/contexts/ChatSessionContext';

const mainNavItems = [
  { path: '/', label: '工作台', exact: true },
  { path: '/chat', label: '消息' },
];

export type SubNavGroup = 'features' | 'admin' | null;

export const builtinFeatureNavItems = [
  { path: '/research', label: '深度研究' },
  { path: '/ppt', label: 'PPT' },
  { path: '/automation', label: '自动化' },
];

export const adminNavItems = [
  { path: '/agents', label: 'Dashboard' },
  { path: '/sessions', label: 'Sessions' },
  { path: '/gateway', label: 'Gateway' },
  { path: '/tools', label: 'Tools' },
  { path: '/skills', label: 'Skills' },
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
      className={cn('flex items-center space-x-4 lg:space-x-6', className)}
      {...props}
    >
      {mainNavItems.map((item) => (
        <Link
          key={item.path}
          href={item.path}
          onClick={() => { if (isActive(item)) startNewChat(); }}
          className={cn(
            'text-sm font-medium transition-colors hover:text-primary',
            isActive(item) ? 'text-primary' : 'text-muted-foreground'
          )}
        >
          {item.label}
        </Link>
      ))}

      <button
        onClick={() => handleGroupClick('features')}
        className={cn(
          'text-sm font-medium transition-colors hover:text-primary flex items-center gap-1',
          showFeatures ? 'text-primary' : 'text-muted-foreground'
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
          'text-sm font-medium transition-colors hover:text-primary flex items-center gap-1',
          showAdmin ? 'text-primary' : 'text-muted-foreground'
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
