# Paper2Tools v2: 学术论文推理步骤分析与工作流提取

## 项目概述

Paper2Tools v2 是一个面向学术论文的推理步骤深度分析系统，旨在从大规模生物信息学论文中自动提取、聚类和总结典型的科研工作流模式。通过语义理解和聚类技术，本项目能够识别出研究人员在解决特定问题时常用的推理路径和工具组合，为科研工作流的标准化和自动化提供数据支撑。

## 核心目标

### 1. 推理步骤的语义聚类
从数十万篇论文的推理链（reasoning chain）中，识别出语义相似的推理步骤模式。例如：
- "使用 BLAST 进行序列比对" 与 "通过 BLAST 搜索同源序列" 应被聚为一类
- "使用 t-test 检验显著性" 与 "进行统计显著性分析" 应被识别为相似步骤

### 2. 工具与推理步骤的精确关联
在推理链 XML 中为每个推理步骤补充关联的工具信息，建立 "推理意图 → 工具实现" 的映射关系。

### 3. 典型工作流的归纳总结
基于聚类结果，提取高频出现的工作流模式，形成可复用的科研流程模板。

## 技术方案

### 整体架构

项目采用三阶段流水线架构（Step1 → Step2 → Step3），每个阶段独立封装，支持单独运行和调试。

```
输入数据 (TOS 对象存储)
  ├─ paper_ocr/xml/*_reasoning_chain.xml    # 原始推理链
  └─ paper_ocr/md/*.md                       # 论文全文
       ↓
┌─────────────────────────────────────────────────────────┐
│ Step1: 向量化与聚类                                      │
│  - 文本向量化 (DashScope text-embedding-v4, 1024 维)    │
│  - KMeans 聚类 (k=30000)                                │
│  - Top 10% 簇选择 + 距离筛选                             │
├─────────────────────────────────────────────────────────┤
│ 输出: data/step1_output/                                │
│  ├─ cluster_labels.json         # 聚类标签               │
│  ├─ cluster_stats.json          # 聚类统计               │
│  ├─ selected_chains.json        # 选中的思维链           │
│  └─ selected_paper_ids.json     # 选中的论文 ID          │
└─────────────────────────────────────────────────────────┘
       ↓
┌─────────────────────────────────────────────────────────┐
│ Step2: 工具信息注入                                      │
│  - LLM 驱动的工具识别 (GPT-5-mini)                      │
│  - 推理步骤 ↔ 工具的精确映射                             │
│  - XML 增强 (插入 <ref type="tool"> 标签)               │
├─────────────────────────────────────────────────────────┤
│ 输出: tos://wenyon-paper/paper_ocr/tools/v2/            │
│       reasoning_chain_refine/{paper_id}_*.xml           │
└─────────────────────────────────────────────────────────┘
       ↓
┌─────────────────────────────────────────────────────────┐
│ Step3: 工作流总结                                        │
│  - LLM 驱动的结构化提取                                  │
│  - 工作流 schema 定义 (步骤/工具/输入输出)               │
│  - 跨论文的工作流聚合                                    │
├─────────────────────────────────────────────────────────┤
│ 输出: data/step3_output/                                │
│  ├─ workflows.json              # 工作流库               │
│  └─ workflow_stats.json         # 统计信息               │
└─────────────────────────────────────────────────────────┘
```

### Step1: 向量化与聚类

#### 数据规模
- **期刊数据集**: 9 个生物信息学核心期刊，约 44.8 万条推理链
- **随机数据集**: 从全领域随机采样 5 万条推理链

#### 向量化技术
- **模型**: DashScope text-embedding-v4 (1024 维，归一化向量)
- **并发策略**: 50 worker 异步并发，自动重试 + jitter backoff
- **增量处理**: 基于 LanceDB 的已有向量检测，支持断点续传
- **流式处理**: 分 chunk 读取 JSONL，内存恒定 (~2GB)

#### 聚类策略
- **算法**: KMeans (k=30000)
- **选择策略**: 
  - 按簇大小排序，选 top 10% (3000 个簇)
  - 每簇取离中心最近的 10 个点
  - 最终输出约 30,000 条高质量思维链
- **评估指标**: 
  - Silhouette score (采样 1 万条，避免 O(n²) OOM)
  - 噪声比例、簇大小分布
  - Calinski-Harabasz、Davies-Bouldin

#### 技术亮点
- **维度灾难应对**: 保留 UMAP 降维能力（1024→50 维），可通过配置开启
- **大规模优化**: chunk_size=5000，减少 flush 次数，吞吐量提升 35 倍
- **幂等性设计**: 中断后重启自动跳过已完成项

### Step2: 工具信息注入

#### LLM 驱动的工具识别
- **模型**: GPT-5-mini (高性价比，适合大规模批处理)
- **输入**: 论文全文 MD + 单个 `<conclusion_reasoning>` 块
- **输出**: JSON 格式的工具列表 + 工具↔步骤映射

#### XML 增强策略
- **插入位置**: 在 `<step>` 节点末尾插入 `<ref type="tool" tool_id="TX">`
- **工具定义**: 在 `<conclusion_reasoning>` 末尾追加 `<tools>` 节点
- **格式兼容**: 与 paper2tools Stage3 产物格式一致

#### 并发与容错
- **异步并发**: `asyncio.Semaphore` 控制并发数 (默认 10)
- **断点续传**: `skip_existing=True` 跳过已存在的输出文件
- **TOS 直传**: 处理结果直接上传到对象存储，无本地缓存

### Step3: 工作流总结

#### 结构化 Schema
```python
Workflow:
  - workflow_id: str
  - title: str
  - description: str
  - source_ids: List[str]  # 来源论文 ID
  - steps: List[WorkflowStep]

WorkflowStep:
  - step_id: int
  - logic_description: str       # 推理逻辑描述
  - tool_intent: str             # 工具使用意图
  - suggested_tools: List[str]   # 推荐工具列表
  - io_schema:
      inputs: List[IOField]      # 输入数据类型
      outputs: List[IOField]     # 输出数据类型
```

#### LLM 提取策略
- **模型**: GPT-5-mini
- **输入**: Step2 增强后的 XML 或任意文本
- **Prompt 设计**: 
  - 显式要求 JSON 输出
  - 允许空输出（对抗幻觉）
  - 所有字段自包含（脱离原文也能理解）
- **解析容错**: JSON 解析失败自动重试一次

## 数据存储

### LanceDB 向量数据库
- **表结构**: `chain_embeddings` (chain_id, vector, paper_id, journal, cluster_id, ...)
- **索引**: 支持 ANN 搜索（为后续相似度查询预留）
- **批量操作**: `batch_update_metadata` 回写聚类标签

### TOS 对象存储
- **输入**: `tos://wenyon-paper/paper_ocr/{xml,md}/`
- **输出**: `tos://wenyon-paper/paper_ocr/tools/v2/reasoning_chain_refine/`
- **访问模式**: 分页读取 (`list_objects` + `marker`)，避免单次请求过大

### 本地缓存
- **JSONL 格式**: 推理链数据持久化，支持流式读取
- **JSON 格式**: 聚类结果、统计信息、选择结果

## 配置管理

所有参数通过 YAML 配置文件管理，支持多场景切换：

- `configs/step1_config.yaml`: 期刊数据集配置
- `configs/step1_random50k_config.yaml`: 随机数据集配置
- `configs/step2_config.yaml`: 工具注入配置
- `configs/step3_config.yaml`: 工作流提取配置
- `configs/domain_journals.yaml`: 期刊列表定义

## 运行方式

### 端到端运行
```bash
# 期刊数据集
python test_journal_embedding.py

# 随机 5 万条
python run_random50k_streaming.py
```

### 分步运行
```bash
# Step1: 向量化 + 聚类
python -m src.main --step 1 --config configs/step1_config.yaml

# Step2: 工具注入
python -m src.main --step 2 --config configs/step2_config.yaml

# Step3: 工作流提取
python -m src.main --step 3 --config configs/step3_config.yaml
```

## 性能指标

### 向量化性能
- **吞吐量**: ~70 RPS (50 worker 并发)
- **内存占用**: ~2GB (流式处理)
- **容错率**: <1% 失败率 (自动重试)

### 聚类性能
- **KMeans k=30000**: 约 5-10 分钟 (44 万条，1024 维)
- **评估指标计算**: 采样 1 万条，<1 分钟

### 工具注入性能
- **并发数**: 10 (受 LLM API 限流约束)
- **单篇耗时**: ~5-10 秒 (取决于论文长度)

## 技术栈

- **语言**: Python 3.12
- **向量化**: DashScope Embedding API, httpx
- **聚类**: scikit-learn (KMeans), HDBSCAN, UMAP
- **向量数据库**: LanceDB, PyArrow
- **LLM**: OpenAI GPT-5-mini, LiteLLM
- **对象存储**: Volcengine TOS SDK
- **异步框架**: asyncio
- **配置管理**: PyYAML

## 项目特色

### 1. 工程化设计
- **模块化**: 每个 Step 独立封装，接口清晰
- **幂等性**: 支持断点续传，中断后重启不重复计算
- **可观测**: 实时进度打印，ETA 估算，详细统计

### 2. 大规模数据处理
- **流式处理**: 内存恒定，支持百万级数据
- **并发优化**: 异步 worker pool，充分利用 I/O 等待时间
- **增量更新**: 基于已有数据检测，避免重复计算

### 3. 灵活配置
- **算法可插拔**: KMeans / HDBSCAN 通过配置切换
- **降维可选**: UMAP 降维通过 `enabled` 开关控制
- **参数可调**: 所有超参数通过 YAML 管理

### 4. 生产就绪
- **容错机制**: 异常采样记录，高错误率提前终止
- **环境隔离**: `.env` 文件管理凭证，不硬编码
- **日志规范**: 结构化日志，便于问题排查

## 应用场景

### 1. 科研工作流推荐
根据用户的研究问题，推荐相似场景下的典型工作流和工具组合。

### 2. 工具使用模式分析
统计特定工具在不同研究场景下的使用频率和组合模式。

### 3. 论文质量评估
通过推理链的完整性和工具使用的合理性，辅助评估论文的方法学质量。

### 4. 科研知识图谱构建
将推理步骤、工具、数据类型构建为知识图谱，支持复杂查询和推理。

## 未来规划

### 短期 (1-3 个月)
- [ ] 完成 44 万条期刊数据的聚类和工具注入
- [ ] 提取 top 1000 个高频工作流模式
- [ ] 构建工作流可视化界面

### 中期 (3-6 个月)
- [ ] 扩展到更多学科领域 (化学、物理、医学)
- [ ] 引入图神经网络优化聚类质量
- [ ] 开发工作流相似度搜索 API

### 长期 (6-12 个月)
- [ ] 构建科研工作流知识图谱
- [ ] 开发工作流自动生成工具
- [ ] 与科研平台集成，提供实时推荐

## 团队与联系

本项目由 [团队名称] 开发维护，专注于科研自动化和知识提取技术。

- **项目主页**: [待补充]
- **技术文档**: `/personal/paper2tools_v2/.claude/CLAUDE.md`
- **开发日志**: `/personal/paper2tools_v2/.claude/TRACE.md`

---

*最后更新: 2026-04-22*
