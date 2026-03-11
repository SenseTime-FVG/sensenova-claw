'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Bot, MessageCircle, MessageSquare, GitBranch, Wrench, Sparkles } from 'lucide-react';

export function DashboardNav() {
  const pathname = usePathname();

  const navItems = [
    { path: '/agents', icon: Bot, label: 'Agents' },
    { path: '/sessions', icon: MessageSquare, label: 'Sessions' },
    { path: '/gateway', icon: GitBranch, label: 'Gateway' },
    { path: '/tools', icon: Wrench, label: 'Tools' },
    { path: '/skills', icon: Sparkles, label: 'Skills' },
  ];

  return (
    <div className="w-12 bg-[#333333] flex flex-col items-center py-2 border-r border-[#2d2d30]">
      <div className="flex flex-col gap-4">
        {navItems.map((item) => {
          const isActive = pathname?.startsWith(item.path);
          return (
            <Link
              key={item.path}
              href={item.path}
              className={`p-2 rounded hover:bg-[#2d2d30] transition-colors ${
                isActive ? 'text-white bg-[#2d2d30]' : 'text-[#858585]'
              }`}
              title={item.label}
            >
              <item.icon size={24} />
            </Link>
          );
        })}
      </div>
      <div className="mt-auto pb-2">
        <a
          href="/chat"
          className="p-2 rounded-full bg-[#0e639c] text-white hover:bg-[#1177bb] transition-colors block"
          title="Chat"
        >
          <MessageCircle size={20} />
        </a>
      </div>
    </div>
  );
}
