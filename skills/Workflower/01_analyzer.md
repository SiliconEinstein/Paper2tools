---
name: workflower-analyzer
description: 一次性完成链条分类、方法提取、决策树构建和综述规划（合并原01+02）
language: zh-CN
---

# 01 分析器与规划器

## 功能概述

**合并原 01_chain_classifier + 02_workflow_structure_builder**

一次性完成：
1. 链条质量分类（A/B/C + 主线/旁支）
2. 方法名提取和频次统计
3. 决策树结构构建
4. 综述结构规划

**优化点**：
- 只读取 selected_chains.json **一次**（包含所有 chain_text）
- 在分类的同时提取方法名，避免二次遍历
- 所有分析结果一次性写入，减少 I/O

## 输入要求

| 文件 | 必须 | 说明 |
|------|------|------|
| `selected_chains.json` | 是 | 推理链列表（chain_id, paper_id, chain_text） |
| `xml/` 目录 | 是 | 仅检查存在性，不读取内容 |
| `md/` 目录 | 是 | 仅批量获取标题（head -5 md/*.md） |

## 输出产物

| 文件 | 格式 | 说明 |
|------|------|------|
| `chain_classification.json` | JSON | 每条链的分类 + 方法列表 + 阶段列表 |
| `workflow_structure.json` | JSON | 决策树结构（阶段 + 方法频次） |
| `step_statistics.json` | JSON | 方法频次统计 |
| `review_plan.json` | JSON | 综述结构规划 |
| `paper_inventory.md` | Markdown | 论文清单表 |
| `paper_mapping.json` | JSON | **新增**：paper_id → 论文元数据映射（标题、作者、期刊、年份、short_name） |
| `workflow_meta.json` | JSON | **新增**：workflow 元数据（用于检索和增量去重） |

## 关键约束

1. **语言**：所有描述字段使用中文
2. **一次遍历**：在分类链条的同时提取方法名和阶段标签
3. **精度**：频次百分比以 A-主线总数为分母，保留一位小数
4. **阈值**：A-主线 < 3 时必须警告用户

## 执行步骤

### Step 1: 环境检查与论文元数据提取

```bash
# 检查目录存在性（不读取内容）
ls xml/ md/ selected_chains.json
```

**提取论文元数据**（从 md 文件前 20 行）：

对每个 `md/{paper_id}.md` 文件：
1. 读取前 20 行
2. 提取：title（通常是第一个 # 标题）、authors、journal、year
3. 生成 short_name（格式：FirstAuthor_Year，如 "Zhang_2023"）
4. 生成 bibitem_key（格式：FirstAuthorYear，如 "Zhang2023"）

**输出 `paper_mapping.json`**：

```json
{
  "812454164008271872": {
    "title": "Microarray profile of differentially expressed genes in a monkey model of allergic asthma",
    "authors": "Zhang X, Wang Y, Li Z",
    "first_author": "Zhang",
    "journal": "Nature Methods",
    "year": "2023",
    "short_name": "Zhang_2023",
    "bibitem_key": "Zhang2023"
  },
  "811909279517769730": {
    "title": "Evidence of genome-wide G4 DNA-mediated gene expression in human cancer cells",
    "authors": "Liu H, Chen M",
    "first_author": "Liu",
    "journal": "Science",
    "year": "2022",
    "short_name": "Liu_2022",
    "bibitem_key": "Liu2022"
  }
}
```

**处理冲突**：如果多篇论文生成相同的 short_name（如同一作者同年发表多篇），在后缀添加字母（Zhang_2023a, Zhang_2023b）。

**输出 `paper_inventory.md`**（论文清单表）：

```markdown
# 论文清单

| Paper ID | Short Name | Title | Authors | Journal | Year |
|----------|------------|-------|---------|---------|------|
| 812454164008271872 | Zhang_2023 | Microarray profile of... | Zhang X, Wang Y, Li Z | Nature Methods | 2023 |
| 811909279517769730 | Liu_2022 | Evidence of genome-wide... | Liu H, Chen M | Science | 2022 |
```

### Step 2: 一次性遍历分类 + 提取（核心优化）

**关键**：在一次遍历中完成所有分析，避免重复读取。

对 `selected_chains.json` 中的每条链：

```python
for chain in selected_chains:
    chain_text = chain["chain_text"]
    
    # 1. 质量评估（四维）
    grade, subtype, reason = classify_chain(chain_text)
    
    # 2. 同时提取方法名和阶段标签
    stages, methods = extract_stages_and_methods(chain_text)
    
    # 3. 记录到分类结果
    classification[chain_id] = {
        "grade": grade,
        "subtype": subtype,
        "reason": reason,
        "stages": stages,           # ← 新增
        "methods_used": methods     # ← 新增
    }
    
    # 4. 同时更新频次统计
    if grade == "A" and subtype == "主线":
        for stage in stages:
            stage_counts[stage] += 1
        for method in methods:
            method_counts[method] += 1
```

**输出**：`chain_classification.json`（增强版，包含 stages 和 methods_used）

### Step 3: 质量评估标准（四维）

| 维度 | 好的链 | 差的链 |
|------|--------|--------|
| **目标完整性** | 从输入到输出的多步骤组合 | 单个公式或技巧 |
| **工具组合性** | 多个工具/算法串联 | 仅一个工具的参数说明 |
| **可迁移性** | 其他数据集/场景可复用 | 高度特化于一个实验 |
| **主流代表性** | 解决该领域的标准问题 | 边缘用途或非典型输入 |

### Step 4: 粒度分类

- **A 类**：完整的多步骤 pipeline
  - **A-主线**：标准输入 + 标准方法
  - **A-旁支**：完整但与主线差异大
- **B 类**：pipeline 中某个阶段的完整操作
- **C 类**：单个工具/公式/技巧

### Step 5: 方法提取规则

从 chain_text 中识别：

**阶段标签**（抽象，跨论文可对齐）：
- 相与晶格表征（Phase & Lattice）
- 成分验证（Composition）
- 氧化态确定（Oxidation State）
- 局部结构探测（Local Structure）
- 占位偏好分析（Site Preference）
- 缺陷机制归属（Defect Mechanism）
- 性能关联（Property Correlation）

**方法名**（具体工具/技术）：
- XRD Rietveld 精修
- XRD 峰位分析
- Raman 光谱
- XPS
- XANES
- SEM/EDXA
- TEM/HRTEM
- 离子半径比较
- 容忍因子计算
- Kröger-Vink 记号
- 电荷平衡分析

### Step 6: 构建决策树结构

基于 Step 2 的统计结果，构建 `workflow_structure.json`：

```json
{
  "stages": [
    {
      "id": 1,
      "name": "相与晶格表征",
      "methods": [
        {"name": "XRD 峰位分析", "count": 9, "percent": 69.2},
        {"name": "XRD Rietveld 精修", "count": 4, "percent": 30.8}
      ],
      "coverage": {"chains": 13, "total": 13, "percent": 100.0}
    }
  ],
  "edges": [
    {"from": 1, "to": 4, "count": 13},
    {"from": 1, "to": 2, "count": 3}
  ],
  "main_path": [1, 4, 5, 6, 7]
}
```

### Step 7: 频次统计

生成 `step_statistics.json`：

```json
{
  "total_a_mainstream": 13,
  "stage_coverage": {
    "相与晶格表征": {"count": 13, "percent": 100.0},
    "占位偏好分析": {"count": 12, "percent": 92.3}
  },
  "critical_stages": ["占位偏好分析", "缺陷机制归属"],
  "sample_size_warning": false
}
```

**频次计算**：
- 分母 = A-主线链总数
- 一条链可使用多种方法，所以同一阶段内方法频次加和可能 > 100%
- 保留一位小数

### Step 8: 子主题检测（链条 > 20 时）

1. 对 A-主线链按"输出类型"分组
2. 判断子主题间关系（上下游/并列/包含）
3. 分裂决策：
   - 最大子主题覆盖 ≥ 70% → 不分裂
   - 否则 → 分裂，询问用户确认

### Step 9: 生成 workflow_meta.json

基于前面的分析结果，生成 workflow 元数据用于检索和增量去重：

```json
{
  "cluster_id": "cluster_6",
  "domain": "bioinformatics",
  "subdomain": "gene_expression_validation",
  
  "workflow_name": "qRT-PCR 验证高通量基因表达数据",
  "workflow_name_en": "qRT-PCR Validation of High-throughput Gene Expression Data",
  
  "problem_description": "如何使用 qRT-PCR 验证微阵列或 RNA-seq 的差异表达基因结果",
  "problem_description_en": "How to validate differentially expressed genes from microarray or RNA-seq using qRT-PCR",
  
  "input_types": ["microarray_data", "RNA-seq_data", "candidate_gene_list"],
  "output_types": ["validation_results", "concordance_rate", "correlation_coefficient"],
  
  "key_methods": [
    {"name": "SYBR Green 检测", "name_en": "SYBR Green detection", "frequency": 0.636},
    {"name": "comparative Ct 法", "name_en": "comparative Ct method", "frequency": 0.455},
    {"name": "单内参归一化", "name_en": "single reference gene normalization", "frequency": 0.636}
  ],
  
  "main_stages": [
    "候选基因选择",
    "RNA 提取与逆转录",
    "qRT-PCR 实验执行",
    "内参归一化",
    "定量方法与统计分析",
    "一致性评估"
  ],
  
  "keywords": [
    "qRT-PCR", "基因表达验证", "微阵列", "RNA-seq",
    "内参基因", "comparative Ct", "一致性评估"
  ],
  "keywords_en": [
    "qRT-PCR", "gene expression validation", "microarray", "RNA-seq",
    "reference gene", "comparative Ct", "concordance assessment"
  ],
  
  "similarity_signature": {
    "method_vector": [0.636, 0.318, 0.455, 0.227],
    "stage_count": 7,
    "stage_sequence_hash": "sha256_hash_of_concatenated_stage_names"
  },
  
  "statistics": {
    "total_papers": 22,
    "a_mainstream_papers": 22,
    "creation_date": "2026-04-28"
  },
  
  "similarity_threshold": 0.85
}
```

**字段说明**：

- **检索字段**：
  - `keywords` / `keywords_en`：关键词匹配
  - `problem_description` / `problem_description_en`：语义搜索（embedding）
  - `input_types` / `output_types`：数据类型匹配
  - `domain` / `subdomain`：领域过滤

- **去重字段**：
  - `similarity_signature.method_vector`：从 step_statistics.json 提取 top-N 方法的频次向量
  - `similarity_signature.stage_sequence_hash`：主路径阶段序列的哈希值
  - `similarity_threshold`：相似度阈值（默认 0.85）

- **生成规则**：
  - `subdomain`：从 workflow_name 推断（如 "qRT-PCR 验证" → "gene_expression_validation"）
  - `input_types` / `output_types`：从 A-主线链的输入输出模式推断
  - `keywords`：从 workflow_structure.json 的高频方法名提取
  - `method_vector`：取频次 top-10 的方法，按频次降序排列
  - `stage_sequence_hash`：将 main_path 对应的阶段名拼接后计算 SHA256

### Step 10: 综述结构规划

生成 `review_plan.json`：

**小 cluster（≤ 20 链）**：
```json
{
  "structure": "single",
  "decision": "单篇综述",
  "sections": ["引言", "阶段1", "阶段2", "...", "结论"],
  "estimated_pages": "18-22"
}
```

**大 cluster（> 20 链）**：
```json
{
  "structure": "multi",
  "decision": "总综述 + 子综述",
  "overview": {
    "sections": ["引言", "通用工作流", "子综述索引", "结论"],
    "pages": "5-8"
  },
  "sub_reviews": [
    {
      "id": "sub1",
      "title": "阶段1-2详解",
      "stages": [1, 2],
      "papers": 8,
      "pages": "15-20"
    }
  ]
}
```

### Step 10: 素材充足性检查

- A-主线 ≥ 3 → 继续
- A-主线 + B ≥ 5 → 继续（B 作案例）
- 否则 → 警告素材不足，询问用户

**输出所有文件**：
1. `chain_classification.json`
2. `workflow_structure.json`
3. `step_statistics.json`
4. `review_plan.json`
5. `paper_inventory.md`
6. `paper_mapping.json`
7. `workflow_meta.json`

## 输出格式

### chain_classification.json（增强版）

```json
{
  "metadata": {
    "cluster_id": "cluster_8",
    "total_chains": 50,
    "unique_papers": 37,
    "classification_date": "2026-04-27"
  },
  "summary": {
    "A_mainstream": 13,
    "A_sidetrack": 21,
    "B_stage": 12,
    "C_single": 4
  },
  "chains": [
    {
      "chain_id": "812491390918328320_0",
      "paper_id": "812491390918328320",
      "grade": "A",
      "subtype": "主线",
      "reason": "完整的掺杂位点确定流程：XRD相分析→Raman光谱占位识别→XPS氧化态分析→离子半径比较→缺陷反应归属→性能关联",
      "stages": [
        "相与晶格表征",
        "局部结构探测",
        "氧化态确定",
        "占位偏好分析",
        "缺陷机制归属",
        "性能关联"
      ],
      "methods_used": [
        "XRD Rietveld精修",
        "Raman光谱",
        "XPS",
        "离子半径比较",
        "Kröger-Vink记号"
      ]
    }
  ]
}
```

## 性能优化总结

| 优化项 | 原方案（01+02分离） | 新方案（合并） | 改善 |
|--------|-------------------|---------------|------|
| selected_chains.json 读取 | 2次 | 1次 | -50% |
| 链条遍历次数 | 2次 | 1次 | -50% |
| 中间文件写入 | 1个 | 4个（一次性） | 更高效 |
| 总耗时（估算） | 100% | 55% | **-45%** |

## 验证清单

- [ ] chain_classification.json 存在且包含 stages 和 methods_used
- [ ] workflow_structure.json 存在且包含 stages 和 edges
- [ ] step_statistics.json 存在且频次正确
- [ ] review_plan.json 存在且包含结构决策
- [ ] paper_inventory.md 存在且包含所有论文
- [ ] **paper_mapping.json 存在且包含所有 paper_id 的元数据**
- [ ] **workflow_meta.json 存在且包含检索和去重字段**
- [ ] 所有描述字段使用中文
- [ ] 频次百分比以 A-主线总数为分母
- [ ] A-主线 ≥ 3（否则已警告用户）
- [ ] **paper_mapping.json 中 short_name 无冲突（或已添加后缀）**
- [ ] **workflow_meta.json 的 method_vector 长度与 key_methods 数量一致**
