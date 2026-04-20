'use client';

import { useCallback, useMemo } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { cn } from '@/lib/utils';
import {
  Settings, ChevronDown, Zap, Presentation, MessageCircle, Home,
  Search, Clock, Brain, Server, Wrench, Star, Shield, Users,
  Boxes,
  type LucideIcon,
} from 'lucide-react';
import { useCustomPages } from '@/hooks/useCustomPages';
import { useSession } from '@/contexts/ws';
import { useI18n } from '@/contexts/I18nContext';

const iconMap: Record<string, LucideIcon> = {
  zap: Zap,
  presentation: Presentation,
  'message-circle': MessageCircle,
  home: Home,
  search: Search,
  settings: Settings,
  users: Users,
  clock: Clock,
  brain: Brain,
  server: Server,
  tool: Wrench,
  star: Star,
  shield: Shield,
  boxes: Boxes,
};

interface NavItem {
  path: string;
  label: string;
  exact?: boolean;
  icon?: string;
}

export interface FeatureNavItem extends NavItem {
  kind: 'builtin' | 'custom' | 'create';
  pageId?: string;
}

const mainNavItemDefs: { path: string; labelKey: string; exact?: boolean; icon?: string }[] = [
  { path: '/', labelKey: 'nav.workspace', exact: true, icon: 'zap' },
  { path: '/ppt', labelKey: 'nav.ppt', icon: 'presentation' },
  { path: '/chat', labelKey: 'nav.chat', icon: 'message-circle' },
  { path: '/office', labelKey: 'nav.office', icon: 'home' },
];

export type SubNavGroup = 'features' | 'admin' | null;

const builtinFeatureNavItemDefs: { path: string; labelKey: string; icon?: string }[] = [
  { path: '/research', labelKey: 'nav.feature.research', icon: 'search' },
  { path: '/automation', labelKey: 'nav.feature.automation', icon: 'settings' },
];

const adminNavItemDefs: { path: string; labelKey: string; icon?: string }[] = [
  { path: '/agents', labelKey: 'nav.adminItems.agents', icon: 'users' },
  { path: '/sessions', labelKey: 'nav.adminItems.sessions', icon: 'clock' },
  { path: '/llms', labelKey: 'nav.adminItems.llms', icon: 'brain' },
  { path: '/gateway', labelKey: 'nav.adminItems.gateway', icon: 'server' },
  { path: '/tools', labelKey: 'nav.adminItems.tools', icon: 'tool' },
  { path: '/skills', labelKey: 'nav.adminItems.skills', icon: 'star' },
  { path: '/mcp', labelKey: 'nav.adminItems.mcp', icon: 'boxes' },
  { path: '/acp', labelKey: 'nav.adminItems.acp', icon: 'shield' },
];

export function useFeatureNavItems(): FeatureNavItem[] {
  const { t } = useI18n();
  const { pages } = useCustomPages();
  return useMemo(() => {
    const builtinItems: FeatureNavItem[] = builtinFeatureNavItemDefs.map((item) => ({
      path: item.path,
      label: t(item.labelKey),
      icon: item.icon,
      kind: 'builtin',
    }));
    const customItems: FeatureNavItem[] = pages.map(p => ({
      path: `/features/${p.slug}`,
      label: p.name,
      pageId: p.slug,
      kind: 'custom',
    }));
    return [
      ...builtinItems,
      ...customItems,
      { path: '/create-feature', label: t('nav.feature.create'), kind: 'create' },
    ];
  }, [pages, t]);
}

export function useAdminNavItems(): NavItem[] {
  const { t } = useI18n();
  return useMemo(() => (
    adminNavItemDefs.map((item) => ({
      path: item.path,
      label: t(item.labelKey),
      icon: item.icon,
    }))
  ), [t]);
}

export function NavIcon({ name }: { name?: string }) {
  if (!name || !iconMap[name]) return null;
  const Icon = iconMap[name];
  return <Icon className="w-3.5 h-3.5" />;
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
  const { t } = useI18n();
  const featureNavItems = useFeatureNavItems();
  const adminNavItems = useAdminNavItems();
  const { startNewChat } = useSession();
  const mainNavItems: NavItem[] = useMemo(() => (
    mainNavItemDefs.map((item) => ({
      path: item.path,
      label: t(item.labelKey),
      exact: item.exact,
      icon: item.icon,
    }))
  ), [t]);
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
          <NavIcon name={item.icon} />
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
        {t('nav.features')}
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
        {t('nav.admin')}
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
