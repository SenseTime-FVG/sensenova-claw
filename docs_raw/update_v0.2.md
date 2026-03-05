# v0.2版本

## 前端页面美化

1. 调色优化
2. 对话部分缺少滑块，message增多会导致页面变得超长
3. 现在整个页面和我提供的模板差别太大了，模板路径 docs_raw/ui/index.html
4. 工具完成的消息直接替换掉对于的工具正在执行中的消息
5. 工具返回的结果也要显示在前端中，对于超长内容使用collapse按钮来开关，对于json内容，使用json_viewer来展示
6. 字体统一使用  中文: Microsoft Yahei，英文：Segoe UI

## tool超长截断逻辑

如果tool返回的内容超过16000个token
1. 把全文内容保存成一个文件，放在workspace对于的session目录下
2. 把返回内容阶段截断到16000个token， 并结尾加上 "\n工具内容超长，以上是截断内容，全文内容保存在<file_path>"


## bug fix
修复历史消息不拼接
修复前端重复消息