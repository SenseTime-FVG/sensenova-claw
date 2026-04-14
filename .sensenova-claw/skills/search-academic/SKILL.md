---
name: search-academic
description: 搜索学术论文和百科知识：ArXiv 论文（支持按领域/作者过滤）、Wikipedia 百科文章。用于学术调研和知识查询。
---

# search-academic - 学术搜索

搜索 ArXiv 论文和 Wikipedia 百科。全部免费，无需 API key。

## 可用脚本

| 脚本 | 平台 | 用途 | API key |
|------|------|------|---------|
| `arxiv_search.py` | ArXiv | 学术论文搜索（预印本） | 无需 |
| `semantic_scholar_search.py` | Semantic Scholar | 全学科论文搜索，含引用数和影响力 | 无需（有 key 限额更高） |
| `pubmed_search.py` | PubMed | 生物医学文献搜索，含结构化摘要 | 无需（有 key 限额更高） |
| `wikipedia_search.py` | Wikipedia | 百科文章搜索 | 无需 |

## 参数说明

### arxiv_search.py

```bash
python3 scripts/arxiv_search.py <query> [选项]
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `query` | 搜索关键词（必填） | — |
| `--limit`, `-n` | 返回结果数量 | 10 |
| `--category`, `-c` | ArXiv 分类过滤（见下方"arxiv常用分类速查"） | — |
| `--sort` | 排序方式：`relevance`, `date`, `submitted` | relevance |

```bash
python3 scripts/arxiv_search.py "transformer attention mechanism" --limit 5
python3 scripts/arxiv_search.py "reinforcement learning" --category cs.AI --sort date --limit 5
```

### semantic_scholar_search.py

```bash
python3 scripts/semantic_scholar_search.py <query> [选项]
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `query` | 搜索关键词（必填） | — |
| `--limit`, `-n` | 返回结果数量 | 10 |
| `--api-key` | Semantic Scholar API Key（也可通过 `S2_API_KEY` 环境变量，可选，提高限额） | — |

```bash
python3 scripts/semantic_scholar_search.py "transformer architecture" --limit 5
python3 scripts/semantic_scholar_search.py "RLHF language model" --limit 10
```

**输出字段**：`title`, `url`, `snippet`（完整摘要，缺失时降级为 tldr）, `tldr`（AI 一句话总结）, `authors`, `year`, `venue`（会议/期刊简称）, `publication_venue`（结构化 venue，含 name/type/url）, `publication_date`, `citation_count`, `influential_citation_count`, `reference_count`, `is_open_access`, `open_access_pdf`, `fields_of_study`, `publication_types`, `doi`, `arxiv_id`, `paper_id`

### pubmed_search.py

```bash
python3 scripts/pubmed_search.py <query> [选项]
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `query` | 搜索关键词（必填），支持 PubMed 查询语法（如 `cancer[Title] AND 2024[pdat]`） | — |
| `--limit`, `-n` | 返回结果数量 | 10 |
| `--api-key` | NCBI API Key（可选，限额从 3 req/s 升至 10 req/s） | — |

```bash
python3 scripts/pubmed_search.py "CRISPR gene editing" --limit 5
python3 scripts/pubmed_search.py "COVID-19 vaccine efficacy" --limit 10
python3 scripts/pubmed_search.py "Alzheimer[Title] AND treatment[Title]" --limit 5
```

**输出字段**：`title`, `url`, `snippet`（含结构化摘要 BACKGROUND/METHODS/RESULTS/CONCLUSIONS）, `authors`, `pmid`, `journal`, `pub_date`, `volume`, `issue`, `pages`, `keywords`（MeSH 关键词）, `pub_types`, `doi`

### wikipedia_search.py

```bash
python3 scripts/wikipedia_search.py <query> [选项]
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `query` | 搜索关键词（必填） | — |
| `--limit`, `-n` | 返回结果数量 | 10 |
| `--lang`, `-l` | 语言版本（`en`, `zh`, `ja`, `de`, `fr` 等） | en |

```bash
python3 scripts/wikipedia_search.py "machine learning" --limit 5
python3 scripts/wikipedia_search.py "深度学习" --lang zh --limit 5
```

### arxiv常用分类速查

顶层领域可直接用（如 `--category cs`），子分类更精确（如 `--category cs.AI`）。

| 领域 | 分类代码 | 说明 |
|------|---------|------|
| **计算机科学** | `cs.AI` | 人工智能 |
| | `cs.LG` | 机器学习 |
| | `cs.CL` | 计算语言学 / NLP |
| | `cs.CV` | 计算机视觉 |
| | `cs.IR` | 信息检索 |
| | `cs.RO` | 机器人 |
| | `cs.SE` | 软件工程 |
| | `cs.DC` | 分布式/并行计算 |
| | `cs.NI` | 网络与互联网 |
| | `cs.CR` | 密码学与安全 |
| | `cs.DB` | 数据库 |
| | `cs.HC` | 人机交互 |
| **统计** | `stat.ML` | 统计机器学习 |
| | `stat.AP` | 应用统计 |
| | `stat.ME` | 统计方法论 |
| **数学** | `math.OC` | 优化与控制 |
| | `math.ST` | 统计理论 |
| | `math.CO` | 组合数学 |
| **物理** | `physics` | 物理（全类） |
| | `cond-mat` | 凝聚态物理 |
| | `quant-ph` | 量子物理 |
| | `hep-th` | 高能理论物理 |
| **经济/金融** | `econ.GN` | 经济学综合 |
| | `q-fin.CP` | 计算金融 |
| | `q-fin.ST` | 统计金融 |
| **生物/医学** | `q-bio.NC` | 神经科学 |
| | `q-bio.GN` | 基因组学 |
| | `q-bio.QM` | 定量方法 |

## 输出格式

标准 JSON：`{"success": true, "query": "...", "provider": "arxiv|wikipedia", "items": [...], "error": null}`
