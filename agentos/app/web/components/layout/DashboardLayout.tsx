'use client';

import { ReactNode } from 'react';
import { Search } from 'lucide-react';
import { DashboardNav } from './DashboardNav';
import { Input } from '@/components/ui/input';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';

interface DashboardLayoutProps {
  children: ReactNode;
}

export function DashboardLayout({ children }: DashboardLayoutProps) {
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

          <DashboardNav className="hidden md:flex mx-6" />

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
      </div>
      <div className="flex-1 overflow-auto bg-muted/10">
        {children}
      </div>
    </div>
  );
}
