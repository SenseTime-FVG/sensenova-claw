# 故障排查

## 1. `bash_command` 未执行

现象：补充分支没有运行。

排查：
- 是否被用户拒绝审批
- 是否超时

处理：
- 继续使用主链结果完成回答
- 在结果中说明补充分支未执行

## 2. vendor 脚本路径不存在

现象：`vendor path not found`。

排查：
- 检查目录：`.sensenova-claw/skills/union-search-plus/vendor/union-search-skill`

处理：
- 重新同步 vendor 目录

## 3. `doctor` 提示缺依赖或找不到 `.env`

现象：
- `python-dotenv is missing`
- `env file not found`

排查：
- 先运行 `union_search_cli.py doctor --env-file .env`
- 确认 `.env` 路径是相对于当前执行目录，而不是 skill vendor 目录
- 确认基础依赖已安装

处理：
- 安装 `scripts/requirements.txt` 中的基础依赖
- 显式传 `--env-file /绝对路径/.env`，避免相对路径歧义

## 4. union 返回空结果

现象：执行成功但 items 为空。

排查：
- 查询词是否过窄
- 该来源是否限流

处理：
- 调整 query 表达
- 从 `preferred` 升级到 `all`

## 5. vendor 命令超时

现象：返回 `vendor command timeout`。

排查：
- 是否首次就跑了 `dev/social/all`
- 是否命中了网络受限平台（如 Reddit、部分社媒）
- 当前网络是否可访问目标站点

处理：
- 先切回单平台烟测，如 `--platforms github`
- 减少 group 覆盖面或适当提高 `--timeout`
- 保留已成功平台结果，并在总结中说明超时平台

## 6. 合并后结果过少

现象：去重后结果显著变少。

排查：
- 可能是多来源返回了大量重复链接

处理：
- 属于正常现象
- 优先保证“去重后高质量证据”
