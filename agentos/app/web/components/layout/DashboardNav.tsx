'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { cn } from '@/lib/utils';

export function DashboardNav({
  className,
  ...props
}: React.HTMLAttributes<HTMLElement>) {
  const pathname = usePathname();

  const navItems = [
    { path: '/agents', label: 'Dashboard' }, // Let's rename '编排中心' to Dashboard for the sleek feel
    { path: '/sessions', label: 'Sessions' },
    { path: '/gateway', label: 'Gateway' },
    { path: '/tools', label: 'Tools' },
    { path: '/cron', label: 'Cron' },
    { path: '/skills', label: 'Skills' },
    { path: '/settings', label: 'Settings' },
    { path: '/chat', label: 'Chat' },
  ];

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
