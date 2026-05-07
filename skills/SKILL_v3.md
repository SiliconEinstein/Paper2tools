---
name: workflow-extraction
description: >-
  从聚类后的多篇论文推理链中提取可复用的 universal workflow，生成综述文章（含决策流程图）和 agent skill set。
  当用户提供一组来自不同论文的推理链/结论聚类结果，希望总结出解决某类问题的通用方法论时使用。
  触发词：提取 workflow、总结方法论、从论文中提取通用流程、写综述、写 skill set、
  extract workflow from papers、summarize methodology across papers。
---

# Workflow Extraction: 从论文聚类到可复用方法论

## 适用场景

用户提供了一组来自多篇论文的推理链（reasoning chains），这些链已被聚类算法归为同一簇，
代表着"解决同一类问题的不同方法实例"。目标是从中提取一个 universal workflow，
产出两个制品：(1) 学术综述文章；(2) 面向 agent 的 skill set。

本 skill **不限定学科领域**——生物信息学、材料科学、NLP、金融量化等任何需要
从多篇论文中归纳通用方法论的场景均适用。

## 输入结构预期

```
cluster_N/
├── selected_chains.json    # 被选中的推理链列表（chain_id, paper_id, chain_text）
├── workflow.json            # 可选：已有的初步 workflow 总结
├── xml/                     # 每篇论文的完整推理链（含所有 conclusions）
│   └── {paper_id}_{chain_idx}.xml
└── md/                      # 论文原文 markdown
    └── {paper_id}.md
```

**关键认知**：chain_text 来自论文的 conclusions/reasoning 部分，捕获的是逻辑推导和公式，
但**实现细节通常只在 Methods 中**。chain_text 是入口点，Methods 是必读的补充。

---

## Phase 1: 结构探查

1. 列目录，确认 xml/、md/、selected_chains.json 存在
2. 读 selected_chains.json，获取链列表
3. 读 workflow.json（若存在）
4. 扫描论文标题：`head -5 md/*.md`

**产出**：论文清单表（paper_id → 标题 → 被选中的 chain 编号）

## Phase 2: 链条质量评估

逐条阅读 chain_text，做**四维评估**：

| 维度 | 好的链 | 差的链 |
|------|--------|--------|
| **目标完整性** | 从输入到输出的多步骤组合 | 单个公式或技巧 |
| **工具组合性** | 多个工具/算法串联 | 仅一个工具的参数说明 |
| **可迁移性** | 其他数据集/场景可复用 | 高度特化于一个实验 |
| **主流代表性** | 解决该领域的标准问题 | 边缘用途或非典型输入 |

**粒度分类**：
- **A 类**：完整的多步骤 pipeline
- **B 类**：pipeline 中某个阶段的完整操作
- **C 类**：单个工具/公式/技巧

**主流性分类**（仅对 A 类）：
- **A-主线**：标准输入 + 标准方法，可作为 workflow 骨干
- **A-旁支**：完整 pipeline 但输入/目标/方法与主线差异较大，应作为"变体"单独讨论

> **判断"旁支"的信号**：该方法解决的子问题与大多数 A 类链不同；输入类型非主流；
> 算法过于特化。旁支不代表质量差——只是不适合作为主线代表。

**决策点**：A-主线 ≥ 3 → 继续；A-主线 + B ≥ 5 → 继续（B 作阶段内案例）；否则警告素材不足。

## Phase 2.5: 子主题检测与分裂决策（链条 > 20 时必做）

1. **对 A-主线链按"输出类型"分组**——不同领域的输出类型不同，但通用分类维度包括：
   - 输出是**排序列表**（ranking）
   - 输出是**子结构/模块集合**（clustering / segmentation）
   - 输出是**模型/网络/图本身**（representation）
   - 输出是**预测值**（prediction）
   - 输出是**富集/显著性列表**（enrichment / hypothesis testing）

2. **判断子主题间关系**：
   - 上下游（A 的输出是 B 的输入）→ 可合并为一个 workflow 的不同阶段
   - 并列（目标和算法范式不同）→ 分裂为独立 workflow
   - 包含（一个是另一个的特例）→ 合并

3. **决策**：最大子主题覆盖 ≥ 70% A-主线链 → 不分裂；否则分裂

4. **向用户报告子主题列表和推荐方案，等待确认**

分裂后每个子 workflow 独立执行 Phase 2.8-7。A-旁支链单独列为"变体方法"。

## Phase 2.6: 综述结构规划——渐进式披露文件树

当 A+B 类链超过 **20 条**时，不应将所有内容塞进一篇综述。
需要先规划文件树结构，再分片并行写作。

### 规划原则

- **每篇子综述覆盖 ≤ 20 篇论文**（保证每篇论文有足够篇幅展开细节）
- **总综述是"地图"**：只给 transition graph、主干路径、各阶段一句话概括、
  子综述的索引和关系图。不展开公式和案例。5-8 页。
- **子综述是"放大镜"**：深入一个或相邻的几个阶段，包含公式、参数、
  四种彩色框、完整案例。15-20 页。

### 分片策略

根据 transition graph 的结构来切分：

1. **按高频节点切分**：每个高频节点（>30% 链覆盖）可以独立成一篇子综述
2. **合并相邻低频节点**：覆盖率 <30% 的相邻节点合并到一篇
3. **旁支单独一篇**：所有 A-旁支链合并为一篇"方法变体与扩展"
4. **上游共享节点**（如"定义 Hamiltonian"）放入总综述，不重复写

### 产出：文件树规划文档

```yaml
# review_plan.yaml
title: "总主题名"
total_chains: 50
total_papers: 47

overview:
  file: overview.tex
  pages: 5-8
  content: transition graph + 主干路径 + 子综述索引
  
sub_reviews:
  - id: A
    title: "子主题 A"
    file: sub_review_A.tex
    stages: ["阶段X", "阶段Y"]     # 从 transition graph 中切出
    chains: ["chain_1", "chain_2", ...]  # 属于这些阶段的链
    papers: 15                       # ≤ 20
    pages: 15-20
    
  - id: B
    title: "子主题 B"
    file: sub_review_B.tex
    stages: ["阶段Z"]
    chains: [...]
    papers: 12
    pages: 15-20
    
  - id: C
    title: "旁支方法与扩展"
    file: sub_review_C.tex
    stages: ["旁支1", "旁支2"]
    chains: [...]  # A-sidetrack chains
    papers: 14
    pages: 10-15
```

### 执行策略

1. 生成 `review_plan.yaml`，向用户展示并确认
2. 总综述和各子综述分别启动独立 subagent 并行写作
3. 每个 subagent 只读自己分片内的论文 XML/MD（控制上下文）
4. 总综述最后写，汇总各子综述的关键结论
5. 交叉引用：子综述之间用"详见子综述 X 的 §Y"互相引用

> **对小 cluster（≤20 条链）**：跳过此 phase，直接写单篇综述。
> **对大 cluster（>20 条链）**：此 phase 必做。

## Phase 2.8: Decision Tree + 频次统计——数据驱动的写作总纲

在分类完成后、深度阅读之前，从 chain_text 中提取步骤序列，统计频次，
生成一张 **decision tree**（不是简单的 transition graph）。

**Decision tree 的核心区别**：不仅画出"步骤 A → 步骤 B"的流向，
更重要的是在每个阶段节点上展示**该阶段可选的工具/方法及其使用频次**，
形成一张"在这个阶段，你可以选什么，多少人选了什么"的决策地图。

### Step 1: 提取步骤标签 + 工具/方法

对每条 A/B 类链的 chain_text，提取：
- **抽象阶段标签**（跨论文可对齐）
- **该步骤使用的具体工具/方法名**（这是 decision tree 的关键数据）

```
chain_id: [("阶段A", ["方法1"]), ("阶段B", ["方法2", "方法3"]), ...]
```

### Step 2: 统计三类频次

```python
node_counts = Counter()    # 每个阶段被多少条链覆盖
edge_counts = Counter()    # 阶段间转换频次
tool_counts = {}           # 每个阶段上各方法的使用论文数
```

### Step 3: Graphviz 渲染为 Decision Tree

每个阶段节点的标签格式：
```
┌─────────────────────────┐
│  阶段名 (N/M chains)     │
│─────────────────────────│
│  方法A ████████ 12篇     │
│  方法B █████    8篇      │
│  方法C ██       3篇      │
└─────────────────────────┘
```

graphviz 中用 HTML label + `<TABLE>` 实现内嵌条形图。
**详细实现（含完整代码、颜色规范、布局调优、常见问题）见子 skill**：
[decision-tree.md](decision-tree.md)

### Step 4: 从 Decision Tree 读出写作总纲

| 图上特征 | 写作决策 |
|----------|---------|
| 主干路径 | 综述的章节顺序 |
| 节点上的方法频次排名 | 每个阶段优先介绍哪个方法 |
| 频次最高的方法 | 作为"标准做法"详细展开 |
| 频次低但独特的方法 | 作为"变体"在框中简要对比 |
| 分叉点 | 章节内的决策讨论："何时选 A，何时选 B" |

### 产出
- `decision_tree.pdf` / `.png` — 嵌入综述引言
- `step_statistics.json` — 全部频次数据

## Phase 3: 深度阅读——双层提取

对每篇 A-主线论文做两层提取。

### 3a. 算法层（从 XML 提取）

读取完整 XML（该论文所有 conclusions，不仅被选中的那条），提取：
- 核心算法/公式，**所有符号必须有定义**
- 方法的具体机制——**精确到子步骤，不能停留在一句话概括**
- 与其他方法的数学关系（等价性、特例关系）

> **精确性要求**：如果 chain_text 概括为"将信号映射到结构"，但论文实际使用了
> 具体的映射规则（如特定的 scoring function、转换公式、子步骤名称），
> 必须在 XML 或 Methods 中确认并补充。一句话概括 ≠ 精确描述。

### 3b. 实现层（从 MD Methods 提取）——**必做，不可跳过**

在 md/{paper_id}.md 中搜索 Methods / Materials / Implementation / Experimental Setup
部分，系统提取以下**实现细节**。这些维度是跨学科通用的：

| 维度 | 要提取的信息 |
|------|-------------|
| **输入预处理与 QC** | 缺失值处理、异常值过滤、归一化、数据清洗 |
| **标识符协调** | 不同数据源之间的 ID/名称/编码映射规则 |
| **外部资源规格** | 使用的数据库/知识库的名称、版本、子集选择、过滤条件 |
| **领域特定偏差控制** | 针对该领域已知偏差的处理（如采样偏差、标注偏差、覆盖度偏差） |
| **统计校准** | null 模型类型、多重检验校正方法、重采样次数 |
| **内部验证** | 交叉验证、held-out、ablation |
| **外部验证** | 独立数据集、跨机构/跨时间泛化 |
| **计算环境** | 硬件、运行时间、并行策略 |

如果论文 Methods 中**未提及**某个维度，记录为"未提及"——这本身是一个发现，
可写入陷阱框（"该方法未报告 X，使用时建议自行补充"）。

> **领域特异性说明**：上表中的"标识符协调"和"领域特定偏差控制"需要根据具体领域展开。
> 例如在基因组学中是 gene ID 映射和 text-mining/degree 偏差；在 NLP 中是
> tokenizer 一致性和 label 分布偏差；在材料科学中是晶体结构格式转换和 DFT 基组偏差。
> **由 agent 根据论文领域自行判断具体展开内容**。

### 产出格式（每篇论文一条 YAML）

```yaml
paper_id: "xxx"
title: "..."
algorithm_layer:
  core_formula: "公式及符号定义"
  mechanism_detail: "精确到子步骤的机制描述"
  method_family: "所属方法族"
implementation_layer:
  input_qc: "..."
  id_mapping: "..."
  external_resource_spec: "名称 + 版本 + 过滤条件"
  domain_bias_control: "..."
  null_model: "..."
  multiple_testing: "..."
  internal_validation: "..."
  external_validation: "..."
  compute_env: "..."
quantitative_results:
  - "具体数值结果"
tools: ["tool1", "tool2"]
gaps_noted: ["未提及的维度列表"]
```

## Phase 4: 提取 Workflow 阶段——三层结构

### 4a. 基础设施层

算法之前和之间的必要步骤，论文 chain_text 常忽略但实操不可跳过：

| 通用阶段 | 内容 |
|----------|------|
| **Stage 0: 输入预处理与标识符协调** | 数据清洗、格式统一、跨源 ID 映射 |
| **Stage 0.5: 外部资源选择与偏差审计** | 选择使用哪个版本的外部资源；检测已知偏差 |

### 4b. 算法层

从 A-主线链归纳核心计算阶段。每个阶段需确定：
- 阶段名称（动词短语）
- 核心算法/公式
- 哪些论文的哪条链覆盖了该阶段

### 4c. 校准与验证层

| 通用阶段 | 内容 |
|----------|------|
| **Stage N-1: 统计校准** | null 模型、多重检验校正、重采样/bootstrap |
| **Stage N: 验证** | 内部（CV/held-out/ablation）+ 外部（独立数据集） |

### 检查清单
- [ ] 每个阶段至少有 2 篇不同论文的证据支持
- [ ] 基础设施层有明确的操作步骤（不是空壳）
- [ ] 阶段间的输入输出接口清晰
- [ ] 校准与验证是必要阶段，不是可选附录

## Phase 4.5: 可执行性审查

> "一个有基本领域背景但不熟悉这个子方向的研究者，能否仅凭我们的描述，
> 在合理时间内从原始数据跑通整个 pipeline？"

逐阶段检查：

| 检查项 | 不合格表现 | 修复方式 |
|--------|----------|---------|
| 输入格式 | 只说"数据矩阵"不说格式/维度 | 补充具体格式说明 |
| 标识符体系 | 只说"IDs"不说哪种 | 补充具体 ID 体系和映射工具 |
| 外部资源获取 | 只说名字不说在哪下载 | 补充下载链接 + 版本 + 过滤阈值 |
| 参数默认值 | 只给范围不给推荐值 | 补充推荐默认值 |
| 工具安装 | 只给名字 | 补充安装命令或 URL |
| 中间产物 | 阶段间传什么不清楚 | 补充中间产物的格式和字段 |

**不合格项直接修复**，不留 TODO。

## Phase 5: 撰写综述

### LaTeX 中文配置（必须）

如果综述使用中文撰写，preamble 必须包含：

```latex
\documentclass{article}
\usepackage{fontspec}
\usepackage{xeCJK}
\setCJKmainfont{Droid Sans Fallback}  % 或 Noto Sans CJK SC
\usepackage{amsmath, amssymb}
\usepackage{graphicx}
\usepackage{xcolor}
\usepackage{tcolorbox}
\usepackage{hyperref}
```

编译命令：`xelatex` 两遍（不是 pdflatex）

### 参考文献格式

正文中使用 `\cite{key}` 或上标引用。文末参考文献格式：

```
[1] 作者1, 作者2, 作者3. 标题. 期刊名, 年份, 卷(期): 页码.
[2] Author A, Author B. Title. Journal Name, 2023, 123(4): 567-890.
```

从论文 markdown 文件开头提取完整的标题、作者、期刊信息。所有 A-主线链的来源论文都必须被引用。

### 小 cluster（≤20 链）：单篇综述

```latex
\section{引言}  % transition graph + 论文表
\section{Stage 0..N+2}  % 每阶段末尾四种彩色框
\section{结论}
```

### 大 cluster（>20 链）：总综述 + 子综述

按 Phase 2.6 的 `review_plan.yaml` 执行。

**总综述（overview.tex）**：
```latex
\section{引言与问题界定}
\section{通用工作流}  % transition graph 为核心，每阶段 1-2 段概述
\section{子综述索引}  % 表格：子综述 ID / 标题 / 覆盖阶段 / 论文数
\section{跨阶段的共性发现}  % 从各子综述中提炼的 3-5 条 cross-cutting insights
\section{结论与展望}
```
不含四种彩色框（那些在子综述中）。5-8 页。

**子综述（sub_review_X.tex）**：
```latex
\section{引言}  % 本子综述覆盖的阶段、在总 workflow 中的位置
\section{Stage A}  % 详细公式+四种彩色框
\section{Stage B}  % 详细公式+四种彩色框
\section{小结}
```
每篇独立可读。15-20 页。

**并行写作**：每篇子综述一个 subagent，只给它该分片的论文列表和 decision tree。
总综述在所有子综述完成后最后写，汇总各子综述的关键发现。

## Phase 5.5: 引文核查（写作完成后必做）

每篇综述完成后，必须检查引文的完整性和准确性：

1. **覆盖检查**：综述中提到的每个具体方法、参数值、实验结果都应有引文支撑。
   扫描正文中所有"X 等人发现..."、"文献中报道..."、"典型值为..."类表述，
   确认每处都有 `\cite{}`。
2. **一致性检查**：bibliography 中的条目与正文引用一一对应，无孤立条目，
   无缺失引用。
3. **交叉引用**：子综述之间、子综述与总综述之间的"详见子综述 X"引用是否正确。

可用 `grep` 提取正文 `\cite{}` keys 与 bib 中 `@type{key,` 做 diff，找出缺失/孤立条目。

## Phase 5.6: 预测-验证对比审查（所有综述必做）

任何提出模型、方法或理论的综述，都必须检查**预测与独立验证之间的闭环**。
这不限于"理论 vs 实验"——实验方法的综述同样需要验证
（如不同测量手段的交叉校验、不同数据集上的泛化检验）。

1. **每个核心方法/模型，是否有至少一个独立验证案例？**
   "独立验证"的含义因领域而异：
   - 理论/计算：与实验观测或更高精度计算对比
   - 实验方法：与其他独立测量技术交叉校验
   - 数据分析：在 held-out 数据集或独立队列上的泛化
   - 工程方法：在不同条件/材料/场景下的鲁棒性检验
   
   如果论文未做独立验证，在 casebox 中标注"尚无独立验证"，
   在 pitfallbox 中讨论可行的验证策略。

2. **定量偏差必须用具体数字**——不能只说"符合较好"或"性能提升"：
   - 给出预测值、验证值、偏差百分比或比值
   - 给出适用范围（在什么条件下偏差 <10%，什么条件下失效）

3. **如果整个 cluster 的验证覆盖率很低**（如大多数论文在"方法提出"阶段停止，
   没有走到"验证"阶段），这本身就是一个重要发现——transition graph / decision tree 
   的漏斗结构会暴露这个 gap，应在总综述中明确讨论。

## Phase 5.7: 总综述的结论 Clustering（大 cluster 必做）

总综述不应只是子综述结论的罗列，而应对所有子综述的结论做一次**二阶分析**：

### 1. 结论分组
收集所有子综述的关键结论（每篇 3-5 条），按主题分组：
- 方法论共识（多篇子综述都同意的结论）
- 定量一致性（不同方法给出相近的数值）
- **矛盾结论**（不同子综述或不同论文之间的冲突）

### 2. 矛盾分析
对每对矛盾结论，分析可能的原因：
- 模型假设不同（如绝热 vs 非绝热）
- 参数选择不同（如 μ*=0.1 vs μ*=0.15）
- 材料体系不同（普适结论 vs 材料特异性结论）
- 近似层次不同（Migdal vs 含顶点修正）

### 3. 开放问题提炼
从矛盾和 gap 中提炼出未来研究问题：
- "X 和 Y 的矛盾暗示需要 Z 方向的进一步研究"
- "pipeline funnel 中 88%→12% 的断层是一个系统性的基础设施缺口"
- "μ* 的拟合参数地位亟待改变——需要从微观推导"

### 产出格式
在总综述的"跨子综述的共性发现"部分，使用以下结构：
```latex
\subsection{方法论共识}
\subsection{定量一致性}
\subsection{矛盾结论与原因分析}
\subsection{开放问题与未来方向}
```

### 写作原则

1. **方法机制精确到子步骤**：chain_text 的一句话概括不够，必须展开
2. **每个公式定义所有符号**
3. **四种彩色框嵌入每个阶段末尾**，不设独立汇总章节
4. **案例框包含实现细节**：不仅是规模数字，还有 QC、ID 映射、资源版本
5. **陷阱框覆盖两类**：
   - (a) 方法本身的已知缺陷
   - (b) 论文未报告的实现细节遗漏（"该方法未报告 X，建议使用时补充 Y"）
6. **A-旁支方法**单独一段标注"变体"，不混入主线
7. **用中文写作时**：术语首次出现给英文，如"度保持随机化（degree-preserving shuffle）"

### LaTeX 彩色框定义

```latex
\newtcolorbox{toolbox}[1][]{
  colback=green!3, colframe=green!40!black, breakable,
  fonttitle=\bfseries\sffamily, title={推荐工具}, #1}
\newtcolorbox{parambox}[1][]{
  colback=blue!3, colframe=blue!40!black, breakable,
  fonttitle=\bfseries\sffamily, title={关键参数}, #1}
\newtcolorbox{casebox}[1][]{
  colback=orange!4, colframe=orange!50!black, breakable,
  fonttitle=\bfseries\sffamily, title={应用案例}, #1}
\newtcolorbox{pitfallbox}[1][]{
  colback=red!3, colframe=red!50!black, breakable,
  fonttitle=\bfseries\sffamily, title={常见陷阱与解决方案}, #1}
```

## Phase 6: 生成流程图（两张）

### 图 1: Transition Graph（数据驱动，Phase 2.8 生成）

已在 Phase 2.8 中用 graphviz 从频次统计生成。这是**定量的**——节点大小和边粗细
反映真实的链覆盖率。嵌入综述引言，作为"通用范式"的可视化支撑。

### 图 2: Decision Flowchart（手动，基于 Phase 4 的阶段分解）

在 transition graph 确定了主干路径后，用 matplotlib 或 graphviz 画一张
**面向实操者的决策流程图**，补充 transition graph 没有的信息：

- 决策菱形（"你有几类证据？""网络是有向还是无向？"）
- 陷阱警告框
- 推荐参数默认值

设计规范：
- 横版，字体 >=11pt
- 输出 PDF + PNG

### 颜色约定

| 用途 | 背景色 | 边框色 | 形状 |
|------|--------|--------|------|
| 输入节点 | `#D6EAF8` | `#2C3E50` | rounded box |
| 决策菱形 | `#FEF5E7` | `#D35400` | diamond |
| 操作步骤 | `#EBF5FB` | `#2471A3` | rounded box |
| 主流选择（高亮） | `#D5F5E3` | `#1E8449` | rounded box |
| 陷阱警告 | `#FDEDEC` | `#C0392B` | rounded box |
| 输出节点 | `#F4ECF7` | `#6C3483` | rounded box |

### 字符编码注意事项

即使 Graphviz 支持 UTF-8，也**不要在节点文字中使用特殊 Unicode 字符**，因为有些字体
（如 PingFang HK）缺失某些字形：
- ⚠ → `[!]`
- ⁻¹ → `^(-1)`
- ≥ → `>=`
- → → `->` 或中文"到"
- α, β → `alpha`, `beta`（若论文要用希腊字母，放在 label 的纯 ASCII 部分）

### 使用率标注原则

**统一使用"使用率"（usage rate）概念**，分母 = 该 workflow 的 A-主线链数。
不要混用"互斥分支概率"和"使用率"两种标注体系——会让读者困惑。

**定义**：某个分支的使用率 = 采用该分支的 A-主线链数 / A-主线链总数。

**关键性质**：
- 一项研究可同时采用多种方法（如同时做 bootstrap + 度保持随机化做校准）
- 因此**同一 Phase 内各分支加和可能超过 100%**
- 保留一位小数（如 58.3%），避免假精确

**边粗细与使用率成正比**（penwidth 1.0–4.5）：
```dot
edge1 [label="★ 主流 ★\n58.3%", penwidth=4.5, color="#1E8449"];
edge2 [label="常用\n33.3%", penwidth=3.0];
edge3 [label="小众\n8.3%", penwidth=1.0];
```

### 诚实性原则（非常重要）

1. **"主流 = 多数"而非"推荐"**：高亮某分支为 ★ 主流 ★ 仅因为它在 A-主线链中出现最多，
   不代表它对所有场景都最优。一定要在文中说明。

2. **小众分支如实显示**：即使某方法只有 1 条链（8.3%），它若真的属于这个 workflow，
   就应当显示。例如量子游走（Saarinen et al. 2023）虽小众但确实是正式发表的网络传播方法，
   不能因"看起来突兀"就删除。

3. **验证每个分支对应的真实论文**：用户可能质疑某个方法的真实性，要能立即查到
   对应的 XML 链和 md 原文。建议在 Phase 3 的笔记中为每个分支标注来源 chain_id。

4. **小样本警告**：若 A-主线链 < 10 条，在 caption 中明确 "$N=X$，结果仅作为领域主流
   倾向的参考"。不要假装有普适统计意义。

## Phase 7: 编译与交付

```bash
xelatex -interaction=nonstopmode review.tex  # pass 1
xelatex -interaction=nonstopmode review.tex  # pass 2
open review.pdf
```

交付物：

小 cluster（≤20 链）：
- review.tex, review.pdf
- transition_graph.pdf, step_statistics.json
- decision_flowchart.pdf（可选）

大 cluster（>20 链）：
- review_plan.yaml（文件树规划）
- overview.tex, overview.pdf（总综述 5-8 页）
- sub_review_A.tex, sub_review_A.pdf（子综述 15-20 页）
- sub_review_B.tex, sub_review_B.pdf
- ...
- transition_graph.pdf, step_statistics.json
- 生成脚本（可复现）

---

## 常见问题

### Q: chain_text 不够精确？ → Phase 3b 读 Methods 补充，以 Methods 为准。
### Q: A 类但不适合主线？ → 标 A-旁支，单独段落讨论。
### Q: Methods 缺实现细节？ → 记"未提及"，写入 pitfallbox。
### Q: C 类链？ → 降级为阶段内技巧示例。
### Q: >20 链怎么高效处理？ → Phase 2.6 分片 + subagent 并行。
### Q: 共享上游阶段？ → 放入总综述或只写一次，分叉箭头表示。

---

## 质量检查清单

### 内容完整性
- [ ] 每个阶段有 >=1 个公式
- [ ] 每个阶段末尾有四种彩色框
- [ ] 案例框含实现细节（QC、ID 映射、资源版本）
- [ ] 陷阱框覆盖：方法缺陷 + 论文遗漏
- [ ] 公式符号首次出现时有定义

### 方法精确性
- [ ] 机制描述精确到子步骤
- [ ] A-旁支方法单独标注
- [ ] 基础设施阶段（QC、ID 映射、资源审计）不遗漏
- [ ] 统计校准和验证是必要阶段

### Decision Tree（Phase 2.8）
- [ ] 每个阶段节点展示了可选方法及其使用论文数
- [ ] 频次最高的方法被标注为"标准做法"

### 引文（Phase 5.5）
- [ ] 每个具体方法/参数/结果都有 \cite
- [ ] 无孤立 bib 条目，无缺失引用
- [ ] 子综述间交叉引用正确

### 预测-验证闭环（Phase 5.6）
- [ ] 每个核心方法/模型有至少一个独立验证案例（或标注"尚无"）
- [ ] 定量偏差用具体数字（预测值、验证值、偏差%）
- [ ] 验证覆盖率低的系统性 gap 被讨论

### 总综述结论 Clustering（Phase 5.7）
- [ ] 结论按共识/一致性/矛盾分组
- [ ] 每对矛盾结论有原因分析
- [ ] 从矛盾和 gap 中提炼了开放问题

### 可执行性
- [ ] 输入格式明确
- [ ] 工具有安装方式或 URL
- [ ] 关键参数有默认推荐值
- [ ] 阶段间中间产物格式明确

### 学术规范
- [ ] 引言含问题界定、范式、论文表
- [ ] 表格有标题、编号、交叉引用
- [ ] 参考文献格式一致
- [ ] 流程图被 \ref 引用

### LaTeX
- [ ] xelatex 两遍无 error
- [ ] 中文字体正确
- [ ] PDF 已 open 给用户
