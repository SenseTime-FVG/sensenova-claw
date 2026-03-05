

# docs_raw 文档

** 是用户直接构造的docs，不要修改这部分内容 **

docs下的文档是模型生成的，你可以修改docs下的文档


# 文档伪代码格式
使用python格式伪代码
以下是示例
```python
from typing import Any, Literal, Optional

Json = dict[str, Any]

Role = Literal["user", "assistant", "tool", "system"]

class Message:
    role: Role
    content: str
    meta: Optional[Json]  # e.g. { toolName, toolCallId, traceId }
    ts: Optional[int]


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool):
        # 注明函数的作用
        # 注明函数可能会调用哪些外部模块的函数
        # 注意不需要写具体的实现，用文字描述主要功能
        pass
```



# 代码要求

dev阶段，你必须记录后端系统完整的日志，以便于检查错误，例如DEBUG level下，保存每次LLM调用的输入

最好能够一键启动，例如 npm run dev 能够同时启动前端和后端


# 测试

写完代码之后必须完成对应的测试

如果需要api配置可以向用户询问

如果有新增功能，需要针对性的写好e2e测试用例，确保功能被激活使用并且没有bug

对于后端，你必须要进行完整的e2e测试，即对后端的api模拟用户输入进行测试，例如输入"帮我搜索英超联赛最近3年的冠亚军分别是什么球队"，并观察完整的日志和最终结果。

对于前端，你需要编写playwright脚本，启动无头浏览器，完整模拟用户的输入，并观察每一步的结果

e2e测试需要使用真实api_key进行真实测试，如果缺少api_key，像用户发出请求



# 其他

使用中文写注释和文档

先思考再行动

遇到外部资料，先使用search/browse等工具获取相关信息再行动
