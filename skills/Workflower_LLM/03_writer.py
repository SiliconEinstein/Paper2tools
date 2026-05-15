"""
Phase 3: 并行生成各章节 LaTeX + 决策树 + 编译 PDF
Agent 负责调度、渲染、编译

用法: python 03_writer.py <cluster_dir>
"""

import asyncio
import json
import re
import subprocess
import sys
import yaml
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from llm_client import llm, llm_parallel

# ── Prompts ──────────────────────────────────────────────────────────────────

INTRO_PROMPT = """基于以下工作流信息，用中文撰写 LaTeX 综述的引言部分（\\section{{引言}}）。

工作流主题: {workflow_name}
阶段列表: {stages}
论文数量: {paper_count}

要求：
1. 包含研究背景（2-3段）
2. 包含方法概述
3. 包含工作流决策树图片引用：
   \\begin{{figure}}[H]
   \\centering
   \\includegraphics[width=\\textwidth,height=0.85\\textheight,keepaspectratio]{{decision_tree.png}}
   \\caption{{工作流决策树}}
   \\label{{fig:decision_tree}}
   \\end{{figure}}
4. 术语首次出现给英文对照
5. 只输出 LaTeX 代码，不要 preamble 和 \\begin{{document}}
6. 不要用 markdown 代码块包裹（不要 ```latex）
"""

STAGE_PROMPT = """基于以下论文提取信息，用中文撰写 LaTeX 综述的一个阶段章节。

阶段名称: {stage_name}
阶段描述: {stage_desc}
相关论文提取:
{extractions_text}

要求：
1. \\section{{{stage_name}}} 开头
2. 包含核心方法说明（含公式，所有符号定义）
3. **必须**包含至少2个彩色框，优先级顺序：
   - toolbox（工具箱）：列出该阶段常用的仪器、软件、试剂盒等，含型号/参数/用途
   - parambox（参数框）：关键参数的推荐值与调优建议
   - casebox（案例框）：典型应用案例或数值结果
   - pitfallbox（陷阱框）：常见错误与解决方案
4. 彩色框格式示例：
   \\begin{{toolbox}}
   \\textbf{{常用工具}}：
   \\begin{{itemize}}
   \\item 原子吸收光谱仪（AAS）：金属浓度定量，检出限 0.01 mg/L
   \\item 0.45 μm 过滤器：溶解态/颗粒态分离
   \\end{{itemize}}
   \\end{{toolbox}}
5. 工具信息非常重要，如果论文提取中有"工具"字段，必须在 toolbox 中体现
6. 只输出 LaTeX 代码，不要用 markdown 代码块包裹
"""

CONCLUSION_PROMPT = """基于以下工作流信息，用中文撰写 LaTeX 综述的结论部分（\\section{{结论}}）。

工作流主题: {workflow_name}
主要发现: {key_findings}
开放问题: {open_questions}

要求：
1. 总结主要发现（编号列表）
2. 讨论局限性
3. 展望未来方向
4. 只输出 LaTeX 代码，不要用 markdown 代码块包裹
"""

LAYER_DOC_PROMPT = """基于以下信息，用中文生成 3 层工作流文档（Markdown 格式）。

工作流主题: {workflow_name}
阶段结构: {stages_json}
论文提取摘要: {extractions_summary}

输出格式：
# 3 层工作流：{workflow_name}

## Layer 1: 算法层（做什么）
### 阶段 N: [名称]
**目标**：...
**步骤**：1. ... 2. ...
**核心公式**：...
**输出**：...

## Layer 2: 实现层（怎么做）
### 阶段 N 实现细节
**仪器参数**：...
**推荐默认值**：...

## Layer 3: 陷阱与最佳实践
### 陷阱 N: [名称]
**问题**：...
**解决方案**：...

## 验证清单
- [ ] 检查项1
"""

DOT_PROMPT = """生成 Graphviz DOT 格式的工作流决策树。

阶段信息（JSON）:
{stages_json}

要求：
1. 图形属性：rankdir=TB, dpi=150, size="10,14!", ratio=fill
2. 节点默认属性：shape=box, style=filled, fontname="Arial", fontsize=11, margin=0.3
3. 节点使用简单文本标签（不用 HTML TABLE）
4. 标签格式：阶段名\\n(覆盖率%)\\n\\n方法1 (N篇)\\n方法2 (N篇)
5. 颜色：高覆盖(>=80%) #D5F5E3，中覆盖 #FEF5E7，低覆盖 #FDEDEC
6. 输入节点 #D6EAF8，输出节点 #F4ECF7
7. 边粗细与使用率成正比（penwidth 1.0-4.5）
8. 边默认属性：fontsize=9
9. 只输出 DOT 代码，不要任何解释
"""

# ── Helpers ──────────────────────────────────────────────────────────────────

PREAMBLE = r"""\documentclass[12pt,a4paper]{article}
\usepackage{fontspec}
\usepackage{xeCJK}
\setCJKmainfont{AR PL UMing CN}
\setCJKsansfont{AR PL KaitiM GB}
\setCJKmonofont{AR PL KaitiM GB}
\usepackage{graphicx}
\usepackage{float}
\usepackage{amsmath}
\usepackage{geometry}
\usepackage{tcolorbox}
\usepackage{hyperref}
\geometry{left=2.5cm,right=2.5cm,top=2.5cm,bottom=2.5cm}
\newtcolorbox{toolbox}[1][]{colback=green!3,colframe=green!40!black,breakable,fonttitle=\bfseries\sffamily,title={推荐工具},#1}
\newtcolorbox{parambox}[1][]{colback=blue!3,colframe=blue!40!black,breakable,fonttitle=\bfseries\sffamily,title={关键参数},#1}
\newtcolorbox{casebox}[1][]{colback=orange!4,colframe=orange!50!black,breakable,fonttitle=\bfseries\sffamily,title={案例研究},#1}
\newtcolorbox{pitfallbox}[1][]{colback=red!3,colframe=red!50!black,breakable,fonttitle=\bfseries\sffamily,title={常见陷阱},#1}
"""


def _build_bibliography(paper_mapping: dict, a_paper_ids: list[str]) -> str:
    lines = ["\\begin{thebibliography}{99}"]
    for pid in a_paper_ids:
        meta = paper_mapping.get(pid, {})
        key = meta.get("bibitem_key", pid[:8])
        authors = meta.get("authors", "")
        title = meta.get("title", "")
        journal = meta.get("journal", "")
        year = meta.get("year", "")
        doi = meta.get("doi", "")

        ref = f"\\bibitem{{{key}}}\n{authors}.\n{title}.\n"
        if journal:
            ref += f"\\textit{{{journal}}}"
        if year:
            ref += f", {year}"
        if doi:
            ref += f". doi:{doi}"
        ref += ".\n"
        lines.append(ref)
    lines.append("\\end{thebibliography}")
    return "\n".join(lines)


def _extract_dot(text: str) -> str:
    """从 LLM 输出中提取 DOT 代码"""
    text = text.strip()
    # 去掉 markdown 代码块
    m = re.search(r"```(?:dot)?\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    if text.startswith("digraph") or text.startswith("graph"):
        return text
    return text


async def run(cluster_dir: Path):
    parts = cluster_dir.resolve().name.split("_")
    cluster_num = parts[1] if len(parts) > 1 else "0"

    # 读取所有输入
    with open(cluster_dir / "workflow_structure.json") as f:
        structure = json.load(f)
    with open(cluster_dir / "paper_extractions.yaml") as f:
        extractions = yaml.safe_load(f) or []
    with open(cluster_dir / "paper_mapping.json") as f:
        paper_mapping = json.load(f)
    with open(cluster_dir / "chain_classification.json") as f:
        classification = json.load(f)
    with open(cluster_dir / "workflow_meta.json") as f:
        meta = json.load(f)

    workflow_name = meta.get("workflow_name", "工作流综述")
    stages = structure["stages"]
    a_paper_ids = list({
        c["paper_id"] for c in classification["chains"]
        if c["grade"] == "A" and c["subtype"] == "主线"
    })

    print(f"[Phase 3] 并行生成 {len(stages)} 个阶段章节 + 引言 + 结论 + 决策树...")

    # ── 并行生成所有章节 ──────────────────────────────────────────────────────

    # 为每个阶段准备提取摘要
    def _stage_extractions(stage_idx: int, stage_name: str, stage_desc: str) -> str:
        """为每个阶段匹配相关论文，使用关键词匹配 + 轮询分配策略"""
        # 从阶段名称和描述中提取关键词
        keywords = []
        # 阶段名称分词
        for word in stage_name.replace("与", " ").replace("/", " ").split():
            if len(word) >= 2:
                keywords.append(word)
        # 阶段描述关键词
        for word in stage_desc.replace("，", " ").replace("、", " ").replace("。", " ").split():
            if len(word) >= 2:
                keywords.append(word)

        # 计算每篇论文与阶段的相关性得分
        scored = []
        for e in extractions:
            score = 0
            # 搜索范围：algorithm_layer, implementation_layer, tools, method_family
            search_text = (
                str(e.get("algorithm_layer", "")) + " " +
                str(e.get("implementation_layer", "")) + " " +
                str(e.get("tools", [])) + " " +
                str(e.get("algorithm_layer", {}).get("method_family", ""))
            ).lower()

            for kw in keywords:
                if kw.lower() in search_text:
                    score += 1

            scored.append((score, e))

        # 按得分排序，取前5篇
        scored.sort(key=lambda x: x[0], reverse=True)
        relevant = [e for score, e in scored[:5] if score > 0]

        # 如果没有匹配到，使用轮询策略分配不同论文
        if not relevant:
            start_idx = (stage_idx * 3) % len(extractions)
            relevant = extractions[start_idx:start_idx + 3]
            if len(relevant) < 3:
                relevant += extractions[:3 - len(relevant)]

        lines = []
        for e in relevant:
            lines.append(f"[{e.get('short_name', '')}]")
            al = e.get("algorithm_layer", {})
            if isinstance(al, dict):
                lines.append(f"  机制: {al.get('mechanism_detail', '')[:300]}")
            il = e.get("implementation_layer", {})
            if isinstance(il, dict):
                lines.append(f"  实现: {il.get('input_qc', '')[:200]}")
            # 添加工具信息
            tools = e.get("tools", [])
            if tools:
                tools_str = "; ".join(tools[:5])  # 最多5个工具
                lines.append(f"  工具: {tools_str}")
        return "\n".join(lines)

    stages_json = json.dumps(stages, ensure_ascii=False, indent=2)
    extractions_summary = "\n".join(
        f"[{e.get('short_name','')}] {e.get('title','')[:80]}"
        for e in extractions[:10]
    )
    key_findings = "\n".join(
        f"- {e.get('short_name','')}: {str(e.get('quantitative_results', ['']))[:150]}"
        for e in extractions[:5]
    )

    # 构建所有 prompts（引言 + 各阶段 + 结论 + 决策树 + 3层文档）
    prompts = [
        INTRO_PROMPT.format(
            workflow_name=workflow_name,
            stages=", ".join(s["name"] for s in stages),
            paper_count=len(a_paper_ids),
        ),
        *[
            STAGE_PROMPT.format(
                stage_name=s["name"],
                stage_desc=s.get("description", ""),
                extractions_text=_stage_extractions(i, s["name"], s.get("description", "")),
            )
            for i, s in enumerate(stages)
        ],
        CONCLUSION_PROMPT.format(
            workflow_name=workflow_name,
            key_findings=key_findings,
            open_questions="方法标准化、跨领域适用性、自动化流程",
        ),
        DOT_PROMPT.format(stages_json=stages_json),
        LAYER_DOC_PROMPT.format(
            workflow_name=workflow_name,
            stages_json=stages_json,
            extractions_summary=extractions_summary,
        ),
    ]

    results = await llm_parallel(prompts, temperature=0.3)

    # 解包结果并清理 markdown 代码块标记
    def _clean_latex(text: str) -> str:
        """移除 LLM 输出中的 markdown 代码块标记"""
        text = text.strip()
        # 移除完整的 ```latex ... ``` 或 ``` ... ``` 包裹
        text = re.sub(r'```(?:latex)?\s*\n(.*?)\n```', r'\1', text, flags=re.DOTALL)
        # 移除开头的 ```latex 或 ```
        text = re.sub(r'^```(?:latex)?\s*\n?', '', text)
        # 移除结尾的 ```
        text = re.sub(r'\n?```\s*$', '', text)
        # 移除任何残留的 ``` 标记
        text = text.replace('```latex', '').replace('```', '')
        return text.strip()

    intro_tex = _clean_latex(results[0])
    stage_texs = [_clean_latex(s) for s in results[1:1 + len(stages)]]
    conclusion_tex = _clean_latex(results[1 + len(stages)])
    dot_raw = results[2 + len(stages)]
    layer_doc = results[3 + len(stages)]

    # ── 写 workflow_3layer.md ─────────────────────────────────────────────────
    (cluster_dir / "workflow_3layer.md").write_text(layer_doc, encoding="utf-8")
    print("  ✓ workflow_3layer.md")

    # ── 写 decision_tree.dot + 渲染 PNG ──────────────────────────────────────
    dot_code = _extract_dot(dot_raw)
    dot_path = cluster_dir / "decision_tree.dot"
    dot_path.write_text(dot_code, encoding="utf-8")

    png_path = cluster_dir / "decision_tree.png"
    r = subprocess.run(
        ["dot", "-Tpng", "-Gdpi=150", str(dot_path), "-o", str(png_path)],
        capture_output=True, text=True
    )
    if r.returncode != 0:
        print(f"  ⚠ dot 渲染失败: {r.stderr[:200]}")
    else:
        print(f"  ✓ decision_tree.png ({png_path.stat().st_size // 1024}KB)")

    # ── 拼装 LaTeX ────────────────────────────────────────────────────────────
    bib = _build_bibliography(paper_mapping, a_paper_ids)
    title_date = f"\\title{{\\textbf{{{workflow_name}}}}}\n\\author{{基于{len(a_paper_ids)}篇文献的工作流分析}}\n\\date{{\\today}}\n"

    tex_parts = [
        PREAMBLE,
        title_date,
        "\\begin{document}\n\\maketitle\n",
        intro_tex,
        "\n".join(stage_texs),
        conclusion_tex,
        bib,
        "\\end{document}",
    ]
    tex_content = "\n\n".join(tex_parts)

    tex_path = cluster_dir / f"review_cluster_{cluster_num}.tex"
    tex_path.write_text(tex_content, encoding="utf-8")
    print(f"  ✓ review_cluster_{cluster_num}.tex")

    # ── 编译 PDF ──────────────────────────────────────────────────────────────
    print("  编译 PDF (xelatex pass 1)...")
    for _ in range(2):
        r = subprocess.run(
            ["xelatex", "-interaction=nonstopmode", tex_path.name],
            capture_output=True, text=True, cwd=cluster_dir
        )
    pdf_path = cluster_dir / f"review_cluster_{cluster_num}.pdf"
    if pdf_path.exists() and pdf_path.stat().st_size > 1000:
        print(f"  ✓ review_cluster_{cluster_num}.pdf ({pdf_path.stat().st_size // 1024}KB)")
    else:
        print(f"  ⚠ PDF 编译失败，保留 .tex 文件")
        if r.stderr:
            print(f"    {r.stderr[-300:]}")

    # ── 清理编译产物 ──────────────────────────────────────────────────────────
    for ext in [".aux", ".log", ".out"]:
        p = cluster_dir / f"review_cluster_{cluster_num}{ext}"
        if p.exists():
            p.unlink()

    # ── 更新 workflow_meta.json（补充 keywords）──────────────────────────────
    print("  提取 keywords...")

    # 从 paper_extractions.yaml 提取关键词
    all_methods = []
    all_tools = []
    for e in extractions:
        # 提取 method_family
        al = e.get("algorithm_layer", {})
        if isinstance(al, dict) and al.get("method_family"):
            all_methods.append(al["method_family"])
        # 提取 tools
        tools = e.get("tools", [])
        if tools:
            all_tools.extend(tools[:3])  # 每篇最多3个工具

    # 统计频次，取 top 关键词
    from collections import Counter
    method_counter = Counter(all_methods)
    tool_counter = Counter(all_tools)

    keywords_cn = [m for m, _ in method_counter.most_common(5)]
    keywords_cn.extend([t for t, _ in tool_counter.most_common(5)])
    keywords_cn = list(dict.fromkeys(keywords_cn))[:10]  # 去重，最多8个

    # 调用 LLM 翻译为英文
    if keywords_cn:
        translate_prompt = f"""将以下中文关键词翻译为英文，保持专业术语准确性。

中文关键词: {', '.join(keywords_cn)}

请严格按以下 JSON 格式输出：
{{"keywords_en": ["<英文1>", "<英文2>", ...]}}
"""
        translate_result = await llm(translate_prompt, temperature=0.1)
        try:
            translate_data = json.loads(translate_result.strip().replace("```json", "").replace("```", ""))
            keywords_en = translate_data.get("keywords_en", [])
        except:
            keywords_en = keywords_cn  # 翻译失败则保持原样
    else:
        keywords_en = []

    # 更新 workflow_meta.json
    meta_path = cluster_dir / "workflow_meta.json"
    with open(meta_path) as f:
        meta = json.load(f)

    meta["keywords"] = keywords_cn
    meta["keywords_en"] = keywords_en

    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"  ✓ 更新 workflow_meta.json (keywords: {len(keywords_cn)})")

    print(f"[Phase 3] 完成")
    print(f"  结果: PDF={pdf_path.stat().st_size // 1024}K" if pdf_path.exists() else "  结果: PDF 编译失败")


if __name__ == "__main__":
    cluster_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    asyncio.run(run(cluster_dir))
