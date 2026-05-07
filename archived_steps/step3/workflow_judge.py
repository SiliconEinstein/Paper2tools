"""
Workflow 适用性判断器 - 使用 LLM 判断思维链是否适合提取 workflow
"""

import json
from pathlib import Path
from typing import Dict, List, Optional

from ..models.llm_providers import gpt_completion


# 判断 prompt 模板
JUDGMENT_PROMPT = """You are a strict workflow quality judge. Your task is to analyze reasoning chains and determine if they describe **concrete, actionable, domain-specific computational or experimental methods** that can be assembled into a workflow solving a specific research problem.

# Cluster {cluster_id} - Reasoning Chains

Total chains: {num_chains}

## Chain Texts (samples):

{chain_texts}

---

## Your Task

Judge whether the **methods and steps described in these chains** can be extracted into a concrete, actionable workflow.

**IMPORTANT**: Focus on WHAT METHODS ARE DESCRIBED, not whether the chains are evaluating those methods. Even if chains discuss "performance evaluation" or "parameter tuning", if they describe specific computational/experimental steps with concrete inputs/outputs, they may still be acceptable.

## ✅ ACCEPT if ALL of these are true:

1. **Specific Biological/Scientific Domain**: The methods target a concrete domain problem
   - ✓ GOOD: "network-based gene prioritization", "protein mutagenesis and activity assay", "RNA-seq read mapping"
   - ✗ BAD: "general machine learning", "generic data analysis", "any classification task"

2. **Concrete Data Types**: Mentions specific biological/scientific data types
   - ✓ GOOD: "gene interaction network", "protein sequences", "FASTQ reads", "microscopy images", "kinetic measurements"
   - ✗ BAD: "training data", "features", "samples", "input files"

3. **Specific Algorithms/Tools/Techniques**: Names concrete methods, not generic operations
   - ✓ GOOD: "random walk with restart", "Jaccard similarity on gene networks", "site-directed mutagenesis", "Michaelis-Menten fitting", "BWA-MEM alignment"
   - ✗ BAD: "machine learning classifier", "data preprocessing", "model training", "statistical analysis"

4. **Implementable Steps**: Describes steps that can be coded or performed in a lab
   - ✓ GOOD: "construct adjacency matrix from KEGG", "propagate scores using heat diffusion", "perform alanine scanning", "measure enzyme activity"
   - ✗ BAD: "define research objectives", "write documentation", "publish results", "plan experiments"

## ❌ REJECT if ANY of these are true:

1. **Generic ML/Stats Methodology**: Describes how to do machine learning/statistics in general
   - Keywords: "通用机器学习", "general classification", "generic training procedure", "cross-validation framework"
   - Example: "通用机器学习实验工作流：数据准备、训练、评估"

2. **Software Engineering**: About software development, not scientific analysis
   - Keywords: "软件发布", "software release", "packaging", "deployment", "distribution", "licensing"
   - Example: "开放源代码软件发布与分发工作流"

3. **Database/Resource Building**: About constructing databases, not using them for analysis
   - Keywords: "数据库构建", "database construction", "内容清单", "data integration", "resource curation"
   - Example: "生物信息学数据库构建与发布工作流"

4. **Pure Benchmarking**: ONLY about comparing methods, no actual analysis workflow
   - Keywords: "benchmarking workflow", "method comparison framework", "performance evaluation protocol"
   - Example: "Empirical benchmarking workflow for comparing alignment tools"
   - NOTE: If chains describe a specific method AND how to evaluate it, that's OK. Reject only if it's PURELY about comparison.

5. **Literature/Documentation**: About reviewing papers or writing docs
   - Keywords: "文献综述", "literature review", "meta-analysis", "documentation workflow"

6. **Project Management**: About planning/managing projects, not doing science
   - Keywords: "project planning", "experimental design framework", "objective setting", "resource allocation"

## Special Cases

- **Method + Evaluation**: If chains describe a specific method (e.g., network propagation) AND discuss how to evaluate it, focus on the METHOD. If the method is concrete and domain-specific, ACCEPT.
- **Parameter Tuning**: If chains describe parameter tuning for a specific algorithm (e.g., "tune diffusion parameter α"), that's part of the workflow. ACCEPT if the underlying method is concrete.
- **Multiple Papers**: Chains from multiple papers in the same cluster often describe variations of the same core method. Look for the common concrete method.

## Decision Rules

- **When in doubt about domain specificity, REJECT**
- **One clear rejection category → REJECT immediately**
- **Require ALL four acceptance criteria**
- **Focus on the METHODS described, not the meta-discussion around them**

## Output Format

Output ONLY a valid JSON object (no markdown, no explanation):

{{
  "cluster_id": {cluster_id},
  "decision": "ACCEPT" or "REJECT",
  "confidence": "high" or "medium" or "low",
  "reasoning": "<brief explanation focusing on WHAT METHODS are described>",
  "key_indicators": {{
    "specific_problem": true or false,
    "clear_io": true or false,
    "domain_tools": true or false,
    "executable_steps": true or false,
    "rejection_category": null or "<category name>"
  }}
}}

Be strict but fair. Output JSON only.
"""


def format_chains_for_judgment(chains: List[Dict], max_chains: int = 5, max_length: int = 800) -> str:
    """格式化 chains 用于判断"""
    texts = []
    for i, chain in enumerate(chains[:max_chains], 1):
        text = chain.get("chain_text", "")
        if len(text) > max_length:
            text = text[:max_length] + "..."
        texts.append(f"### Chain {i} (paper_id: {chain.get('paper_id', 'unknown')})\n\n{text}\n")

    return "\n".join(texts)


async def judge_cluster_async(
    cluster_id: int,
    chains: List[Dict],
    temperature: float = 0.1,
    verbose: bool = False,
) -> Optional[Dict]:
    """
    使用 LLM 判断 cluster 是否适合提取 workflow

    Args:
        cluster_id: cluster ID
        chains: 该 cluster 的所有 chains
        temperature: LLM 温度（低温度更稳定）
        verbose: 是否打印详细信息

    Returns:
        判断结果 dict，包含 decision, confidence, reasoning 等字段
        如果解析失败返回 None
    """
    if verbose:
        print(f"  [判断] Cluster {cluster_id} ({len(chains)} chains)...", flush=True)

    # 格式化 prompt
    chain_texts = format_chains_for_judgment(chains)
    prompt = JUDGMENT_PROMPT.format(
        cluster_id=cluster_id,
        num_chains=len(chains),
        chain_texts=chain_texts,
    )

    try:
        # 调用 LLM
        response = await gpt_completion(
            prompt=prompt,
            temperature=temperature,
            max_tokens=1000,
        )

        # 解析 JSON
        # 移除可能的 markdown fence
        response = response.strip()
        if response.startswith("```"):
            lines = response.split("\n")
            response = "\n".join(lines[1:-1]) if len(lines) > 2 else response
        if response.startswith("```json"):
            response = response[7:]
        if response.endswith("```"):
            response = response[:-3]

        result = json.loads(response.strip())

        if verbose:
            decision = result.get("decision", "UNKNOWN")
            reasoning = result.get("reasoning", "")
            print(f"    → {decision}: {reasoning}", flush=True)

        return result

    except json.JSONDecodeError as e:
        if verbose:
            print(f"    ✗ JSON 解析失败: {e}", flush=True)
            print(f"    Response: {response[:200]}...", flush=True)
        return None
    except Exception as e:
        if verbose:
            print(f"    ✗ 判断失败: {e}", flush=True)
        return None


def judge_cluster(
    cluster_id: int,
    chains: List[Dict],
    temperature: float = 0.1,
    verbose: bool = False,
) -> Optional[Dict]:
    """同步版本的 judge_cluster_async"""
    import asyncio
    return asyncio.run(judge_cluster_async(cluster_id, chains, temperature, verbose))
