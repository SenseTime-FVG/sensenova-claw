import { WorkbenchLayout } from "../components/WorkbenchLayout";
import { Card } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { BookOpen, ExternalLink, TrendingUp, Users, DollarSign, Sparkles } from "lucide-react";

export default function ResearchPage() {
  const researchItems = [
    {
      id: 1,
      title: "2024年企业SaaS市场趋势分析",
      summary: "AI驱动的自动化工具正在重塑企业办公场景，预计未来三年市场规模将增长42%，重点关注智能协作、数据安全和个性化定制三大方向...",
      category: "市场趋势",
      icon: TrendingUp,
      date: "2024-03-18",
      sources: 5,
      highlights: ["AI自动化", "市场增长42%", "智能协作"],
      status: "latest",
    },
    {
      id: 2,
      title: "竞品功能对比：Notion vs Monday.com",
      summary: "深度对比两款主流协作工具的核心功能、定价策略和用户体验。Notion在灵活性和自定义方面表现突出，而Monday.com在项目管理和团队协作功能更加完善...",
      category: "竞品分析",
      icon: Users,
      date: "2024-03-17",
      sources: 8,
      highlights: ["功能对比", "定价策略", "用户体验"],
      status: "completed",
    },
    {
      id: 3,
      title: "用户调研报告：办公效率痛点分析",
      summary: "基于500+企业用户访谈，发现三大核心痛点：信息分散导致的查找困难(67%)、重复性任务耗时(58%)、跨部门协作效率低(52%)...",
      category: "用户研究",
      icon: Users,
      date: "2024-03-15",
      sources: 12,
      highlights: ["500+用户", "三大痛点", "数据洞察"],
      status: "completed",
    },
    {
      id: 4,
      title: "AI Agent技术发展趋势与应用场景",
      summary: "探索大语言模型在办公自动化领域的最新进展，重点关注Multi-Agent协作、工具调用能力和个性化学习三个技术方向，以及在邮件处理、文档生成、数据分析等场景的应用...",
      category: "技术趋势",
      icon: Sparkles,
      date: "2024-03-14",
      sources: 15,
      highlights: ["Multi-Agent", "工具调用", "场景应用"],
      status: "completed",
    },
    {
      id: 5,
      title: "企业级SaaS定价策略研究",
      summary: "分析Top20 SaaS产品的定价模型，发现基于用户数的订阅制仍是主流(65%)，但基于使用量的按需付费模式增长迅速(年增长38%)...",
      category: "商业模式",
      icon: DollarSign,
      date: "2024-03-12",
      sources: 6,
      highlights: ["订阅制65%", "按需付费增长", "定价模型"],
      status: "completed",
    },
  ];

  return (
    <WorkbenchLayout isCollapsed={true}>
      <main className="flex-1 overflow-y-auto p-6">
        <div className="max-w-4xl mx-auto">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h1 className="text-2xl font-semibold mb-1">深度研究</h1>
              <p className="text-sm text-gray-600">
                AI Agent 自动调研的市场洞察与竞品分析
              </p>
            </div>
            <Button className="gap-2">
              <BookOpen className="w-4 h-4" />
              新建调研任务
            </Button>
          </div>

          <div className="space-y-4">
            {researchItems.map((item) => {
              const Icon = item.icon;
              return (
                <Card
                  key={item.id}
                  className="p-5 hover:shadow-lg transition-shadow cursor-pointer group"
                >
                  <div className="flex items-start gap-4">
                    <div className="w-12 h-12 rounded-lg bg-blue-100 flex items-center justify-center shrink-0">
                      <Icon className="w-6 h-6 text-blue-600" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-2">
                        <Badge variant="outline" className="text-xs">
                          {item.category}
                        </Badge>
                        {item.status === "latest" && (
                          <Badge className="text-xs bg-green-500">最新</Badge>
                        )}
                        <span className="text-sm text-gray-500 ml-auto">
                          {item.date}
                        </span>
                      </div>

                      <h3 className="font-semibold text-lg mb-2 group-hover:text-blue-600 transition-colors">
                        {item.title}
                      </h3>

                      <p className="text-sm text-gray-600 mb-3 line-clamp-2">
                        {item.summary}
                      </p>

                      <div className="flex flex-wrap gap-2 mb-3">
                        {item.highlights.map((highlight, index) => (
                          <span
                            key={index}
                            className="px-2 py-1 bg-gray-100 text-gray-700 text-xs rounded"
                          >
                            {highlight}
                          </span>
                        ))}
                      </div>

                      <div className="flex items-center justify-between">
                        <span className="text-xs text-gray-500">
                          基于 {item.sources} 个信息源
                        </span>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="gap-1 opacity-0 group-hover:opacity-100 transition-opacity"
                        >
                          查看详情
                          <ExternalLink className="w-3 h-3" />
                        </Button>
                      </div>
                    </div>
                  </div>
                </Card>
              );
            })}
          </div>
        </div>
      </main>
    </WorkbenchLayout>
  );
}
