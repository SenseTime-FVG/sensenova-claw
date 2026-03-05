'use client';

import { ChatContainer } from '@/components/chat/ChatContainer';
import { ActivityBar } from '@/components/layout/ActivityBar';
import { Sidebar } from '@/components/layout/Sidebar';
import { StatusBar } from '@/components/layout/StatusBar';
import { TitleBar } from '@/components/layout/TitleBar';
import { SessionProvider } from '@/contexts/SessionContext';
import { UIProvider } from '@/contexts/UIContext';
import { WebSocketProvider } from '@/contexts/WebSocketContext';

export default function Page() {
  return (
    <WebSocketProvider>
      <UIProvider>
        <SessionProvider>
          <div className="main-layout">
            <TitleBar />
            <div className="body-layout">
              <ActivityBar />
              <Sidebar />
              <ChatContainer />
            </div>
            <StatusBar />
          </div>
        </SessionProvider>
      </UIProvider>
    </WebSocketProvider>
  );
}
