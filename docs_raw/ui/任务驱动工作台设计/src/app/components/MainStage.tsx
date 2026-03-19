import { TaskSummaryCard } from "./TaskSummaryCard";
import { ResultCard } from "./ResultCard";
import { Card } from "./ui/card";
import { Button } from "./ui/button";
import { Sparkles, Clock, CheckCircle2 } from "lucide-react";
import { useDrop } from "react-dnd";

interface Task {
  id: string;
  title: string;
  goal: string;
  stage: string;
  status: "idle" | "running" | "completed" | "error";
}

interface MainStageProps {
  currentTask?: Task;
  state: "empty" | "processing" | "completed" | "approval";
  onFileDrop?: (file: { name: string; path: string; type: string }) => void;
}

export function MainStage({ currentTask, state, onFileDrop }: MainStageProps) {
  const [{ isOver }, drop] = useDrop(() => ({
    accept: "FILE",
    drop: (item: { name: string; path: string; type: string }) => {
      onFileDrop?.(item);
    },
    collect: (monitor) => ({
      isOver: monitor.isOver(),
    }),
  }));

  // 空状态
  if (state === "empty") {
    return (
      <main
        ref={drop}
        className={`flex-1 overflow-y-auto p-6 ${isOver ? "bg-blue-50" : ""}`}
      >
        <div className="max-w-4xl mx-auto">
          <div className="text-center py-12">
            <Sparkles className="w-12 h-12 text-blue-600 mx-auto mb-4" />
            <h2 className="text-xl font-semibold mb-2">开始新任务</h2>
            <p className="text-gray-600 mb-8">
              使用下方快捷动作快速开始，或描述你需要完成的任务
            </p>
          </div>

          {/* 高频任务模板 */}
          <div className="grid grid-cols-2 gap-4 mb-8">
            <Card className="p-4 hover:shadow-md transition-shadow cursor-pointer">
              <h3 className="font-semibold mb-2">回复重要邮件</h3>
              <p className="text-sm text-gray-600">自动分析收件箱，起草专业回复</p>
            </Card>
            <Card className="p-4 hover:shadow-md transition-shadow cursor-pointer">
              <h3 className="font-semibold mb-2">准备周会议题</h3>
              <p className="text-sm text-gray-600">基于本周日历和任务，生成议程</p>
            </Card>
            <Card className="p-4 hover:shadow-md transition-shadow cursor-pointer">
              <h3 className="font-semibold mb-2">总结项目进展</h3>
              <p className="text-sm text-gray-600">汇总文档和对话，生成周报草稿</p>
            </Card>
            <Card className="p-4 hover:shadow-md transition-shadow cursor-pointer">
              <h3 className="font-semibold mb-2">安排团队会议</h3>
              <p className="text-sm text-gray-600">检查成员日历，推荐最佳时间</p>
            </Card>
          </div>

          {/* 最近任务 */}
          <div>
            <h3 className="font-semibold mb-3">最近任务</h3>
            <div className="space-y-2">
              {["回复产品设计反馈邮件", "总结上周OKR进展", "安排季度复盘会议"].map(
                (task, index) => (
                  <Card
                    key={index}
                    className="p-3 flex items-center justify-between hover:shadow-sm transition-shadow cursor-pointer"
                  >
                    <div className="flex items-center gap-3">
                      <CheckCircle2 className="w-4 h-4 text-green-600" />
                      <span className="text-sm">{task}</span>
                    </div>
                    <span className="text-xs text-gray-500">2天前</span>
                  </Card>
                )
              )}
            </div>
          </div>
        </div>
      </main>
    );
  }

  // 执行中状态
  if (state === "processing" && currentTask) {
    return (
      <main className="flex-1 overflow-y-auto p-6">
        <div className="max-w-4xl mx-auto">
          <TaskSummaryCard
            title={currentTask.title}
            goal={currentTask.goal}
            stage={currentTask.stage}
            status={currentTask.status}
          />

          <Card className="p-6">
            <div className="flex items-center gap-3 mb-4">
              <Clock className="w-5 h-5 text-blue-600 animate-spin" />
              <h2 className="font-semibold">正在执行</h2>
            </div>
            <div className="space-y-3">
              <div className="flex items-center gap-3">
                <CheckCircle2 className="w-4 h-4 text-green-600" />
                <span className="text-sm text-gray-700">正在读取收件箱邮件</span>
              </div>
              <div className="flex items-center gap-3">
                <div className="w-4 h-4 rounded-full border-2 border-blue-600 border-t-transparent animate-spin"></div>
                <span className="text-sm text-gray-700">正在分析邮件内容和上下文</span>
              </div>
              <div className="flex items-center gap-3">
                <div className="w-4 h-4 rounded-full border-2 border-gray-300"></div>
                <span className="text-sm text-gray-400">准备起草回复邮件</span>
              </div>
            </div>
          </Card>
        </div>
      </main>
    );
  }

  // 已完成状态
  if (state === "completed" && currentTask) {
    return (
      <main className="flex-1 overflow-y-auto p-6">
        <div className="max-w-4xl mx-auto">
          <TaskSummaryCard
            title={currentTask.title}
            goal={currentTask.goal}
            stage={currentTask.stage}
            status={currentTask.status}
          />

          <ResultCard
            summary="已为您起草专业回复邮件，基于原邮件的三个关键问题进行了详细回应，并确认了下一步行动计划。"
            preview={
              <div className="space-y-3">
                <div>
                  <p className="text-sm text-gray-500 mb-1">收件人：张经理</p>
                  <p className="text-sm text-gray-500 mb-3">主题：Re: 关于Q1产品路线图的反馈</p>
                </div>
                <div className="text-sm leading-relaxed">
                  <p className="mb-3">张经理，您好！</p>
                  <p className="mb-3">
                    感谢您对Q1产品路线图的详细反馈。针对您提出的三个关键问题，我回复如下：
                  </p>
                  <p className="mb-2">1. 关于新功能优先级调整...</p>
                  <p className="mb-2">2. 关于资源配置问题...</p>
                  <p className="mb-3">3. 关于时间节点安排...</p>
                  <p>期待您的进一步指导。</p>
                </div>
              </div>
            }
            sources={[
              "收件箱 - 张经理的邮件 (2026年3月17日)",
              "文档 - Q1产品路线图v2.3",
              "日历 - 产品评审会议记录",
            ]}
            nextActions={[
              { label: "发送邮件", primary: true },
              { label: "继续修改" },
            ]}
          />
        </div>
      </main>
    );
  }

  // 待审批状态
  if (state === "approval" && currentTask) {
    return (
      <main className="flex-1 overflow-y-auto p-6">
        <div className="max-w-4xl mx-auto">
          <TaskSummaryCard
            title={currentTask.title}
            goal={currentTask.goal}
            stage={currentTask.stage}
            status="running"
          />

          <Card className="p-6 border-orange-200 bg-orange-50">
            <h2 className="font-semibold mb-4 text-orange-900">等待您的审批</h2>
            <p className="text-sm text-orange-800 mb-4">
              以下操作将修改外部数据，请确认后继续：
            </p>
            <div className="bg-white rounded-lg p-4 mb-4">
              <h3 className="font-medium mb-2">即将执行的操作</h3>
              <ul className="space-y-2 text-sm">
                <li className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-green-600" />
                  发送邮件给张经理
                </li>
                <li className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-green-600" />
                  将邮件标记为已回复
                </li>
              </ul>
            </div>
            <div className="flex gap-3">
              <Button size="lg">批准并执行</Button>
              <Button variant="outline" size="lg">
                取消
              </Button>
            </div>
          </Card>
        </div>
      </main>
    );
  }

  return null;
}