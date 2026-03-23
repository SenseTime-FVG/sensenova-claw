import './globals.css';
import type { Metadata } from 'next';
import { DM_Sans } from "next/font/google";
import { NotificationProvider } from '@/components/notification/NotificationProvider';
import { ThemeProvider } from "@/components/ThemeProvider";
import { AuthProvider } from '@/contexts/AuthContext';
import { ChatSessionProvider } from '@/contexts/ChatSessionContext';
import { FilePanelProvider } from '@/contexts/FilePanelContext';
import { UserPreferencesProvider } from '@/contexts/UserPreferencesContext';
import ProtectedRoute from '@/components/ProtectedRoute';
import { cn } from "@/lib/utils";

const dmSans = DM_Sans({subsets:['latin'],variable:'--font-sans', weight:['400','500','600','700']});

export const metadata: Metadata = {
  title: 'AgentOS',
  description: '事件驱动 AI Agent 平台',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" className={cn("font-sans antialiased", dmSans.variable)} suppressHydrationWarning>
      <body>
        <ThemeProvider
            attribute="class"
            defaultTheme="system"
            enableSystem
            disableTransitionOnChange
          >
          <NotificationProvider>
            <AuthProvider>
              <ChatSessionProvider>
                <FilePanelProvider>
                  <UserPreferencesProvider>
                    <ProtectedRoute>
                      {children}
                    </ProtectedRoute>
                  </UserPreferencesProvider>
                </FilePanelProvider>
              </ChatSessionProvider>
            </AuthProvider>
          </NotificationProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
