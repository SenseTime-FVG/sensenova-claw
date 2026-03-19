import { useState } from "react";
import { WorkbenchLayout } from "../components/WorkbenchLayout";
import { Badge } from "../components/ui/badge";
import { Input } from "../components/ui/input";
import { Search, CheckCheck } from "lucide-react";
import { cn } from "../components/ui/utils";

interface Conversation {
  id: number;
  name: string;
  avatar: string;
  isBot: boolean;
  lastMessage: string;
  time: string;
  unread?: boolean;
}

export default function ChatPage() {
  const [selectedConversation, setSelectedConversation] = useState<number | null>(null);

  const conversations: Conversation[] = [
    {
      id: 1,
      name: "市场分析助手",
      avatar: "📊",
      isBot: true,
      lastMessage: "已完成Q2市场趋势分析，发现三个关键增长点...",
      time: "3月16日",
      unread: true,
    },
    {
      id: 2,
      name: "数据助手",
      avatar: "📈",
      isBot: true,
      lastMessage: "销售数据已更新，本周环比增长12%",
      time: "3月15日",
      unread: true,
    },
    {
      id: 3,
      name: "文档生成器",
      avatar: "📝",
      isBot: true,
      lastMessage: "产品需求文档已生成，请查收并反馈意见...",
      time: "3月14日",
      unread: false,
    },
    {
      id: 4,
      name: "日程助理",
      avatar: "📅",
      isBot: true,
      lastMessage: "明天有3个会议安排，已为您准备会议资料",
      time: "3月13日",
      unread: false,
    },
    {
      id: 5,
      name: "智能摘要",
      avatar: "💡",
      isBot: true,
      lastMessage: "会议纪要已生成：讨论了产品路线图和技术方案...",
      time: "3月12日",
      unread: false,
    },
    {
      id: 6,
      name: "研发协作",
      avatar: "👥",
      isBot: false,
      lastMessage: "技术评审文档已分享给你",
      time: "3月11日",
      unread: false,
    },
    {
      id: 7,
      name: "产品团队",
      avatar: "🎯",
      isBot: false,
      lastMessage: "需求文档已更新，请查看最新版本",
      time: "3月10日",
      unread: false,
    },
    {
      id: 8,
      name: "设计协作",
      avatar: "🎨",
      isBot: false,
      lastMessage: "UI设计稿已上传，请审阅",
      time: "3月9日",
      unread: false,
    },
    {
      id: 9,
      name: "运营数据",
      avatar: "📊",
      isBot: false,
      lastMessage: "用户增长报告已生成",
      time: "3月8日",
      unread: false,
    },
    {
      id: 10,
      name: "任务管理助手",
      avatar: "✅",
      isBot: true,
      lastMessage: "你好！我是任务管理助手，可以帮你追踪项目进度和待办事项",
      time: "3月7日",
      unread: false,
    },
  ];

  return (
    <WorkbenchLayout isCollapsed={true}>
      <div className="flex flex-1 h-full overflow-hidden">
        {/* 左侧对话列表 */}
        <div className="w-96 border-r bg-white flex flex-col">
          {/* 搜索栏 */}
          <div className="p-3 border-b">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <Input
                placeholder="搜索对话"
                className="pl-9 bg-gray-50 border-0"
              />
            </div>
          </div>

          {/* 对话列表 */}
          <div className="flex-1 overflow-y-auto">
            {conversations.map((conv) => (
              <div
                key={conv.id}
                onClick={() => setSelectedConversation(conv.id)}
                className={cn(
                  "px-4 py-3 cursor-pointer hover:bg-gray-50 transition-colors border-b border-gray-100",
                  selectedConversation === conv.id && "bg-blue-50 hover:bg-blue-50"
                )}
              >
                <div className="flex items-start gap-3">
                  {/* 头像 */}
                  <div className="w-10 h-10 rounded flex items-center justify-center bg-gray-100 shrink-0 text-lg">
                    {conv.avatar}
                  </div>

                  {/* 内容 */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-sm text-gray-900">
                          {conv.name}
                        </span>
                        {conv.isBot && (
                          <Badge variant="secondary" className="text-xs px-1.5 py-0 h-5">
                            Agent
                          </Badge>
                        )}
                      </div>
                      <span className="text-xs text-gray-500 shrink-0 ml-2">
                        {conv.time}
                      </span>
                    </div>
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-sm text-gray-600 line-clamp-1 flex-1">
                        {conv.lastMessage}
                      </p>
                      {conv.unread && (
                        <div className="w-2 h-2 rounded-full bg-red-500 shrink-0 mt-1.5"></div>
                      )}
                      {selectedConversation === conv.id && !conv.unread && (
                        <CheckCheck className="w-4 h-4 text-blue-600 shrink-0 mt-0.5" />
                      )}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 右侧对话内容区 */}
        <div className="flex-1 flex items-center justify-center bg-gray-50">
          {selectedConversation ? (
            <div className="text-center">
              <div className="text-6xl mb-4">💬</div>
              <p className="text-gray-600">对话内容将在这里显示</p>
            </div>
          ) : (
            <div className="text-center">
              <div className="text-6xl mb-4">🤖</div>
              <p className="text-gray-600">选择一个对话开始聊天</p>
            </div>
          )}
        </div>
      </div>
    </WorkbenchLayout>
  );
}
