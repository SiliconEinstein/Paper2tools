"""Workflow 提取模块 - 从文本中提取结构化 workflow"""

import json
import re
from typing import Optional
from .schema import Workflow


def _build_extraction_prompt(text: str) -> str:
    """构建 workflow 提取 prompt"""
    return f"""你是一个专业的工作流分析专家。请从以下文本中提取出结构化的工作流（workflow）。

文本内容：
{text}

请识别文本中描述的方法论、流程或工作流，并按以下 JSON 格式输出：

{{
  "workflow_id": "唯一标识符（可基于内容生成）",
  "title": "工作流标题",
  "description": "工作流整体描述",
  "source_ids": ["来源标识"],
  "steps": [
    {{
      "step_id": 1,
      "logic_description": "这一步的逻辑描述（用自然语言说明这一步在做什么）",
      "tool_intent": "这一步需要什么工具功能（描述工具的作用意图）",
      "suggested_tools": ["工具1", "工具2"],
      "io_schema": {{
        "inputs": [
          {{"name": "输入参数名", "type": "数据类型", "description": "参数描述"}}
        ],
        "outputs": [
          {{"name": "输出名", "type": "数据类型", "description": "输出描述"}}
        ]
      }}
    }}
  ]
}}

要求：
1. 只输出 JSON，不要有其他文字
2. 如果文本中没有明确的工作流，返回空 steps: []
3. step_id 从 1 开始递增
4. suggested_tools 可以为空列表
5. io_schema 的 inputs/outputs 可以为空列表
6. 确保 JSON 格式正确，可被解析

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
