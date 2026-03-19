import { useState } from "react";
import { useNavigate, useLocation } from "react-router";
import { LayoutGrid, MessageSquare, BookOpen, Presentation, Zap, Folder, File, ChevronRight } from "lucide-react";
import { cn } from "./ui/utils";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./ui/tabs";
import { useDrag } from "react-dnd";
import { Button } from "./ui/button";

const navItems = [
  { path: "/", label: "工作台", icon: LayoutGrid },
  { path: "/chat", label: "Chat", icon: MessageSquare },
  { path: "/research", label: "深度研究", icon: BookOpen },
  { path: "/ppt", label: "PPT", icon: Presentation },
  { path: "/automation", label: "自动化", icon: Zap },
];

interface FileItemProps {
  name: string;
  type: "file" | "folder";
  path: string;
  children?: FileItemProps[];
}

const fileTree: FileItemProps[] = [
  {
    name: "项目文档",
    type: "folder",
    path: "/项目文档",
    children: [
      { name: "Q1产品路线图.pdf", type: "file", path: "/项目文档/Q1产品路线图.pdf" },
      { name: "技术架构设计.docx", type: "file", path: "/项目文档/技术架构设计.docx" },
    ],
  },
  {
    name: "数据分析",
    type: "folder",
    path: "/数据分析",
    children: [
      { name: "sales_data.xlsx", type: "file", path: "/数据分析/sales_data.xlsx" },
      { name: "用户行为报告.pdf", type: "file", path: "/数据分析/用户行为报告.pdf" },
    ],
  },
  { name: "会议记录.txt", type: "file", path: "/会议记录.txt" },
  { name: "OKR规划表.xlsx", type: "file", path: "/OKR规划表.xlsx" },
];

function DraggableFileItem({ item }: { item: FileItemProps }) {
  const [expanded, setExpanded] = useState(false);
  const [{ isDragging }, drag] = useDrag(() => ({
    type: "FILE",
    item: { name: item.name, path: item.path, type: item.type },
    collect: (monitor) => ({
      isDragging: monitor.isDragging(),
    }),
  }));

  const isFolder = item.type === "folder";

  return (
    <div>
      <div
        ref={drag}
        className={cn(
          "flex items-center gap-2 px-3 py-1.5 rounded hover:bg-gray-100 cursor-pointer text-sm",
          isDragging && "opacity-50"
        )}
        onClick={() => isFolder && setExpanded(!expanded)}
      >
        {isFolder && (
          <ChevronRight
            className={cn(
              "w-3 h-3 text-gray-500 transition-transform",
              expanded && "rotate-90"
            )}
          />
        )}
        {isFolder ? (
          <Folder className="w-4 h-4 text-blue-600" />
        ) : (
          <File className="w-4 h-4 text-gray-500" />
        )}
        <span className="text-gray-700 truncate">{item.name}</span>
      </div>
      {isFolder && expanded && item.children && (
        <div className="ml-4 mt-1 space-y-1">
          {item.children.map((child, index) => (
            <DraggableFileItem key={index} item={child} />
          ))}
        </div>
      )}
    </div>
  );
}

export function LeftNav() {
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <nav className="w-56 border-r bg-gray-50 flex flex-col">
      <Tabs defaultValue="workbench" className="flex-1 flex flex-col">
        <TabsList className="w-full grid grid-cols-2 rounded-none border-b bg-transparent p-0">
          <TabsTrigger
            value="workbench"
            className="rounded-none data-[state=active]:border-b-2 data-[state=active]:border-blue-600 data-[state=active]:bg-transparent"
          >
            工作台
          </TabsTrigger>
          <TabsTrigger
            value="files"
            className="rounded-none data-[state=active]:border-b-2 data-[state=active]:border-blue-600 data-[state=active]:bg-transparent"
          >
            文件区
          </TabsTrigger>
        </TabsList>

        <TabsContent value="workbench" className="flex-1 p-4 mt-0">
          <div className="space-y-1">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = location.pathname === item.path;

              return (
                <button
                  key={item.path}
                  onClick={() => navigate(item.path)}
                  className={cn(
                    "w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left transition-colors",
                    "hover:bg-gray-100",
                    isActive && "bg-white shadow-sm font-medium"
                  )}
                >
                  <Icon
                    className={cn("w-5 h-5", isActive ? "text-blue-600" : "text-gray-600")}
                  />
                  <span className={cn(isActive ? "text-gray-900" : "text-gray-700")}>
                    {item.label}
                  </span>
                </button>
              );
            })}
          </div>
        </TabsContent>

        <TabsContent value="files" className="flex-1 p-4 mt-0 overflow-y-auto">
          {/* 用户指定文件夹 */}
          <div className="mb-6">
            <div className="flex items-center justify-between mb-2 px-1">
              <h3 className="text-xs font-semibold text-gray-500 uppercase">我的文件</h3>
              <Button variant="ghost" size="sm" className="h-6 text-xs">
                选择文件夹
              </Button>
            </div>
            <div className="space-y-1">
              {fileTree.map((item, index) => (
                <DraggableFileItem key={index} item={item} />
              ))}
            </div>
          </div>

          {/* Agent默认文件夹 */}
          <div>
            <div className="flex items-center mb-2 px-1">
              <h3 className="text-xs font-semibold text-gray-500 uppercase">Agent工作区</h3>
            </div>
            <div className="space-y-1">
              <DraggableFileItem
                item={{
                  name: "生成的内容",
                  type: "folder",
                  path: "/agent/generated",
                  children: [
                    { name: "市场分析报告.pdf", type: "file", path: "/agent/generated/市场分析报告.pdf" },
                    { name: "竞品对比表.xlsx", type: "file", path: "/agent/generated/竞品对比表.xlsx" },
                  ],
                }}
              />
              <DraggableFileItem
                item={{
                  name: "调研资料",
                  type: "folder",
                  path: "/agent/research",
                  children: [
                    { name: "行业趋势总结.docx", type: "file", path: "/agent/research/行业趋势总结.docx" },
                    { name: "用户访谈记录.txt", type: "file", path: "/agent/research/用户访谈记录.txt" },
                  ],
                }}
              />
              <DraggableFileItem
                item={{
                  name: "任务历史",
                  type: "folder",
                  path: "/agent/history",
                  children: [
                    { name: "3月任务归档.zip", type: "file", path: "/agent/history/3月任务归档.zip" },
                  ],
                }}
              />
            </div>
          </div>
        </TabsContent>
      </Tabs>
    </nav>
  );
}