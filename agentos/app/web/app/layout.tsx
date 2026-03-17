import './globals.css';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'AgentOS',
  description: '事件驱动 AI Agent 平台',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
