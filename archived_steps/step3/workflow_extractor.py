"""Workflow 提取模块 - 从文本中提取结构化 workflow"""

import json
import re
from typing import Optional
from .schema import Workflow


def _build_extraction_prompt(text: str) -> str:
    """构建 workflow 提取 prompt"""
    return f"""你是一个专业的工作流分析专家。请从以下文本中提取**机器可读、便于 Agent 生成代码或复现实验**的结构化工作流（workflow）。

文本内容：
{text}

## 目标
在忠实于原文的前提下，尽量补齐：**稳定标识、版本化工具引用、可调参数、数据出处、表格级字段提示、可量化验收**（若原文未给出则留空或合理推断并标注为推断——但不得编造不存在的 accession）。

## 输出 JSON 格式（字段说明与约束）

{{
  "workflow_id": "snake_case 唯一标识",
  "title": "工作流标题",
  "description": "1-4 句：目标、适用场景、主要产物",
  "source_ids": ["来源 paper_id 等"],
  "keywords": ["英文或中英文检索词", "方法缩写", "核心数据类型名", "..."],
  "research_questions": [
    "以 How can I / 如何 … 开头的、可检索的具体任务问句（3-8 条，覆盖整条流程）"
  ],
  "datasets": [
    {{
      "dataset_id": "简短 id，如 GSE12345 或文献中的数据集昵称",
      "source_type": "GEO|SRA|ArrayExpress|Zenodo|10x|Synapse|补充材料|作者仓库|…",
      "accession_or_url": "accession、DOI 或 URL；未知则空字符串",
      "description": "物种/模态/用途一句话",
      "note": "下载或引用说明；无则空字符串"
    }}
  ],
  "benchmarks": [
    {{
      "benchmark_id": "如 bm_01",
      "metric": "指标名称（如 spearman_correlation）",
      "linked_step_id": 1,
      "expected_direction": "higher_is_better|lower_is_better|exact_match|unspecified",
      "acceptance_criteria": "若原文有阈值/Pass 条件则写清；否则写空字符串",
      "how_to_compute": "若原文描述了计算方式则简述；否则空字符串"
    }}
  ],
  "steps": [
    {{
      "step_id": 1,
      "step_name": "snake_case 步骤名，如 qc_and_trim",
      "logic_description": "本步在做什么（自然语言）",
      "tool_intent": "需要何种工具能力（一句话）",
      "suggested_tools": ["简短工具/软件名，与 tool_refs 对应；可为空"],
      "tool_refs": [
        "工具名 + 版本/年份 + 可解析链接或 DOI，如 scikit-learn v1.3 (https://scikit-learn.org/)；无版本则写「版本未注明」"
      ],
      "parameters": [
        "key=value 形式的可调分析/实验参数，如 correlation_metric=spearman；湿实验可写 incubation_time=48h 等原文出现的量"
      ],
      "io_schema": {{
        "inputs": [
          {{
            "name": "snake_case 名",
            "type": "file_path|table|matrix|fasta|numeric|text|list[string]|record|labware|document|other",
            "description": "语义与单位",
            "column_hints": ["当 type 为 table/matrix 时，列出 3-12 个建议列名；非表格可省略或空数组"]
          }}
        ],
        "outputs": [
          {{
            "name": "snake_case",
            "type": "同上",
            "description": "…",
            "column_hints": []
          }}
        ]
      }}
    }}
  ]
}}

## 硬性要求
1. 只输出 JSON，不要 markdown 围栏、不要解释性前后文。
2. 若无明确工作流，返回 "steps": []，其它顶层字段仍给出合理默认值（keywords/research_questions 可为空数组）。
3. step_id 从 1 递增；linked_step_id 必须对应已有 step_id。
4. suggested_tools 与 tool_refs：优先写**可脚本化**工具（命令行、R/Python 包）；GUI 软件（如 Prism）可写，但须在 parameters 或 description 中说明典型替代（如用 Python scipy 做同等检验）——若原文未提则不必臆造。
5. io_schema：inputs/outputs 的 name 在全文内尽量**可串联成数据流**（上一步 output name 可被下一步 input 引用）。
6. column_hints：对 table/matrix 类型**尽量给出列名**，便于 Agent 生成 DataFrame/schema。
7. datasets：凡原文出现具体数据库编号、公开数据链接、标准数据集名称，必须列入 datasets；没有的则为空数组。
8. benchmarks：凡原文出现显著性阈值、验收标准、与基线比较结论可转为 Pass/Fail 规则的，写入 benchmarks；否则空数组。
9. source_ids：列出文本中全部 paper_id / 样本 id；勿遗漏。
10. 禁止用占位符如「工具1」「参数名」；一律替换为从原文抽象出的真实语义名称。

请输出 JSON："""


def _parse_llm_response(response: str) -> dict:
    """从 LLM 响应中提取并解析 JSON"""
    # 去除可能的 markdown code block 包裹
    response = response.strip()

    # 尝试提取 ```json ... ``` 或 ``` ... ``` 包裹的内容
    json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', response, re.DOTALL)
    if json_match:
        response = json_match.group(1).strip()

    # 解析 JSON
    try:
        data = json.loads(response)
        return data
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON 解析失败: {e}\n响应内容: {response[:500]}")


async def extract_workflow(
    text: str,
    source_id: str = "",
    temperature: float = 0.3
) -> Optional[Workflow]:
    """
    从文本中提取 workflow

    Args:
        text: 输入文本
        source_id: 来源标识
        temperature: LLM 温度参数

    Returns:
        Workflow 对象，如果提取失败返回 None
    """
    from src.models.llm_providers import gpt5_mini_completion

    # 构建 prompt
    prompt = _build_extraction_prompt(text)

    # 调用 LLM
    try:
        response = await gpt5_mini_completion(prompt, temperature=temperature)
    except Exception as e:
        print(f"  ✗ LLM 调用失败: {e}")
        return None

    # 解析响应
    try:
        data = _parse_llm_response(response)
    except ValueError as e:
        print(f"  ✗ JSON 解析失败: {e}")
        # 重试一次，使用更严格的 prompt
        retry_prompt = prompt + "\n\n注意：必须输出有效的 JSON 格式，不要有任何其他文字。"
        try:
            response = await gpt5_mini_completion(retry_prompt, temperature=0.1)
            data = _parse_llm_response(response)
        except Exception as retry_e:
            print(f"  ✗ 重试后仍失败: {retry_e}")
            return None

    # 校验必需字段
    required_fields = ["workflow_id", "title", "description", "steps"]
    for field in required_fields:
        if field not in data:
            print(f"  ✗ 缺少必需字段: {field}")
            return None

    # 补充 source_ids
    if "source_ids" not in data:
        data["source_ids"] = [source_id] if source_id else []
    elif source_id and source_id not in data["source_ids"]:
        data["source_ids"].append(source_id)

    # 构建 Workflow 对象
    try:
        workflow = Workflow.from_dict(data)
        return workflow
    except Exception as e:
        print(f"  ✗ Workflow 对象构建失败: {e}")
        return None
