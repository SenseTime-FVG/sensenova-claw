#!/usr/bin/env python3
"""union-search-plus 结果融合工具。

提供统一去重、重排和覆盖度评估能力，供 skill 在 deep 阶段调用。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse, urlunparse
import re


TRACKING_KEYS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "gclid",
    "fbclid",
}


@dataclass
class CoverageMetrics:
    """搜索覆盖度指标。"""

    source_count: int
    topic_coverage: float
    valid_evidence_count: int



def normalize_title(value: str) -> str:
    """规范化标题，便于近似去重。"""
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip().casefold()



def normalize_url(value: str) -> str:
    """规范化 URL，去除常见跳转参数和追踪参数。"""
    if not value:
        return ""

    raw = value.strip()
    if not raw:
        return ""

    parsed = urlparse(raw)

    # Yahoo 跳转 URL 特殊处理。
    if parsed.netloc.casefold().endswith("search.yahoo.com"):
        ru_values = parse_qs(parsed.query).get("RU")
        if ru_values:
            raw = unquote(ru_values[0])
            parsed = urlparse(raw)

    if not parsed.scheme or not parsed.netloc:
        return raw.casefold()

    query_parts: list[str] = []
    for part in parsed.query.split("&"):
        if not part:
            continue
        key = part.split("=", 1)[0].casefold()
        if key in TRACKING_KEYS or key.startswith("utm_"):
            continue
        query_parts.append(part)

    normalized = urlunparse(
        (
            parsed.scheme.casefold(),
            parsed.netloc.casefold(),
            parsed.path.rstrip("/"),
            "",
            "&".join(query_parts),
            "",
        )
    )
    return normalized



def extract_link(item: dict[str, Any]) -> str:
    """从通用 item 结构中提取链接。"""
    for key in ("link", "url", "href", "permalink", "source_url"):
        value = item.get(key)
        if value:
            return str(value)
    return ""



def extract_title(item: dict[str, Any]) -> str:
    """从通用 item 结构中提取标题。"""
    for key in ("title", "name", "headline"):
        value = item.get(key)
        if value:
            return str(value)
    return ""



def _source_name(item: dict[str, Any]) -> str:
    """抽取来源名。"""
    return str(
        item.get("_source_platform")
        or item.get("provider")
        or item.get("source")
        or "unknown"
    )



def _tokenize(text: str) -> list[str]:
    """分词：英文按空白/标点拆分，中文按 bigram 拆分以保留语义。"""
    tokens: list[str] = []
    # 先提取英文/数字 token
    tokens.extend(re.findall(r"[a-zA-Z0-9]+", text.lower()))
    # 中文部分用 bigram（二元组）保留短语语义
    cjk_chars = re.findall(r"[\u4e00-\u9fff]+", text)
    for segment in cjk_chars:
        if len(segment) == 1:
            tokens.append(segment)
        else:
            for i in range(len(segment) - 1):
                tokens.append(segment[i : i + 2])
    return [t for t in tokens if t]



def _match_score(item: dict[str, Any], query: str) -> float:
    """简单相关性分，用于重排。"""
    if not query:
        return 0.0

    q_tokens = set(_tokenize(query))
    if not q_tokens:
        return 0.0

    content = " ".join(
        [
            extract_title(item),
            str(item.get("snippet", "")),
            str(item.get("content", "")),
        ]
    )
    tokens = set(_tokenize(content))
    if not tokens:
        return 0.0

    overlap = len(q_tokens & tokens)
    return overlap / max(len(q_tokens), 1)



def deduplicate_and_rank(items: list[dict[str, Any]], query: str = "") -> list[dict[str, Any]]:
    """统一去重 + 重排。

    - 去重键：规范化 URL 优先，其次规范化标题。
    - 重排：相关性优先，其次保留更多 snippet 的条目。
    """
    deduped: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()

    for item in items:
        if not isinstance(item, dict):
            continue

        title = extract_title(item)
        link = extract_link(item)
        url_key = normalize_url(link)
        title_key = normalize_title(title)

        if url_key and url_key in seen_urls:
            continue
        if title_key and title_key in seen_titles:
            continue

        if url_key:
            seen_urls.add(url_key)
        if title_key:
            seen_titles.add(title_key)

        normalized = dict(item)
        normalized.setdefault("title", title)
        normalized.setdefault("link", link)
        normalized["source"] = _source_name(item)
        normalized["_match_score"] = _match_score(normalized, query)
        deduped.append(normalized)

    deduped.sort(
        key=lambda x: (
            float(x.get("_match_score", 0.0)),
            len(str(x.get("snippet", ""))) + len(str(x.get("content", ""))),
        ),
        reverse=True,
    )

    for item in deduped:
        item.pop("_match_score", None)

    return deduped



def _topic_coverage(items: list[dict[str, Any]], query: str) -> float:
    """估算 topic 覆盖率：query 词在结果文本中的覆盖比例。"""
    q_tokens = set(_tokenize(query))
    if not q_tokens:
        return 1.0

    combined = "\n".join(
        " ".join(
            [
                extract_title(item),
                str(item.get("snippet", "")),
                str(item.get("content", "")),
            ]
        )
        for item in items
        if isinstance(item, dict)
    )
    tokens = set(_tokenize(combined))
    if not tokens:
        return 0.0

    return len(q_tokens & tokens) / max(len(q_tokens), 1)



def assess_insufficiency(
    items: list[dict[str, Any]],
    query: str,
    min_sources: int,
    min_topic_coverage: float,
    min_valid_evidence: int,
) -> dict[str, Any]:
    """判定主链结果是否不足。"""
    # 用 (来源名, 域名) 作为去重键，避免多个 unknown 来源被合并成一个
    source_keys: set[tuple[str, str]] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        name = _source_name(item)
        link = extract_link(item)
        if name == "unknown" and not link:
            continue
        # unknown 来源按域名区分
        domain = urlparse(link).netloc.casefold() if link else ""
        source_keys.add((name, domain) if name == "unknown" else (name, ""))
    valid_evidence = [
        item
        for item in items
        if isinstance(item, dict) and extract_title(item).strip() and extract_link(item).strip()
    ]

    metrics = CoverageMetrics(
        source_count=len(source_keys),
        topic_coverage=_topic_coverage(valid_evidence, query),
        valid_evidence_count=len(valid_evidence),
    )

    insufficient_reasons: list[str] = []
    if metrics.source_count < min_sources:
        insufficient_reasons.append(
            f"来源数不足: {metrics.source_count} < {min_sources}"
        )
    if metrics.topic_coverage < min_topic_coverage:
        insufficient_reasons.append(
            f"主题覆盖不足: {metrics.topic_coverage:.2f} < {min_topic_coverage:.2f}"
        )
    if metrics.valid_evidence_count < min_valid_evidence:
        insufficient_reasons.append(
            f"有效证据不足: {metrics.valid_evidence_count} < {min_valid_evidence}"
        )

    return {
        "is_insufficient": len(insufficient_reasons) > 0,
        "reasons": insufficient_reasons,
        "metrics": {
            "source_count": metrics.source_count,
            "topic_coverage": round(metrics.topic_coverage, 4),
            "valid_evidence_count": metrics.valid_evidence_count,
        },
        "thresholds": {
            "min_sources": min_sources,
            "min_topic_coverage": min_topic_coverage,
            "min_valid_evidence": min_valid_evidence,
        },
    }
