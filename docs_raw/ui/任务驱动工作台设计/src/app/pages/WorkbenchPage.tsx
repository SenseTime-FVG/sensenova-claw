import { useState } from "react";
import { WorkbenchLayout } from "../components/WorkbenchLayout";
import { MainStage } from "../components/MainStage";

type TaskState = "empty" | "running" | "pending_approval" | "completed";

export default function WorkbenchPage() {
  const [state, setState] = useState<TaskState>("empty");
  const [currentTask, setCurrentTask] = useState<string>("");

  const handleSubmit = (message: string) => {
    setCurrentTask(message);
    setState("running");

    // 模拟任务执行
    setTimeout(() => {
      setState("pending_approval");
    }, 3000);
  };

  const handleFileDrop = (files: { name: string; type: string }[]) => {
    console.log("Files dropped:", files);
  };

  // 默认显示示例数据
  const thoughtTrace = {
    steps: [
      "分析用户需求",
      "检索相关文档",
      "生成初步方案",
      "验证可行性",
      "准备执行计划",
    ],
  };

  const sources = [
    { name: "产品路线图文档", type: "file" as const },
    { name: "张经理邮件", type: "file" as const },
    { name: "会议记录", type: "file" as const },
    { name: "sales_data.xlsx", type: "file" as const },
    { name: "市场调研报告", type: "web" as const, url: "https://example.com/research" },
  ];

  const parameters = [
    { label: "目标受众", value: "企业客户" },
    { label: "时间范围", value: "Q2 2024" },
    { label: "优先级", value: "高" },
  ];

  const taskProgress = [
    { task: "数据收集与分析", step: 4, total: 4, status: "completed" as const },
    { task: "方案生成", step: 2, total: 3, status: "running" as const },
    { task: "风险评估", step: 0, total: 2, status: "running" as const },
    { task: "结果输出", step: 0, total: 1, status: "running" as const },
  ];

  return (
    <WorkbenchLayout
      thoughtTrace={thoughtTrace}
      sources={sources}
      parameters={parameters}
      taskProgress={taskProgress}
      deepWorkLink="https://example.com/workflow/123"
      onSubmit={handleSubmit}
      isCollapsed={false}
    >
      <MainStage currentTask={currentTask} state={state} onFileDrop={handleFileDrop} />
    </WorkbenchLayout>
  );
}