---
name: workflower
description: 从论文聚类提取通用工作流的优化流程协调器
language: zh-CN
---

# Workflower: 论文工作流提取系统

## 功能概述

从一组聚类后的论文推理链中提取可复用的通用工作流（universal workflow），产出：
1. 学术综述文章（LaTeX，含决策流程图）
2. 3层工作流文档（算法层、实现层、陷阱层）
3. 可视化决策树

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
- `paper_mapping.json`
- `workflow_meta.json`

### 阶段 2: 深度提取器 (`02_extractor.md`)

**职责**：
- 深度阅读 A-主线论文的 XML 和 MD
- 提取算法层和实现层信息
- 并行处理多篇论文

**输入**：`chain_classification.json`, `paper_mapping.json`, `md/`, `xml/`

**输出**：
- `paper_extractions.yaml`
- `.extraction_progress.json`（进度追踪，隐藏文件）

### 阶段 3: 文档与综述生成器 (`03_writer.md`)

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


## 全局约束（所有子 skill 必须遵守）

1. **语言要求**：
   - 所有输出文档（.md, .tex, .yaml 描述字段）必须使用中文
   - 术语首次出现时给英文对照，格式：`中文术语（English Term）`
   - JSON/YAML 的键名保持英文（便于程序处理）

2. **质量标准**：
   - 必须读论文 Methods 部分，不能只依赖 chain_text
   - 必须包含定量结果和具体参数
   - 必须标注论文遗漏的信息（gaps_noted）
   - **所有输出内容面向最终用户**：禁止出现"详见原文"、"详见推理链"、"此处省略"、"参见 paper_id"等开发者/内部占位文本。每一段描述必须自包含，读者无需查阅原始数据即可理解
   - **参考文献零省略**：每条 `\bibitem` 必须列出全部作者（不得用 "et al." 缩写）、完整标题（不截断）、期刊名、年份、卷号、页码。信息来源是 MD 文件头部的完整引用元数据，不可凭记忆补全或编造

3. **格式规范**：
   - LaTeX 使用 xeCJK 配置支持中文
   - **中文字体必须使用 TeX Live 自带的 Fandol 系列**：正文 `\setCJKmainfont{FandolSong}`，无衬线 `\setCJKsansfont{FandolHei}`，等宽 `\setCJKmonofont{FandolFang}`（与 `03_writer.md` 一致）。Fandol 对中文标点与弯引号覆盖远优于 `Droid Sans Fallback`。
   - 编译前可检查：`kpathwhich FandolSong-Regular.otf`（应位于 TeX 发行版 `fonts/opentype/public/fandol/`）；若 `fc-list` 已注册，也可用 `fc-list | grep -i fandol`。
   - **无 TeX Live / 找不到 Fandol 时**可暂用 `Droid Sans Fallback` 或系统已安装的 `Noto Sans CJK SC`，并在 `03_writer.md` 中按「字体回退」处理。
   - 决策树节点使用简单文本标签（避免 HTML TABLE 导致渲染问题）
   - 3 层文档必须包含案例研究和验证清单

4. **检查点机制**：
   - 每个阶段完成后生成对应的输出文件
   - 下一阶段开始前检查依赖文件是否存在
   - 如果依赖文件缺失，提示用户先执行前置阶段

## 增量去重检查（可选）

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

## 最终输出文件清单

完成所有阶段后，保留以下文件：

### 必须保留的文件

**人类可读输出**：
- `review_cluster_N.pdf` - 综述 PDF（主要交付物）
- `decision_tree.png` - 决策树可视化

**Agent 可读输出**：
- `workflow_3layer.md` - 3 层工作流文档（算法层、实现层、陷阱层）
- `review_cluster_N.tex` - LaTeX 源文件（含完整引用和结构）
- `decision_tree.dot` - Graphviz 源文件

**元数据**：
- `workflow_meta.json` - 检索和去重字段（method_vector, stage_sequence_hash 等）
- `workflow_structure.json` - 决策树结构（用于下游检索）

**调试/追溯**：
- `paper_extractions.yaml` - 论文提取结果（含 short_name, title, 算法层和实现层信息）

**原始输入**（不删除）：
- `selected_chains.json` - 选中的推理链列表
- `xml/` - 推理链 XML 文件
- `md/` - 论文 Markdown 文件

### 应删除的中间文件

阶段 3 完成后，删除以下文件：
- `chain_classification.json` - 已整合到 paper_extractions.yaml
- `step_statistics.json` - 已整合到 workflow_structure.json
- `review_plan.json` - 已整合到 review.tex
- `paper_inventory.md` - 已整合到 review.tex
- `paper_mapping.json` - 已整合到 review.tex 的 \bibitem
- `.extraction_progress.json` - 进度追踪文件（隐藏文件）
- `review_cluster_N.aux`, `review_cluster_N.log`, `review_cluster_N.out` - LaTeX 编译产物
- `decision_tree.pdf` - 与 decision_tree.png 重复（保留 PNG 即可）

## 验证清单

完成后检查以下项目：

### 文件完整性
- [ ] workflow_structure.json 存在且包含决策树结构
- [ ] **workflow_meta.json 存在且包含检索和去重字段**
- [ ] paper_extractions.yaml 存在且包含 ≥3 篇论文的提取
- [ ] **paper_extractions.yaml 中每篇论文都有 short_name 和 title 字段**
- [ ] workflow_3layer.md 存在且包含 3 层内容
- [ ] review_cluster_N.tex 存在且可编译
- [ ] **review_cluster_N.tex 中使用 \cite{bibitem_key}，无裸 paper_id**
- [ ] **参考文献完整（count(\bibitem) == count(A-主线论文)）**
- [ ] decision_tree.dot 存在且语法正确
- [ ] decision_tree.png 存在且可查看
- [ ] **review_cluster_N.pdf 存在且 > 100 字节**
- [ ] **中间文件已清理（见上方"应删除的中间文件"清单）**

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