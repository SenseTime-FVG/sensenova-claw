"""引用管理器：解析脚注引用，按 URL 去重，分配全局编号。

CitationManager 处理使用 [^key] 脚注格式的报告文本，
将符号引用转换为 [N] 编号引用 + 参考文献列表。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse, urlunparse


# ─── Citation 数据类 ───────────────────────────────────────────────────────────

@dataclass
class Citation:
    """单条引用记录。"""

    # 脚注 key（如 reuters_tesla_q4）
    key: str
    # 原始 URL
    url: str
    # 来源标题
    title: str
    # 全局编号（处理后分配）
    index: int = 0
    # 引用此来源的所有脚注 key 列表（URL 去重时可能多个 key 指向同一来源）
    alias_keys: list[str] = field(default_factory=list)


# ─── URL 标准化 ──────────────────────────────────────────────────────────────

def _normalize_url(url: str) -> str:
    """标准化 URL：小写协议和主机名，去除尾部斜杠。"""
    parsed = urlparse(url.strip())
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/") if parsed.path != "/" else ""
    normalized = urlunparse((scheme, netloc, path, parsed.params, parsed.query, ""))
    return normalized


# ─── 脚注解析正则 ────────────────────────────────────────────────────────────

# 匹配正文中的脚注引用：[^key]（不在行首，非定义）
_FOOTNOTE_REF_RE = re.compile(r"\[\^([\w-]+)\](?!:)")

# 匹配脚注定义：[^key]: 内容（行首）
# 内容中可能包含 Markdown 链接 [title](url) 或纯文本 + URL
_FOOTNOTE_DEF_RE = re.compile(
    r"^\[\^([\w-]+)\]:\s*(.+)$",
    re.MULTILINE,
)

# 从脚注定义内容中提取 Markdown 链接 [title](url)
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

# 从脚注定义内容中提取裸 URL（备用）
_BARE_URL_RE = re.compile(r"https?://\S+")


def _parse_footnote_def(content: str) -> tuple[str, str]:
    """从脚注定义内容解析 (title, url)。

    支持格式：
    - [title](url)
    - [title](url) - category
    - title - url
    - url
    """
    # 优先匹配 Markdown 链接
    link_match = _MD_LINK_RE.search(content)
    if link_match:
        return link_match.group(1).strip(), link_match.group(2).strip()

    # 尝试裸 URL
    url_match = _BARE_URL_RE.search(content)
    if url_match:
        url = url_match.group(0)
        # 标题取 URL 之前的部分
        title = content[:url_match.start()].strip().rstrip("-").rstrip()
        return title or url, url

    # 都没有，整个内容作为标题
    return content.strip(), ""


# ─── CitationManager ──────────────────────────────────────────────────────────

class CitationManager:
    """脚注引用处理器。

    处理流程：
    1. 从子报告收集所有脚注定义（key → title, url）
    2. 按 URL 去重，合并指向同一来源的不同 key
    3. 扫描终稿正文中的 [^key] 引用，按首次出现顺序分配全局编号
    4. 替换 [^key] → [N]，生成参考文献列表
    """

    def __init__(self) -> None:
        # key → (title, url)：所有脚注定义
        self._definitions: dict[str, tuple[str, str]] = {}
        # normalized_url → Citation：去重后的引用池
        self._pool: dict[str, Citation] = {}
        # key → normalized_url：key 到去重 URL 的映射
        self._key_to_norm_url: dict[str, str] = {}

    def collect_definitions(self, text: str) -> None:
        """从文本中收集所有脚注定义，按 URL 去重。"""
        for match in _FOOTNOTE_DEF_RE.finditer(text):
            key = match.group(1)
            content = match.group(2)
            title, url = _parse_footnote_def(content)

            self._definitions[key] = (title, url)

            if url:
                norm_url = _normalize_url(url)
                self._key_to_norm_url[key] = norm_url

                if norm_url not in self._pool:
                    self._pool[norm_url] = Citation(
                        key=key,
                        url=url,
                        title=title,
                        alias_keys=[key],
                    )
                else:
                    existing = self._pool[norm_url]
                    if key not in existing.alias_keys:
                        existing.alias_keys.append(key)

    def process_report(self, report_text: str) -> tuple[str, str]:
        """处理终稿：替换 [^key] → [N]，生成参考文献列表。

        参数:
            report_text: 终稿文本（含 [^key] 引用和脚注定义）

        返回:
            (处理后的正文, 参考文献 Markdown 文本)
        """
        # 扫描正文中的引用，按首次出现顺序分配编号
        key_to_index: dict[str, int] = {}
        ordered_citations: list[Citation] = []
        counter = 0

        for match in _FOOTNOTE_REF_RE.finditer(report_text):
            key = match.group(1)
            # 通过 URL 去重：不同 key 可能指向同一来源
            norm_url = self._key_to_norm_url.get(key)

            if norm_url and norm_url in self._pool:
                citation = self._pool[norm_url]
                # 检查这个来源是否已经分配了编号
                primary_key = citation.key
                if primary_key not in key_to_index:
                    counter += 1
                    citation.index = counter
                    key_to_index[primary_key] = counter
                    ordered_citations.append(citation)
                # 别名 key 也映射到同一编号
                if key not in key_to_index:
                    key_to_index[key] = key_to_index[primary_key]
            elif key not in key_to_index:
                # 没有 URL 的脚注，仍然分配编号
                counter += 1
                title = self._definitions.get(key, (key, ""))[0]
                fallback = Citation(key=key, url="", title=title, index=counter, alias_keys=[key])
                key_to_index[key] = counter
                ordered_citations.append(fallback)

        # 替换正文中的 [^key] → [N]
        def replace_ref(m: re.Match) -> str:
            k = m.group(1)
            idx = key_to_index.get(k)
            return f"[{idx}]" if idx else m.group(0)

        processed = _FOOTNOTE_REF_RE.sub(replace_ref, report_text)

        # 移除脚注定义行
        processed = _FOOTNOTE_DEF_RE.sub("", processed)

        # 清理多余空行（脚注定义移除后可能留下）
        processed = re.sub(r"\n{3,}", "\n\n", processed).strip()

        # 生成参考文献列表
        ref_lines: list[str] = []
        for citation in ordered_citations:
            if citation.url:
                ref_lines.append(f"{citation.index}. [{citation.title}]({citation.url})")
            else:
                ref_lines.append(f"{citation.index}. {citation.title}")

        references = "\n".join(ref_lines)

        return processed, references

    def export_json(self) -> dict:
        """导出引用数据为 JSON 可序列化字典。"""
        all_citations = [c for c in self._pool.values() if c.index > 0]
        all_citations.sort(key=lambda c: c.index)
        return {
            "total_citations": len(all_citations),
            "citations": [
                {
                    "index": c.index,
                    "key": c.key,
                    "url": c.url,
                    "title": c.title,
                    "alias_keys": c.alias_keys,
                }
                for c in all_citations
            ],
        }
