import { WorkbenchLayout } from "../components/WorkbenchLayout";
import { Card } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Zap, Play, Pause } from "lucide-react";

export default function AutomationPage() {
  const automations = [
    {
      id: 1,
      name: "自动整理每日邮件摘要",
      description: "每天早上9点自动生成昨日邮件摘要",
      status: "active",
      lastRun: "今天 09:00",
      frequency: "每日",
    },
    {
      id: 2,
      name: "周报自动生成",
      description: "每周五下午生成本周工作总结",
      status: "active",
      lastRun: "3月14日",
      frequency: "每周",
    },
    {
      id: 3,
      name: "重要邮件提醒",
      description: "检测到重要邮件时立即推送通知",
      status: "paused",
      lastRun: "3月15日",
      frequency: "实时",
    },
  ];

  return (
    <WorkbenchLayout isCollapsed={true}>
      <main className="flex-1 overflow-y-auto p-6">
        <div className="max-w-4xl mx-auto">
          <div className="flex items-center justify-between mb-6">
            <h1 className="text-2xl font-semibold">自动化</h1>
            <Button className="gap-2">
              <Zap className="w-4 h-4" />
              创建新自动化
            </Button>
          </div>

          <div className="space-y-3">
            {automations.map((automation) => (
              <Card
                key={automation.id}
                className="p-5 hover:shadow-md transition-shadow"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      <Zap className="w-5 h-5 text-blue-600" />
                      <h3 className="font-medium">{automation.name}</h3>
                      <Badge
                        variant={automation.status === "active" ? "default" : "secondary"}
                        className="text-xs"
                      >
                        {automation.status === "active" ? "运行中" : "已暂停"}
                      </Badge>
                    </div>
                    <p className="text-sm text-gray-600 mb-3 ml-8">
                      {automation.description}
                    </p>
                    <div className="flex items-center gap-4 text-sm text-gray-500 ml-8">
                      <span>频率: {automation.frequency}</span>
                      <span>•</span>
                      <span>上次运行: {automation.lastRun}</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {automation.status === "active" ? (
                      <Button variant="outline" size="sm" className="gap-2">
                        <Pause className="w-4 h-4" />
                        暂停
                      </Button>
                    ) : (
                      <Button variant="outline" size="sm" className="gap-2">
                        <Play className="w-4 h-4" />
                        启动
                      </Button>
                    )}
                    <Button variant="ghost" size="sm">
                      编辑
                    </Button>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        </div>
      </main>
    </WorkbenchLayout>
  );
}