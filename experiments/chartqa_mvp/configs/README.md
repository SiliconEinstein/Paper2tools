# MVP I/O 契约

本目录固定 ChartQA MVP 的三类核心输入输出结构：

- `question_decomposition.schema.json`：问题分解输出（子任务 DAG + claim 集合）
- `retrieval_result.schema.json`：检索与裁剪输出（多粒度召回 + 聚焦子表）
- `attribution_result.schema.json`：归因与验证输出（claim -> cell/lineage）

## 使用方式

1. 研发阶段：新模块输出 JSON 后，先过 schema 校验再进入下游。
2. 联调阶段：所有服务接口（分解、检索、归因）统一按 schema 交互。
3. 实验阶段：把每次实验产物写入 `artifacts/`，可批量校验字段一致性。

## 校验脚本

见：`../scripts/validate_json_io.py`

示例：

```bash
python experiments/chartqa_mvp/scripts/validate_json_io.py \
  --schema experiments/chartqa_mvp/configs/question_decomposition.schema.json \
  --input experiments/chartqa_mvp/artifacts/sample_decomposition.json
```

