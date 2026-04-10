"""引用预处理工具：供 deep-research-controller 在生成终稿前调用。

读取指定目录下的所有子报告，统一引用编号、去重，
原地更新子报告文件并生成 global_sources.md。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sensenova_claw.capabilities.tools.base import Tool, ToolRiskLevel


class PrepareReportCitationsTool(Tool):
    name = "prepare_report_citations"
    description = (
        "预处理子报告引用：读取 sub_reports/ 下所有子报告，"
        "统一引用编号、去重，原地更新各子报告文件中的引用编号，"
        "生成 global_sources.md 和 citations.json。"
        "在发送给 report-agent 之前调用。"
    )
    risk_level = ToolRiskLevel.LOW
    parameters = {
        "type": "object",
        "properties": {
            "report_dir": {
                "type": "string",
                "description": "报告目录路径，如 workspace/reports/2026-04-10-ai-chip",
            },
        },
        "required": ["report_dir"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        from sensenova_claw.capabilities.deep_research.citation_manager import (
            CitationManager,
        )

        kwargs.pop("_path_policy", None)
        kwargs.pop("_agent_workdir", None)
        report_dir = Path(kwargs["report_dir"])
        sub_reports_dir = report_dir / "sub_reports"

        if not sub_reports_dir.exists():
            return {"success": False, "error": f"子报告目录不存在: {sub_reports_dir}"}

        # 读取所有子报告
        sub_reports: dict[str, str] = {}
        for md_file in sorted(sub_reports_dir.glob("*.md")):
            dim_id = md_file.stem
            sub_reports[dim_id] = md_file.read_text(encoding="utf-8")

        if not sub_reports:
            return {"success": False, "error": "子报告目录为空"}

        # 预处理引用：统一编号，各子报告独立返回
        cm = CitationManager()
        updated_reports, global_sources = cm.preprocess_individual_reports(sub_reports)

        # 原地更新各子报告文件
        for dim_id, updated_text in updated_reports.items():
            file_path = sub_reports_dir / f"{dim_id}.md"
            file_path.write_text(updated_text, encoding="utf-8")

        # 写入全局来源列表
        sources_path = report_dir / "global_sources.md"
        sources_path.write_text(global_sources, encoding="utf-8")

        # 写入 citations.json
        citations_path = report_dir / "citations.json"
        citations_data = cm.export_json()
        with open(citations_path, "w", encoding="utf-8") as f:
            json.dump(citations_data, f, ensure_ascii=False, indent=2)

        return {
            "success": True,
            "updated_sub_reports": [
                str(sub_reports_dir / f"{d}.md") for d in updated_reports
            ],
            "global_sources_path": str(sources_path),
            "citations_path": str(citations_path),
            "total_citations": citations_data["total_citations"],
            "dimensions_processed": list(sub_reports.keys()),
        }
