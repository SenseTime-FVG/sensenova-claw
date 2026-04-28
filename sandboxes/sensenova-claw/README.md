# Sensenova-Claw Sandbox

事件驱动 AI Agent 平台，支持多 LLM 提供商、工具调用、多 Agent 协作。在 OpenShell 沙箱中安全运行。

## Quick Start

### 从社区仓库启动（推荐）

```sh
openshell sandbox create \
  --forward 8000 \
  --from sensenova-claw \
  -- sensenova-claw-start
```

创建后追加前端端口转发：

```sh
openshell forward start 3000 <sandbox-name>
```

### 从本地源码构建启动

```sh
# 1. 在仓库根目录构建镜像
cd /path/to/sensenova-claw
docker build -f sandboxes/sensenova-claw/Dockerfile -t sensenova-claw-sandbox:v0.5 .

# 2. 导入镜像到 OpenShell 集群（k3s）
CLUSTER=$(docker ps --format '{{.Names}}' | grep openshell-cluster)
docker save sensenova-claw-sandbox:v0.5 | docker exec -i "$CLUSTER" ctr -n k8s.io images import -

# 3. 创建沙箱（使用非 latest 标签避免远程拉取）
openshell sandbox create \
  --forward 8000 \
  --from sensenova-claw-sandbox:v0.5 \
  --policy sandboxes/sensenova-claw/policy.yaml \
  -- sensenova-claw-start

# 4. 转发前端端口
openshell forward start 3000 <sandbox-name>
```

> **注意：** `--forward` 参数只能使用一次，多端口需要用 `openshell forward start` 追加。
> 使用非 `latest` 标签（如 `v0.5`）可避免 k8s 尝试从远程 registry 拉取本地镜像。

### 启动后访问

- **Dashboard:** http://127.0.0.1:3000
- **API:** http://127.0.0.1:8000
- **Health Check:** http://127.0.0.1:8000/health

首次启动后在 Dashboard 中配置 LLM provider 和 API key。

## 常用操作

```sh
# 查看沙箱列表
openshell sandbox list

# 查看沙箱日志
openshell logs <sandbox-name> --source sandbox

# 在沙箱内执行命令
openshell sandbox exec <sandbox-name> -- curl localhost:8000/health

# 查看端口转发列表
openshell forward list

# 删除沙箱
openshell sandbox delete <sandbox-name>
```

## 挂载工作区

将宿主机项目目录上传到沙箱内供 Agent 操作：

```sh
openshell sandbox create \
  --forward 8000 \
  --from sensenova-claw-sandbox:v0.5 \
  --upload ~/my-project:/sandbox/workspace \
  -- sensenova-claw-start
```

## 端口说明

| 端口 | 服务 | 说明 |
|------|------|------|
| 3000 | Next.js Dashboard | Web 管理界面 |
| 8000 | FastAPI Backend | REST API + WebSocket |

## 功能

- 多 LLM 支持（OpenAI、Anthropic、Gemini、Qwen 等）
- 内置工具（bash 命令、文件读写、网页搜索、URL 抓取）
- 多 Agent 协作与委派
- 定时任务（Cron）
- Skills 编排系统
- 记忆系统

## 自定义策略

默认 policy 限制文件系统写入范围（`/sandbox`、`/tmp`、`~/.sensenova-claw`），如需调整：

```sh
openshell policy set <sandbox-name> --policy my-policy.yaml
```

参考 `policy.yaml` 了解策略格式。

## 相关链接

- [Sensenova-Claw 仓库](https://github.com/SenseTime-FVG/sensenova-claw)
- [OpenShell 文档](https://docs.openshell.dev)
