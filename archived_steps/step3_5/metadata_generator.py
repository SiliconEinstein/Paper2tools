"""metadata.json 生成器 — 从代码中提取检索用元数据"""

from __future__ import annotations

import json
from typing import Any, Dict

from src.models.llm_providers import gpt_completion
from .code_validator import strip_markdown_fences


_SYSTEM_INSTRUCTIONS = """\
You are a metadata extraction expert. Given a workflow's code and tests,
produce a **metadata.json** for semantic retrieval.

## Rules

1. Summarize the CODE, not the original JSON spec.
2. Extract keywords from actual function/class/variable names in the code.
3. Research questions should describe concrete tasks this workflow enables.
4. Input/output types come from the code's dataclass definitions.
5. Tools come from the placeholder functions (those raising NotImplementedError).

## Required JSON schema

```json
{
  "workflow_id": "string",
  "title": "string",
  "description": "string (1-3 sentences, from code docstrings)",
  "keywords": ["string", "..."],
  "research_questions": ["string", "..."],
  "input_types": [{"name": "string", "type": "string", "description": "string"}],
  "output_types": [{"name": "string", "type": "string", "description": "string"}],
  "tools": [{"name": "string", "description": "string"}],
  "num_steps": "integer",
  "complexity": "low|medium|high"
}
```

Output valid JSON only. No markdown fences, no explanation.
"""


def _build_prompt(
    workflow: Dict[str, Any],
    workflow_code: str,
    test_code: str,
) -> str:
    spec = json.dumps(workflow, ensure_ascii=False, indent=2)
    return f"""{_SYSTEM_INSTRUCTIONS}

## Original specification (for workflow_id and title only)

```json
{spec}
```

## workflow.py

```python
{workflow_code}
```

## test_example.py

```python
{test_code}
```

Generate the metadata JSON now.
"""


def _parse_metadata_response(raw: str) -> Dict[str, Any]:
    """从 LLM 输出中解析 JSON，容忍 markdown 围栏。"""
    text = strip_markdown_fences(raw)
    return json.loads(text)


_REQUIRED_FIELDS = {
    "workflow_id", "title", "keywords",
    "research_questions", "tools", "num_steps",
}


def _validate_metadata(meta: Dict[str, Any]) -> list[str]:
    errors = []
    for field in _REQUIRED_FIELDS:
        if field not in meta:
            errors.append(f"Missing field: {field}")
    return errors


class WorkflowMetadataGenerator:
    """生成 metadata.json 并验证必需字段存在。"""

    def __init__(
        self,
        temperature: float = 0.3,
        retry_temperature: float = 0.1,
        max_retries: int = 1,
    ):
        self.temperature = temperature
        self.retry_temperature = retry_temperature
        self.max_retries = max_retries

    async def generate(
        self,
        workflow: Dict[str, Any],
        workflow_code: str,
        test_code: str,
    ) -> Dict[str, Any]:
        """返回验证通过的 metadata dict。"""
        prompt = _build_prompt(workflow, workflow_code, test_code)

        raw = await gpt_completion(prompt, temperature=self.temperature)
        try:
            meta = _parse_metadata_response(raw)
            errors = _validate_metadata(meta)
            if not errors:
                return meta
        except (json.JSONDecodeError, ValueError) as e:
            errors = [f"JSON parse error: {e}"]

        # 重试
        for attempt in range(self.max_retries):
            retry_prompt = (
                f"{prompt}\n\n"
                f"# IMPORTANT: previous attempt had errors:\n"
                f"# {'; '.join(errors)}\n"
                f"# Fix them. Output valid JSON only."
            )
            raw = await gpt_completion(retry_prompt, temperature=self.retry_temperature)
            try:
                meta = _parse_metadata_response(raw)
                errors = _validate_metadata(meta)
                if not errors:
                    return meta
            except (json.JSONDecodeError, ValueError) as e:
                errors = [f"JSON parse error: {e}"]

        raise ValueError(
            f"Metadata generation failed after {1 + self.max_retries} attempts: "
            f"{'; '.join(errors)}"
        )
