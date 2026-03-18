'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { cn } from '@/lib/utils';
import { Bot, MessageSquare, GitBranch, Wrench, Sparkles, MessageCircle } from 'lucide-react';

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
    { path: '/skills', label: 'Skills' },
    { path: '/settings', label: 'Settings' },
    { path: '/chat', label: 'Chat' },
  ];

  return (
    <nav
      className={cn("flex items-center space-x-4 lg:space-x-6", className)}
      {...props}
    >
      {navItems.map((item) => {
        const isActive = pathname?.startsWith(item.path);
        return (
          <Link
            key={item.path}
            href={item.path}
            className={cn(
              "text-sm font-medium transition-colors hover:text-primary",
              isActive ? "text-primary" : "text-muted-foreground"
            )}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
