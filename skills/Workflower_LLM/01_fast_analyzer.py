"""
Phase 1 Fast: 仅基于 selected_chains.json 快速分析工作流主线
不读取 MD 文件，直接从推理链文本中提取核心信息

用法: python 01_fast_analyzer.py <cluster_dir>
"""

import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from llm_client import llm

# ── Prompts ──────────────────────────────────────────────────────────────────

WORKFLOW_ANALYSIS_PROMPT = """你是工作流分析专家。基于以下推理链集合，识别核心工作流主线。

推理链数据（{num_chains} 条）:
{chains_summary}

请严格按以下 JSON 格式输出：

{{
  "workflow_name": "<工作流核心主题，10字以内，中文>",
  "workflow_name_en": "<工作流核心主题的英文翻译，10词以内>",
  "research_problem": "<该工作流解决的核心研究问题，一句话>",
  "core_stages": [
    {{"name": "<阶段名>", "description": "<简述>", "coverage": <覆盖率0-1>}},
    ...
  ],
  "chain_classification": [
    {{
      "chain_id": "<chain_id>",
      "paper_id": "<paper_id>",
      "grade": "A|B|C",
      "subtype": "主线|变体|边缘",
      "rationale": "<分类理由，一句话>"
    }},
    ...
  ],
  "key_papers": ["<paper_id1>", "<paper_id2>", ...],
  "recommended_deep_read": ["<paper_id1>", "<paper_id2>", ...]
}}

分类标准：
- A-主线：完整覆盖核心工作流，方法典型，结果完整
- B-变体：覆盖部分核心阶段，或有方法变体
- C-边缘：仅涉及个别阶段，或主题偏离

recommended_deep_read: 最多5篇最值得深度阅读的论文（用于后续详细提取）
"""

# paper_mapping 由 Phase 2 从 MD 文件生成，Phase 1 不再生成


async def run(cluster_dir: Path):
    from datetime import datetime

    parts = cluster_dir.resolve().name.split("_")
    cluster_num = parts[1] if len(parts) > 1 else "0"

    # 推断 domain（从路径中提取）
    domain = "unknown"
    path_parts = cluster_dir.resolve().parts
    for i, part in enumerate(path_parts):
        if part == "data" and i + 1 < len(path_parts):
            domain = path_parts[i + 1]
            break

    # 读取 selected_chains.json
    chains_file = cluster_dir / "selected_chains.json"
    if not chains_file.exists():
        print(f"[Error] {chains_file} 不存在")
        return

    with open(chains_file) as f:
        chains = json.load(f)

    print(f"[Phase 1 Fast] 分析 {len(chains)} 条推理链...")

    # ── Step 1: 构建推理链摘要 ──────────────────────────────────────────────
    chains_summary = []
    for i, chain in enumerate(chains[:50], 1):  # 最多50条避免超长
        summary = f"[Chain {i}] paper_id={chain['paper_id']}, chain_id={chain['chain_id']}\n"
        summary += f"  Steps: {chain['num_steps']}\n"
        summary += f"  Text: {chain['chain_text'][:800]}...\n"  # 每条最多800字符
        chains_summary.append(summary)

    chains_summary_text = "\n".join(chains_summary)

    # ── Step 2: 调用 LLM 分析工作流主线 ──────────────────────
    print("  调用 LLM 分析工作流主线...")

    workflow_result = await llm(
        WORKFLOW_ANALYSIS_PROMPT.format(
            num_chains=len(chains),
            chains_summary=chains_summary_text
        ),
        temperature=0.2
    )

    # ── Step 3: 解析结果 ──────────────────────────────────────────────────
    def _clean_json(text: str) -> str:
        """清理 LLM 输出中的 markdown 代码块标记"""
        text = text.strip()
        # 移除 ```json ... ``` 包裹
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        text = text.replace("```json", "").replace("```", "")
        return text.strip()

    try:
        workflow_analysis = json.loads(_clean_json(workflow_result))
    except json.JSONDecodeError as e:
        print(f"[Error] JSON 解析失败: {e}")
        print(f"  Workflow result (前500字符): {workflow_result[:500]}")
        # 尝试保存原始输出用于调试
        (cluster_dir / "debug_workflow_output.txt").write_text(workflow_result, encoding="utf-8")
        print(f"  原始输出已保存到 debug_workflow_output.txt")
        return

    # ── Step 4: 写入输出文件 ──────────────────────────────────────────────

    # chain_classification.json
    classification_output = {
        "workflow_name": workflow_analysis["workflow_name"],
        "research_problem": workflow_analysis["research_problem"],
        "chains": workflow_analysis["chain_classification"],
        "statistics": {
            "total": len(chains),
            "A_main": sum(1 for c in workflow_analysis["chain_classification"] if c["grade"] == "A" and c["subtype"] == "主线"),
            "B_variant": sum(1 for c in workflow_analysis["chain_classification"] if c["grade"] == "B"),
            "C_edge": sum(1 for c in workflow_analysis["chain_classification"] if c["grade"] == "C")
        }
    }

    with open(cluster_dir / "chain_classification.json", "w", encoding="utf-8") as f:
        json.dump(classification_output, f, ensure_ascii=False, indent=2)
    print(f"  ✓ chain_classification.json ({classification_output['statistics']['A_main']} A-主线)")

    # workflow_structure.json
    workflow_structure = {
        "workflow_name": workflow_analysis["workflow_name"],
        "stages": workflow_analysis["core_stages"]
    }
    with open(cluster_dir / "workflow_structure.json", "w", encoding="utf-8") as f:
        json.dump(workflow_structure, f, ensure_ascii=False, indent=2)
    print(f"  ✓ workflow_structure.json ({len(workflow_analysis['core_stages'])} 阶段)")

    # workflow_meta.json（Phase 1a 生成基础字段）
    workflow_meta = {
        "workflow_name": workflow_analysis["workflow_name"],
        "workflow_name_en": workflow_analysis["workflow_name_en"],
        "research_problem": workflow_analysis["research_problem"],
        "main_stages": [s["name"] for s in workflow_analysis["core_stages"]],
        "cluster_id": cluster_num,
        "domain": domain,
        "total_chains": len(chains),
        "creation_date": datetime.now().strftime("%Y-%m-%d"),
        "key_papers": workflow_analysis["key_papers"],
        "recommended_deep_read": workflow_analysis["recommended_deep_read"],
        # Phase 3 补充字段（占位）
        "keywords": [],
        "keywords_en": []
    }
    with open(cluster_dir / "workflow_meta.json", "w", encoding="utf-8") as f:
        json.dump(workflow_meta, f, ensure_ascii=False, indent=2)
    print(f"  ✓ workflow_meta.json")

    # paper_inventory.md（简化版，不依赖 paper_mapping）
    inventory_lines = [
        f"# Cluster {cluster_num}: {workflow_analysis['workflow_name']}\n",
        f"**研究问题**: {workflow_analysis['research_problem']}\n",
        f"**总链数**: {len(chains)}\n",
        f"**A-主线**: {classification_output['statistics']['A_main']}\n",
        f"**推荐深度阅读**: {len(workflow_analysis['recommended_deep_read'])} 篇\n",
        "\n## 论文清单\n"
    ]

    for pid in workflow_analysis["key_papers"]:
        deep_read_mark = "⭐" if pid in workflow_analysis["recommended_deep_read"] else ""
        inventory_lines.append(f"- {deep_read_mark} {pid}\n")

    with open(cluster_dir / "paper_inventory.md", "w", encoding="utf-8") as f:
        f.writelines(inventory_lines)
    print(f"  ✓ paper_inventory.md")

    print(f"[Phase 1 Fast] 完成")
    print(f"  工作流: {workflow_analysis['workflow_name']}")
    print(f"  核心阶段: {len(workflow_analysis['core_stages'])}")
    print(f"  推荐深度阅读: {workflow_analysis['recommended_deep_read']}")


if __name__ == "__main__":
    cluster_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    asyncio.run(run(cluster_dir))
