'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { cn } from '@/lib/utils';
import { Settings } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

const mainNavItems = [
  { path: '/', label: '工作台', exact: true },
  { path: '/chat', label: 'Chat' },
  { path: '/research', label: '深度研究' },
  { path: '/ppt', label: 'PPT' },
  { path: '/automation', label: '自动化' },
];

const adminNavItems = [
  { path: '/agents', label: 'Dashboard' },
  { path: '/sessions', label: 'Sessions' },
  { path: '/gateway', label: 'Gateway' },
  { path: '/tools', label: 'Tools' },
  { path: '/skills', label: 'Skills' },
];

export function DashboardNav({
  className,
  ...props
}: React.HTMLAttributes<HTMLElement>) {
  const pathname = usePathname();

  const isActive = (item: { path: string; exact?: boolean }) => {
    if (item.exact) return pathname === item.path;
    return pathname?.startsWith(item.path);
  };

  const isAdminActive = adminNavItems.some((item) =>
    pathname?.startsWith(item.path)
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
          className={cn(
            'text-sm font-medium transition-colors hover:text-primary',
            isActive(item) ? 'text-primary' : 'text-muted-foreground'
          )}
        >
          {item.label}
        </Link>
      ))}

      <DropdownMenu>
        <DropdownMenuTrigger
          className={cn(
            'text-sm font-medium transition-colors hover:text-primary flex items-center gap-1',
            isAdminActive ? 'text-primary' : 'text-muted-foreground'
          )}
        >
          <Settings className="h-3.5 w-3.5" />
          管理
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          {adminNavItems.map((item) => (
            <DropdownMenuItem key={item.path} asChild>
              <Link
                href={item.path}
                className={cn(
                  pathname?.startsWith(item.path) && 'font-medium'
                )}
              >
                {item.label}
              </Link>
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
    </nav>
  );
}
