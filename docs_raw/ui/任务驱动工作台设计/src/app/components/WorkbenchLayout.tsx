import { TopBar } from "./TopBar";
import { LeftNav } from "./LeftNav";
import { RightContext } from "./RightContext";
import { BottomInput } from "./BottomInput";

interface WorkbenchLayoutProps {
  children: React.ReactNode;
  thoughtTrace?: { steps: string[] };
  sources?: { name: string; type: "file" | "web"; url?: string }[];
  parameters?: { label: string; value: string }[];
  taskProgress?: { task: string; step: number; total: number; status: "running" | "completed" }[];
  deepWorkLink?: string;
  isCollapsed?: boolean;
  onSubmit?: (message: string) => void;
}

export function WorkbenchLayout({
  children,
  thoughtTrace,
  sources,
  parameters,
  taskProgress,
  deepWorkLink,
  isCollapsed,
  onSubmit,
}: WorkbenchLayoutProps) {
  return (
    <div className="h-screen flex flex-col">
      <TopBar />
      <div className="flex-1 flex overflow-hidden">
        <LeftNav />
        <div className="flex-1 flex flex-col">
          {children}
          <BottomInput onSubmit={onSubmit} />
        </div>
        <RightContext
          thoughtTrace={thoughtTrace}
          sources={sources}
          parameters={parameters}
          taskProgress={taskProgress}
          deepWorkLink={deepWorkLink}
          isCollapsed={isCollapsed}
        />
      </div>
    </div>
  );
}