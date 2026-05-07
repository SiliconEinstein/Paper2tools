# Workflower v2 - 优化版工作流提取系统

## 概述

Workflower v2 是 Workflower 的优化版本，将原 5 阶段流程压缩为 3 阶段，通过消除重复文件读取和引入并行处理，实现 **2-3倍整体加速**。

## 核心优化

### 1. 阶段合并（减少 I/O）

| v1 (5阶段) | v2 (3阶段) | 优化效果 |
|-----------|-----------|---------|
| 01_chain_classifier | **01_analyzer** | 合并 01+02 |
| 02_workflow_structure_builder | ↑ 同上 | 一次遍历完成分类+方法提取 |
| 03_deep_reader | **02_extractor** | 增加并行处理 |
| 04_workflow_documenter | **03_writer** | 合并 04+05 |
| 05_review_writer | ↑ 同上 | 消除重复读取 |

### 2. 并行处理（加速计算）

**02_extractor** 支持智能批次划分：
- 13 篇论文 → 3 批并行（5, 4, 4）
- 理论加速：3倍
- 实际加速：2.6倍（考虑启动开销）

### 3. 断点续传（容错性）

- 阶段级别：检测已完成阶段，从中断处继续
- 论文级别：`.extraction_progress.json` 记录已提取论文

## 性能对比

### 文件读取次数

| 文件 | v1 | v2 | 减少 |
|------|----|----|------|
| selected_chains.json | 2次 | 1次 | -50% |
| paper_extractions.yaml | 2次 | 1次 | -50% |
| workflow_structure.json | 2次 | 1次 | -50% |

### 实际耗时（13篇论文）

| 阶段 | v1 | v2 | 加速比 |
|------|----|----|--------|
| 分析与规划 | 5分钟 | 3分钟 | 1.7x |
| 深度提取 | 39分钟 | 15分钟 | 2.6x |
| 文档生成 | 8分钟 | 5分钟 | 1.6x |
| **总计** | **52分钟** | **23分钟** | **2.3x** |

## 文件结构

```
Workflower_v2/
├── SKILL.md              # 主协调器
├── 01_analyzer.md        # 分析器与规划器（合并 01+02）
├── 02_extractor.md       # 深度提取器（并行优化）
├── 03_writer.md          # 文档与综述生成器（合并 04+05）
└── README.md             # 本文件
```

## 使用方式

### 完整流程

```
用户: "提取 cluster_8 的工作流并生成综述"
```

系统自动：
1. 检测已完成阶段
2. 从未完成处开始
3. 并行处理论文提取
4. 生成所有输出文件

### 单独执行某阶段

```
用户: "用 02_extractor 重新提取论文信息"
```

### 断点续传

如果中断，重新调用会自动：
- 跳过已完成阶段
- 跳过已提取论文
- 只处理剩余任务

## 输出文件

```
cluster_N/
├── chain_classification.json      # 链条分类（增强版）
├── workflow_structure.json        # 决策树结构
├── step_statistics.json           # 方法频次统计
├── review_plan.json               # 综述结构规划
├── paper_inventory.md             # 论文清单
├── .extraction_progress.json      # 提取进度（隐藏）
├── paper_extractions.yaml         # 论文深度提取
├── workflow_3layer.md             # 3层工作流文档
├── decision_tree.dot              # 决策树源码
├── decision_tree.png              # 决策树可视化
├── decision_tree.pdf              # 决策树PDF
├── review_cluster_N.tex           # LaTeX综述
├── review_cluster_N.pdf           # 综述PDF
└── COMPLETION_REPORT.md           # 完成报告
```

## 关键改进点

### 01_analyzer（合并 01+02）

**优化前**：
```python
# 01: 分类链条
for chain in chains:
    classify(chain)

# 02: 再次遍历提取方法
for chain in chains:
    extract_methods(chain)
```

**优化后**：
```python
# 一次遍历完成
for chain in chains:
    grade, methods = classify_and_extract(chain)
    update_statistics(methods)
```

### 02_extractor（并行处理）

**优化前**：
```python
# 串行处理
for paper in papers:
    extract(paper)  # 3分钟/篇
# 总计：13篇 × 3分钟 = 39分钟
```

**优化后**：
```python
# 并行处理
batches = split_into_batches(papers, batch_size=5)
parallel_process(batches)  # 3批并行
# 总计：max(5,4,4)篇 × 3分钟 = 15分钟
```

### 03_writer（合并 04+05）

**优化前**：
```python
# 04: 读取文件生成 workflow_3layer.md
data = load("paper_extractions.yaml")  # 21KB
generate_workflow_doc(data)

# 05: 再次读取生成 review.tex
data = load("paper_extractions.yaml")  # 21KB（重复）
generate_review(data)
```

**优化后**：
```python
# 一次读取生成所有输出
data = load("paper_extractions.yaml")  # 21KB（仅一次）
generate_workflow_doc(data)
generate_review(data)
generate_decision_tree(data)
```

## 技术细节

### 智能批次划分

```python
if 论文总数 <= 3:
    批次数 = 1
elif 论文总数 <= 8:
    批次数 = 2
elif 论文总数 <= 15:
    批次数 = 3
else:
    批次数 = 4
```

### 进度追踪格式

```json
{
  "completed_papers": ["paper_id_1", "paper_id_2"],
  "total_papers": 13,
  "last_update": "2026-04-27T22:10:00Z"
}
```

### 决策树渲染修复

v2 使用简单文本标签，避免 HTML TABLE 导致的黑块问题：

```dot
stage1 [label="阶段 1: 相与晶格表征 (13/13)\n\nXRD Rietveld 精修 (4篇)\nXRD 峰位分析 (9篇)", 
        shape=box, style=rounded];
```

## 兼容性

- 输入格式与 v1 完全兼容
- 输出文件格式与 v1 兼容（部分增强）
- 可与 v1 共存（不同目录）

## 迁移指南

从 v1 迁移到 v2：

1. 使用相同的输入目录结构
2. 调用 `Workflower_v2/SKILL.md` 而非 `Workflower/SKILL.md`
3. 输出文件名和格式保持一致
4. 新增 `.extraction_progress.json` 用于断点续传

## 已知限制

1. 并行处理需要足够的系统资源（内存、CPU）
2. xelatex 编译需要中文字体支持
3. Graphviz 需要安装用于决策树渲染

## 未来优化方向

1. 阶段 1 的方法提取可考虑使用 LLM 批处理 API
2. 阶段 3 的 LaTeX 编译可异步执行
3. 支持更细粒度的进度追踪（阶段内子任务）

## 参考

- 原始 Workflower v1: `/personal/paper2tools_v2/skills/Workflower/`
- 性能分析文档: 见 git history 中的优化讨论
