'use client';

import { ReactNode, useEffect, useState, useCallback, useMemo } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  DashboardNav,
  useFeatureNavItems,
  adminNavItems,
  type SubNavGroup,
} from './DashboardNav';
import { Search, Bell } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { cn } from '@/lib/utils';
import { useChatSession } from '@/contexts/ChatSessionContext';
import { authFetch, API_BASE } from '@/lib/authFetch';

function GlobalReminderBell() {
  const [todayCount, setTodayCount] = useState(0);

  useEffect(() => {
    authFetch(`${API_BASE}/api/cron/runs?limit=100`)
      .then(r => r.json())
      .then(data => {
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        const todayMs = today.getTime();
        const runs = (data.runs || []) as { started_at_ms: number }[];
        setTodayCount(runs.filter(r => r.started_at_ms >= todayMs).length);
      })
      .catch(() => {});
  }, []);

  return (
    <Link
      href="/automation"
      className="relative p-1.5 rounded-lg hover:bg-muted transition-colors"
      title={`今日 ${todayCount} 条提醒`}
    >
      <Bell className="w-5 h-5 text-muted-foreground" />
      {todayCount > 0 && (
        <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-[16px] rounded-full bg-primary text-primary-foreground text-[10px] font-bold flex items-center justify-center px-0.5">
          {todayCount > 99 ? '99+' : todayCount}
        </span>
      )}
    </Link>
  );
}

interface DashboardLayoutProps {
  children: ReactNode;
}

export function DashboardLayout({ children }: DashboardLayoutProps) {
  const pathname = usePathname();
  const [manualGroup, setManualGroup] = useState<SubNavGroup>(null);
  const featureNavItems = useFeatureNavItems();
  const { startNewChat } = useChatSession();

  const isFeatureActive = featureNavItems.some((item) =>
    pathname?.startsWith(item.path)
  );
  const isAdminActive = adminNavItems.some((item) =>
    pathname?.startsWith(item.path)
  );

  const visibleGroup: SubNavGroup = useMemo(() => {
    if (manualGroup) return manualGroup;
    if (isFeatureActive) return 'features';
    if (isAdminActive) return 'admin';
    return null;
  }, [manualGroup, isFeatureActive, isAdminActive]);

  const handleGroupToggle = useCallback((group: SubNavGroup) => {
    setManualGroup(group);
  }, []);

  const subNavItems =
    visibleGroup === 'features'
      ? featureNavItems
      : visibleGroup === 'admin'
        ? adminNavItems
        : null;

  return (
    <div className="flex flex-col h-screen bg-background text-foreground overflow-hidden">
      <div className="border-b border-border flex-shrink-0">
        <div className="flex h-16 items-center px-4">
          <div className="flex items-center gap-2 mr-4">
            <div className="w-8 h-8 bg-primary text-primary-foreground rounded-lg flex items-center justify-center font-bold">
              AO
            </div>
            <span className="text-lg font-bold tracking-tight">AgentOS</span>
          </div>
          
          <DashboardNav
            className="hidden md:flex mx-6"
            activeGroup={visibleGroup}
            onGroupToggle={handleGroupToggle}
          />
          
          <div className="ml-auto flex items-center space-x-4">
            <div className="hidden lg:block">
              <div className="relative">
                <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  type="search"
                  placeholder="Search..."
                  className="w-64 pl-8 bg-muted/50 focus-visible:ring-1"
                />
              </div>
            </div>
            <GlobalReminderBell />
            <Avatar className="h-8 w-8 cursor-pointer">
              <AvatarImage src="https://github.com/shadcn.png" alt="@shadcn" />
              <AvatarFallback>AO</AvatarFallback>
            </Avatar>
          </div>
        </div>

        <div
          className={cn(
            'overflow-hidden transition-all duration-200 ease-in-out',
            subNavItems ? 'max-h-12 opacity-100' : 'max-h-0 opacity-0'
          )}
        >
          <div className="flex items-center space-x-1 px-4 py-2 bg-muted/30 border-t border-border/50">
            {subNavItems?.map((item) => (
              <Link
                key={item.path}
                href={item.path}
                onClick={() => { if (pathname?.startsWith(item.path)) startNewChat(); }}
                className={cn(
                  'px-3 py-1.5 text-sm rounded-md transition-colors',
                  pathname?.startsWith(item.path)
                    ? 'bg-primary/10 text-primary font-medium'
                    : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'
                )}
              >
                {item.label}
              </Link>
            ))}
          </div>
        </div>
      </div>
      <div className="flex-1 overflow-auto bg-muted/10">
        {children}
      </div>
    </div>
  );
}
