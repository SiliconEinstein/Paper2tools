---
name: workflower-v2
description: 从论文聚类提取通用工作流的优化流程协调器（3阶段并行优化版本）
language: zh-CN
---

# Workflower v2: 论文工作流提取系统（优化版）

## 功能概述

从一组聚类后的论文推理链中提取可复用的通用工作流（universal workflow），产出：
1. 学术综述文章（LaTeX，含决策流程图）
2. 3层工作流文档（算法层、实现层、陷阱层）
3. 可视化决策树

**v2 优化重点**：
- **3阶段设计**：将原5阶段压缩为3阶段，减少中间文件和上下文切换
- **并行处理**：阶段2支持多论文并行提取，加速2-3倍
- **一次读取**：消除重复文件读取，减少12%+ I/O开销
- **断点续传**：支持进度保存和恢复

## 性能对比

| 指标 | v1 (5阶段) | v2 (3阶段) | 改善 |
|------|-----------|-----------|------|
| selected_chains.json 读取 | 2次 | 1次 | -50% |
| paper_extractions.yaml 读取 | 2次 | 1次 | -50% |
| workflow_structure.json 读取 | 2次 | 1次 | -50% |
| 13篇论文深度提取 | 39分钟（串行） | 15分钟（并行） | **-62%** |
| 总体耗时（估算） | 100% | 45-55% | **-45~55%** |

## 适用场景

- 用户提供了一组来自多篇论文的推理链（reasoning chains）
- 这些链已被聚类算法归为同一簇
- 目标是总结出解决某类问题的通用方法论
- 不限定学科领域（生物信息学、材料科学、NLP、金融量化等均适用）

## 输入结构预期

```
cluster_N/
├── selected_chains.json    # 被选中的推理链列表（chain_id, paper_id, chain_text）
├── xml/                     # 每篇论文的完整推理链（含所有 conclusions）
│   └── {paper_id}_{chain_idx}.xml
└── md/                      # 论文原文 markdown
    └── {paper_id}.md
```

## 3阶段流程

### 阶段 1: 分析器与规划器 (`01_analyzer.md`)

**合并原 01_chain_classifier + 02_workflow_structure_builder**

**职责**：
- 链条质量分类（A/B/C + 主线/旁支）
- 方法名提取和频次统计
- 决策树结构构建
- 综述结构规划

**输入**：`selected_chains.json`, `xml/`, `md/`

**输出**：
- `chain_classification.json`（增强版，包含 stages 和 methods_used）
- `workflow_structure.json`
- `step_statistics.json`
- `review_plan.json`
- `paper_inventory.md`
- `paper_mapping.json`（**新增**：paper_id → 论文元数据映射）
- `workflow_meta.json`（**新增**：用于检索和增量去重）

**优化点**：
- 一次遍历完成分类 + 方法提取，避免二次读取
- 在分类时同步构建决策树结构
- 减少 selected_chains.json 读取次数：2次 → 1次

### 阶段 2: 深度提取器 (`02_extractor.md`)

**优化原 03_deep_reader**

**职责**：
- 深度阅读 A-主线论文的 XML 和 MD
- 提取算法层和实现层信息
- 并行处理多篇论文

**输入**：`chain_classification.json`, `paper_mapping.json`, `md/`, `xml/`

**输出**：
- `paper_extractions.yaml`
- `.extraction_progress.json`（进度追踪，隐藏文件）

**优化点**：
- **智能批次划分**：
  - ≤3篇：1批
  - 4-8篇：2批
  - 9-15篇：3批
  - >15篇：4批
- **并行执行**：每批启动独立 subagent，并行处理
- **断点续传**：支持从中断处恢复
- **预期加速**：13篇论文从39分钟降至15分钟（2.6倍）

### 阶段 3: 文档与综述生成器 (`03_writer.md`)

**合并原 04_workflow_documenter + 05_review_writer**

**职责**：
- 生成 3 层工作流文档
- 撰写中文 LaTeX 综述
- 生成决策树可视化
- 编译 PDF

**输入**：
- `paper_extractions.yaml`
- `workflow_structure.json`
- `step_statistics.json`
- `chain_classification.json`
- `review_plan.json`
- `paper_mapping.json`（**新增**：论文元数据映射，用于引用替换）
- `md/`（提取论文标题）

**输出**：
- `workflow_3layer.md`
- `review_cluster_N.tex`
- `decision_tree.dot`
- `decision_tree.png`
- `decision_tree.pdf`
- `review_cluster_N.pdf`（如环境支持）

**优化点**：
- 一次性读取所有输入文件，避免重复 I/O
- 消除 paper_extractions.yaml 的重复读取（原方案读2次）
- 消除 workflow_structure.json 的重复读取（原方案读2次）
- 所有输出文件一次性生成

## 执行流程

```
用户输入: cluster_N/
    ↓
[1] 分析器与规划器
    ├─ 链条分类（A/B/C）
    ├─ 方法提取（同步）
    ├─ 决策树构建
    └─ 综述规划 → chain_classification.json, workflow_structure.json, ...
    ↓
[2] 深度提取器（并行）
    ├─ 批次划分（智能）
    ├─ 并行处理（subagents）
    └─ 进度追踪 → paper_extractions.yaml
    ↓
[3] 文档与综述生成器
    ├─ 3层工作流文档
    ├─ LaTeX 综述
    ├─ 决策树可视化
    └─ PDF 编译 → workflow_3layer.md, review.tex, decision_tree.png, ...
```

## 使用方式

### 方式 1：完整流程（推荐）

直接调用本 skill，自动按顺序执行所有 3 个阶段：
```
用户: "提取 cluster_8 的工作流并生成综述"
```

系统会：
1. 检测已完成的阶段（通过检查输出文件是否存在）
2. 从未完成的阶段开始执行
3. 在关键决策点（如子主题分裂）询问用户
4. 每个阶段完成后生成检查点

### 方式 2：单独执行某个阶段

如果只需要重新执行某个阶段，可以直接调用对应的子 skill：
```
用户: "用 03_writer 重新生成综述，使用中文"
```

### 方式 3：断点续传

如果流程中断，重新调用本 skill 会自动检测已完成的阶段，从中断处继续。

阶段 2 支持论文级别的断点续传：
- 检查 `.extraction_progress.json`
- 跳过已完成的论文
- 只处理剩余论文

## 全局约束（所有子 skill 必须遵守）

1. **语言要求**：
   - 所有输出文档（.md, .tex, .yaml 描述字段）必须使用中文
   - 术语首次出现时给英文对照，格式：`中文术语（English Term）`
   - JSON/YAML 的键名保持英文（便于程序处理）

2. **质量标准**：
   - 必须读论文 Methods 部分，不能只依赖 chain_text
   - 必须包含定量结果和具体参数
   - 必须标注论文遗漏的信息（gaps_noted）

3. **格式规范**：
   - LaTeX 使用 xeCJK 配置支持中文
   - **中文字体必须使用 `Droid Sans Fallback`**（系统已确认可用），不要使用 `Noto Sans CJK SC` 等未安装字体
   - 编译前检查字体可用性：`fc-list | grep -i "droid"`
   - 决策树节点使用简单文本标签（避免 HTML TABLE 导致渲染问题）
   - 3 层文档必须包含案例研究和验证清单

4. **检查点机制**：
   - 每个阶段完成后生成对应的输出文件
   - 下一阶段开始前检查依赖文件是否存在
   - 如果依赖文件缺失，提示用户先执行前置阶段

## 执行逻辑（总协调器）

当用户调用本 skill 时，执行以下逻辑：

### Step 1: 环境检查

```python
检查 cluster_N/ 目录结构
确认 selected_chains.json, xml/, md/ 存在
```

### Step 2: 阶段检测

```python
已完成阶段 = []
if exists("chain_classification.json") and exists("workflow_structure.json") and exists("paper_mapping.json") and exists("workflow_meta.json"): 
    已完成阶段.append(1)
if exists("paper_extractions.yaml"): 
    已完成阶段.append(2)
if exists("workflow_3layer.md") and exists("review_cluster_N.tex") and exists("review_cluster_N.pdf") and exists("decision_tree.pdf"): 
    已完成阶段.append(3)

下一阶段 = max(已完成阶段) + 1 if 已完成阶段 else 1
```

### Step 3: 执行阶段

```python
for 阶段 in range(下一阶段, 4):
    if 阶段 == 1:
        执行 01_analyzer.md
        if 需要子主题分裂:
            询问用户确认
    elif 阶段 == 2:
        执行 02_extractor.md（并行处理）
        if 中断后恢复:
            从 .extraction_progress.json 读取进度
    elif 阶段 == 3:
        执行 03_writer.md
        验证输出文件（review.pdf, decision_tree.pdf, paper_extractions.yaml, workflow_structure.json）
        清理中间文件（.extraction_progress.json, /tmp/paper_titles.txt, LaTeX 编译产物）
    
    验证输出文件存在
    生成检查点
```

### Step 4: 增量去重检查（可选）

**在阶段 1 完成后，检查是否已存在高度相似的 workflow**：

```python
if 阶段 == 1 and exists("workflow_meta.json"):
    # 扫描同 domain 下已有的 workflow_meta.json 文件
    similar_workflows = []
    for existing_meta in glob(f"../{domain}/workflows/*/workflow_meta.json"):
        similarity = calculate_similarity(
            current_meta["similarity_signature"],
            existing_meta["similarity_signature"]
        )
        if similarity > existing_meta["similarity_threshold"]:
            similar_workflows.append((existing_meta["cluster_id"], similarity))
    
    if similar_workflows:
        print(f"警告: 检测到 {len(similar_workflows)} 个高度相似的 workflow:")
        for cluster_id, sim in similar_workflows:
            print(f"  - {cluster_id} (相似度: {sim:.2%})")
        
        user_choice = ask_user("是否继续生成？[y/N]")
        if user_choice.lower() != 'y':
            exit("用户取消生成")
```

**相似度计算**：
- `method_vector` 余弦相似度（权重 0.7）
- `stage_sequence_hash` 完全匹配（权重 0.3）
- 综合相似度 = 0.7 × cos_sim + 0.3 × (1 if hash_match else 0)

### Step 5: 完成报告

```python
生成 COMPLETION_REPORT.md，包含：
- 统计信息（论文数、链条数、分类结果）
- 关键发现
- 生成的文件清单（包括 paper_mapping.json 和 workflow_meta.json）
- 输出文件校验结果（4 个必需文件的存在性和大小）
- 中间文件清理记录
- 验证清单
- 性能指标（耗时、加速比）
```

## 错误处理

### 依赖文件缺失

```
错误: workflow_structure.json 不存在
建议: 请先执行阶段 1（分析器与规划器）
命令: 调用 01_analyzer.md
```

### 素材不足

```
警告: A-主线链条 < 3，素材不足以提取通用工作流
建议: 
1. 调整聚类参数，增加链条数量
2. 或将 B 类链条作为阶段内案例补充
```

### 子主题分裂决策

```
检测到 2 个子主题：
1. 子主题 A（覆盖 60% A-主线链）
2. 子主题 B（覆盖 40% A-主线链）

推荐方案: 分裂为 2 个独立 workflow
是否分裂？[Y/n]
```

### 并行处理中断

```
检测到未完成的提取任务：
- 已完成: 8/13 篇论文
- 剩余: 5 篇论文

是否从断点继续？[Y/n]
```

## 验证清单

完成后检查以下项目：

### 文件完整性
- [ ] chain_classification.json 存在且包含 stages 和 methods_used
- [ ] workflow_structure.json 存在且包含决策树结构
- [ ] step_statistics.json 存在且频次正确
- [ ] review_plan.json 存在且包含结构决策
- [ ] **paper_mapping.json 存在且包含所有 paper_id 的元数据**
- [ ] **workflow_meta.json 存在且包含检索和去重字段**
- [ ] paper_extractions.yaml 存在且包含 ≥3 篇论文的提取
- [ ] **paper_extractions.yaml 中每篇论文都有 short_name 和 title 字段**
- [ ] workflow_3layer.md 存在且包含 3 层内容
- [ ] review_cluster_N.tex 存在且可编译
- [ ] **review_cluster_N.tex 中使用 \cite{bibitem_key}，无裸 paper_id**
- [ ] **参考文献完整（count(\bibitem) == count(A-主线论文)）**
- [ ] decision_tree.dot 存在且语法正确
- [ ] decision_tree.png 存在且可查看
- [ ] decision_tree.pdf 存在且无渲染问题
- [ ] **review_cluster_N.pdf 存在且 > 100 字节**
- [ ] **输出文件校验通过（4 个必需文件）**
- [ ] **中间文件已清理（.extraction_progress.json, /tmp/paper_titles.txt, LaTeX 编译产物）**

### 语言规范
- [ ] 所有 .md 和 .tex 文件使用中文撰写
- [ ] 术语首次出现时有英文对照
- [ ] YAML 描述字段使用中文

### 内容质量
- [ ] 3 层文档包含案例研究
- [ ] 综述包含 4 种彩色框（案例/陷阱/工具/参数）
- [ ] 决策树节点显示方法频次
- [ ] 每个方法有具体参数和定量结果
- [ ] 决策树使用简单文本标签（无 HTML TABLE）

### 性能指标
- [ ] 阶段 1 耗时记录
- [ ] 阶段 2 并行加速比记录
- [ ] 阶段 3 耗时记录
- [ ] 总体耗时 vs v1 对比

## 示例

### 输入

```
data/materials_science/workflows/cluster_8/
├── selected_chains.json  (50 chains, 37 papers)
├── xml/  (37 files)
└── md/   (37 files)
```

### 输出

```
cluster_8/
├── chain_classification.json      (1.5K, 增强版)
├── workflow_structure.json        (1KB)
├── step_statistics.json           (2.4K)
├── review_plan.json               (2.2K)
├── paper_inventory.md             (3KB)
├── .extraction_progress.json      (0.5K, 隐藏文件)
├── paper_extractions.yaml         (21K)
├── workflow_3layer.md             (14KB, 中文)
├── decision_tree.dot              (4.9K)
├── decision_tree.png              (160K)
├── decision_tree.pdf              (36K)
├── review_cluster_8.tex           (27KB, 中文)
├── review_cluster_8.pdf           (101KB, 中文)
└── COMPLETION_REPORT.md           (6KB, 中文)
```

### 性能数据（13篇论文案例）

| 阶段 | v1 耗时 | v2 耗时 | 加速比 |
|------|--------|--------|--------|
| 阶段 1 | 5分钟 | 3分钟 | 1.7x |
| 阶段 2 | 39分钟 | 15分钟 | 2.6x |
| 阶段 3 | 8分钟 | 5分钟 | 1.6x |
| **总计** | **52分钟** | **23分钟** | **2.3x** |

## 参考

- 原始 Workflower v1：5阶段设计（保留作为参考）
- 各子 skill 文档：详细的执行步骤和约束
- 性能优化分析：数据流分析和瓶颈识别
