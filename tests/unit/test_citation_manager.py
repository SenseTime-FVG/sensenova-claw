"""CitationManager 单元测试（TDD 先写测试）。"""
import pytest
from sensenova_claw.capabilities.deep_research.citation_manager import (
    Citation,
    CitationManager,
)


# ─── 测试数据 ──────────────────────────────────────────────────────────────────

SINGLE_SOURCE_REPORT = """
# Research on AI Safety

Some content here.

## Sources
1. [AI Safety Overview](https://example.com/ai-safety)
"""

MULTI_SOURCE_REPORT = """
# Research on Climate Change

Climate change is a major issue.

## Sources
1. [Climate Science](https://climate.org/science)
2. [IPCC Report](https://ipcc.ch/report/2023)
3. [NASA Climate](https://climate.nasa.gov/overview)
"""

NO_SOURCES_REPORT = """
# Research on History

History is fascinating.

No sources listed here.
"""

TRAILING_SLASH_REPORT = """
# Research on Web Standards

Web standards matter.

## Sources
1. [W3C Home](https://www.w3c.org/)
2. [MDN Docs](https://developer.mozilla.org/en-US/)
"""


# ─── Citation 数据类测试 ────────────────────────────────────────────────────────

def test_citation_default_fields():
    """Citation 应有合理的默认值。"""
    c = Citation(
        id="c1",
        url="https://example.com",
        title="Example",
        source_category="web",
        snippet="",
        dimension_id="dim1",
    )
    assert c.id == "c1"
    assert c.referenced_in == []
    assert c.credibility == 0.0
    assert c.access_time is None


def test_citation_referenced_in_mutable_default():
    """每个 Citation 实例应有独立的 referenced_in 列表。"""
    c1 = Citation(id="a", url="u1", title="T1", source_category="web",
                  snippet="", dimension_id="d1")
    c2 = Citation(id="b", url="u2", title="T2", source_category="web",
                  snippet="", dimension_id="d2")
    c1.referenced_in.append("dim_x")
    assert c2.referenced_in == []


# ─── extract_and_register 测试 ────────────────────────────────────────────────

def test_extract_single_source():
    """从包含单个来源的报告中提取一个 Citation。"""
    mgr = CitationManager()
    report, new_citations = mgr.extract_and_register(SINGLE_SOURCE_REPORT, "dim_safety")

    assert len(new_citations) == 1
    assert new_citations[0].url == "https://example.com/ai-safety"
    assert new_citations[0].title == "AI Safety Overview"
    assert new_citations[0].dimension_id == "dim_safety"
    # 原始报告不变
    assert report == SINGLE_SOURCE_REPORT


def test_extract_multiple_sources():
    """从包含多个来源的报告中提取所有 Citation。"""
    mgr = CitationManager()
    _, new_citations = mgr.extract_and_register(MULTI_SOURCE_REPORT, "dim_climate")

    assert len(new_citations) == 3
    urls = [c.url for c in new_citations]
    assert "https://climate.org/science" in urls
    assert "https://ipcc.ch/report/2023" in urls
    assert "https://climate.nasa.gov/overview" in urls


def test_dedup_same_url():
    """同一 URL 第二次出现时不创建新条目，只更新 referenced_in。"""
    mgr = CitationManager()

    report1 = "# Report 1\n\n## Sources\n1. [Example](https://example.com/page)\n"
    report2 = "# Report 2\n\n## Sources\n1. [Example Again](https://example.com/page)\n"

    _, new1 = mgr.extract_and_register(report1, "dim_a")
    _, new2 = mgr.extract_and_register(report2, "dim_b")

    assert len(new1) == 1
    assert len(new2) == 0  # 重复 URL，没有新增条目

    # 池中只有一条记录
    assert len(mgr.pool) == 1

    # 该条目应同时记录两个维度
    citation = list(mgr.pool.values())[0]
    assert "dim_a" in citation.referenced_in
    assert "dim_b" in citation.referenced_in


def test_url_normalization_trailing_slash():
    """尾部斜杠不同的 URL 应被视为同一来源。"""
    mgr = CitationManager()

    report_with_slash = "# R1\n\n## Sources\n1. [Site](https://example.com/page/)\n"
    report_without_slash = "# R2\n\n## Sources\n1. [Site](https://example.com/page)\n"

    _, new1 = mgr.extract_and_register(report_with_slash, "dim_x")
    _, new2 = mgr.extract_and_register(report_without_slash, "dim_y")

    assert len(new1) == 1
    assert len(new2) == 0  # 标准化后相同，视为重复
    assert len(mgr.pool) == 1


def test_url_normalization_scheme_host_lowercase():
    """URL 的协议和主机名应被小写标准化。"""
    mgr = CitationManager()

    report1 = "# R1\n\n## Sources\n1. [Site](HTTPS://Example.COM/path)\n"
    report2 = "# R2\n\n## Sources\n1. [Site](https://example.com/path)\n"

    _, new1 = mgr.extract_and_register(report1, "dim_p")
    _, new2 = mgr.extract_and_register(report2, "dim_q")

    assert len(new1) == 1
    assert len(new2) == 0
    assert len(mgr.pool) == 1


def test_no_sources_section():
    """没有 ## Sources 节时，返回空列表，池不变。"""
    mgr = CitationManager()
    report, new_citations = mgr.extract_and_register(NO_SOURCES_REPORT, "dim_history")

    assert new_citations == []
    assert len(mgr.pool) == 0
    assert report == NO_SOURCES_REPORT


def test_pool_is_readonly_copy():
    """pool 属性应返回副本，不允许外部修改内部状态。"""
    mgr = CitationManager()
    mgr.extract_and_register(SINGLE_SOURCE_REPORT, "dim_test")

    pool_copy = mgr.pool
    pool_copy["fake_key"] = None  # type: ignore

    assert "fake_key" not in mgr.pool


# ─── build_global_reference 测试 ──────────────────────────────────────────────

def test_merge_two_reports():
    """合并两份报告后应生成包含全局引用的文本。"""
    mgr = CitationManager()
    mgr.extract_and_register(SINGLE_SOURCE_REPORT, "safety")
    mgr.extract_and_register(MULTI_SOURCE_REPORT, "climate")

    sub_reports = {
        "safety": SINGLE_SOURCE_REPORT,
        "climate": MULTI_SOURCE_REPORT,
    }
    merged_text, all_citations = mgr.build_global_reference(sub_reports)

    # 合并文本包含两个维度标题
    assert "safety" in merged_text
    assert "climate" in merged_text

    # 全局引用列表包含所有 4 个 URL（1 + 3）
    assert len(all_citations) == 4

    # 合并文本末尾包含全局引用节
    assert "## Global References" in merged_text or "## References" in merged_text


def test_shared_citation_tracks_all_dimensions():
    """跨维度共享的 URL 应在全局引用中标注所有来源维度。"""
    mgr = CitationManager()

    shared_url = "https://shared-source.com/article"
    report_a = f"# Report A\n\n## Sources\n1. [Shared Article]({shared_url})\n"
    report_b = f"# Report B\n\n## Sources\n1. [Same Article]({shared_url})\n"

    mgr.extract_and_register(report_a, "dim_a")
    mgr.extract_and_register(report_b, "dim_b")

    sub_reports = {"dim_a": report_a, "dim_b": report_b}
    merged_text, all_citations = mgr.build_global_reference(sub_reports)

    # 池中只有一条
    assert len(all_citations) == 1

    # 该引用记录了两个维度
    shared = all_citations[0]
    assert "dim_a" in shared.referenced_in
    assert "dim_b" in shared.referenced_in

    # 合并文本中应提及两个维度
    assert "dim_a" in merged_text
    assert "dim_b" in merged_text


# ─── export_json 测试 ─────────────────────────────────────────────────────────

def test_export_structure():
    """export_json 应返回字典，键为 URL，值包含 Citation 所有字段。"""
    mgr = CitationManager()
    mgr.extract_and_register(SINGLE_SOURCE_REPORT, "dim_safety")

    result = mgr.export_json()

    assert isinstance(result, dict)
    assert len(result) == 1

    citation_data = list(result.values())[0]
    assert "id" in citation_data
    assert "url" in citation_data
    assert "title" in citation_data
    assert "source_category" in citation_data
    assert "snippet" in citation_data
    assert "dimension_id" in citation_data
    assert "credibility" in citation_data
    assert "referenced_in" in citation_data


def test_export_empty():
    """空池的 export_json 应返回空字典。"""
    mgr = CitationManager()
    result = mgr.export_json()
    assert result == {}


def test_export_json_serializable():
    """export_json 的结果应该可以被 json.dumps 序列化。"""
    import json
    mgr = CitationManager()
    mgr.extract_and_register(MULTI_SOURCE_REPORT, "dim_climate")

    result = mgr.export_json()
    # 不应抛出异常
    serialized = json.dumps(result)
    assert len(serialized) > 0
