"""test_example.py 生成器 — 为每个 workflow 创建可运行的示例脚本"""

from __future__ import annotations

import json
from typing import Any, Dict

from src.models.llm_providers import gpt_completion
from .code_validator import validate_python_code, strip_markdown_fences


_SYSTEM_INSTRUCTIONS = """\
You are an expert Python developer creating runnable test examples for bioinformatics workflows.

Given:
1. A workflow specification (JSON)
2. The generated workflow.py code

Produce a **test_example.py** script that:

## Requirements

1. **Module docstring** — explain:
   - What this workflow does (1-2 sentences)
   - What inputs it expects (types and meaning)
   - What research questions it can answer
   - Example use cases

2. **Mock data construction** — create minimal synthetic input data that:
   - Matches the WorkflowInput dataclass structure
   - Uses simple, small-scale data (e.g., 5-10 genes, small matrices)
   - Is self-contained (no external files needed)

3. **Workflow execution** — call `execute_workflow(inputs)` and print results

4. **Runnable** — must have `if __name__ == "__main__":` block

5. **Imports** — import from `workflow` module (same directory)

6. **Output format** — raw Python code only, no markdown fences

## Example structure

```python
\"\"\"
Test example for [Workflow Name].

This workflow does X, Y, Z. It takes A as input and produces B.
Useful for research questions like: ...
\"\"\"

from workflow import execute_workflow, WorkflowInput
import numpy as np

def create_mock_data():
    # Create minimal synthetic data
    ...
    return WorkflowInput(...)

if __name__ == "__main__":
    inputs = create_mock_data()
    result = execute_workflow(inputs)
    print("Result:", result)
```
"""


def _build_prompt(workflow: Dict[str, Any], workflow_code: str) -> str:
    spec = json.dumps(workflow, ensure_ascii=False, indent=2)
    return f"""{_SYSTEM_INSTRUCTIONS}

## Workflow specification

```json
{spec}
```

## Generated workflow.py code

```python
{workflow_code}
```

Generate the complete test_example.py now.
"""


class TestExampleGenerator:
    """生成 test_example.py 并验证语法。"""

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
    ) -> str:
        """返回通过 AST 验证的 test_example.py 代码。"""
        prompt = _build_prompt(workflow, workflow_code)

        # 第一次尝试
        raw = await gpt_completion(prompt, temperature=self.temperature)
        code = strip_markdown_fences(raw)
        ok, errors = validate_python_code(code, check_interface=False)
        if ok:
            return code

        # 重试
        for attempt in range(self.max_retries):
            retry_prompt = (
                f"{prompt}\n\n"
                f"# IMPORTANT: previous attempt had errors:\n"
                f"# {'; '.join(errors)}\n"
                f"# Fix them. Output only valid Python code."
            )
            raw = await gpt_completion(retry_prompt, temperature=self.retry_temperature)
            code = strip_markdown_fences(raw)
            ok, errors = validate_python_code(code, check_interface=False)
            if ok:
                return code

        raise ValueError(
            f"Test generation failed after {1 + self.max_retries} attempts: "
            f"{'; '.join(errors)}"
        )
