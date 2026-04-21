# paper2tools_v2 项目指南

## 项目概述

paper2tools_v2 是一个独立的学术论文推理步骤分析项目，专注于：
- 推理步骤的语义理解与聚类
- 工具与推理步骤的精确关联
- 典型工作流的归纳总结

### 核心功能
- **Step1**: 文本向量化与语义聚类 - 对推理步骤进行向量化并按语义相似度聚类
- **Step2**: 工具信息注入 - 在 reasoning_chain XML 中为每个推理步骤补充关联的工具信息
- **Step3**: 工作流总结 - 基于增强后的数据总结典型工作流模式

### 主要入口
- `src/main.py`: CLI 主入口
- `src/step1/pipeline.py`: Step1 流水线
- `src/step2/pipeline.py`: Step2 流水线
- `src/step3/pipeline.py`: Step3 流水线

## 架构设计原则

### 模块化与独立性
- 每个 Step 独立封装，可单独运行和测试
- 共享功能统一放在 `src/common/` 模块
- 每个模块都有对应的单元测试

### 数据流设计
```
输入数据 (data/input/)
  ├─ reasoning_chain.xml        # 原始推理链
  └─ _tools_extract_result.json # 工具提取结果
       ↓
Step1: 向量化与聚类
  └─→ data/step1_output/
       ├─ step_embeddings.npy    # 步骤向量
       ├─ clusters.json          # 聚类结果
       └─ cluster_analysis.json  # 聚类分析
       ↓
Step2: 工具信息注入
  └─→ data/step2_output/
       └─ reasoning_chain.enriched.xml  # 增强后的推理链
       ↓
Step3: 工作流总结
  └─→ data/step3_output/
       ├─ workflows.json         # 工作流库
       └─ workflow_stats.json    # 统计信息
```

### 可配置性
- 所有参数通过 YAML 配置文件管理
- 支持多种 embedding 模型和聚类算法
- 可灵活调整匹配策略和阈值

## 目录结构
```
paper2tools_v2/
├── .claude/
│   ├── CLAUDE.md              # 本文件
│   └── TRACE.md               # 过程日志
├── src/
│   ├── step1/                 # Step1: 文本向量化与聚类
│   ├── step2/                 # Step2: 工具信息注入
│   ├── step3/                 # Step3: 工作流总结
│   ├── common/                # 共享模块
│   └── main.py                # CLI 主入口
├── tests/                     # 单元测试
├── data/                      # 数据目录
├── configs/                   # 配置文件
├── notebooks/                 # Jupyter notebooks
├── requirements.txt           # Python 依赖
└── README.md                  # 项目说明
```

## 开发注意事项

### 代码风格
- 使用 `pathlib.Path` 处理文件路径
- 所有批处理操作必须打印进度信息
- 函数和类都要有清晰的 docstring

### 测试策略
- 每个模块都有对应的单元测试
- 使用小规模测试数据验证功能
- 集成测试验证端到端流程

### 断联恢复
如果 Claude Code session 断联：
1. 查看 `data/` 目录确认已完成的步骤
2. 查看 `.claude/TRACE.md` 了解最后的进度
3. 告诉我"继续之前的任务"，我会读取上下文恢复工作

## 文档体系

本项目维护两份核心文档，均位于 `.claude/` 目录下：
- **`.claude/CLAUDE.md`**（本文件）：经验法则——跨场景适用的判断准则
- **`.claude/TRACE.md`**：过程日志——遇到的问题、做出的决策、变更记录

具体事件写 TRACE.md，发现可复用的判断准则后提炼到 CLAUDE.md。

## 经验法则（持续更新）

> **元规则**: 在对话过程中，当一个决策、踩坑或架构选择可以提炼为**跨场景适用的判断准则**时，更新此章节。记录的不是"做了什么"，而是"以后遇到类似情况该怎么判断"。附注日期。

### 1. 框架先行，代码后置

在开始编写具体实现前，先搭建完整的项目框架：
- 明确的目录结构
- 清晰的模块职责划分
- 预留的测试文件
- 配置文件模板

这样可以确保后续开发有清晰的路径，避免频繁重构。（2026-04-21）
