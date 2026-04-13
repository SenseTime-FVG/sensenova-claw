"""引用预处理工具：供 deep-research-controller 在终稿生成后调用。

读取终稿和指定子报告中的脚注定义，按 URL 去重，
将终稿中的 [^key] 替换为 [N] 编号，追加参考文献列表。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sensenova_claw.capabilities.tools.base import Tool, ToolRiskLevel


def _resolve_path(raw: str, agent_workdir: str | None) -> Path:
    """与 read_file/write_file 保持一致的路径解析。"""
    p = Path(raw).expanduser()
    if p.is_absolute():
        return p.resolve()
    if agent_workdir:
        return (Path(agent_workdir) / p).resolve()
    return p.resolve()


class PrepareReportCitationsTool(Tool):
    name = "prepare_report_citations"
    description = (
        "处理终稿引用：从指定的子报告文件收集脚注定义（按 URL 去重），"
        "将终稿中的 [^key] 脚注引用替换为 [N] 编号，"
        "在终稿末尾追加参考文献列表。在终稿生成后调用。"
    )
    risk_level = ToolRiskLevel.LOW
    parameters = {
        "type": "object",
        "properties": {
            "report_path": {
                "type": "string",
                "description": "终稿文件的绝对路径，如 /home/user/.sensenova-claw/workdir/.../report.md",
            },
            "sub_report_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "所有子报告文件的绝对路径列表",
            },
        },
        "required": ["report_path", "sub_report_paths"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        from sensenova_claw.capabilities.deep_research.citation_manager import (
            CitationManager,
        )

        kwargs.pop("_path_policy", None)
        agent_workdir = kwargs.pop("_agent_workdir", None)

        report_path = _resolve_path(kwargs["report_path"], agent_workdir)
        sub_report_paths = [
            _resolve_path(p, agent_workdir) for p in kwargs["sub_report_paths"]
        ]

        if not report_path.exists():
            return {"success": False, "error": f"终稿不存在: {report_path}"}

        cm = CitationManager()

        # Step 1: 从指定的子报告收集脚注定义
        scanned: list[str] = []
        for sr_path in sub_report_paths:
            if not sr_path.exists():
                continue
            text = sr_path.read_text(encoding="utf-8")
            cm.collect_definitions(text)
            scanned.append(str(sr_path))

        # 也从终稿自身收集（report-agent 可能引入新脚注定义）
        report_text = report_path.read_text(encoding="utf-8")
        cm.collect_definitions(report_text)

        # Step 2: 处理终稿
        processed_text, references = cm.process_report(report_text)

        # Step 3: 追加参考文献列表并覆写终稿
        final_text = f"{processed_text}\n\n## 参考文献\n\n{references}\n"
        report_path.write_text(final_text, encoding="utf-8")

        # Step 4: 写入 citations.json（与终稿同目录）
        citations_dir = report_path.parent
        citations_path = citations_dir / "citations.json"
        citations_data = cm.export_json()
        with open(citations_path, "w", encoding="utf-8") as f:
            json.dump(citations_data, f, ensure_ascii=False, indent=2)

        return {
            "success": True,
            "report_path": str(report_path),
            "citations_path": str(citations_path),
            "total_citations": citations_data["total_citations"],
            "sub_reports_scanned": scanned,
        }
