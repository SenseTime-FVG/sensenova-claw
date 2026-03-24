# 安全策略

> 路径：`sensenova_claw/platform/security/`

Sensenova-Claw 的安全模块提供 Token 认证、系统路径保护等能力。

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

Sensenova-Claw 采用 Jupyter-lab 风格的 Token 认证：

- 首次启动生成随机 token，持久化到 `~/.sensenova-claw/token` 文件
- 后续重启自动复用已有 token，无需重新登录
- HTTP 请求通过 `Authorization: Bearer <token>` 或 URL 参数 `?token=<token>` 认证
- WebSocket 连接通过 URL 参数 `?token=<token>` 认证
- 健康检查、认证相关端点在白名单中免认证

---

## Secret Store（API Key 安全存储）

Sensenova-Claw 通过 Setup 页面保存 API Key 时，优先使用 **keyring** 安全存储，config.yml 中只写入引用（如 `secret:sensenova_claw/llm.providers.openai.api_key`），密钥本身不出现在配置文件中。

如果 keyring 不可用或调用失败，会自动回退到本地文件 `~/.sensenova-claw/data/secret/secret.yml`，不会把密钥明文写回 `config.yml`。

### 启用 keyring

**Linux 服务器（无桌面环境，推荐）：**

```bash
pip install keyrings.alt
```

安装后 secret 存储在 `~/.local/share/python_keyring/` 下的加密文件中。

**Linux 桌面环境：**

```bash
# GNOME
sudo apt install gnome-keyring libsecret-1-dev
pip install secretstorage

# KDE
sudo apt install kwalletmanager
```

**验证 keyring 是否可用：**

```bash
python3 -c "
import keyring
keyring.set_password('test', 'key', 'value')
print(keyring.get_password('test', 'key'))  # 输出 value 表示可用
keyring.delete_password('test', 'key')
"
```

安装后重启 Sensenova-Claw，新保存的 API Key 会自动使用 keyring 存储。

---

## 配置

在 `config.yml` 中配置安全相关选项：

```yaml
security:
  auth_enabled: true  # 是否启用 Token 认证
```

**注意事项**：

- 配置变更后需要重启服务才能生效
