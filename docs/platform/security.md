# 安全策略 PathPolicy

> 路径：`agentos/platform/security/`

PathPolicy 是 AgentOS 的文件系统安全模块，通过三区域模型控制 Agent 对文件系统的读写权限。

---

## 设计概览

```python
class PathPolicy:
    workspace: Path              # 绿色区域（始终允许）
    _granted: list[Path]         # 黄色区域（预授权）

    classify(target: Path) -> PathZone  # GREEN, YELLOW, RED
    check_read(file_path) -> PathVerdict   # ALLOW, DENY, NEED_GRANT
    check_write(file_path) -> PathVerdict
    grant(dir_path) -> Path      # 添加到黄色区域
    revoke(dir_path)             # 从黄色区域移除
```

---

## 三区域模型

PathPolicy 将文件系统划分为三个区域，每个区域有不同的访问权限：

| 区域 | 颜色 | 权限 | 说明 |
|------|------|------|------|
| GREEN | 绿色 | 始终允许读写 | `workspace` 目录及其子目录 |
| YELLOW | 黄色 | 预授权允许读写 | `config.yml` 中 `granted_paths` 配置的目录 |
| RED | 红色 | 拒绝访问 | 其他所有路径 |

**分类逻辑**：

```python
def classify(target: Path) -> PathZone:
    if target 在 workspace 目录下:
        return PathZone.GREEN
    if target 在任一 granted 目录下:
        return PathZone.YELLOW
    return PathZone.RED
```

---

## 权限检查

### check_read / check_write

返回值类型 `PathVerdict`：

| 值 | 含义 |
|----|------|
| `ALLOW` | 允许操作 |
| `DENY` | 拒绝操作 |
| `NEED_GRANT` | 需要用户授权（当前未实现交互式授权） |

### 系统路径保护

`is_system_path()` 检测系统关键路径，这些路径**始终被阻止**访问，无论配置如何：

- `/etc/`、`/usr/`、`/bin/`、`/sbin/` 等系统目录
- `/proc/`、`/sys/` 等虚拟文件系统

---

## 在工具中的应用

PathPolicy 在文件操作工具执行前进行权限检查：

```python
# read_file 工具
async def read_file(file_path: str):
    verdict = path_policy.check_read(file_path)
    if verdict != PathVerdict.ALLOW:
        return f"拒绝访问: {file_path}"
    # 执行读取...

# write_file 工具
async def write_file(file_path: str, content: str):
    verdict = path_policy.check_write(file_path)
    if verdict != PathVerdict.ALLOW:
        return f"拒绝访问: {file_path}"
    # 执行写入...
```

**路径解析规则**：

- 相对路径自动解析为 `workspace` 下的相对路径
- 符号链接会被解析为实际路径后再进行区域分类
- `..` 路径遍历会被正确处理，防止跳出授权区域

---

## 动态授权

支持运行时动态管理黄色区域：

```python
# 添加授权目录
path_policy.grant(Path("/home/user/data"))

# 撤销授权
path_policy.revoke(Path("/home/user/data"))
```

---

## 配置

在 `config.yml` 中预配置授权路径：

```yaml
system:
  granted_paths:
    - /home/user/projects
    - /tmp/workspace
```

**注意事项**：

- `workspace` 目录默认为项目根目录下的 `workspace/` 文件夹
- PathPolicy 实例需要支持 JSON 序列化，以便在工具执行时传递上下文
- 配置变更后需要重启服务才能生效
