# paper2tools_v2 过程日志

> 记录项目开发过程中遇到的问题、做出的决策、变更记录。具体事件写这里，提炼出的判断准则归入 `CLAUDE.md`。

---

## 2026-04-21

### 项目初始化 - 框架搭建

**背景**: 新建 paper2tools_v2 项目，独立于 paper2tools，用于学术论文推理步骤的深度分析。

**决策**:
1. **项目独立性**: 与 paper2tools 完全解耦，不复用代码，只消费其输出数据
2. **三步骤架构**:
   - Step1: 推理步骤文本 → 向量化 → 语义聚类
   - Step2: reasoning_chain XML + 工具信息 → 增强 XML
   - Step3: 增强数据 → 典型工作流总结
3. **模块化设计**: 每个 Step 独立目录，共享功能放 `common/`
4. **测试优先**: 每个模块都预留对应的测试文件

**输入数据格式**（来自 paper2tools）:
- `reasoning_chain.xml`: 包含 `<conclusion_reasoning>` → `<reasoning>` → `<step id="N">` 结构
- `_tools_extract_result.json`: 包含 `tools[]`（工具列表）和 `ptlink[]`（工具链）
- 新 Schema 中 tools 有 `var[]` 版本粒度结构，ptlink 有 `prereq[]` + `compute[]`

**创建的文件**: 完整项目框架，包括：
- 源码文件（src/ 下 17 个 Python 文件）
- 测试文件（tests/ 下 14 个 Python 文件）
- 配置文件（configs/ 下 3 个 YAML 文件）
- 项目文件（README.md, requirements.txt, .gitignore）
- 文档文件（.claude/CLAUDE.md, .claude/TRACE.md）

---

### 数据库模块抽离 - src/db/ 创建

**背景**: 用户要求"关于lance数据库的基础操作需要抽离出来，单独存放在db文件夹中，要有模块化、接口化思想"

**调研结果**（通过 Agent 探索）:
- paper2tools_v2 当前状态：src/db/ 不存在，step1/vectorizer.py 和 clustering.py 只有 docstring 无实现
- paper2tools v1 参考：src/db/ 有 14 个文件，包含完整的 Lance 工具别名库（5 张表）和进度追踪表
- v1 设计模式：PyArrow schema 独立定义（schema.py）、内存缓存层、TOS 增量同步机制

**设计决策**:
1. **接口与实现分离**: 定义 VectorStore/MetadataStore 抽象基类（base.py）
2. **Schema 独立**: schema.py 只依赖 pyarrow，不导入 lancedb（避免多进程问题）
3. **内存缓存**: cache.py 实现 LRU 缓存，减少数据库 I/O
4. **TOS 同步**: sync.py 实现增量上传/下载（快照对比机制）
5. **配置管理**: config.py 定义 LanceDBConfig 数据类

**创建的文件**（src/db/ 下 8 个文件）:
- `__init__.py`: 模块导出
- `base.py`: VectorStore/MetadataStore 抽象基类
- `schema.py`: PyArrow schema 定义（4 个 schema）
- `cache.py`: VectorCache/MetadataCache 实现
- `config.py`: LanceDBConfig/VectorStoreConfig 配置类
- `sync.py`: LanceTosSync 同步管理器
- `lance_vector_store.py`: LanceVectorStore 实现
- `lance_metadata_store.py`: LanceMetadataStore 实现

**问题**: 创建过程耗时过长（7 个文件串行写入）

**根因分析**:
1. 用 Agent 探索了可以直接 Glob/Grep 完成的简单查询
2. 逐个文件串行写入，没有并行
3. 每个文件写了大量 docstring（200+ 行），实际代码占比低

**改进方向**（已写入 CLAUDE.md）:
- 简单查询直接用 Glob/Grep，不用 Agent
- 互不依赖的文件用并行工具调用
- docstring 精简，只写核心内容
- 批量创建相似文件用 Bash 循环

---

### Step1 向量化与聚类设计

**背景**: 继续设计 Step1，已完成 data_loader 设计，现在设计 vectorizer 和 clustering。

**关键决策**:

1. **向量化结果持久化**: 使用 LanceDB 存储向量，不用 .npy 文件
   - 原因: 支持增量更新（只向量化新 step）、ANN 搜索、聚类调参时不重算
   - 策略: 首次全量向量化，后续只处理 LanceDB 中不存在的 step_id

2. **Embedding 模型**: 使用自定义 HTTP API（dashscope provider）
   - API: `https://openapi.dp.tech/openapi/v1/test/vectorize`
   - 请求: `POST {"text": "...", "provider": "dashscope"}` + accessKey header
   - 响应: `{"status": 0, "data": {"vector": [512 floats]}}`
   - 维度: 512

3. **聚类粒度**: ReasoningStep（不是 ReasoningChain）
   - 每个 step 独立向量化和聚类

4. **聚类算法**: 优先 HDBSCAN（自动发现簇数），备选 KMeans（需搜索最优 k）

5. **聚类后处理**: 按簇大小排序 → 取 top 10% → 每个簇提取 1 个 workflow
   - 假设: 聚类质量好的情况下，大簇代表常见模式

6. **数据规模**: 未知，需要统计 bioinformatics 领域有多少论文有 reasoning_chain.xml

**更新的文件**:
- `src/step1/vectorizer.py`: 替换为使用 gaia-lkm 的 Embedder（异步、并发、重试）
- `src/step1/pipeline.py`: 更新为异步调用 vectorize_reasoning_chains
- `src/db/schema.py`: 向量维度注释改为 512，去掉 has_tool_refs 字段
- `configs/step1_config.yaml`: 更新 vectorizer 配置（去掉 model_type，增加 concurrency 等）
- `src/step1/data_loader.py`: ReasoningStep 去掉 has_tool_refs，解析逻辑不再检测 tool refs

**待完成**:
- 统计数据规模（TOS 上 bioinformatics 论文数、总 step 数）
- 在 clustering.py 或 pipeline.py 中设计 top 10% 簇选择逻辑

---

### Step1 代码实现完成

**背景**: 将 Step1 的四个模块从规划文档转为可运行代码。

**实现内容**:

1. **data_loader.py** - 数据加载
   - `ReasoningStep` / `ReasoningChain` dataclass 定义
   - `load_journal_config()`: 从 domain_journals.yaml 读取期刊列表
   - `build_paper_id_list()`: 构建/缓存 paper_id 列表（两级缓存）
   - `parse_reasoning_chain_xml()`: lxml 解析 XML，提取 conclusion_reasoning 块
   - `load_reasoning_chains_from_tos()`: ThreadPoolExecutor 并行加载
   - `save/load_reasoning_chains_to/from_jsonl()`: JSONL 持久化
   - `load_data_for_step1()`: 主入口，串联上述逻辑

2. **vectorizer.py** - 向量化
   - `create_embedder()`: 根据配置创建 gaia-lkm Embedder 实例
   - `vectorize_reasoning_chains()`: 异步批量向量化，增量写入 LanceDB
     - 展平 chains → steps，过滤已存在 step_id，调用 embedder.embed_batch()

3. **clustering.py** - 聚类
   - `KMeansClustering` / `HDBSCANClustering`: 聚类算法实现
   - `create_clustering_algorithm()`: 工厂函数
   - `evaluate_clustering()`: silhouette / calinski_harabasz / davies_bouldin 指标
   - `find_optimal_k()`: 自动搜索最优 k（silhouette 方法）
   - `cluster_steps()`: 从 LanceDB 读取向量 → 聚类 → 回写 cluster_id
   - `save_cluster_results()`: 保存 labels.json / stats.json / centers.npy

4. **pipeline.py** - 主流程
   - `run_step1_pipeline()`: 串联 加载→向量化→聚类→保存，5 步骤带进度打印

5. **src/step1/__init__.py**: 导出所有公共接口

6. **src/main.py**: CLI 主入口，支持 `--step 1/2/3/all --config`

**关键设计**:
- 向量化增量：通过对比 LanceDB 中已有 step_id 实现，重跑自动跳过
- 聚类幂等：每次重新执行，cluster_id 回写覆盖（聚类是全局操作）
- 异步向量化：复用 gaia-lkm Embedder，worker pool + 自动重试

**遗留问题**:
- `JournalMapper` 的实际构造函数签名需要与 paper2tools 对齐（当前假设接受 `cache_dir` 参数）
- `LanceTosStore.get_object()` 接口需要确认（当前假设返回 str）

---

## 2026-04-21 (续)

### Step1 首次运行 - 环境配置与调试

**背景**: 完成 Step1 代码实现后，开始首次运行测试。

**遇到的问题**:

1. **TOS 认证问题**: 
   - 初始运行报 403 Access Denied
   - 用户创建 `.env` 文件提供 TOS 凭证
   - 发现 Windows 行尾符 `\r` 导致 bucket name 解析错误
   - 解决: `sed -i 's/\r$//' .env`

2. **期刊列表配置错误**:
   - 配置文件包含 31 个期刊，但用户要求只处理前 9 个核心期刊
   - 修改 `configs/domain_journals.yaml`，只保留前 9 个期刊
   - 清理 cache 和 lance_db，强制重新构建

3. **输出缓冲问题**:
   - 初始运行用 `python3 test_step1.py` 无法看到实时输出
   - 改用 `python3 -u` (unbuffered) + `tee` 记录日志
   - 最终用 `nohup python3 -u test_step1.py > /tmp/step1_run.log 2>&1 &` 后台运行

4. **paper_list 输出位置**:
   - 用户指出应该将 paper_id_list 保存到 step1_output 作为正式输出
   - 修改 `src/step1/pipeline.py`，在加载数据后将 paper_list 从 cache 复制到 output_dir

**当前状态**:
- 测试脚本在后台运行（PID: 1207489）
- 输出记录到 `/tmp/step1_run.log`
- 正在执行 journal mapping 构建（从 TOS 扫描所有论文路径）
- 预计耗时较长，等待完成后查看结果

**修改的文件**:
- `configs/domain_journals.yaml`: 只保留 9 个核心期刊
- `src/step1/pipeline.py`: 添加 paper_list 复制到 step1_output 的逻辑
- `.env`: 修复行尾符问题

**待验证**:
- journal mapping 构建是否成功
- paper_id 筛选是否正确（只包含 9 个期刊的论文）
- reasoning_chain.xml 加载是否正常
- 向量化和聚类是否能完成


---

## 2026-04-21（续）

### Step2 工具信息注入实现

**背景**: 实现 Step2，从论文 MD + reasoning_chain.xml 中提取工具信息并注入 XML。

**关键决策**:

1. **输入来源澄清**: Step2 输入不是 `_tools_extract_result.json`，而是论文 MD（`paper_ocr/md/`）和 reasoning_chain.xml（`paper_ocr/xml/`）
2. **输出路径**: `tos://wenyon-paper/paper_ocr/tools/v2/reasoning_chain_refine/`，文件名 `{paper_id}_reasoning_chain_refine.xml`
3. **LLM 策略**: 对每个 `<conclusion_reasoning>` 块单独调用 LLM，传入该块的 reasoning XML + 完整论文 MD，让 LLM 识别工具并建立 tool↔step 映射
4. **输出格式**: 与 paper2tools Stage3 产物一致——`<ref type="tool" tool_id="TX">` 插入 step 末尾，`<tools>` 节点追加到 conclusion_reasoning 末尾
5. **模型复用**: 直接复用 paper2tools 的 `src/models/llm_providers.py`（已迁移到本项目）
6. **TOS 访问**: 直接使用 `tos` SDK，不依赖 paper2tools 的 `LanceTosStore`（避免耦合）

**创建的文件**:
- `configs/config.yaml`: LLM provider 配置
- `configs/step2_config.yaml`: 重写为 TOS 路径 + LLM 配置
- `src/utils.py`: 配置加载（与 paper2tools 同构）
- `prompts/step2_extract_tools.md`: LLM prompt 模板
- `src/step2/data_loader.py`: TOS 数据加载（XML + MD）
- `src/step2/tool_extractor.py`: LLM 工具提取
- `src/step2/xml_enricher.py`: XML 注入逻辑
- `src/step2/pipeline.py`: 异步并发主流程
- `src/step2/__init__.py`: 模块导出
- `src/main.py`: 新增 Step2 入口
- `test_step2.py`: 测试脚本

**实现细节**:
- TOS endpoint 归一化：`tos-s3-cn-beijing.volces.com` → `tos-cn-beijing.volces.com`
- paper_id 文件系统化：`/` → `%2F`（与 paper2tools 一致）
- 环境变量加载：在 data_loader.py 中自动 `load_dotenv()`
- 列举优化：`list_objects` 设置 `max_keys=1000` 避免单次请求过大
- 异步并发：使用 `asyncio.Semaphore` 控制并发数（默认 10）
- 断点续传：`skip_existing=True` 时跳过已存在的输出文件

**测试状态**:
- TOS 连接正常（已验证）
- 代码缩进错误已修复（data_loader.py 重复代码删除）
- 测试脚本后台运行中（TOS 列举操作耗时较长）
- 待验证：完整的 LLM 调用 → XML 注入 → 上传流程

**运行方式**:
```bash
# 测试单篇论文
python test_step2.py

# 批量运行
python -m src.main --step 2 --config configs/step2_config.yaml
```

**已知问题**:
- TOS `list_objects` 操作在大量文件时耗时较长（已设置 `max_keys=1000` 分页）
- 需要确保 `.env` 文件存在且包含正确的 TOS 凭证

---

## 2026-04-21（续）

### Step3 Workflow 提取模块实现

**背景**: 设计并实现 Step3，目标是从任意文本（论文或思维链）中提取结构化 workflow。与原有空壳设计的关键差异：**不依赖 Step2 的 enriched XML**，通用化处理任意文本输入。

**关键决策**:
1. **LLM 驱动提取**: 使用 `gpt5_mini_completion` 将非结构化文本转为结构化 JSON
2. **通用化 schema**: 去掉 `domain_tags` 等领域相关字段，保留 `source_ids` 追踪来源
3. **不处理长文本**: 暂不做分块/摘要策略，直接发全文给 LLM
4. **聚合暂缓**: `workflow_aggregator.py` 保留为 placeholder，待有多源聚合需求时实现

**输出 schema**:
```json
{
  "workflow_id": "string",
  "title": "string",
  "description": "string",
  "source_ids": ["string"],
  "steps": [{
    "step_id": 1,
    "logic_description": "...",
    "tool_intent": "...",
    "suggested_tools": ["..."],
    "io_schema": {"inputs": [...], "outputs": [...]}
  }]
}
```

**创建/修改的文件**:
- `src/step3/schema.py`（新建）: IOField, IOSchema, WorkflowStep, Workflow dataclass，含 to_dict/from_dict
- `src/step3/workflow_extractor.py`（重写）: prompt 构建 + LLM 调用 + JSON 解析，解析失败自动重试一次
- `src/step3/data_loader.py`（重写）: 通用文本加载器，支持 .txt/.xml/.json/.md
- `src/step3/pipeline.py`（重写）: 加载文本 → 逐个提取 → 保存 JSON + 统计
- `src/step3/__init__.py`: 模块导出
- `configs/step3_config.yaml`: 简化为 input_path/output_dir/temperature/verbose
- `src/main.py`: 添加 run_step3，接入 CLI

---

### src/models 精简重构

**背景**: `llm_providers.py` 配置混乱，264 行中大量未使用的代码。

**精简内容**:
| 删除项 | 原因 |
|--------|------|
| `_llm_exception_context()` (44 行) | 过度工程，异常本身信息已足够 |
| `gpt5_mini_litellm_completion()` | 与 `gpt5_mini_completion` 功能重复 |
| `_deepseek_cfg` / `_qwen_cfg` / `_doubao_cfg` | 从未使用 |
| `_gpugeek_image_base` / `_gpugeek_image_model` | 从未使用 |
| `BaseLLMProvider` 抽象类 (base.py) | 无任何子类实现 |
| `mcp_url` / `wiki_search_api_base` 属性 | 与本项目无关 |

**重构内容**:
- 统一配置获取为 `_get_env_or_config(provider, key, env_var)`，环境变量优先
- 客户端只在有 key+base_url 时才创建，避免空配置报错
- 264 行 → ~190 行

**验证**: step2 pipeline 引用的 `gpt5_mini_completion`, `gpt_completion`, `gemini_completion` 均保持不变，import OK

---

## 2026-04-21 晚 - 端到端测试流程实现与启动

### 任务需求

用户要求同时运行两个测试：
1. **期刊测试**: 特定期刊论文（bioinformatics 领域 9 个期刊）
2. **随机50k测试**: 从 XML 文件夹随机选取 5 万条数据

流程: Step1（聚类）→ 选择 top 10% 簇 → Step2（工具信息注入）→ Step3（workflow 提取）

要求: 后台运行，自动监控，遇到错误自动修复，明早看到结果。

### 实现内容

**1. 新增模块**:
- `src/step1/cluster_selector.py`: 从聚类结果选择 top 10% 簇，每簇至多 10 条思维链
- `src/step1/visualizer.py`: 生成 PCA 降维可视化和对比图
- `src/step2/batch_processor.py`: 批量处理多篇论文，拼接思维链文本
- `src/step3/step2_loader.py`: 从 Step2 输出的 XML 加载文本送入 Step3
- `run_full_pipeline.py`: 端到端测试脚本，并行运行两个测试
- `monitor_pipeline.sh`: 监控脚本，每 5 分钟检查一次状态

**2. 修改内容**:
- `src/step1/data_loader.py`: 实现 `mode="random_sample"` 逻辑，修复 `LanceTosStore.list_tos_objects()` 调用
- `src/step1/pipeline.py`: 修复 `target_domain` 缺失问题（random_sample 模式）
- `src/step1/clustering.py`: 增加空向量检查，避免 `tuple index out of range`
- `src/step3/data_loader.py`: 增加 `mode="step2_output"` 自动检测

### 遇到的问题与修复

**问题 1-4**: TOS API 调用、配置缺失、空数据检查 — 已全部修复

**问题 5**: Embedding API 401 Unauthorized
- **根因**: `configs/step1_config.yaml` 中的 `access_key` 已过期
- **状态**: **未解决** — 外部 API 密钥问题
- **影响**: 两个测试都卡在 Step1 向量化阶段

### 当前状态

**流水线**: 运行中（PID 1297716），被 401 错误阻塞
**日志**: `logs/full_pipeline.log`, `logs/monitor.log`
**监控**: `monitor_pipeline.sh` 每 5 分钟检查一次

**阻塞**: Embedding API 密钥过期，无法完成 Step1 向量化

**待用户处理**: 更新 `configs/step1_config.yaml` 和 `configs/step1_random50k_config.yaml` 中的 `vectorizer.access_key`

---

## 2026-04-22

### Random 50k 流水线 - TOS 凭证与分页读取问题

**背景**: 用户要求"同步开始随机 5w 篇 xml 的处理"，从 TOS 随机领域采样 5 万篇论文。

**遇到的问题**:

**问题 1**: Random 50k 流水线从 bioinformatics 列表采样，不是随机领域
- **现象**: `run_random50k_streaming.py` 的 `get_paper_ids()` 从 `paper_ids_bioinformatics.json` 采样 5 万个
- **根因**: 代码逻辑错误，应该从 TOS 枚举 `paper_ocr/xml/` 获取不限期刊的 paper_id
- **修复**: 改为 TOS 分页读取逻辑

**问题 2**: TOS 操作全部返回 403 Access Denied
- **现象**: `list_objects`、`get_object`、`head_object` 全部 403
- **排查过程**: 
  1. 怀疑 list 权限不足，尝试用 `get_object` 单个下载 → 也 403
  2. 怀疑 `paper_ocr/xml/` 路径权限，尝试 `paper_ocr/md/` → 也 403
  3. 检查 `StageConfig` 发现 `tos_access_key` 和 `tos_secret_key` 为空
- **根因**: `.env` 文件存在但未加载，`os.getenv()` 读到空字符串
- **修复**: 在 `run_random50k_streaming.py` 开头加 `load_dotenv('/personal/paper2tools_v2/.env')`

**问题 3**: 下载阶段 100% 失败但无错误日志
- **现象**: "成功: 0 | 失败: 7000"，但日志中没有异常信息
- **根因**: `except Exception:` 裸捕获只计数不记录
- **修复**: 改为 `except Exception as exc: if failed < 5: print(exc)`

**问题 4**: 自己编写的 TOS 枚举代码运行失败
- **现象**: `AttributeError: 'LanceTosStore' object has no attribute 'client'`
- **根因**: 没有先读 `staged_lance/storage.py` 的实际接口，用了不存在的属性和方法
- **修复**: 参考已有代码，用 `get_tos_client()` 和 `config.tos_bucket`

**最终方案**: TOS 分页读取 `paper_ocr/xml/`，筛选 `_reasoning_chain.xml` 后缀，收集到 5 万个 paper_id 就停止。

**结果**: 185 页收集到 5 万个 paper_id（38 秒），下载阶段待测试。

---

### Journal 向量化流水线 - chunk_size 优化

**背景**: Journal 数据集（448k 条思维链）向量化速度慢，ETA 141 分钟。

**问题**: chunk_size=64 导致 7006 个 chunk，每个 chunk 都要 flush 到 LanceDB，I/O 开销巨大。

**优化**: 
- 将 `test_journal_embedding.py` 的 chunk_size 从 64 改为 5000
- 减少 chunk 数量从 7006 → 90
- 减少 flush 次数，提升吞吐量

**结果**: 
- Chunk 23: 4999 ok, 68 RPS, ETA 4 分钟（相比之前 141 分钟大幅提升）
- 内存稳定在 1.6GB（RSS），无 OOM 风险

**当前状态**: Journal 流水线运行中（PID 150922），已完成 34/90 chunk（59988/448443），ETA 31 分钟。

---

### 经验总结（已写入 CLAUDE.md）

1. **环境变量加载**: `.env` 必须在脚本开头 `load_dotenv()` 显式加载
2. **错误记录**: 批处理中至少记录前 N 个错误，不要静默吞掉异常
3. **接口复用**: 使用外部模块前先读其源码，不要猜 API
4. **chunk_size 调优**: 大规模批处理的 chunk_size 直接影响吞吐量，观察 flush 耗时占比

---

### 聚类算法改进 - UMAP 降维 + 参数调优

**背景**: 当前 HDBSCAN 聚类在 1024 维空间上效果差（维度灾难），min_cluster_size=10 对 44 万条数据太小，评估指标 O(n²) 在大规模数据上不可行。

**验证前提**: DashScope text-embedding-v4 输出向量已严格归一化（norm=1.0），因此欧氏距离 ∝ 余弦距离。距离度量本身不是问题。

**核心问题**:
1. 1024 维空间中密度估计失效（所有点距离趋于相同）
2. min_cluster_size=10 → 大量小簇 + 高噪声
3. silhouette_score 全量计算 O(n²) → OOM

**改动内容**:
1. `src/step1/clustering.py`:
   - 新增 `reduce_dimensions_umap()`: UMAP 1024→50 维，metric='cosine'
   - 修改 `cluster_steps()`: 新增 `umap_config` 参数，可选在聚类前降维
   - 改进 `evaluate_clustering()`: 采样 silhouette（1 万条），新增 noise_ratio、簇大小分布统计
   - 改进打印：展示 top 20 最大簇、完整统计面板

2. `configs/step1_config.yaml` + `configs/step1_random50k_config.yaml`:
   - 新增 `umap` 配置块（enabled/n_components/n_neighbors/min_dist/metric）
   - min_cluster_size: 10→100, min_samples: 5→10

3. `requirements.txt`: 新增 umap-learn>=0.5.3

4. 更新所有 caller（pipeline.py, test_journal_embedding.py, run_random50k_streaming.py, run_random50k_step_by_step.py）传入 umap_config

**当前状态**: Journal 向量化进行中（325026/448443），聚类将在向量化完成后运行。

---

### 聚类策略调整 - 改用 KMeans + 距离选择

**背景**: 用户要求先不用 UMAP 降维（降维会损失信息），改用简单的 KMeans，固定 k=30000，选 top 10% 簇，每簇取离中心最近的 10 个点。

**改动内容**:
1. `configs/step1_config.yaml` + `configs/step1_random50k_config.yaml`:
   - `algorithm: "kmeans"`, `n_clusters: 30000`
   - `umap.enabled: false`（保留配置，后续需要时可开启）

2. `src/step1/cluster_selector.py` 重写:
   - 输入：`vector_store, centers, labels, chain_ids`
   - 逻辑：按簇大小排序 → 选 top 10% → 每簇计算成员到中心的距离 → 取最近 K 个
   - 输出：`selected_chains.json`（含 chain_id/cluster_id/distance/paper_id/chain_text）、`selection_stats.json`、`selected_paper_ids.json`

3. `test_journal_embedding.py` + `run_random50k_streaming.py`:
   - 聚类后调用 `select_top_clusters()` + `save_selection()`

**当前状态**: Journal 向量化 84.1% (377011/448443)，向量化完成后将运行 KMeans k=30000。

---