'use client';

import { ReactNode, useState, useCallback, useMemo } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  DashboardNav,
  useFeatureNavItems,
  adminNavItems,
  type SubNavGroup,
} from './DashboardNav';
import { Search } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { cn } from '@/lib/utils';

interface DashboardLayoutProps {
  children: ReactNode;
}

export function DashboardLayout({ children }: DashboardLayoutProps) {
  const pathname = usePathname();
  const [manualGroup, setManualGroup] = useState<SubNavGroup>(null);
  const featureNavItems = useFeatureNavItems();

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
