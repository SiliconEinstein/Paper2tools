"""workflow.py 代码生成器 — 将 Step3 的 workflow JSON 转化为可执行 Python 模块"""

from __future__ import annotations

import json
from typing import Any, Dict

from src.models.llm_providers import gpt_completion
from .code_validator import validate_python_code, strip_markdown_fences


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_SYSTEM_INSTRUCTIONS = """\
You are an expert Python code generator for bioinformatics workflows.
Given a workflow specification (JSON), produce a **single, complete, importable Python module**.

## Output requirements

1. **Workflow class** — one class whose methods correspond to the workflow steps.
   - Each method takes typed inputs and returns typed outputs.
   - Data flows between steps via explicit return values / arguments (no hidden state).

2. **Typed I/O** — use `@dataclass` for input/output structures.
   Include a top-level `WorkflowInput` and `WorkflowOutput` dataclass.

3. **`execute_workflow(inputs: WorkflowInput) -> WorkflowOutput`** — the single entry-point
   an AI agent calls. Create the Workflow instance, run all steps in sequence,
   and return the final output.

4. **Tool placeholders** — for every external tool call (e.g., BWA-MEM, GATK,
   BLAST, specific R packages), create a **standalone function** that:
   - Has a clear docstring explaining what the tool does.
   - Contains a `# TODO:` comment with a concrete usage hint.
   - Raises `NotImplementedError("tool_name not implemented. ...")`.

5. **Allowed imports**: stdlib, numpy, pandas, scipy, typing, dataclasses,
   pathlib, logging, collections, itertools. Do NOT import unavailable packages.

6. **Output format**: raw Python code only. No markdown fences, no explanations
   outside the code. The output must be directly parseable by `ast.parse()`.
"""


def _build_prompt(workflow: Dict[str, Any]) -> str:
    spec = json.dumps(workflow, ensure_ascii=False, indent=2)
    return f"""{_SYSTEM_INSTRUCTIONS}

## Workflow specification

```json
{spec}
```

Generate the complete Python module now.
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class WorkflowCodeGenerator:
    """生成 workflow.py 代码并做 AST 验证，失败可重试。"""

    def __init__(
        self,
        temperature: float = 0.3,
        retry_temperature: float = 0.1,
        max_retries: int = 1,
    ):
        self.temperature = temperature
        self.retry_temperature = retry_temperature
        self.max_retries = max_retries

    async def generate(self, workflow: Dict[str, Any]) -> str:
        """返回通过 AST 验证的 Python 代码字符串。失败则抛出 ValueError。"""
        prompt = _build_prompt(workflow)

        # 第一次尝试
        raw = await gpt_completion(prompt, temperature=self.temperature)
        code = strip_markdown_fences(raw)
        ok, errors = validate_python_code(code, check_interface=True)
        if ok:
            return code

        # 重试
        for attempt in range(self.max_retries):
            retry_prompt = (
                f"{prompt}\n\n"
                f"# IMPORTANT: your previous attempt had errors:\n"
                f"# {'; '.join(errors)}\n"
                f"# Fix them. Output only valid Python code."
            )
            raw = await gpt_completion(retry_prompt, temperature=self.retry_temperature)
            code = strip_markdown_fences(raw)
            ok, errors = validate_python_code(code, check_interface=True)
            if ok:
                return code

        raise ValueError(
            f"Code generation failed after {1 + self.max_retries} attempts: "
            f"{'; '.join(errors)}"
        )
