# Paper2Tools v2

学术论文推理步骤深度分析系统 -- 从大规模论文中提取、聚类和总结科研工作流模式。

## 项目概述

Paper2Tools v2 从学术论文的推理链（reasoning chain）出发，通过语义向量化、聚类和 LLM 驱动的信息提取，自动识别高频科研工作流模式及其关联工具。

### 三阶段流水线

| 阶段 | 功能 | 核心技术 |
|------|------|----------|
| **Step1** | 推理链向量化与聚类 | DashScope Embedding + KMeans |
| **Step2** | 工具信息注入 | GPT-5-mini + XML 增强 |
| **Step3** | 工作流结构化提取 | LLM + JSON Schema |

```
TOS 对象存储
  ├─ paper_ocr/xml/*_reasoning_chain.xml
  └─ paper_ocr/md/*.md
       ↓
Step1 → 向量化 → KMeans(k=30000) → Top 10% 簇 → 每簇最近 10 条
       ↓
Step2 → LLM 识别工具 → 注入 <ref type="tool"> → 上传 enriched XML
       ↓
Step3 → LLM 提取结构化工作流 → workflows.json
```

## 快速开始

### 环境准备

```bash
pip install -r requirements.txt

# 配置环境变量 (.env)
TOS_ACCESS_KEY=...
TOS_SECRET_KEY=...
LITELLM_PROXY_API_BASE=...
LITELLM_PROXY_API_KEY=...
```

### 运行

```bash
# 端到端运行（期刊数据集）
python test_journal_embedding.py

# 端到端运行（随机 5 万条）
python run_random50k_streaming.py

# 分步运行
python -m src.main --step 1 --config configs/step1_config.yaml
python -m src.main --step 2 --config configs/step2_config.yaml
python -m src.main --step 3 --config configs/step3_config.yaml
```

## 项目结构

```
paper2tools_v2/
├── src/
│   ├── step1/                  # 向量化与聚类
│   │   ├── data_loader.py      #   TOS 数据加载、XML 解析
│   │   ├── vectorizer.py       #   DashScope Embedding 异步客户端
│   │   ├── clustering.py       #   聚类对外唯一入口（API 由此导入）
│   │   ├── cluster/            #   聚类实现（KMeans/HDBSCAN/凝聚/GPU/指标/选簇）
│   │   └── pipeline.py         #   Step1 主流程
│   ├── step2/                  # 工具信息注入
│   │   ├── data_loader.py      #   XML + MD 数据加载
│   │   ├── tool_extractor.py   #   LLM 工具识别
│   │   ├── xml_enricher.py     #   XML 标签注入
│   │   └── pipeline.py         #   Step2 主流程
│   ├── step3/                  # 工作流提取
│   │   ├── schema.py           #   Workflow 数据结构定义
│   │   ├── workflow_extractor.py #  LLM 结构化提取
│   │   └── pipeline.py         #   Step3 主流程
│   ├── db/                     # LanceDB 向量数据库封装
│   ├── models/                 # LLM Provider 配置
│   └── main.py                 # CLI 入口
├── configs/                    # YAML 配置文件
│   ├── step1_config.yaml       #   期刊数据集配置
│   ├── step1_random50k_config.yaml # 随机数据集配置
│   ├── step2_config.yaml
│   ├── step3_config.yaml
│   └── domain_journals.yaml    #   期刊列表
├── tests/                      # 单元测试
├── data/                       # 数据与输出
│   ├── cache/                  #   缓存文件
│   ├── lance_db/               #   LanceDB 向量库
│   └── step1_output/           #   聚类结果与选择结果
├── notebooks/                  # 文档与分析
│   └── PROJECT_OVERVIEW.md     #   项目策划书
├── prompts/                    # LLM Prompt 模板
└── requirements.txt
```

## 数据规模

| 数据集 | 论文数 | 推理链数 | 向量维度 |
|--------|--------|----------|----------|
| 期刊 (bioinformatics) | ~62,000 | ~448,000 | 1024 |
| 随机采样 | 50,000 | 待统计 | 1024 |

## 配置说明

所有参数通过 YAML 配置管理，核心参数：

```yaml
# Step1 聚类配置
clustering:
  algorithm: "kmeans"     # kmeans / hdbscan
  n_clusters: 30000       # KMeans 簇数

# Step1 向量化配置
vectorizer:
  model: "text-embedding-v4"
  dimension: 1024
  concurrency: 50         # 异步 worker 数
```

## 技术栈

- **向量化**: DashScope text-embedding-v4 (1024 维)
- **聚类**: scikit-learn KMeans, HDBSCAN
- **向量数据库**: LanceDB + PyArrow
- **LLM**: GPT-5-mini (via LiteLLM Proxy)
- **对象存储**: Volcengine TOS
- **异步**: asyncio + httpx

## 测试

```bash
pytest tests/
pytest tests/test_step1/
pytest tests/test_step2/
pytest tests/test_step3/
```

## 详细文档

- [项目策划书](notebooks/PROJECT_OVERVIEW.md) -- 完整技术方案与规划
- `.claude/TRACE.md` -- 开发过程日志

## License

MIT
