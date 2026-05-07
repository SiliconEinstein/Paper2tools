"""AST 验证和代码质量检查"""

import ast
from typing import List, Tuple


def validate_python_code(
    code: str,
    *,
    check_interface: bool = True,
) -> Tuple[bool, List[str]]:
    """验证生成的 Python 代码。返回 (is_valid, error_messages)。"""
    errors: List[str] = []

    # 1. AST 解析
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, [f"SyntaxError: {e.msg} (line {e.lineno})"]

    # 2. 检查 execute_workflow 函数存在
    if check_interface:
        func_names = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        if "execute_workflow" not in func_names:
            errors.append("Missing required function: execute_workflow()")

    return (len(errors) == 0), errors


def strip_markdown_fences(text: str) -> str:
    """去除 LLM 输出中的 markdown 代码围栏。"""
    text = text.strip()
    if text.startswith("```"):
        # 去掉第一行 (```python 或 ```)
        first_nl = text.index("\n") if "\n" in text else len(text)
        text = text[first_nl + 1:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()
