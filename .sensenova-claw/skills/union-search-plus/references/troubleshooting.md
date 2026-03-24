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

## 3. union 返回空结果

现象：执行成功但 items 为空。

排查：
- 查询词是否过窄
- 该来源是否限流

处理：
- 调整 query 表达
- 从 `preferred` 升级到 `all`

## 4. 合并后结果过少

现象：去重后结果显著变少。

排查：
- 可能是多来源返回了大量重复链接

处理：
- 属于正常现象
- 优先保证“去重后高质量证据”
