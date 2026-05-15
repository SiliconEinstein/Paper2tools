"""
Phase 2: 并行提取 A-主线论文的算法层和实现层信息
Agent 调度 + LLM API 并行处理

用法: python 02_extractor.py <cluster_dir>
"""

import asyncio
import json
import sys
import yaml
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from llm_client import llm_parallel

EXTRACT_PROMPT = """你是一个学术论文信息提取专家。从以下论文推理链中提取结构化信息。

论文: {short_name} ({paper_id})
推理链:
{chain_text}

MD 摘要（Methods 部分）:
{methods_text}

请严格按以下 YAML 格式输出，所有描述字段使用中文，禁止出现"详见原文"等占位文本：

algorithm_layer:
  core_formula: >-
    <核心算法/公式，所有符号必须有定义>
  mechanism_detail: >-
    <方法机制，精确到子步骤，格式：步骤1 → 步骤2 → ...>
  method_family: "<所属方法族>"
implementation_layer:
  input_qc: "<输入预处理与质控>"
  id_mapping: "<标识符协调规则>"
  external_resource_spec: "<外部资源名称/版本/过滤条件>"
  domain_bias_control: "<领域特定偏差控制>"
  null_model: "<null 模型类型，未提及则写'未提及'>"
  multiple_testing: "<多重检验校正，未提及则写'未提及'>"
  internal_validation: "<内部验证方法>"
  external_validation: "<外部验证方法，未提及则写'未提及'>"
  compute_env: "<硬件/软件/运行时间>"
quantitative_results:
  - "<具体数值结果1>"
  - "<具体数值结果2>"
tools:
  - "<工具/仪器/软件1>"
gaps_noted:
  - "<未报告的维度1>"
"""


def _extract_methods_text(md_path: Path, max_chars: int = 3000) -> str:
    """从 MD 文件提取 Methods 部分"""
    if not md_path.exists():
        return ""
    content = md_path.read_text(encoding="utf-8", errors="ignore")
    # 找 Methods 部分
    for marker in ["## Method", "## Material", "## Experimental", "## 方法", "### Method"]:
        idx = content.lower().find(marker.lower())
        if idx != -1:
            return content[idx:idx + max_chars]
    # 没找到就返回中间部分
    mid = len(content) // 3
    return content[mid:mid + max_chars]


def _extract_paper_metadata(md_path: Path) -> dict:
    """从 MD 文件提取论文元数据（标题、作者、年份、期刊）"""
    if not md_path.exists():
        return {}

    try:
        import re
        content = md_path.read_text(encoding="utf-8", errors="ignore")
        lines = content.split("\n")

        metadata = {}

        # ── 提取期刊和年份 ──
        # 扫描前30行，匹配多种格式
        for line in lines[:30]:
            line_s = line.strip()
            if not line_s or line_s.startswith('#') or line_s.startswith('!'):
                continue

            # 格式1: "Water Research 37 (2003) 4295-4303"
            m = re.search(r'^([A-Z][\w\s&]+?)\s+\d+\s*\((\d{4})\)', line_s)
            if m and 'year' not in metadata:
                metadata['journal'] = m.group(1).strip()
                metadata['year'] = m.group(2)
                continue

            # 格式2: "WATER RESEARCH 46 (2012) I233-I240"
            m = re.search(r'^([A-Z][A-Z\s&]+?)\s+\d+\s*\((\d{4})\)', line_s)
            if m and 'year' not in metadata:
                metadata['journal'] = m.group(1).strip().title()
                metadata['year'] = m.group(2)
                continue

            # 格式3: "Wat. Res. Vol. 34, No. 4, pp. 1097-1106, 2000"
            m = re.search(r'(Wat\.?\s*Res\.?|Water Research|Environ\.?\s*Sci\.?\s*(?:&|and)\s*Technol)', line_s, re.IGNORECASE)
            if m and 'year' not in metadata:
                metadata['journal'] = 'Water Research' if 'wat' in m.group(1).lower() else m.group(1)
                # 取行末的年份（避免抓到 pp. 页码）
                yr = re.search(r'(?:,\s*)(\d{4})\s*$', line_s)
                if not yr:
                    yr = re.search(r'\((\d{4})\)', line_s)
                if yr:
                    metadata['year'] = yr.group(1)
                continue

            # 格式4: 独立年份行 "© 2003 Elsevier" 或 "© 2000 ..."
            if 'year' not in metadata:
                m = re.search(r'[©]\s*(\d{4})', line_s)
                if m:
                    metadata['year'] = m.group(1)
                    continue

            # 格式5: "Received Date: ..." 或 "doi:..." 行含年份
            if 'year' not in metadata:
                if 'received' in line_s.lower() or 'accepted' in line_s.lower() or 'doi' in line_s.lower():
                    years = re.findall(r'\b((?:19|20)\d{2})\b', line_s)
                    if years:
                        metadata['year'] = years[-1]

        # ── 提取标题（第一个 # 标题，跳过 "Accepted Manuscript" 等）──
        skip_titles = {'accepted manuscript', 'graphical abstract', 'highlights', 'contents'}
        found_accepted = False
        for i, line in enumerate(lines[:40]):
            if line.startswith('# ') and not line.startswith('##'):
                title = line[2:].strip()
                if title.lower() in skip_titles:
                    found_accepted = True
                    continue
                if title and not title.startswith('!'):
                    metadata['title'] = title
                    break
            # "Accepted Manuscript" 后的第一个非空纯文本行（跳过图片）可能就是标题
            elif found_accepted and line.strip() and not line.startswith('!') and not line.startswith('#'):
                candidate = line.strip()
                # 标题特征：长度>20，首字母大写，不含冒号（排除元数据行）
                if len(candidate) > 20 and candidate[0].isupper() and ':' not in candidate[:10]:
                    metadata['title'] = candidate
                    break

        # ── 提取作者（标题后的第一个非空非图片行）──
        title_found = False
        title_line_idx = -1
        for i, line in enumerate(lines[:35]):
            if line.startswith('# ') and not line.startswith('##'):
                title_candidate = line[2:].strip()
                if title_candidate.lower() not in skip_titles:
                    title_found = True
                    title_line_idx = i
                    break
            elif found_accepted and line.strip() and not line.startswith('!') and not line.startswith('#'):
                # Plain text title after "Accepted Manuscript"
                if len(line.strip()) > 20:
                    title_found = True
                    title_line_idx = i
                    break

        if title_found and title_line_idx >= 0:
            for line in lines[title_line_idx + 1:title_line_idx + 15]:
                line_s = line.strip()
                # 跳过空行、图片、标题、短行
                if not line_s or line_s.startswith('!') or line_s.startswith('#') or len(line_s) < 10:
                    continue
                # 跳过明显的元数据行（PII, DOI, Reference, To appear in, Received Date）
                if any(kw in line_s for kw in ['PII:', 'DOI:', 'Reference:', 'To appear in:', 'Received Date:', 'Accepted Date:']):
                    continue
                # 作者行特征：含逗号分隔的名字、上标、或星号，且不含冒号
                if ':' not in line_s and ('$^{' in line_s or (',' in line_s and any(c.isupper() for c in line_s))):
                    # 清理 LaTeX 上标和特殊标记
                    authors_raw = re.sub(r'\$[^$]*\$', '', line_s)
                    authors_raw = re.sub(r'[*†‡§¶¹²³⁴⁵⁶⁷⁸⁹⁰ˡ]', '', authors_raw).strip()
                    # 清理残留的上标数字和特殊字符
                    authors_raw = re.sub(r'\s+', ' ', authors_raw).strip()

                    # 提取第一作者姓氏
                    parts = [p.strip() for p in authors_raw.split(',') if p.strip()]
                    if parts and len(parts) >= 2:  # 至少2个作者才认为是作者行
                        # 取第一个作者的最后一个单词作为姓氏
                        first_name_parts = parts[0].split()
                        if first_name_parts:
                            # 跳过单字母（可能是名的首字母），取姓
                            surname_candidates = [w for w in first_name_parts if len(w) > 1 and w[0].isupper()]
                            if surname_candidates:
                                metadata['first_author'] = surname_candidates[-1]
                        metadata['authors'] = authors_raw
                        break

        # ── 验证年份合理性 ──
        if 'year' in metadata:
            try:
                yr = int(metadata['year'])
                if yr < 1950 or yr > 2030:
                    del metadata['year']
            except ValueError:
                del metadata['year']

        return metadata
    except Exception:
        return {}


def _parse_yaml_block(text: str) -> dict:
    """从 LLM 输出中解析 YAML 块"""
    # 去掉 markdown 代码块标记
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        return yaml.safe_load(text) or {}
    except Exception:
        return {"parse_error": text[:200]}


async def run(cluster_dir: Path):
    # 读取 Phase 1 输出
    with open(cluster_dir / "chain_classification.json") as f:
        classification = json.load(f)

    # paper_mapping.json 可能不存在（新版 Phase 1 不生成），初始化为空字典
    paper_mapping_file = cluster_dir / "paper_mapping.json"
    if paper_mapping_file.exists():
        with open(paper_mapping_file) as f:
            paper_mapping = json.load(f)
    else:
        paper_mapping = {}

    with open(cluster_dir / "selected_chains.json") as f:
        all_chains = json.load(f)

    chain_texts = {c["chain_id"]: c["chain_text"] for c in all_chains}

    # 筛选 A-主线链
    a_chains = [
        c for c in classification["chains"]
        if c["grade"] == "A" and c["subtype"] == "主线"
    ]
    print(f"[Phase 2] {len(a_chains)} A-主线链，并行提取中...")

    # 断点续传
    progress_file = cluster_dir / ".extraction_progress.json"
    completed = set()
    if progress_file.exists():
        with open(progress_file) as f:
            completed = set(json.load(f).get("completed_papers", []))
        print(f"  断点续传：已完成 {len(completed)} 篇")

    pending = [c for c in a_chains if c["paper_id"] not in completed]
    if not pending:
        print("  所有论文已提取，跳过")
        return

    # 构建 prompts
    prompts = []
    meta_list = []
    updated_paper_mapping = {}  # 用于收集更新后的元数据

    for chain in pending:
        paper_id = chain["paper_id"]
        meta = paper_mapping.get(paper_id, {})
        md_path = cluster_dir / "md" / f"{paper_id}.md"

        # 从 MD 文件提取真实元数据
        real_metadata = _extract_paper_metadata(md_path)

        # 更新 paper_mapping
        if real_metadata:
            year = real_metadata.get('year', meta.get('year', 'Unknown'))
            first_author = real_metadata.get('first_author', '')

            # 构建 short_name
            if first_author and year != 'Unknown':
                short_name = f"{first_author}_{year}"
            else:
                short_name = meta.get("short_name", paper_id[:8])

            updated_meta = {
                "paper_id": paper_id,
                "short_name": short_name,
                "title": real_metadata.get('title', meta.get('title', 'Unknown')),
                "authors": real_metadata.get('authors', meta.get('authors', 'Unknown')),
                "year": year,
                "journal": real_metadata.get('journal', meta.get('journal', 'Unknown')),
                "bibitem_key": short_name
            }
            updated_paper_mapping[paper_id] = updated_meta
        else:
            # 保留原有元数据
            short_name = meta.get("short_name", paper_id[:8])
            updated_paper_mapping[paper_id] = meta

        chain_text = chain_texts.get(chain["chain_id"], "")
        methods_text = _extract_methods_text(md_path)

        prompts.append(EXTRACT_PROMPT.format(
            short_name=short_name,
            paper_id=paper_id,
            chain_text=chain_text[:4000],
            methods_text=methods_text,
        ))
        meta_list.append({
            "paper_id": paper_id,
            "short_name": short_name,
            "title": updated_paper_mapping[paper_id].get("title", ""),
            "bibitem_key": updated_paper_mapping[paper_id].get("bibitem_key", ""),
        })

    # 并行调用 LLM
    results = await llm_parallel(prompts, temperature=0.2)

    # 解析并合并结果
    extractions = []

    # 加载已有结果
    output_file = cluster_dir / "paper_extractions.yaml"
    if output_file.exists() and completed:
        with open(output_file) as f:
            existing = yaml.safe_load(f) or []
        extractions.extend(existing)

    for meta, raw in zip(meta_list, results):
        parsed = _parse_yaml_block(raw)
        entry = {
            "paper_id": meta["paper_id"],
            "short_name": meta["short_name"],
            "title": meta["title"],
            "bibitem_key": meta["bibitem_key"],
            **parsed,
        }
        extractions.append(entry)
        completed.add(meta["paper_id"])

        # 保存进度
        with open(progress_file, "w") as f:
            json.dump({"completed_papers": list(completed), "total": len(a_chains)}, f)

    # 写入最终结果
    with open(output_file, "w", encoding="utf-8") as f:
        yaml.dump(extractions, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    # 更新 paper_mapping.json（合并新提取的元数据 + 补全所有论文）
    if updated_paper_mapping:
        full_mapping = paper_mapping.copy()
        full_mapping.update(updated_paper_mapping)
    else:
        full_mapping = paper_mapping.copy()

    # 为所有 Unknown 论文尝试从 MD 文件提取元数据
    md_dir = cluster_dir / "md"
    enriched_count = 0
    if md_dir.exists():
        for pid, meta in full_mapping.items():
            if meta.get("short_name", "Unknown_Unknown") != "Unknown_Unknown":
                continue  # 已有元数据
            md_path = md_dir / f"{pid}.md"
            real_metadata = _extract_paper_metadata(md_path)
            if real_metadata:
                year = real_metadata.get('year', 'Unknown')
                first_author = real_metadata.get('first_author', '')
                short_name = f"{first_author}_{year}" if first_author and year != 'Unknown' else meta.get("short_name", pid[:8])
                full_mapping[pid] = {
                    "paper_id": pid,
                    "short_name": short_name,
                    "title": real_metadata.get('title', meta.get('title', 'Unknown')),
                    "authors": real_metadata.get('authors', meta.get('authors', 'Unknown')),
                    "year": year,
                    "journal": real_metadata.get('journal', meta.get('journal', 'Unknown')),
                    "bibitem_key": short_name
                }
                enriched_count += 1

    mapping_file = cluster_dir / "paper_mapping.json"
    with open(mapping_file, "w", encoding="utf-8") as f:
        json.dump(full_mapping, f, ensure_ascii=False, indent=2)

    updated_count = len(updated_paper_mapping) + enriched_count
    print(f"  ✓ 更新 paper_mapping.json ({updated_count} 篇元数据, 其中 {enriched_count} 篇非A-主线补全)")

    print(f"[Phase 2] 完成，{len(extractions)} 篇 → paper_extractions.yaml")


if __name__ == "__main__":
    cluster_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    asyncio.run(run(cluster_dir))
