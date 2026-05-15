#!/usr/bin/env python3
"""
从 paper_extractions.yaml + selected_chains.json + workflow_structure.json
直接生成 GAIA schema.json，不依赖 review PDF/Markdown
"""
import json
import yaml
import sys
import os
from pathlib import Path
from typing import Any
import asyncio
import re

# 添加 Workflower_LLM 到路径以使用其 llm_client
sys.path.insert(0, str(Path(__file__).parent / "Workflower_LLM"))
from llm_client import llm, llm_parallel


def parse_llm_json(text: str) -> dict:
    """解析 LLM 返回的 JSON，处理常见格式问题"""
    text = text.strip()
    # 移除 markdown 代码块标记
    text = re.sub(r'```(?:json)?\s*\n(.*?)\n```', r'\1', text, flags=re.DOTALL)
    text = re.sub(r'^```(?:json)?\s*\n?', '', text)
    text = re.sub(r'\n?```\s*$', '', text)
    text = text.replace('```json', '').replace('```', '')

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        # 尝试修复常见问题：未转义的反斜杠
        # 在 JSON 字符串中，\后面如果不是合法转义字符，需要转义为 \\
        print(f"  ⚠ JSON 解析失败，尝试修复: {e}")
        # 简单策略：将所有单个 \ 替换为 \\（但保留已经转义的）
        fixed = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', text)
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            print(f"  ✗ 修复失败，原始文本:\n{text[:500]}")
            raise


async def generate_schema(cluster_dir: Path) -> dict[str, Any]:
    """生成完整的 schema.json"""

    # ── 加载输入文件 ──────────────────────────────────────────────────────────
    with open(cluster_dir / "paper_extractions.yaml") as f:
        extractions = yaml.safe_load(f)

    with open(cluster_dir / "selected_chains.json") as f:
        chains = json.load(f)

    with open(cluster_dir / "workflow_structure.json") as f:
        workflow_struct = json.load(f)

    workflow_name = workflow_struct["workflow_name"]
    stages = workflow_struct["stages"]

    # 过滤掉有 parse_error 的论文
    valid_extractions = [e for e in extractions if "parse_error" not in e]

    print(f"[生成 Schema] {workflow_name}")
    print(f"  论文: {len(valid_extractions)} 篇")
    print(f"  推理链: {len(chains)} 条")
    print(f"  阶段: {len(stages)} 个")

    # ── 1. 生成 Workflow 描述和结论 ──────────────────────────────────────────
    print("\n[1/6] 生成 workflow 描述和结论...")

    # 提取推理链摘要
    chain_samples = "\n\n".join([
        f"[Chain {i+1}] {c['chain_text'][:500]}..."
        for i, c in enumerate(chains[:5])
    ])

    workflow_prompt = f"""基于以下超导比热计算工作流的推理链样本，生成工作流的总体描述和结论。

工作流名称: {workflow_name}

阶段列表:
{chr(10).join(f"- {s['name']}: {s['description']}" for s in stages)}

推理链样本（前5条）:
{chain_samples}

请生成以下内容（JSON格式）:
{{
  "description": "工作流的总体描述（2-3段，包含科学问题、整体流程、适用场景）",
  "conclusions": "结论总结（1-2段，总结主要发现和方法特点）",
  "open_issues": "未解决问题和局限性（1段，去掉套话）",
  "claims": [
    {{"id": "c1", "text": "原子声明1（可包含LaTeX公式）"}},
    {{"id": "c2", "text": "原子声明2"}},
    ...
  ]
}}

要求:
- description 要包含物理背景和计算目标
- conclusions 要量化、具体
- claims 拆分为独立的、可验证的原子声明（3-5条）
- 使用 LaTeX 公式（行内用 $...$，独立行用 $$...$$）
- CRITICAL: JSON字符串中的反斜杠必须转义为双反斜杠（\\\\），例如 \\\\Delta、\\\\sqrt
"""

    workflow_result = await llm(workflow_prompt, temperature=0.2)
    workflow_data = parse_llm_json(workflow_result)

    # ── 2. 生成 Steps（包含 substeps） ──────────────────────────────────────
    print("[2/6] 生成 steps 和 substeps...")

    steps = []
    for stage_idx, stage in enumerate(stages):
        stage_name = stage["name"]
        stage_desc = stage["description"]

        # 找到与该阶段相关的推理链
        relevant_chains = []
        for chain in chains:
            chain_text = chain["chain_text"].lower()
            # 简单关键词匹配
            keywords = stage_name.replace("与", " ").replace("/", " ").split()
            if any(kw.lower() in chain_text for kw in keywords if len(kw) >= 2):
                relevant_chains.append(chain)

        if not relevant_chains:
            relevant_chains = chains[:3]  # fallback

        # 提取该阶段相关的论文
        relevant_papers = []
        for e in valid_extractions[:5]:
            al = e.get("algorithm_layer", {})
            if isinstance(al, dict):
                mech = str(al.get("mechanism_detail", ""))
                if any(kw in mech for kw in keywords if len(kw) >= 2):
                    relevant_papers.append(e)

        if not relevant_papers:
            relevant_papers = valid_extractions[:3]

        # 构建 step prompt
        chains_text = "\n\n".join([
            f"[Chain {i+1}]\n{c['chain_text'][:800]}"
            for i, c in enumerate(relevant_chains[:3])
        ])

        papers_text = "\n\n".join([
            f"[{e.get('short_name', '')}]\n"
            f"机制: {str(e.get('algorithm_layer', {}).get('mechanism_detail', ''))[:400]}\n"
            f"实现: {str(e.get('implementation_layer', {}).get('input_qc', ''))[:300]}\n"
            f"工具: {', '.join(e.get('tools', [])[:5])}"
            for e in relevant_papers
        ])

        step_prompt = f"""基于以下信息，为工作流阶段"{stage_name}"生成结构化描述。

阶段描述: {stage_desc}

相关推理链:
{chains_text}

相关论文提取:
{papers_text}

请生成以下JSON:
{{
  "id": "step_{stage_idx + 1}",
  "name": "{stage_name}",
  "description": "该阶段的1-2句话概述",
  "substeps": [
    {{
      "name": "子步骤1名称",
      "description": "详细描述（包含公式、具体操作）"
    }},
    ...
  ],
  "recommended_tools": "- 工具1: 用途和参数\\n- 工具2: ...",
  "key_parameters": "- 参数1: 推荐值和调优建议\\n- 参数2: ...",
  "common_pitfalls": "- 陷阱1: 问题描述 → 解决方案\\n- 陷阱2: ..."
}}

要求:
- substeps 应该是该阶段的逻辑子步骤（2-4个），每个有清晰的name和详细的description
- description 中保留 LaTeX 公式，但必须正确转义：JSON字符串中的反斜杠必须写成双反斜杠（\\\\），例如 \\\\sqrt、\\\\Delta、\\\\mathbf
- recommended_tools 只列出具名软件/工具，不要通用类别
- key_parameters 要具体（参数名+数值范围+物理意义）
- common_pitfalls 要实用（常见错误+解决方案）

CRITICAL: 在JSON字符串中，所有LaTeX公式的反斜杠必须转义为双反斜杠。例如：
- 错误: "\\sqrt{{x}}"
- 正确: "\\\\sqrt{{x}}"
"""

        step_result = await llm(step_prompt, temperature=0.3)
        step_data = parse_llm_json(step_result)

        # 添加 method_ids 和 paper_ref_ids（稍后填充）
        step_data["method_ids"] = []
        step_data["paper_ref_ids"] = [f"ref{i+1}" for i in range(len(relevant_papers))]

        steps.append(step_data)
        print(f"  ✓ {stage_name} ({len(step_data['substeps'])} substeps)")

    # ── 3. 生成 Methods ──────────────────────────────────────────────────────
    print("[3/6] 生成 methods...")

    # 收集所有 method_family
    method_families = set()
    for e in valid_extractions:
        al = e.get("algorithm_layer", {})
        if isinstance(al, dict):
            mf = al.get("method_family", "")
            if mf:
                method_families.add(mf)

    methods = []
    for idx, mf in enumerate(sorted(method_families)[:10]):  # 最多10个方法
        method_prompt = f"""为以下方法生成结构化描述:

方法名称: {mf}

请生成以下JSON:
{{
  "id": "method_{idx + 1}",
  "name": "{mf}",
  "description": "一句话概括核心思路",
  "assumptions": "- 假设1\\n- 假设2\\n...",
  "applicability": "- 适用场景1\\n- 适用场景2\\n...",
  "relationship": "与其他方法的关系（如果有）"
}}

要求简洁、专业。如果包含LaTeX公式，JSON字符串中的反斜杠必须转义为双反斜杠（\\\\）。
"""

        method_result = await llm(method_prompt, temperature=0.2)
        method_data = parse_llm_json(method_result)
        method_data["paper_ref_ids"] = []
        methods.append(method_data)

    print(f"  ✓ {len(methods)} 个方法")

    # ── 4. 生成 Tools ────────────────────────────────────────────────────────
    print("[4/6] 提取 tools...")

    # 收集所有具名工具
    all_tools = set()
    for e in valid_extractions:
        tools = e.get("tools", [])
        for tool in tools:
            # 过滤掉通用类别描述
            if any(keyword in tool.lower() for keyword in ["数值", "求解器", "积分器", "未报告", "未提及"]):
                continue
            # 保留具名软件
            if any(char.isupper() or char.isdigit() for char in tool):
                all_tools.add(tool)

    tools = list(all_tools)[:20]  # 最多20个工具
    print(f"  ✓ {len(tools)} 个具名工具")

    # ── 5. 生成 Paper Refs ───────────────────────────────────────────────────
    print("[5/6] 生成 paper_refs...")

    paper_refs = []
    for idx, e in enumerate(valid_extractions):
        paper_id = e.get("paper_id", "")
        short_name = e.get("short_name", "")
        title = e.get("title", "")

        # 提取贡献
        al = e.get("algorithm_layer", {})
        contribution = ""
        if isinstance(al, dict):
            mf = al.get("method_family", "")
            if mf:
                contribution = f"提出/使用了{mf}方法"

        paper_refs.append({
            "id": f"ref{idx + 1}",
            "citation": f"[{short_name}] {title}",
            "description": contribution or "贡献于该工作流",
            "is_cluster_member": True
        })

    print(f"  ✓ {len(paper_refs)} 篇文献")

    # ── 6. 组装最终 Schema ───────────────────────────────────────────────────
    print("[6/6] 组装 schema...")

    schema = {
        "workflow": {
            "id": f"workflow_{cluster_dir.name}",
            "name": workflow_name,
            "description": workflow_data["description"],
            "step_ids": [s["id"] for s in steps],
            "member_paper_ids": [e["paper_id"] for e in valid_extractions],
            "conclusions": workflow_data["conclusions"],
            "open_issues": workflow_data.get("open_issues", ""),
            "claims": workflow_data["claims"]
        },
        "steps": steps,
        "tools": tools,
        "methods": methods,
        "data": [],  # 超导比热计算通常不涉及公开数据集
        "paper_refs": paper_refs
    }

    return schema


async def main():
    if len(sys.argv) < 2:
        print("用法: python generate_schema.py <cluster_dir>")
        print("示例: python generate_schema.py data/Superconductivity/workflows_top50/cluster_172")
        sys.exit(1)

    cluster_dir = Path(sys.argv[1])

    if not cluster_dir.exists():
        print(f"错误: 目录不存在: {cluster_dir}")
        sys.exit(1)

    # 检查必需文件
    required_files = [
        "paper_extractions.yaml",
        "selected_chains.json",
        "workflow_structure.json"
    ]

    for fname in required_files:
        if not (cluster_dir / fname).exists():
            print(f"错误: 缺少文件: {fname}")
            sys.exit(1)

    # 生成 schema
    schema = await generate_schema(cluster_dir)

    # 写入文件
    output_path = cluster_dir / "schema.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(schema, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Schema 生成完成: {output_path}")
    print(f"   - Workflow: {schema['workflow']['name']}")
    print(f"   - Steps: {len(schema['steps'])}")
    print(f"   - Methods: {len(schema['methods'])}")
    print(f"   - Tools: {len(schema['tools'])}")
    print(f"   - Papers: {len(schema['paper_refs'])}")


if __name__ == "__main__":
    asyncio.run(main())
