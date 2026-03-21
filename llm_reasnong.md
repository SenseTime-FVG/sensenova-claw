## Openai

官方现在控制的不是 thinking_effort 这个名字，而是 reasoning effort：

用 Responses API 时，参数写成 reasoning: { effort: "..." }。官方示例就是这样写的。支持值按模型而定，常见有 none、minimal、low、medium、high、xhigh。降低 effort 通常会更快、消耗更少 reasoning tokens。

用 Chat Completions API 时，参数名是顶层的 reasoning_effort，不是嵌套对象。

如果你说的 “opensdk” 指的是 OpenAI 官方 SDK，下面这样写就行。

1) OpenAI SDK
Node.js / TypeScript（Responses API，推荐）
import OpenAI from "openai";

const client = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY,
});

const resp = await client.responses.create({
  model: "gpt-5.4",
  input: "请分析这段代码为什么可能出现内存泄漏，并给出修复建议。",
  reasoning: {
    effort: "low",   // 可改成 none / low / medium / high 等
  },
});

console.log(resp.output_text);
Python（Responses API，推荐）
from openai import OpenAI

client = OpenAI(api_key="YOUR_API_KEY")

resp = client.responses.create(
    model="gpt-5.4",
    input="请分析这段代码为什么可能出现内存泄漏，并给出修复建议。",
    reasoning={
        "effort": "low"   # 可改成 none / low / medium / high 等
    }
)

print(resp.output_text)




## Kimi / Moonshot

Moonshot 官方文档现在暴露的是 thinking 开关，不是 reasoning_effort。文档说明这个参数默认是开启的，可用 {"type":"disabled"} 关闭；官方 GitHub 示例也直接给了 OpenAI SDK 的写法：extra_body={"thinking":{"type":"disabled"}}。我没有查到它有 low / medium / high 这种 effort 档位。

你可以把它理解成：

{
  "thinking": { "type": "enabled" }
}

或

{
  "thinking": { "type": "disabled" }
}

所以对 Kimi 来说，更像是“能不能想”，不是 “想多深”。

## GLM / 智谱

GLM 也不是 reasoning_effort，而是 thinking 对象。官方参数表写得很明确：
thinking.type 只有 enabled / disabled 两档；另外还有 thinking.clear_thinking，用来控制是否清理历史轮次里的 reasoning_content。GLM-5、GLM-4.7 默认开启 thinking，且文档专门讲了 turn-level thinking、interleaved thinking、preserved thinking。

也就是你可用：

{
  "thinking": {
    "type": "enabled",
    "clear_thinking": true
  }
}

或

{
  "thinking": {
    "type": "disabled"
  }
}

这里的重点是：

type 控制本轮开关

clear_thinking 控制是否把历史 reasoning 一起带回去

但我没查到官方有 low / medium / high 这种 effort 强度档。

## MiniMax

MiniMax 的 OpenAI 兼容接口里，我查到的重点不是 effort 开关，而是 推理内容怎么返回。官方 OpenAI 兼容文档给的是 extra_body={"reasoning_split": True}，这样 thinking 会单独出现在 reasoning_details 里；否则 native OpenAI format 下，推理内容会放进 content 里的 <think> 标签中。官方标准文本接口也把 M2.7 / M2.5 / M2.1 / M2 这些标成了 reasoning models。

也就是说 MiniMax 目前更像：

{
  "extra_body": {
    "reasoning_split": true
  }
}

而不是：

{
  "reasoning_effort": "high"
}

我在它当前 OpenAI 兼容文档里没有查到 reasoning_effort，也没有查到 enable_thinking 这类官方开关；现阶段公开文档里更明确的是 “推理输出格式”，不是 “推理强度控制”。

## Qwen / DashScope compatible-mode

Qwen 这边控制得最像“可调推理”，但参数名也不是 reasoning_effort。
阿里云百炼官方文档写的是：

enable_thinking: true/false：开关思考模式

thinking_budget: <int>：限制思考过程最多使用多少 token

而且文档明确说，enable_thinking 不是 OpenAI 标准参数；Python SDK 通过 extra_body 传，Node.js 和 curl 顶层传。

对于你这个 base URL https://dashscope.aliyuncs.com/compatible-mode/v1，如果走 Chat Completions，就可以这样理解：

{
  "enable_thinking": true,
  "thinking_budget": 50
}

如果用 OpenAI Python SDK，则是：

extra_body={
    "enable_thinking": True,
    "thinking_budget": 50
}

另外，阿里云的 Responses API 文档里我明确查到了 enable_thinking，但没有在那一页查到 thinking_budget；所以 Chat Completions 支持 budget 是明确的，Responses API 是否同样支持 budget，我这次没找到同等级别的官方说明。

## DeepSeek（你这里是直连 api.deepseek.com）

DeepSeek 官方直连 API 也不是 reasoning_effort。现在官方写法是两种：

直接选推理模型：model="deepseek-reasoner"

或在 deepseek-chat 上加：thinking: {"type":"enabled"}

而且官方文档明确说：如果用 OpenAI SDK，thinking 要放在 extra_body 里。输出字段是 reasoning_content。

示意就是：

{
  "model": "deepseek-chat",
  "thinking": { "type": "enabled" }
}

或者直接：

{
  "model": "deepseek-reasoner"
}

我没有在 DeepSeek 直连官方文档里查到 thinking_budget 或 reasoning_effort 这种强度/预算参数。
顺手补充一下：如果你不是直连 DeepSeek，而是走阿里云百炼托管的 DeepSeek，阿里云那层会额外提供 enable_thinking 和 thinking_budget。但这属于 DashScope 的封装，不是 api.deepseek.com 那套直连文档。

## Step / 阶跃星辰

Step 当前公开文档里，我查到的是：

推理模型会返回 reasoning 字段

如果你想兼容 DeepSeek 风格输出，可以设置 reasoning_format="deepseek-style"，这时可用 reasoning_content 读思考过程

API 参数表里写了 reasoning_format，没有写 enable_thinking 或 thinking_budget 这类控制项

所以它更像这样：

{
  "reasoning_format": "deepseek-style"
}

这控制的是返回字段格式，不是推理强度。
目前我没有在 Step 的官方文档里查到可公开使用的 reasoning_effort、enable_thinking 或 thinking_budget。官方更像是通过选推理模型（如 step-3.5-flash、step-3、step-r1-v-mini）来决定能力，再用 reasoning_format 决定输出兼容格式。