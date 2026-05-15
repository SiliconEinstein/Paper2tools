---
name: workflower-writer
description: 整合为3层工作流文档，撰写中文LaTeX综述，生成决策树可视化，编译PDF（合并原04+05）
language: zh-CN
---

# 03 文档与综述生成器

## 功能概述

一次性完成：
1. 生成 3 层工作流文档（workflow_3layer.md）
2. 撰写中文 LaTeX 综述（review.tex）
3. 生成决策树可视化（decision_tree.dot/png）
4. 编译 PDF（如环境支持）
5. 清理中间文件

## 输入要求

| 文件 | 必须 | 说明 |
|------|------|------|
| `paper_extractions.yaml` | 是 | 阶段 2 的输出 |
| `workflow_structure.json` | 是 | 阶段 1 的输出 |
| `step_statistics.json` | 是 | 阶段 1 的输出 |
| `chain_classification.json` | 是 | 阶段 1 的输出 |
| `review_plan.json` | 是 | 阶段 1 的输出 |
| `paper_mapping.json` | 是 | **新增**：论文元数据映射（用于替换 paper_id 引用） |
| `md/` 目录 | 是 | 用于提取论文标题和作者信息 |

## 输出产物

| 文件 | 格式 | 说明 |
|------|------|------|
| `workflow_3layer.md` | Markdown | 3 层工作流文档（中文） |
| `review_cluster_N.tex` | LaTeX | 综述文章（中文） |
| `decision_tree.dot` | Graphviz | 决策树源码 |
| `decision_tree.png` | PNG | 决策树可视化 |
| `decision_tree.pdf` | PDF | 决策树 PDF 版 |
| `review_cluster_N.pdf` | PDF | 编译后的综述（如环境支持） |

## 关键约束

1. **语言**：所有文档使用中文；术语首次出现时给英文对照
2. **一次读取**：paper_extractions.yaml 和 workflow_structure.json 只读一次
3. **LaTeX 配置**：必须使用 xeCJK 支持中文
4. **四种彩色框**：综述中每个阶段末尾必须包含适用的彩色框
5. **可执行性**：3 层文档必须通过可执行性审查
6. **决策树格式**：使用简单文本标签（避免 HTML TABLE 导致的渲染问题）

## 执行步骤

### Step 1: 一次性读取所有输入文件

读取所有必需的输入文件，避免重复 I/O。

### Step 2: 生成 3 层工作流文档

#### Layer 1: 算法层（做什么）

从 workflow_structure.json 的阶段定义出发，为每个阶段撰写：

| 内容 | 说明 |
|------|------|
| **目标** | 该阶段要达到什么 |
| **步骤** | 具体操作序列（编号列表） |
| **核心公式** | 从 paper_extractions 的 algorithm_layer 中提取，符号必须有定义 |
| **输出** | 该阶段产出什么 |

包含三个通用基础设施阶段：
- Stage 0: 输入预处理与标识符协调
- Stage 0.5: 外部资源选择与偏差审计
- Stage N: 统计校准与验证

#### Layer 2: 实现层（怎么做）

从 paper_extractions 的 implementation_layer 中提取：

| 内容 | 说明 |
|------|------|
| **仪器/软件参数** | 具体设置值 |
| **数据处理协议** | 数据格式、预处理步骤 |
| **参数默认值** | 推荐值和适用范围 |
| **参考数据库** | 名称、版本、获取方式 |

#### Layer 3: 陷阱与最佳实践

从 paper_extractions 的 gaps_noted 和跨论文比较中提取：

**(a) 方法本身的已知缺陷**：
- 从文献中已知的方法局限
- 适用范围限制

**(b) 论文未报告的实现细节遗漏**：
- 从 gaps_noted 中"未提及"条目汇总
- 格式："该方法未报告 X，建议使用时补充 Y"

每个陷阱包含：
- **问题描述**
- **证据**（哪些论文/数据支持）
- **解决方案**

#### 案例研究

从 paper_extractions 中选择 1-3 个最具代表性的案例，展开完整的证据链。

#### 可执行性审查

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

#### 验证清单和决策树

文档末尾添加：
- 可打勾的验证清单（每个阶段一组检查项）
- 文本格式的决策树（便于快速参考）
- 工作流置信度分级（高/中/低）

### Step 3: 生成 LaTeX 综述

#### Preamble 配置

**字体选择策略**：

1. **首选 Fandol**（TeX Live 自带，中文标点与弯引号字形齐全）：
   ```latex
   \usepackage{fontspec}  % 必须在 xeCJK 之前
   \usepackage{xeCJK}
   \setCJKmainfont{FandolSong}
   \setCJKsansfont{FandolHei}
   \setCJKmonofont{FandolFang}
   ```
   验证方法：检查 `/usr/share/texlive/texmf-dist/fonts/opentype/public/fandol/FandolSong-Regular.otf` 是否存在
   
   **重要**：Fandol 是 TeX Live 字体，XeLaTeX 可以直接使用，**不需要** `fc-list` 能看到。只要文件存在就可用。

2. **备选 Droid Sans Fallback**（仅当 Fandol 文件不存在时）：
   ```latex
   \setCJKmainfont{Droid Sans Fallback}
   \setCJKsansfont{Droid Sans Fallback}
   \setCJKmonofont{Droid Sans Fallback}
   ```

**实际使用**：在生成 .tex 文件前，检查 Fandol 文件是否存在（不要用 fc-list）。如果存在就用 Fandol，否则用 Droid Sans Fallback。

#### 四种彩色框定义

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

#### 综述结构

**小 cluster（≤ 20 链）**：单篇综述
```latex
\section{引言}           % 问题界定、决策树、论文表
\section{阶段 1: ...}    % 每阶段详细说明 + 末尾四种彩色框
\section{阶段 2: ...}
...
\section{结论}           % 开放问题、未来方向
\begin{thebibliography}{99}  % 参考文献（必须）
\end{thebibliography}
```

**大 cluster（> 20 链）**：总综述 + 子综述

总综述（overview.tex）：
```latex
\section{引言与问题界定}
\section{通用工作流}           % transition graph 为核心
\section{子综述索引}           % 表格：子综述 ID/标题/覆盖阶段/论文数
\section{跨子综述的共性发现}    % 方法论共识、定量一致性、矛盾结论
\section{结论与展望}
\begin{thebibliography}{99}  % 参考文献（必须）
\end{thebibliography}
```

子综述（sub_review_X.tex）：
```latex
\section{引言}          % 在总 workflow 中的位置
\section{阶段 A}        % 详细公式 + 四种彩色框
\section{阶段 B}
\section{小结}
\begin{thebibliography}{99}  % 参考文献（必须）
\end{thebibliography}
```

**强制要求**：
1. **决策树图片**：在引言部分必须插入决策树可视化：
   ```latex
   \begin{figure}[H]
   \centering
   \includegraphics[width=0.9\textwidth]{decision_tree.png}
   \caption{工作流决策树}
   \label{fig:decision_tree}
   \end{figure}
   ```
2. **四种彩色框**：每个阶段末尾必须包含适用的彩色框（toolbox, parambox, casebox, pitfallbox），至少 1 个
3. **参考文献**：文档末尾必须有完整的 `\begin{thebibliography}{99}...\end{thebibliography}` 部分，包含所有 A-主线论文

#### 写作原则

1. **方法机制精确到子步骤**：chain_text 的一句话概括不够，必须展开
2. **每个公式定义所有符号**
3. **四种彩色框嵌入每个阶段末尾**，不设独立汇总章节
4. **案例框包含实现细节**：不仅是规模数字，还有 QC、ID 映射、资源版本
5. **陷阱框覆盖两类**：
   - (a) 方法本身的已知缺陷
   - (b) 论文未报告的实现细节遗漏
6. **A-旁支方法**单独一段标注"变体"，不混入主线
7. **使用 short_name 引用论文**：在正文中使用 `\cite{bibitem_key}` 或 "Zhang et al. (2023)" 格式，不使用裸 paper_id

#### 引文核查

1. **覆盖检查**：综述中每个具体方法、参数值、实验结果都有 `\cite{}` 支撑
2. **一致性检查**：bibliography 条目与正文引用一一对应
3. **交叉引用**：子综述间"详见子综述 X 的 §Y"引用正确
4. **禁止裸 paper_id**：不得出现 "论文 812454164008271872" 这样的引用，必须使用 `\cite{Zhang2023}` 或 "Zhang et al. (2023)"

#### 预测-验证对比审查

1. 每个核心方法/模型是否有至少一个独立验证案例？
   - 如无，在 casebox 中标注"尚无独立验证"
   - 在 pitfallbox 中讨论可行的验证策略
2. 定量偏差必须用具体数字（预测值、验证值、偏差%）
3. 如果整个 cluster 验证覆盖率低，在结论中明确讨论

#### 参考文献

从 `paper_mapping.json` 提取完整的标题、作者、期刊信息。**每条引用必须包含全部作者、完整标题、期刊、年份、卷号、页码**。格式：

```latex
\begin{thebibliography}{99}
\bibitem{Zhang2023} Zhang X, Wang Y, Li Z, Chen M, Liu H. Microarray profile of differentially expressed genes in a monkey model of allergic asthma. Nature Methods, 2023, 20(5): 123-135.
\bibitem{Liu2022} Liu H, Chen M, Wang J, Zhao L. Evidence of genome-wide G4 DNA-mediated gene expression in human cancer cells. Science, 2022, 378(6615): 456-461.
\end{thebibliography}
```

**强制约束**：
1. **所有 A-主线论文必须被引用**：从 `chain_classification.json` 获取 A-主线论文列表，确保每篇都有对应的 `\bibitem`
2. **禁止省略或截断**：参考文献部分必须完整，不得因篇幅限制而省略
3. **禁止 "et al." 缩写**：必须列出全部作者姓名，不得用 "et al."、"等" 或任何缩写形式替代
4. **禁止编造**：所有信息必须来自 `paper_mapping.json`（其数据来源为 MD 文件头部）。如果 volume/pages 字段为空，则省略该部分（写"期刊名, 年份"即可），但绝不可编造虚假的卷号页码。如果 journal 为空，使用 DOI 链接代替（格式：`\url{https://doi.org/...}`）。**绝不可使用 "Unknown Journal" 等占位符**
5. **自动验证**：生成后检查 `count(\bibitem) == count(A-主线论文)`，如不一致则报错并列出遗漏的论文
4. **使用 bibitem_key**：每个 `\bibitem{key}` 的 key 必须与 `paper_mapping.json` 中的 `bibitem_key` 一致

### Step 4: 生成决策树可视化

用 Graphviz DOT 语言生成决策树。

**节点标签格式**（简单文本，避免 HTML TABLE）：

```dot
stage1 [label="阶段 1: 相与晶格表征 (13/13)\n\nXRD Rietveld 精修 (4篇)\nXRD 峰位分析 (9篇)\nRaman 光谱 (12篇)", 
        shape=box, style=rounded, fillcolor="#D5F5E3"];
```

**关键要点**：
- 使用 `\n` 换行，不使用 HTML TABLE
- 使用简单文本标签，避免特殊 Unicode 字符
- ⚠ → `[!]`
- ⁻¹ → `^(-1)`
- ≥ → `>=`
- → → `->`

**颜色约定**：

| 用途 | 背景色 | 形状 |
|------|--------|------|
| 输入节点 | `#D6EAF8` | rounded box |
| 决策菱形 | `#FEF5E7` | diamond |
| 操作步骤 | `#EBF5FB` | rounded box |
| 主流选择 | `#D5F5E3` | rounded box |
| 陷阱警告 | `#FDEDEC` | rounded box |
| 输出节点 | `#F4ECF7` | rounded box |

**使用率标注**：
- 分母 = A-主线链总数
- 同一阶段内各方法加和可能 > 100%
- 保留一位小数
- 边粗细与使用率成正比（penwidth 1.0-4.5）

### Step 5: 渲染和编译

#### 决策树渲染

```bash
dot -Tpng decision_tree.dot -o decision_tree.png
dot -Tpdf decision_tree.dot -o decision_tree.pdf
```

#### LaTeX 编译

**编译前必须检查字体**：

```bash
grep "setCJKmainfont" review_cluster_N.tex
kpathwhich FandolSong-Regular.otf   # 应输出 .otf 路径；若无则未正确安装 TeX Live
```

如果仍使用旧模板中的 `Droid Sans Fallback` 或错误的 Noto 名称，**优先改为 Fandol**：

```bash
sed -i 's/setCJKmainfont{Droid Sans Fallback}/setCJKmainfont{FandolSong}/g; s/setCJKsansfont{Droid Sans Fallback}/setCJKsansfont{FandolHei}/g; s/setCJKmonofont{Droid Sans Fallback}/setCJKmonofont{FandolFang}/g' review_cluster_N.tex
# 若曾写 Noto 但未安装，可改为 FandolSong / FandolHei / FandolFang
```

**编译命令**：

```bash
xelatex -interaction=nonstopmode review_cluster_N.tex  # pass 1
xelatex -interaction=nonstopmode review_cluster_N.tex  # pass 2
```

如果 xelatex 不可用，标注"需要外部编译"，但 .tex 文件必须完整且字体可用。

### Step 6: 输出文件校验

**在清理中间文件之前，必须验证所有关键输出文件已正确生成。**

#### 必须存在的文件

| 文件 | 校验规则 |
|------|---------|
| `review_cluster_N.pdf` | 文件存在 + 大小 > 100 字节 + `file` 命令确认为 PDF 格式 |
| `decision_tree.pdf` | 文件存在 + 大小 > 100 字节 + `file` 命令确认为 PDF 格式 |
| `paper_extractions.yaml` | 文件存在 + 大小 > 100 字节 |
| `workflow_structure.json` | 文件存在 + 大小 > 100 字节 + JSON 格式有效 |

#### 校验命令

```bash
# 检查文件存在性和大小
for file in review_cluster_N.pdf decision_tree.pdf paper_extractions.yaml workflow_structure.json; do
    if [ ! -f "$file" ]; then
        echo "ERROR: 缺少必需文件 $file"
        exit 1
    fi
    size=$(stat -f%z "$file" 2>/dev/null || stat -c%s "$file" 2>/dev/null)
    if [ "$size" -lt 100 ]; then
        echo "ERROR: 文件 $file 过小 ($size 字节)，可能生成失败"
        exit 1
    fi
done

# 验证 PDF 格式
file review_cluster_N.pdf | grep -q "PDF" || { echo "ERROR: review_cluster_N.pdf 不是有效的 PDF 文件"; exit 1; }
file decision_tree.pdf | grep -q "PDF" || { echo "ERROR: decision_tree.pdf 不是有效的 PDF 文件"; exit 1; }

# 验证 JSON 格式
python3 -c "import json; json.load(open('workflow_structure.json'))" || { echo "ERROR: workflow_structure.json 不是有效的 JSON 文件"; exit 1; }

echo "✓ 所有必需文件校验通过"
```

**如果任何校验失败，必须报错并停止，不执行后续清理步骤。**

### Step 7: 清理中间文件

**只有在 Step 6 校验通过后才执行清理。**

#### 必须清理的文件

```bash
# 进度追踪文件（来自 Stage 2）
rm -f .extraction_progress.json

# 临时文件（来自 Stage 1）
rm -f /tmp/paper_titles.txt

# LaTeX 编译产物
rm -f review_cluster_*.aux
rm -f review_cluster_*.log
rm -f review_cluster_*.out

echo "✓ 中间文件清理完成"
```

#### 可选清理（保留供调试）

```bash
# 决策树源码（可选保留）
# rm -f decision_tree.dot
```

**注意**：不要删除任何输出文件（.pdf, .yaml, .json, .md）。

### Step 8: 总综述结论 Clustering（大 cluster 必做）

对所有子综述的结论做二阶分析：

1. **结论分组**：方法论共识、定量一致性、矛盾结论
2. **矛盾分析**：分析可能原因（假设不同、参数不同、材料体系不同）
3. **开放问题提炼**：从矛盾和 gap 中提炼未来研究方向

```latex
\subsection{方法论共识}
\subsection{定量一致性}
\subsection{矛盾结论与原因分析}
\subsection{开放问题与未来方向}
```

## 输出格式

### workflow_3layer.md

```markdown
# 3 层工作流：[主题名称]

## Layer 1: 算法层（做什么）

### 阶段 1: [阶段名]（Phase Name）
**目标**：...
**步骤**：
1. ...
2. ...
**核心公式**：$公式$，其中 $符号$ = 定义
**输出**：...

---

## Layer 2: 实现层（怎么做）

### 阶段 1 实现细节
**仪器参数**：...
**数据处理**：...
**推荐默认值**：...

---

## Layer 3: 陷阱与最佳实践

### 陷阱 1: [陷阱名称]
**问题**：...
**证据**：...
**解决方案**：...

---

## 案例研究

### 案例 1: [案例名称]
...

## 验证清单
- [ ] 检查项 1
- [ ] 检查项 2

## 决策树
```

### Step 7: 清理中间文件

完成所有输出后，删除以下中间文件：
- `chain_classification.json` - 已整合到 paper_extractions.yaml
- `step_statistics.json` - 已整合到 workflow_structure.json
- `review_plan.json` - 已整合到 review.tex
- `paper_inventory.md` - 已整合到 review.tex
- `paper_mapping.json` - 已整合到 review.tex 的 \bibitem
- `.extraction_progress.json` - 进度追踪文件（隐藏文件）
- `review_cluster_N.aux`, `review_cluster_N.log`, `review_cluster_N.out` - LaTeX 编译产物
- `decision_tree.pdf` - 与 decision_tree.png 重复（保留 PNG 即可）

保留以下文件：
- `review_cluster_N.pdf`, `decision_tree.png` - 人类可读输出
- `workflow_3layer.md`, `review_cluster_N.tex`, `decision_tree.dot` - Agent 可读输出
- `workflow_meta.json`, `workflow_structure.json` - 元数据
- `paper_extractions.yaml` - 调试/追溯
- `selected_chains.json`, `xml/`, `md/` - 原始输入

## 验证清单

### 3 层文档
- [ ] workflow_3layer.md 存在
- [ ] 全文使用中文（术语有英文对照）
- [ ] 包含 Layer 1（算法层）、Layer 2（实现层）、Layer 3（陷阱层）
- [ ] 每个阶段至少 2 篇论文的证据支持
- [ ] 基础设施阶段（QC、ID 映射、资源审计）不遗漏
- [ ] 至少 1 个完整案例研究
- [ ] 验证清单存在且可打勾
- [ ] 可执行性审查通过
- [ ] 公式符号首次出现时有定义

### LaTeX 综述
- [ ] review_cluster_N.tex 存在
- [ ] 综述全文使用中文
- [ ] 术语首次出现时有英文对照
- [ ] xeCJK preamble 配置正确
- [ ] **四种彩色框已定义**（toolbox, parambox, casebox, pitfallbox）
- [ ] **引言部分包含决策树图片**（`\includegraphics{decision_tree.png}`）
- [ ] 每个阶段有 ≥ 1 个公式
- [ ] **每个阶段末尾有彩色框**（至少 1 个，适用项全部包含）
- [ ] 案例框含实现细节（QC、ID 映射、资源版本）
- [ ] 陷阱框覆盖：方法缺陷 + 论文遗漏
- [ ] 引言含问题界定、范式、论文表
- [ ] **正文中使用 `\cite{bibitem_key}` 或 "FirstAuthor et al. (Year)"，无裸 paper_id**
- [ ] **参考文献部分存在**（`\begin{thebibliography}{99}...\end{thebibliography}`）
- [ ] **参考文献完整且格式一致（使用 paper_mapping.json 生成）**
- [ ] **所有 A-主线论文已被引用（count(\bibitem) == count(A-主线论文)）**
- [ ] 引文覆盖检查通过（无漏引）
- [ ] 每个核心方法有独立验证案例（或标注"尚无"）
- [ ] 定量偏差用具体数字

### 可视化
- [ ] decision_tree.dot 存在且语法正确
- [ ] decision_tree.png 已生成
- [ ] 节点显示方法频次
- [ ] 使用率标注以 A-主线总数为分母
- [ ] 使用简单文本标签（无 HTML TABLE）

### LaTeX 编译
- [ ] xelatex 两遍无 error（或标注需外部编译）
- [ ] 中文字体为 **Fandol**（`FandolSong` / `FandolHei` / `FandolFang`）或等价路径加载，编译无字体缺失
- [ ] review_cluster_N.pdf 已生成（或标注环境限制）

### 输出文件校验
- [ ] review_cluster_N.pdf 存在且 > 100 字节
- [ ] decision_tree.png 存在且 > 100 字节
- [ ] paper_extractions.yaml 存在且 > 100 字节
- [ ] workflow_structure.json 存在且 > 100 字节且 JSON 有效
- [ ] PDF 文件格式校验通过

### 中间文件清理
- [ ] chain_classification.json 已删除
- [ ] step_statistics.json 已删除
- [ ] review_plan.json 已删除
- [ ] paper_inventory.md 已删除
- [ ] paper_mapping.json 已删除
- [ ] .extraction_progress.json 已删除
- [ ] LaTeX 编译产物（.aux, .log, .out）已删除
- [ ] decision_tree.pdf 已删除
