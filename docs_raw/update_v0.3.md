todolist:

## 新建gateway/channel能力

允许从多个不同的channel来访问agent

新增Gateway模块，Gateway能够接收来自不同channel的消息，并把消息发送到PublicBus上

同时，gateway负责把publicBus上来自不同channel的消息分发给各个channel

channel就是不同用户的消息来源，例如现在的网页前端，或者是TUI

新增TUI功能，用户能够从命令行访问agent，使用Textual python库来实现
