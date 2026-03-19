# 安全策略

> 路径：`agentos/platform/security/`

AgentOS 的安全模块提供 Token 认证、系统路径保护等能力。

---

## 文件系统访问

文件操作工具（`read_file`、`write_file`、`bash_command`）不设置路径限制：

- `read_file` / `write_file`：相对路径基于 Agent 工作目录（`_agent_workdir`）解析，绝对路径直接使用
- `bash_command`：`working_dir` 参数指定工作目录，默认使用 Agent 工作目录

**路径解析规则**：

- 相对路径自动解析为 Agent 工作目录下的路径
- 绝对路径直接使用，不做区域限制
- `..` 路径遍历通过 `Path.resolve()` 标准化

---

## Token 认证

AgentOS 采用 Jupyter-lab 风格的 Token 认证：

- 每次启动生成新 token
- HTTP 请求通过 `Authorization: Bearer <token>` 或 URL 参数 `?token=<token>` 认证
- WebSocket 连接通过首条消息携带 token 认证
- 健康检查、认证相关端点在白名单中免认证

---

## 配置

在 `config.yml` 中配置安全相关选项：

```yaml
security:
  auth_enabled: true  # 是否启用 Token 认证
```

**注意事项**：

- 配置变更后需要重启服务才能生效
