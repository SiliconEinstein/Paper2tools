# paper2tools_v2 项目指南

## 项目概述

paper2tools_v2 是一个学术论文工作流提取系统，从大规模论文语料中自动发现和总结科研工作流模式。

### 核心功能
- **Step1**: 推理链向量化与语义聚类 - 使用 LanceDB 存储向量，agglomerative 聚类发现相似工作流
- **Step2**: Workflower 输入准备 - 为每个聚类构建标准化目录，下载 TOS 文件，生成批量调用脚本
- **Step3**: Workflow 检索系统 - 多路召回（语义向量 + 关键词 + 输入输出类型 + 方法名）+ 重排序

### 主要入口
- `src/main.py`: CLI 主入口
- `src/step1/pipeline.py`: Step1 流水线（向量化 + 聚类 + 元数据存储）
- `src/step2/pipeline.py`: Step2 流水线（目录构建 + 文件下载 + 任务生成）
- `src/step3/pipeline.py`: Step3 流水线（索引构建 + 检索）

## 架构设计原则

### 模块化与独立性
- 每个 Step 独立封装，可单独运行和测试
- 共享功能统一放在 `src/common/` 模块
- 每个模块都有对应的单元测试

### 数据流设计
```
输入数据 (data/{domain}/)
  ├─ reasoning_chain.xml        # 原始推理链（从 TOS 下载）
  └─ _tools_extract_result.json # 工具提取结果
       ↓
Step1: 向量化与聚类
  └─→ data/lance_db/
       ├─ chain_embeddings/      # 向量表（含 domain, cluster_id, xml_path, md_path）
       └─ cluster_metadata/      # 聚类元数据表（质心、簇内相似度、论文列表）
       ↓
Step2: Workflower 输入准备
  └─→ data/{domain}/workflows/
       ├─ cluster_0/
       │   ├─ selected_chains.json
       │   ├─ md/{paper_id}.md
       │   └─ xml/{paper_id}_{conclusion_id}.xml
       ├─ cluster_1/...
       ├─ run_workflows.sh       # 批量调用脚本
       └─ workflow_tasks.json    # 任务清单
       ↓
Step3: (手动) 用户运行 Workflower skill
  └─→ data/{domain}/workflows/cluster_N/
       ├─ workflow_structure.json
       ├─ paper_extractions.yaml
       ├─ workflow_3layer.md
       ├─ review.pdf
       └─ decision_tree.pdf
       ↓
Step3: Workflow 检索系统
  └─→ data/workflow_index/
       ├─ workflow_embeddings/      # LanceDB 向量索引
       ├─ keyword_inverted_index.json
       ├─ type_index.json
       ├─ method_index.json
       └─ workflow_registry.json
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
│   ├── step1/                 # Step1: 向量化 + 聚类 + 元数据
│   │   ├── pipeline.py        # 主流程
│   │   ├── data_loader.py     # TOS 数据加载
│   │   ├── vectorizer.py      # 批量 embedding
│   │   ├── clustering.py      # 聚类算法（agglomerative）
│   │   ├── cluster_metadata.py # 聚类元数据构建与存储
│   │   └── file_downloader.py # TOS 文件下载（被 Step2 复用）
│   ├── step2/                 # Step2: Workflower 输入准备
│   │   ├── pipeline.py        # 主流程
│   │   ├── cluster_loader.py  # 从 Lance 加载聚类数据
│   │   ├── workflow_dir_builder.py  # 构建 Workflower 目录
│   │   └── task_generator.py  # 生成批量脚本和清单
│   ├── step3/                 # Step3: Workflow 检索系统
│   │   ├── pipeline.py        # 主流程
│   │   ├── index_builder.py   # 索引构建
│   │   ├── retriever.py       # 多路召回 + 重排序
│   │   └── utils.py           # 辅助函数
│   ├── db/                    # LanceDB 向量数据库层
│   │   ├── lance_vector_store.py
│   │   └── schema.py
│   ├── models/                # LLM providers
│   └── main.py                # CLI 主入口
├── archived_steps/            # 已归档的旧 step2-4 代码
├── skills/Workflower/         # Workflower 3 阶段 skill
├── tests/                     # 单元测试
├── data/                      # 数据目录
├── configs/                   # 配置文件
└── requirements.txt
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

### 2. 效率优先原则 - 避免过度探索和串行操作

**症状**: 完成简单任务耗时过长（如创建 7 个文件花费数分钟）

**根因**:
1. 用 Agent 探索可以直接 Glob/Grep 完成的简单查询
2. 逐个文件串行写入，没有利用并行能力
3. 每个文件写大量 docstring/注释，实际代码占比低
4. 过度设计，写了很多"可能用到"但当前不需要的代码

**处方**:
- **探索策略**: 简单查询（列文件、搜关键词）直接用 Glob/Grep，只在复杂场景用 Agent
- **并行操作**: 互不依赖的文件/操作用并行工具调用（一次 function_calls 块包含多个 invoke）
- **精简文档**: docstring 只写核心职责和参数说明，不写使用示例和长篇设计思想
- **最小实现**: 只写当前需要的代码，不预留"可能用到"的功能
- **批量创建**: 创建多个相似文件时，用 Bash 循环 + echo/cat 比逐个 Write 快

**适用场景**: 创建项目框架、批量生成配置文件、简单代码重构

（2026-04-21）

### 3. 认证失败先查凭证到位没有

遇到 403/401 时，**第一步验证凭证是否非空且正确**（打印前缀即可），再去排查 API 调用方式。凭证来源链路（`.env` → `load_dotenv()` → `os.getenv()` → SDK config）中任何一环断裂都会导致空凭证静默传入，表现为权限错误而非配置错误。（2026-04-22）

### 4. 批处理异常必须采样记录

`except Exception: count += 1` 是反模式——失败计数没有诊断价值。至少记录前 N 个异常的类型和消息（`if failed < 5: log(exc)`）。错误率异常高时（>50%）应提前终止，不要跑完全量再发现。（2026-04-22）

### 5. 调用外部模块前先读其接口

不要凭印象猜属性名和方法签名。花 30 秒 Grep/Read 已有调用模式，比写错后调试 10 分钟高效得多。（2026-04-22）

### 6. 写入频率和计算并发是独立参数

chunk_size 控制写入频率，worker 数控制计算并发，两者分别调优。小 chunk + 高频 flush 会让 I/O 成为瓶颈。观察指标：flush 耗时占比 >30% 就该增大 chunk。（2026-04-22）

### 7. 设计文档先行，避免边写边改

**症状**: 实现复杂模块时频繁返工，架构不清晰导致模块职责混乱。

**处方**:
- 对于多模块协作的功能（如 Step2），先写设计文档（DESIGN.md）明确：
  - 输入输出格式
  - 模块职责划分
  - 数据流向
  - 关键接口签名
- 设计文档经用户确认后再开始实现
- 实现时严格按设计文档，避免临时改动

**适用场景**: 新增 pipeline、重构多模块系统、集成外部 skill

（2026-04-29）

### 8. 复用已有逻辑优于重写

**症状**: 新模块需要类似功能时，从头实现导致代码重复和不一致。

**处方**:
- 实现前先 Grep 搜索已有类似功能（如 TOS 下载、文件路径生成）
- 优先通过 import 复用，而非复制粘贴
- 如果需要微调，考虑：
  1. 参数化原函数（最佳）
  2. 包装原函数（次优）
  3. 重写（最后手段）

**案例**: Step2 的 `workflow_dir_builder.py` 直接 import Step1 的 `file_downloader.py`，复用 TOS 客户端初始化和下载逻辑。

（2026-04-29）

### 10. Skill 文档中的必填字段要用 ⚠️ 显式标注

**症状**: AI agent 执行 skill 时遗漏关键字段（如 paper_refs），导致输出缺乏溯源信息。

**根因**: Skill 文档中的"建议"字段和"必填"字段视觉上无区分，agent 容易跳过。

**处方**:
- 必填字段在文档中用 ⚠️ 标注，并在关键规则和质量检查清单中重复强调
- 质量检查清单要包含"字段存在性"和"字段完整性"两类检查
- 溯源字段（如 paper_refs）只需在顶层记录一次，不需要细化到每个子步骤

**适用场景**: 编写 AI agent 执行的 skill 文档、prompt 模板

（2026-05-13）

### 9. 批量任务脚本要有进度反馈和验证

**症状**: 批量脚本运行后不知道哪些任务完成、哪些失败。

**处方**:
- 生成的 shell 脚本应包含：
  - 清晰的任务编号和进度提示（`Task 1/10`）
  - 每个任务的关键信息（cluster ID, 链数, 论文数）
  - 任务间的暂停点（`read -p "Press Enter..."`）
  - 输出文件验证（检查关键文件是否存在）
- 同时生成 JSON 清单文件（`workflow_tasks.json`）供程序化追踪

**案例**: Step2 的 `task_generator.py` 生成的脚本会在每个 cluster 处理后验证 `workflow_structure.json` 是否存在。

（2026-04-29）
