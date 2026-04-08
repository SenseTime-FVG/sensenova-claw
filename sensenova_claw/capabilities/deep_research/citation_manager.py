"""引用管理器：提取、去重并维护全局引用池。

CitationManager 作为透明中间件运行在 Research Agent 子报告之上，
解析 ## Sources 节，按 URL 去重，维护跨维度的全局引用池。
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse, urlunparse


# ─── Citation 数据类 ───────────────────────────────────────────────────────────

@dataclass
class Citation:
    """单条引用记录。"""

    # 唯一标识符
    id: str
    # 原始 URL
    url: str
    # 来源标题（来自 Markdown 链接文本）
    title: str
    # 来源分类（默认 "web"）
    source_category: str
    # 摘要片段
    snippet: str
    # 首次关联的维度 ID
    dimension_id: str
    # 可信度评分（0.0 ~ 1.0）
    credibility: float = 0.0
    # 访问时间（可选）
    access_time: Optional[datetime] = None
    # 引用此来源的所有维度列表
    referenced_in: list[str] = field(default_factory=list)


# ─── URL 标准化工具函数 ────────────────────────────────────────────────────────

def _normalize_url(url: str) -> str:
    """标准化 URL：小写协议和主机名，去除尾部斜杠。

    例如:
        HTTPS://Example.COM/path/ -> https://example.com/path
        https://example.com/path  -> https://example.com/path
    """
    parsed = urlparse(url.strip())
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    # 去除路径尾部斜杠（根路径 "/" 保留为空）
    path = parsed.path.rstrip("/") if parsed.path != "/" else ""
    normalized = urlunparse((scheme, netloc, path, parsed.params, parsed.query, ""))
    return normalized


# ─── Sources 节解析正则 ────────────────────────────────────────────────────────

# 匹配 "N. [title](url)" 格式的 Markdown 链接
_SOURCE_ENTRY_RE = re.compile(
    r"^\s*\d+\.\s+\[([^\]]+)\]\(([^)]+)\)",
    re.MULTILINE,
)

# 匹配 "## Sources" 节（大小写不敏感）
_SOURCES_SECTION_RE = re.compile(
    r"##\s+Sources\s*\n(.*?)(?=\n##\s|\Z)",
    re.DOTALL | re.IGNORECASE,
)


def _parse_sources_section(report: str) -> list[tuple[str, str]]:
    """从报告文本中解析 ## Sources 节，返回 (title, url) 元组列表。"""
    section_match = _SOURCES_SECTION_RE.search(report)
    if not section_match:
        return []

    section_text = section_match.group(1)
    entries = _SOURCE_ENTRY_RE.findall(section_text)
    # entries: [(title, url), ...]
    return entries


# ─── CitationManager ──────────────────────────────────────────────────────────

class CitationManager:
    """全局引用池管理器。

    - 从 Research Agent 子报告中提取引用
    - 按标准化 URL 去重
    - 跨维度追踪引用来源
    - 生成带全局编号的合并报告
    """

    def __init__(self) -> None:
        # 内部引用池：标准化 URL → Citation
        self._pool: dict[str, Citation] = {}

    @property
    def pool(self) -> dict[str, Citation]:
        """返回引用池的只读副本，防止外部意外修改内部状态。"""
        return dict(self._pool)

    def extract_and_register(
        self,
        sub_report: str,
        dimension_id: str,
    ) -> tuple[str, list[Citation]]:
        """从子报告中提取引用并注册到全局池。

        参数:
            sub_report:   Research Agent 输出的子报告文本（包含 ## Sources 节）
            dimension_id: 当前维度标识符（如 "climate", "safety"）

        返回:
            (原始报告文本不变, 本次新增的 Citation 列表)
            - 重复 URL 不计入新增，只更新其 referenced_in
        """
        entries = _parse_sources_section(sub_report)
        new_citations: list[Citation] = []

        for title, url in entries:
            norm_url = _normalize_url(url)

            if norm_url in self._pool:
                # 已存在：仅更新引用维度列表
                existing = self._pool[norm_url]
                if dimension_id not in existing.referenced_in:
                    existing.referenced_in.append(dimension_id)
            else:
                # 新增：创建 Citation 并注册
                citation = Citation(
                    id=str(uuid.uuid4()),
                    url=url.strip(),
                    title=title.strip(),
                    source_category="web",
                    snippet="",
                    dimension_id=dimension_id,
                    referenced_in=[dimension_id],
                )
                self._pool[norm_url] = citation
                new_citations.append(citation)

        return sub_report, new_citations

    def build_global_reference(
        self,
        sub_reports: dict[str, str],
    ) -> tuple[str, list[Citation]]:
        """合并所有子报告，在末尾附加全局引用列表。

        参数:
            sub_reports: 维度 ID → 子报告文本 的映射

        返回:
            (合并后的报告文本, 全局引用池中的所有 Citation 列表)
        """
        # 合并各维度报告，添加维度标题
        sections: list[str] = []
        for dimension_id, report_text in sub_reports.items():
            header = f"## [{dimension_id}]"
            sections.append(f"{header}\n\n{report_text.strip()}")

        merged_body = "\n\n---\n\n".join(sections)

        # 构建全局引用节
        all_citations = list(self._pool.values())
        ref_lines: list[str] = []
        for idx, citation in enumerate(all_citations, start=1):
            dims_str = ", ".join(citation.referenced_in) if citation.referenced_in else "-"
            ref_lines.append(
                f"{idx}. [{citation.title}]({citation.url})  "
                f"_(dimensions: {dims_str})_"
            )

        global_ref_section = "## Global References\n\n" + "\n".join(ref_lines)

        merged_text = merged_body + "\n\n---\n\n" + global_ref_section

        return merged_text, all_citations

    def export_json(self) -> dict:
        """将引用池导出为 JSON 可序列化字典。

        键为标准化 URL，值为包含 Citation 所有字段的字典。
        """
        result: dict = {}
        for norm_url, citation in self._pool.items():
            result[norm_url] = {
                "id": citation.id,
                "url": citation.url,
                "title": citation.title,
                "source_category": citation.source_category,
                "snippet": citation.snippet,
                "dimension_id": citation.dimension_id,
                "credibility": citation.credibility,
                "access_time": (
                    citation.access_time.isoformat()
                    if citation.access_time is not None
                    else None
                ),
                "referenced_in": list(citation.referenced_in),
            }
        return result
