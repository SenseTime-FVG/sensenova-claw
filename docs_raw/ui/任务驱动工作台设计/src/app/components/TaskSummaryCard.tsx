import { Card } from "./ui/card";
import { Badge } from "./ui/badge";

interface TaskSummaryCardProps {
  title: string;
  goal: string;
  stage: string;
  status: "idle" | "running" | "completed" | "error";
}

export function TaskSummaryCard({ title, goal, stage, status }: TaskSummaryCardProps) {
  const statusConfig = {
    idle: { label: "待处理", color: "bg-gray-100 text-gray-700" },
    running: { label: "执行中", color: "bg-blue-100 text-blue-700" },
    completed: { label: "已完成", color: "bg-green-100 text-green-700" },
    error: { label: "失败", color: "bg-red-100 text-red-700" },
  };

  const currentStatus = statusConfig[status];

  return (
    <Card className="p-6 mb-6">
      <div className="flex items-start justify-between mb-3">
        <h1 className="text-2xl font-semibold">{title}</h1>
        <Badge className={currentStatus.color}>{currentStatus.label}</Badge>
      </div>
      <p className="text-gray-700 mb-2">{goal}</p>
      <p className="text-sm text-gray-500">当前阶段：{stage}</p>
    </Card>
  );
}
