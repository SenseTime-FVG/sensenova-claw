'use client';

import { ReactNode, useState, useCallback, useMemo } from 'react';
import Link from 'next/link';
import dynamic from 'next/dynamic';
import { useRouter } from 'next/navigation';
import {
  DashboardNav,
  NavIcon,
  type FeatureNavItem,
  type SubNavGroup,
} from './DashboardNav';
import { Search } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { DndProvider } from 'react-dnd';
import { HTML5Backend } from 'react-dnd-html5-backend';
import { cn } from '@/lib/utils';
import { useSession } from '@/contexts/ws';
import { useI18n } from '@/contexts/I18nContext';
import { TodoDropdown } from '@/components/dashboard/TodoDropdown';
import { NotificationDropdown } from '@/components/notification/NotificationDropdown';
import { UserDropdown } from './UserDropdown';
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from '@/components/ui/resizable';
import { useNavigation } from '@/hooks/useNavigation';
import { ContextMenu } from '@/components/files/ContextMenu';
import { FeatureDeleteDialog } from '@/components/features/FeatureDeleteDialog';

const GlobalFilePanel = dynamic(() => import('@/components/files/GlobalFilePanel').then(mod => mod.GlobalFilePanel), {
  loading: () => <div className="h-full bg-muted/10 animate-pulse" />,
  ssr: false,
});

interface DashboardLayoutProps {
  children: ReactNode;
}

const ADMIN_PATHS = ['/agents', '/sessions', '/llms', '/gateway', '/tools', '/skills', '/mcp', '/settings', '/acp', '/office'];

export function DashboardLayout({ children }: DashboardLayoutProps) {
  const router = useRouter();
  const [manualGroup, setManualGroup] = useState<SubNavGroup>(null);
  const [featureContextMenu, setFeatureContextMenu] = useState<{ item: FeatureNavItem; x: number; y: number } | null>(null);
  const [featureToDelete, setFeatureToDelete] = useState<FeatureNavItem | null>(null);
  const { startNewChat } = useSession();
  const { t } = useI18n();

  const {
    pathname,
    visibleGroup,
    subNavItems,
  } = useNavigation(manualGroup);

  const hideRightPanel = useMemo(() => 
    ADMIN_PATHS.some(p => pathname?.startsWith(p)),
    [pathname]
  );

  const handleGroupToggle = useCallback((group: SubNavGroup) => {
    setManualGroup(group);
  }, []);

  const openFeatureContextMenu = useCallback((event: React.MouseEvent, item: FeatureNavItem) => {
    if (item.kind !== 'custom') return;
    event.preventDefault();
    setFeatureContextMenu({ item, x: event.clientX, y: event.clientY });
  }, []);

  return (
    <div className="flex flex-col h-screen bg-background text-foreground overflow-hidden">
      {/* ── 顶部导航栏：毛玻璃效果 ── */}
      <header
        className="relative z-[200] flex-shrink-0 border-b"
        style={{
          borderColor: 'var(--nav-border)',
          background: 'var(--nav-bg)',
          backdropFilter: 'blur(20px) saturate(180%)',
          WebkitBackdropFilter: 'blur(20px) saturate(180%)',
        }}
      >
        <div className="flex h-14 items-center px-5 gap-2">
          {/* 品牌标识 */}
          <Link href="/" className="flex items-center gap-2.5 mr-2 group">
            <div className="w-8 h-8 bg-primary text-primary-foreground rounded-[10px] flex items-center justify-center font-bold text-xs tracking-tight shadow-sm group-hover:shadow-md transition-shadow">
              SC
            </div>
            <span className="text-[15px] font-bold tracking-[-0.02em] text-foreground">
              Sensenova-Claw
            </span>
          </Link>

          {/* 分隔线 */}
          <div className="w-px h-5 bg-border/60 mx-2 hidden md:block" />

          {/* 主导航 */}
          <DashboardNav
            className="hidden md:flex mx-1"
            activeGroup={visibleGroup}
            onGroupToggle={handleGroupToggle}
          />

          {/* 右侧工具区 */}
          <div className="ml-auto flex items-center gap-1">
            <div className="hidden lg:block mr-2">
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground/60" />
                <Input
                  type="search"
                  placeholder={t('common.searchPlaceholder')}
                  className="w-52 h-8 pl-8 text-sm bg-transparent border-border/50 rounded-lg focus-visible:ring-1 focus-visible:ring-primary/30 focus-visible:border-primary/40 placeholder:text-muted-foreground/40"
                />
              </div>
            </div>
            <TodoDropdown />
            <NotificationDropdown />
            <div className="w-px h-5 bg-border/40 mx-1.5" />
            <UserDropdown />
          </div>
        </div>

        {/* ── 二级导航栏 ── */}
        <div
          className={cn(
            'overflow-hidden transition-all duration-250 ease-[cubic-bezier(0.4,0,0.2,1)]',
            subNavItems ? 'max-h-10 opacity-100' : 'max-h-0 opacity-0'
          )}
        >
          <div className="flex items-center gap-0.5 px-5 py-1.5 border-t border-border/30">
            {subNavItems?.map((item) => (
              <Link
                key={item.path}
                href={item.path}
                data-testid={'kind' in item && item.kind === 'custom' ? `feature-nav-item-${item.pageId}` : undefined}
                onClick={() => { if (pathname?.startsWith(item.path)) startNewChat(); }}
                onContextMenu={'kind' in item ? (event) => openFeatureContextMenu(event, item as FeatureNavItem) : undefined}
                className={cn(
                  'px-3 py-1 text-[13px] rounded-lg transition-all duration-150 flex items-center gap-1.5',
                  pathname?.startsWith(item.path)
                    ? 'bg-primary/10 text-primary font-semibold'
                    : 'text-muted-foreground hover:text-foreground hover:bg-[var(--nav-pill-hover)]'
                )}
              >
                {'icon' in item && <NavIcon name={(item as { icon?: string }).icon} />}
                {item.label}
              </Link>
            ))}
          </div>
        </div>
      </header>

      {/* ── 主内容区 ── */}
      <DndProvider backend={HTML5Backend}>
        {hideRightPanel ? (
          <div className="flex-1 overflow-auto bg-muted/20 p-2.5">
            <div className="h-full rounded-[var(--panel-radius)] bg-background border border-border/40 overflow-auto shadow-sm">
              {children}
            </div>
          </div>
        ) : (
          <ResizablePanelGroup
            orientation="horizontal"
            className="flex-1 p-2.5 gap-2.5 bg-muted/20"
          >
            <ResizablePanel
              id="dashboard-main"
              defaultSize="83%"
              minSize="40%"
              className="overflow-hidden"
            >
              <div className="h-full overflow-auto rounded-[var(--panel-radius)] bg-background border border-border/40 shadow-sm">
                {children}
              </div>
            </ResizablePanel>
            <ResizableHandle invisible />
            <ResizablePanel
              id="dashboard-side"
              defaultSize="17%"
              minSize="8%"
              maxSize="30%"
              className="overflow-hidden"
            >
              <GlobalFilePanel />
            </ResizablePanel>
          </ResizablePanelGroup>
        )}
      </DndProvider>
      {featureContextMenu ? (
        <ContextMenu
          x={featureContextMenu.x}
          y={featureContextMenu.y}
          onClose={() => setFeatureContextMenu(null)}
          testId="feature-context-menu"
          items={[{
            label: '删除功能',
            onClick: () => setFeatureToDelete(featureContextMenu.item),
            testId: 'feature-context-menu-delete',
          }]}
        />
      ) : null}
      <FeatureDeleteDialog
        open={!!featureToDelete}
        featureId={featureToDelete?.pageId || ''}
        featureName={featureToDelete?.label || ''}
        onOpenChange={(open) => {
          if (!open) {
            setFeatureToDelete(null);
          }
        }}
        onDeleted={() => {
          if (featureToDelete && pathname?.startsWith(`/features/${featureToDelete.pageId}`)) {
            router.replace('/create-feature');
          }
          setFeatureToDelete(null);
        }}
      />
    </div>
  );
}
