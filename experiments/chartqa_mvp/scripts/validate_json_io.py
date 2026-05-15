#!/usr/bin/env python3
"""
使用 JSON Schema 校验 MVP I/O 文件。

示例:
python experiments/chartqa_mvp/scripts/validate_json_io.py \
  --schema experiments/chartqa_mvp/configs/question_decomposition.schema.json \
  --input experiments/chartqa_mvp/artifacts/sample_decomposition.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate JSON with schema")
    parser.add_argument("--schema", required=True, help="Schema file path")
    parser.add_argument("--input", required=True, help="Input JSON file path")
    args = parser.parse_args()

    schema_path = Path(args.schema)
    input_path = Path(args.input)

    if not schema_path.exists():
        print(f"[Error] schema not found: {schema_path}")
        return 2
    if not input_path.exists():
        print(f"[Error] input not found: {input_path}")
        return 2

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    instance = json.loads(input_path.read_text(encoding="utf-8"))

    try:
        from jsonschema import Draft202012Validator  # type: ignore
    except Exception:
        print("[Error] jsonschema 未安装，请先执行: pip install jsonschema")
        return 2

    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path))

    if not errors:
        print(f"[OK] {input_path} passed {schema_path.name}")
        return 0

    print(f"[FAIL] {input_path} has {len(errors)} validation errors:")
    for i, err in enumerate(errors, 1):
        path = ".".join(str(p) for p in err.absolute_path) or "<root>"
        print(f"  {i}. path={path}")
        print(f"     message={err.message}")
    return 1


if __name__ == "__main__":
    sys.exit(main())

