# Paper2Tools v2

从大规模论文推理链中自动发现、结构化提取、代码复现与检索科研工作流。

## 项目概述

Paper2Tools v2 以论文 **reasoning chain（推理链）** 为起点，通过向量化聚类筛出高频研究模式，再用 Agent Skills 将思维链提炼为可执行工作流（含元数据与 ARM 复现包），并支持基于向量库的工作流/思维链检索。

### 端到端流程

```
TOS 对象存储 (paper_ocr/)
  ├─ xml/*_reasoning_chain.xml
  └─ md/*.md
       ↓
Step1：向量化 + 聚类 + 选链 + 下载语料
  ├─ DashScope Embedding
  ├─ Agglomerative / KMeans 等（见 src/step1/cluster/）
  └─ 输出 selected_chains.json、xml/、md/
       ↓
Workflower_v2（Agent Skill）
  ├─ 判断可提取性 → 筛选核心链 → 提取元数据
  └─ 输出 workflow/workflow_metadata.json、papers_metadata.json
       ↓
Workflow2Code（Agent Skill）
  ├─ 生成 ARM 题目与计划 → 实现代码与测试 → 迭代优化
  └─ 输出 ARM/（code、dataset、result、trace）
       ↓
Step3：工作流 / 思维链检索（src/step3）
  └─ 多路召回 + 重排序（chain_search API）
```

更完整的 Skill 串联说明见 [workflow_cluster_raw/workflow/readme.md](https://github.com/starbilibili/workflow_cluster_raw/blob/main/workflow/readme.md)（同仓库 `workflow/skills/` 目录）。

## 快速开始

### 环境准备

```bash
pip install -r requirements.txt

# 在项目根目录配置 .env（勿提交到 Git）
TOS_ACCESS_KEY=...
TOS_SECRET_KEY=...
TOS_BUCKET=...
TOS_ENDPOINT=...

# Embedding（Step1 / Step3）
API_URL=https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings
ACCESS_KEY=...                    # 或 DASHSCOPE_API_KEY

# LLM（Step2 / Skills / Step3）
GPUGEEK_API_KEY=...
GPUGEEK_API_BASE=https://api.gpugeek.com/v1
LITELLM_PROXY_API_BASE=...
LITELLM_PROXY_API_KEY=...

# 思维链向量库检索（Step3 chain_search，可选）
LKM_BYTEHOUSE_HOST=...
LKM_BYTEHOUSE_USER=...
LKM_BYTEHOUSE_PASSWORD=...
LKM_BYTEHOUSE_DATABASE=...
```

### 运行流水线（CLI）

```bash
# Step1：向量化 + 聚类（示例配置）
python -m src.main --step 1 --config configs/step1_config.yaml

# Step2：工具注入 XML（历史流程，配置见 configs/step2_config.yaml）
python -m src.main --step 2 --config configs/step2_config.yaml

# Step3：思维链检索
python -m src.main --step 3 --config configs/step3_config.yaml \
  --action chain_search --query "超导磁阻测量工作流" --top-k 5
```

领域级 Step1 脚本与大批量语料多在本地 `data/{domain}/` 维护；本仓库 **仅附带 `data/bioinformatics/step1_output/` 聚类结果** 作为示例（完整 `workflows/`、`reasoning_chains*.jsonl` 等大文件见 `.gitignore`）。

### 运行 Agent Skills

在某一簇目录下（含 `selected_chains.json`、`md/`、`xml/`）：

| 阶段 | Skill | 主要输出 |
|------|--------|----------|
| 元数据提取 | `skills/Workflower_v2/` | `workflow/workflow_metadata.json`、`papers_metadata.json` |
| 代码复现与验证 | `skills/Workflow2Code/` | `ARM/`（plan、code、dataset、result、trace） |
| 综述式提取（旧） | `skills/Workflower/` | LaTeX 综述、决策树等 |
| LLM 批处理提取 | `skills/Workflower_LLM/` | 脚本化三阶段提取 |

在 Cursor / Claude Code 中加载对应 `SKILL.md` 后按阶段执行即可。

## 项目结构

```
paper2tools_v2/
├── src/
│   ├── step1/              # 向量化、聚类、选链、下载 xml/md
│   ├── step3/              # 工作流检索、chain_search API
│   ├── db/                 # LanceDB 封装
│   └── models/             # LLM Provider（GPUGEEK / LiteLLM 等）
├── skills/
│   ├── Workflower_v2/      # 工作流元数据提取（推荐）
│   ├── Workflow2Code/      # ARM 复现与测试迭代
│   ├── Workflower/         # 早期三阶段 skill
│   ├── Workflower_LLM/     # LLM 脚本化提取
│   ├── ChainSearchEntry/   # 思维链检索入口 skill
│   ├── WorkflowSearchEntry/
│   ├── QuestionRefiner/
│   └── LKMRetrievalOrchestrator/
├── configs/                # Step1/2/3 与各领域配置
├── data/
│   └── bioinformatics/     # 仓库内示例：step1_output 聚类产物
├── experiments/            # 实验性 MVP（如 chartqa_mvp）
├── archived_steps/         # 历史 step2/3/4 实现归档
├── scripts/                # 辅助脚本
├── tests/                  # 当前流水线测试
├── run_batch_judge_workflows.py
└── requirements.txt
```

## 支持的领域（本地数据）

| 领域 | domain key | 说明 |
|------|------------|------|
| 生物信息学 | `bioinformatics` | 仓库含 step1_output 示例 |
| 超导 | `superconductivity` | 本地 `data/Superconductivity/` |
| 材料科学 | `materials_science` | 本地维护 |
| 环境科学 | `environmental_science` | 本地维护 |
| 数学 | `mathematics` | 本地维护 |
| 流体力学 | `fluid_mechanics` | 本地维护 |

期刊列表见 `configs/domain_journals.yaml`。

## Workflower_v2 输出示例

```
cluster_{id}/
├── selected_chains.json
├── md/、xml/
└── workflow/
    ├── workflow_metadata.json    # 步骤、工具、paper_refs
    ├── papers_metadata.json      # 论文参数、expected_results、environment
    ├── workflow_visualization.html
    └── stage1_extractability_judgment.json  # 等中间产物（可选）
```

## Workflow2Code / ARM 输出示例

```
ARM/
├── plan/
├── code/                 # workflow.py、test_runner.py
├── dataset/              # problems/*.md、test_cases.json
├── result/               # v1_baseline、v2_.../TEST_REPORT.md
└── trace/                # 迭代与问题生成记录
```

## 技术栈

- **向量化**：DashScope text-embedding-v4（维度见配置，常用 512/1024）
- **聚类**：Agglomerative、KMeans、HDBSCAN（`src/step1/cluster/`）
- **向量库**：LanceDB；Step3 可选 ByteHouse 思维链表
- **LLM**：GPUGEEK / LiteLLM Proxy
- **对象存储**：Volcengine TOS
- **Agent**：Cursor Skills（Workflower_v2、Workflow2Code 等）

## 测试

```bash
pytest tests/
```

## 相关仓库

- 应用代码与 Skills：[SiliconEinstein/Paper2tools](https://github.com/SiliconEinstein/Paper2tools)（本仓库）
- 聚类语料与示例 cluster：[starbilibili/workflow_cluster_raw](https://github.com/starbilibili/workflow_cluster_raw/tree/main/workflow/cluster)

## 开发文档（本地）

- `STEP1_REDESIGN.md`、`STEP2_DESIGN.md` — 分阶段设计说明
- `.claude/CLAUDE.md`、`.claude/TRACE.md` — 项目约定与开发日志
- `docs/` — 报告与图表（**不纳入本 Git 仓库**）

## License

MIT
