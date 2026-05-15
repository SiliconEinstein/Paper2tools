# chartqa_mvp

本目录用于承载 ChartQA 研究计划的可复现实验资产。

## 目录约定

- `configs/`: 实验配置（数据切分、检索参数、执行参数）
- `scripts/`: 可执行脚本（训练/评测/消融）
- `reports/`: 结果报告（指标表、误差分析）
- `artifacts/`: 中间产物（预测、日志、缓存）

## 当前状态

- 研究计划文档：`data/chartqa/workflows/cluster_0/RESEARCH_PLAN.md`
- 下一步优先任务：修复 `paper_extractions.yaml` 中 `parse_error`，并固化 MVP 的输入输出 schema。

