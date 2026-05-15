# Paper2Tools v2

学术论文工作流提取系统 -- 从大规模论文中自动发现和总结科研工作流模式。

## 项目概述

Paper2Tools v2 从学术论文的推理链（reasoning chain）出发，通过语义向量化、聚类和 LLM 驱动的工作流提取，自动识别高频科研工作流模式。

### 核心流程

```
TOS 对象存储 (paper_ocr/)
  ├─ xml/*_reasoning_chain.xml  # 推理链 XML
  └─ md/*.md                     # 论文全文 Markdown
       ↓
Step1: 向量化 + 聚类 + 选择
  ├─ DashScope Embedding (512维)
  ├─ Agglomerative Clustering (自适应簇数)
  ├─ 选择 top 10% 簇
  └─ 每簇取离质心最近的 50 条链
       ↓
       下载 xml/md 到 data/{domain}/workflows/
       ↓
Workflower Skill (手动)
  ├─ 深度阅读论文 Methods 部分
  ├─ 提取 workflow 阶段与方法
  └─ 生成 LaTeX 综述 + 决策树
       ↓
Step3: Workflow 检索系统 (规划中)
  └─ 多路召回 + 重排序
```

## 快速开始

### 环境准备

```bash
pip install -r requirements.txt

# 配置环境变量 (.env)
TOS_ACCESS_KEY=...
TOS_SECRET_KEY=...
TOS_SECRET_KEY=...
TOS_BUCKET=...
DASHSCOPE_API_KEY=...
LITELLM_PROXY_API_BASE=...
LITELLM_PROXY_API_KEY=...
```

### 运行 Step1（通用领域流程）

```bash
# 完整流程：向量化 + 聚类 + 选择 + 下载
python run_step1_domain.py --domain materials_science
python run_step1_domain.py --domain environmental_science
python run_step1_domain.py --domain mathematics
python run_step1_domain.py --domain fluid_mechanics
python run_step1_domain.py --domain superconductivity

# 跳过向量化（使用已有向量）
python run_step1_domain.py --domain materials_science --skip-vectorization

# 仅下载（跳过聚类）
python run_step1_domain.py --domain materials_science --skip-clustering
```

**前置条件**：
- 如果 `data/{domain}/step1_output/paper_ids.json` 或 `paper_ids_{domain}.json` 存在，直接使用（跳过期刊检索）
- 否则从 `configs/domain_journals.yaml` 中的期刊列表构建 paper_ids

**输出**：
- `data/{domain}/step1_output/` — 聚类结果（cluster_centers.npy, cluster_labels.json, cluster_stats.json）
- `data/{domain}/workflows/cluster_{id}/` — 每个簇的 selected_chains.json + xml/ + md/
- `data/lance_db/` — 全局向量库（所有领域共用，通过 `domain` 字段区分）

### 运行 Workflower Skill

```bash
cd data/{domain}/workflows/cluster_{id}
# 使用 Claude Code 的 /workflower skill
# 输出: workflow_structure.json, review.tex, review.pdf, decision_tree.pdf
```

## 项目结构

```
paper2tools_v2/
├── src/
│   ├── step1/                  # Step1: 向量化与聚类
│   │   ├── data_loader.py      #   TOS 数据加载、期刊映射
│   │   ├── vectorizer.py       #   DashScope Embedding 批量调用
│   │   ├── clustering.py       #   聚类算法入口
│   │   ├── cluster/            #   聚类实现（Agglomerative/KMeans/HDBSCAN/GPU）
│   │   │   ├── agglomerative.py    #   受约束凝聚聚类（大规模优化）
│   │   │   ├── selector.py         #   簇选择与最近链提取
│   │   │   └── metrics.py          #   聚类质量指标
│   │   ├── workflow_file_organizer.py  # 按簇下载 xml/md
│   │   └── pipeline.py         #   Step1 主流程
│   ├── db/                     # LanceDB 向量数据库封装
│   │   ├── lance_vector_store.py
│   │   └── schema.py
│   └── models/                 # LLM Provider 配置
├── skills/Workflower/          # Workflower 3 阶段 skill
│   ├── SKILL_v2.md             #   Skill 定义（Phase 1-7）
│   └── prompts/                #   各阶段 Prompt 模板
├── configs/
│   ├── domain_journals.yaml    #   领域期刊配置
│   └── step1_superconductivity_config.yaml  # 超导专用配置（示例）
├── run_step1_domain.py         # 通用领域 Step1 入口脚本
├── run_step1_superconductivity.py  # 超导专用脚本（历史）
├── data/
│   ├── lance_db/               #   全局向量库（所有领域共用）
│   ├── {domain}/               #   各领域数据目录
│   │   ├── cache/              #     paper_ids 缓存
│   │   ├── step1_output/       #     聚类结果
│   │   └── workflows/          #     下载的 xml/md（按簇组织）
│   └── workflows_100/          #   历史数据（100 个簇）
├── notebooks/                  # 分析与文档
│   └── PROJECT_OVERVIEW.md     #   项目策划书
└── tests/                      # 单元测试
```

## 支持的领域

| 领域 | domain key | 代表性期刊 | 论文数 | 推理链数 |
|------|-----------|-----------|--------|---------|
| 超导 | `superconductivity` | Superconductivity | 54,789 | 312,261 |
| 材料科学 | `materials_science` | Nature Materials, Acta Materialia, ... | 84,168 | 405,524 |
| 环境科学 | `environmental_science` | Nature Sustainability, ES&T, Water Research, ... | 60,999 | ~300k |
| 数学 | `mathematics` | Annals of Math, SIAM, JCP, ... | ~50k | ~250k |
| 流体力学 | `fluid_mechanics` | JFM, Physics of Fluids, PRF, ... | ~40k | ~200k |
| 生物信息学 | `bioinformatics` | Bioinformatics, NAR, Genome Research, ... | 62,000 | 448,000 |

*注：材料科学、环境科学、数学、流体力学的期刊列表已配置，但向量化可能未完成*

## 数据规模

| 指标 | 数值 |
|------|------|
| 全局向量库 (data/lance_db) | 721,991 条 (superconductivity 486,991 + materials_science 235,000) |
| 向量维度 | 512 |
| 聚类算法 | Agglomerative (受约束凝聚，两阶段近似) |
| 选择策略 | Top 10% 簇 × 每簇 50 条最近链 |

## 配置说明

### 领域期刊配置 (configs/domain_journals.yaml)

```yaml
materials_science:
  label: "材料科学"
  journals:
    - "Nature Materials"
    - "Acta Materialia"
    - "Chemistry of Materials"
    # ...
```

### Step1 聚类配置（动态生成，无需单独 yaml）

```python
# run_step1_domain.py 中的 _build_config()
clustering:
  algorithm: "agglomerative"
  agglomerative:
    max_size: 500           # 簇大小上限
    min_pair_sim: 0.55      # 合并阈值（余弦相似度）
    micro_k: 3000           # 微聚类数量
  selection:
    top_percent: 0.10       # 选前 10% 的簇
    max_per_cluster: 50     # 每簇最多 50 条链
```

## 技术栈

- **向量化**: DashScope text-embedding-v4 (512 维)
- **聚类**: Agglomerative Clustering (受约束凝聚，两阶段近似)
- **向量数据库**: LanceDB + PyArrow
- **LLM**: GPT-4o-mini / Claude Sonnet (via LiteLLM Proxy)
- **对象存储**: Volcengine TOS
- **异步**: asyncio + httpx

## Workflower Skill 输出示例

每个 cluster 经过 Workflower 处理后生成：

```
data/{domain}/workflows/cluster_{id}/
├── selected_chains.json        # 50 条链的元数据
├── xml/                        # 50 个 XML 文件
├── md/                         # 对应论文的 MD 文件
├── workflow_structure.json     # 结构化工作流（阶段 + 方法）
├── paper_extractions.yaml      # 每篇论文的提取结果
├── workflow_3layer.md          # 三层工作流描述
├── review.tex                  # LaTeX 综述（含 toolbox/parambox/casebox/pitfallbox）
├── review.pdf                  # 编译后的 PDF
└── decision_tree.pdf           # 决策树可视化
```

## 测试

```bash
pytest tests/
pytest tests/test_step1/
```

## 详细文档

- [项目策划书](notebooks/PROJECT_OVERVIEW.md) -- 完整技术方案与规划
- `.claude/CLAUDE.md` -- 项目经验法则
- `.claude/TRACE.md` -- 开发过程日志
- `skills/Workflower/SKILL_v2.md` -- Workflower Skill 定义

## License

MIT
