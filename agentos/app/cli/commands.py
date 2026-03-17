"""CommandDispatcher - 所有 / 命令"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentos.app.cli.app import CLIApp


# ── Tab 补全定义 ──────────────────────────────────────

# 顶层命令
TOP_COMMANDS = [
    "/new", "/session", "/agent", "/tool", "/skill",
    "/history", "/debug", "/help", "/quit",
]

# 子命令映射
SUB_COMMANDS: dict[str, list[str]] = {
    "/session": ["list", "switch", "current"],
    "/agent":   ["list", "create", "delete", "info", "switch", "config"],
    "/tool":    ["list", "enable", "disable"],
    "/skill":   ["list", "search", "enable", "disable"],
    "/debug":   ["on", "off"],
}


def get_completions(buffer: str) -> list[str]:
    """根据当前输入返回可用的补全项"""
    text = buffer.rstrip()
    has_space = buffer != buffer.rstrip()  # 末尾有空格
    if not text or text == "/":
        return TOP_COMMANDS

    # 已输入空格 → 进入子命令补全
    if has_space or " " in text:
        parts = text.split(maxsplit=1)
        cmd = parts[0].lower()
        partial = parts[1] if len(parts) > 1 else ""
        subs = SUB_COMMANDS.get(cmd, [])
        if not partial:
            return subs
        return [s for s in subs if s.startswith(partial)]

    # 匹配顶层命令前缀（如 "/se" → ["/session", "/skill"]）
    return [c for c in TOP_COMMANDS if c.startswith(text)]


class CommandDispatcher:
    """CLI 命令分派器"""

    def __init__(self, app: CLIApp):
        self.app = app

    async def dispatch(self, raw: str) -> str | None:
        """分派命令，返回 "quit" 表示退出"""
        parts = raw.strip().split(maxsplit=2)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""
        arg2 = parts[2] if len(parts) > 2 else ""

        if cmd == "/quit":
            return "quit"
        if cmd in ("/help", "/"):
            self._show_help()

        # ── 会话管理 ──────────────────────────────
        elif cmd == "/new":
            sid = await self.app._create_session(arg.strip() or None)
            self.app.console.print(f"[green]✓ 新会话: {sid} (Agent: {arg or 'default'})[/green]")
        elif cmd == "/session":
            await self._handle_session(arg.strip(), arg2.strip())
        elif cmd in ("/history", "/h"):
            await self.app._send_query({
                "type": "get_messages",
                "payload": {"session_id": self.app.current_session_id},
            })

        # ── Agent 管理 ──────────────────────────────
        elif cmd == "/agent":
            await self._handle_agent(arg.strip(), arg2.strip(), raw)

        # ── 工具管理 ──────────────────────────────
        elif cmd == "/tool":
            await self._handle_tool(arg.strip(), arg2.strip())

        # ── 技能管理 ──────────────────────────────
        elif cmd == "/skill":
            await self._handle_skill(arg.strip(), arg2.strip())

        # ── 系统 ──────────────────────────────
        elif cmd == "/debug":
            if arg.lower() == "on":
                self.app.debug = True
                self.app.console.print("[cyan]调试模式已开启[/cyan]")
            elif arg.lower() == "off":
                self.app.debug = False
                self.app.console.print("[cyan]调试模式已关闭[/cyan]")
            else:
                self.app.console.print(f"[cyan]调试模式: {'开启' if self.app.debug else '关闭'}[/cyan]")
        else:
            self.app.console.print(f"[yellow]未知命令: {cmd}[/yellow]")
            self._show_help()
        return None

    # ── Session 子命令 ──────────────────────────────

    async def _handle_session(self, subcmd: str, rest: str) -> None:
        """处理 /session <subcmd> ..."""
        if subcmd in ("", "list", "ls"):
            await self.app._send_query({"type": "list_sessions", "payload": {}})
        elif subcmd in ("switch", "sw"):
            if not rest:
                self.app.console.print("[red]用法: /session switch <session_id>[/red]")
            else:
                await self.app._load_session(rest.strip())
                self.app.console.print(f"[green]✓ 已切换到 {rest.strip()}[/green]")
        elif subcmd == "current":
            self.app.console.print(f"会话: {self.app.current_session_id}")
            self.app.console.print(f"Agent: {self.app.current_agent_id}")
            self.app.console.print(f"调试: {'开启' if self.app.debug else '关闭'}")
        else:
            self.app.console.print("""[cyan]Session 子命令:[/cyan]
  /session list                 列出历史会话
  /session switch <id>          切换会话
  /session current              当前会话信息""")

    # ── Agent 子命令 ──────────────────────────────

    async def _handle_agent(self, subcmd: str, rest: str, raw: str) -> None:
        """处理 /agent <subcmd> ..."""
        if subcmd in ("", "list", "ls"):
            await self.app._send_query({"type": "list_agents", "payload": {}})
        elif subcmd == "create":
            await self._agent_create(raw)
        elif subcmd == "delete":
            await self._agent_delete(rest)
        elif subcmd == "info":
            await self._agent_info(rest)
        elif subcmd in ("switch", "use"):
            await self._agent_switch(rest)
        elif subcmd == "config":
            await self._agent_config(rest, raw)
        else:
            self.app.console.print("""[cyan]Agent 子命令:[/cyan]
  /agent list                       列出可用 Agent
  /agent create <id> <name>         创建 Agent
  /agent delete <id>                删除 Agent
  /agent info [id]                  查看 Agent 详情
  /agent switch <id>                切换 Agent（创建新会话）
  /agent config <id> <key> <value>  修改 Agent 配置""")

    async def _agent_create(self, raw: str) -> None:
        """创建 Agent: /agent create <id> <name>"""
        parts = raw.strip().split(maxsplit=3)
        if len(parts) < 4:
            self.app.console.print("[red]用法: /agent create <id> <name>[/red]")
            return
        agent_id = parts[2]
        name = parts[3]
        resp = await self.app._http_post("/api/agents", {"id": agent_id, "name": name})
        if resp.get("_error"):
            self.app.console.print(f"[red]创建失败: {resp.get('detail')}[/red]")
        else:
            self.app.console.print(f"[green]✓ Agent 已创建: {resp.get('id')} ({resp.get('model', '')})[/green]")

    async def _agent_delete(self, agent_id: str) -> None:
        if not agent_id:
            self.app.console.print("[red]用法: /agent delete <id>[/red]")
            return
        resp = await self.app._http_delete(f"/api/agents/{agent_id}")
        if resp.get("_error"):
            self.app.console.print(f"[red]删除失败: {resp.get('detail')}[/red]")
        else:
            self.app.console.print(f"[green]✓ Agent 已删除: {agent_id}[/green]")

    async def _agent_info(self, agent_id: str) -> None:
        agent_id = agent_id or self.app.current_agent_id
        resp = await self.app._http_get(f"/api/agents/{agent_id}")
        if resp.get("_error"):
            self.app.console.print(f"[red]查询失败: {resp.get('detail')}[/red]")
            return
        self.app.console.print(f"\n[bold]{resp.get('id')}[/bold] - {resp.get('name', '')}")
        self.app.console.print(f"  描述: {resp.get('description', '-')}")
        self.app.console.print(f"  Provider: {resp.get('provider', '-')}  Model: {resp.get('model', '-')}")
        self.app.console.print(f"  Temperature: {resp.get('temperature', '-')}  MaxTokens: {resp.get('maxTokens', '-')}")
        self.app.console.print(f"  工具: {resp.get('toolCount', 0)} 个  技能: {resp.get('skillCount', 0)} 个")
        self.app.console.print(f"  会话数: {resp.get('sessionCount', 0)}")
        tools = resp.get("tools", [])
        if tools:
            self.app.console.print(f"  工具列表: {', '.join(tools[:10])}")
        skills = resp.get("skills", [])
        if skills:
            self.app.console.print(f"  技能列表: {', '.join(skills[:10])}")
        self.app.console.print()

    async def _agent_switch(self, agent_id: str) -> None:
        if not agent_id:
            self.app.console.print("[red]用法: /agent switch <id>[/red]")
            return
        resp = await self.app._http_get(f"/api/agents/{agent_id}")
        if resp.get("_error"):
            self.app.console.print(f"[red]Agent 不存在: {agent_id}[/red]")
            return
        sid = await self.app._create_session(agent_id)
        self.app.console.print(f"[green]✓ 已切换到 Agent: {agent_id}  新会话: {sid}[/green]")

    async def _agent_config(self, rest: str, raw: str) -> None:
        """修改 Agent 配置: /agent config <id> <key> <value>"""
        parts = raw.strip().split(maxsplit=4)
        if len(parts) < 5:
            self.app.console.print("[red]用法: /agent config <id> <key> <value>[/red]")
            self.app.console.print("[dim]可用 key: name, description, provider, model, temperature, systemPrompt[/dim]")
            return
        agent_id = parts[2]
        key = parts[3]
        value = parts[4]
        if key == "temperature":
            try:
                value = float(value)
            except ValueError:
                self.app.console.print("[red]temperature 需要是数字[/red]")
                return
        elif key == "max_tokens":
            try:
                value = int(value)
            except ValueError:
                self.app.console.print("[red]max_tokens 需要是整数[/red]")
                return
        resp = await self.app._http_put(f"/api/agents/{agent_id}/config", {key: value})
        if resp.get("_error"):
            self.app.console.print(f"[red]更新失败: {resp.get('detail')}[/red]")
        else:
            self.app.console.print(f"[green]✓ {agent_id}.{key} 已更新[/green]")

    # ── 工具子命令 ──────────────────────────────

    async def _handle_tool(self, subcmd: str, tool_name: str) -> None:
        if subcmd in ("", "list", "ls"):
            await self._tools_list()
        elif subcmd == "enable" and tool_name:
            resp = await self.app._http_put(f"/api/tools/{tool_name}/enabled", {"enabled": True})
            if isinstance(resp, dict) and resp.get("_error"):
                self.app.console.print(f"[red]启用失败: {resp.get('detail')}[/red]")
            else:
                self.app.console.print(f"[green]✓ {tool_name} 已启用[/green]")
        elif subcmd == "disable" and tool_name:
            resp = await self.app._http_put(f"/api/tools/{tool_name}/enabled", {"enabled": False})
            if isinstance(resp, dict) and resp.get("_error"):
                self.app.console.print(f"[red]禁用失败: {resp.get('detail')}[/red]")
            else:
                self.app.console.print(f"[yellow]✓ {tool_name} 已禁用[/yellow]")
        else:
            self.app.console.print("""[cyan]工具子命令:[/cyan]
  /tool list                    列出所有工具
  /tool enable <name>           启用工具
  /tool disable <name>          禁用工具""")

    async def _tools_list(self) -> None:
        resp = await self.app._http_get("/api/tools")
        if isinstance(resp, dict) and resp.get("_error"):
            self.app.console.print(f"[red]获取失败: {resp.get('detail')}[/red]")
            return
        tools = resp if isinstance(resp, list) else []
        if not tools:
            self.app.console.print("[dim]暂无工具[/dim]")
            return
        self.app.console.print(f"\n[bold]已注册工具[/bold] ({len(tools)} 个)\n")
        for t in tools:
            status = "[green]✓[/green]" if t.get("enabled", True) else "[red]✗[/red]"
            risk = t.get("riskLevel", "low")
            desc = (t.get("description") or "")[:50]
            self.app.console.print(f"  {status} {t['name']:20s}  {risk:6s}  {desc}")
        self.app.console.print()

    # ── 技能子命令 ──────────────────────────────

    async def _handle_skill(self, subcmd: str, query: str) -> None:
        if subcmd in ("", "list", "ls"):
            await self._skills_list()
        elif subcmd == "search" and query:
            resp = await self.app._http_get(f"/api/skills/search?q={urllib_quote(query)}")
            if isinstance(resp, dict) and resp.get("_error"):
                self.app.console.print(f"[red]搜索失败: {resp.get('detail')}[/red]")
                return
            local = resp.get("local_results", [])
            remote = resp.get("remote_results", [])
            if local:
                self.app.console.print(f"\n[bold]本地匹配[/bold] ({len(local)} 个)")
                for s in local:
                    self.app.console.print(f"  {s['name']:24s}  {s.get('description', '')[:40]}")
            if remote:
                self.app.console.print(f"\n[bold]市场结果[/bold] ({len(remote)} 个)")
                for s in remote:
                    installed = " [green](已安装)[/green]" if s.get("installed") else ""
                    self.app.console.print(f"  {s['name']:24s}  {s.get('source', ''):10s}  {s.get('description', '')[:30]}{installed}")
            if not local and not remote:
                self.app.console.print(f"[dim]未找到匹配: {query}[/dim]")
            self.app.console.print()
        elif subcmd == "enable" and query:
            resp = await self.app._http(
                "PATCH", f"/api/skills/{query}", {"enabled": True}
            )
            if isinstance(resp, dict) and resp.get("_error"):
                self.app.console.print(f"[red]启用失败: {resp.get('detail')}[/red]")
            else:
                self.app.console.print(f"[green]✓ {query} 已启用[/green]")
        elif subcmd == "disable" and query:
            resp = await self.app._http(
                "PATCH", f"/api/skills/{query}", {"enabled": False}
            )
            if isinstance(resp, dict) and resp.get("_error"):
                self.app.console.print(f"[red]禁用失败: {resp.get('detail')}[/red]")
            else:
                self.app.console.print(f"[yellow]✓ {query} 已禁用[/yellow]")
        else:
            self.app.console.print("""[cyan]技能子命令:[/cyan]
  /skill list                   列出所有技能
  /skill search <关键词>        搜索技能
  /skill enable <name>          启用技能
  /skill disable <name>         禁用技能""")

    async def _skills_list(self) -> None:
        resp = await self.app._http_get("/api/skills")
        if isinstance(resp, dict) and resp.get("_error"):
            self.app.console.print(f"[red]获取失败: {resp.get('detail')}[/red]")
            return
        skills = resp if isinstance(resp, list) else []
        if not skills:
            self.app.console.print("[dim]暂无技能[/dim]")
            return
        self.app.console.print(f"\n[bold]已加载技能[/bold] ({len(skills)} 个)\n")
        for s in skills:
            status = "[green]✓[/green]" if s.get("enabled", True) else "[red]✗[/red]"
            cat = s.get("category", "")
            desc = (s.get("description") or "")[:40]
            self.app.console.print(f"  {status} {s['name']:24s}  {cat:10s}  {desc}")
        self.app.console.print()

    # ── 帮助 ──────────────────────────────

    def _show_help(self) -> None:
        self.app.console.print("""
[bold]AgentOS CLI[/bold]

  [cyan]会话[/cyan]
    /new [agent]                     创建新会话
    /session list                    列出历史会话
    /session switch <id>             切换会话
    /session current                 当前会话信息
    /history                         消息历史

  [cyan]Agent[/cyan]
    /agent list                      列出可用 Agent
    /agent create <id> <name>        创建 Agent
    /agent delete <id>               删除 Agent
    /agent info [id]                 查看 Agent 详情
    /agent switch <id>               切换 Agent（创建新会话）
    /agent config <id> <key> <val>   修改 Agent 配置

  [cyan]工具[/cyan]
    /tool list                 列出所有工具
    /tool enable <name>        启用工具
    /tool disable <name>       禁用工具

  [cyan]技能[/cyan]
    /skill list                列出所有技能
    /skill search <词>         搜索技能
    /skill enable <name>       启用技能
    /skill disable <name>      禁用技能

  [cyan]系统[/cyan]
    /debug on|off              调试模式
    /help                      显示帮助
    /quit                      退出

  [dim]按 Tab 键可补全命令和子命令[/dim]
""")


def urllib_quote(s: str) -> str:
    """URL 编码辅助"""
    import urllib.parse
    return urllib.parse.quote(s, safe="")
