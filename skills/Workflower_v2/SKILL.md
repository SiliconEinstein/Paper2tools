# Workflower_v2 - 从推理链中提取科研工作流

**用途**：从聚类推理链中提取经过验证的科研工作流，确保严格遵循工作流定义，所有方法/工具均来自实际论文。

**使用者**：执行工作流提取任务的 AI agent

**输入**：
- `selected_chains.json` - 来自论文的聚类推理链
- 原始论文 Markdown 文件（位于 `md/` 目录）

**输出**（统一保存在输入目录下的 `workflow/` 子目录中）：
- `workflow/workflow_metadata.json` - 核心工作流结构（步骤、依赖、判断节点）
- `workflow/papers_metadata.json` - 论文级参数与方法 + ARM 环境配置
- `workflow/workflow_visualization.html` - 可视化页面

**ARM 支持**：
- `papers_metadata.json` 包含顶层 `environment` 字段，定义 agent 运行工作流所需的完整环境配置
- 包括：Python 版本、依赖包、计算工具（DFT/DFPT 代码）、硬件要求
- 每篇论文包含 `computational_setup` 字段，记录具体的计算参数（k点、截断能、收敛标准等）
- Agent 拿到 papers_metadata.json 后能够：
  1. 搭建运行环境（安装依赖）
  2. 配置计算工具（设置参数）
  3. 复现论文结果（使用相同的计算设置）

---

## 工作流定义（严格标准）

有效工作流必须同时满足以下全部条件：

1. **问题导向性**：针对某一类特定问题设计，问题描述清晰具体
2. **程序性**：操作序列清晰，顺序明确
3. **步骤依赖性**：后续步骤依赖前序步骤的结果
4. **可泛化性**：可跨多个实例应用，而非特定于某篇论文
5. **清晰的输入输出**：每个步骤有可识别的输入和输出

**加分项**（非必须）：
- 包含条件分支或判断节点

**最低支撑数量**：至少 10 条推理链支撑同一核心工作流

---

## 输出路径规则

所有生成的文件统一保存在输入目录下的 `workflow/` 子目录中。例如：
- 输入：`.../selected_chains.json`
- 输出：`.../workflow/workflow_metadata.json`
- 输出：`.../workflow/papers_metadata.json`

阶段性中间文件（如 stage1、stage2 输出）也保存在同一 `workflow/` 目录下。

---

## 四阶段流程

### 阶段一：判断可提取性
**详细说明**：`scripts/01_judge_extractability.md`

读取 `selected_chains.json`，判断：
- 是否有 ≥10 条链支撑同一工作流？
- 该工作流是否满足全部 5 项严格标准？
- 若存在多个工作流，哪个是最核心的？

**输出**：GO/NO-GO 决策 + 理由说明

---

### 阶段二：筛选核心推理链
**详细说明**：`scripts/02_select_chains.md`

确定：
- 哪些链（≥10 条）构成核心工作流
- 这些链来自哪些论文
- 公共步骤序列是什么

**输出**：链 ID 列表 + 论文 ID 列表 + 初步步骤大纲

---

### 阶段三：提取元数据
**详细说明**：`scripts/03_extract_metadata.md`

生成两个文件：

**workflow_metadata.json**：
- 核心步骤（严格来自推理链，不得虚构）
- 步骤依赖关系与输入输出
- 判断节点（如有）
- **⚠️ paper_refs**：顶层必须包含所有相关论文的 ID 列表（溯源）

**papers_metadata.json**：
- 每篇论文的参数（参数取值、设备规格等）
- 实验方法与工具（严格来自论文）
- 材料属性

**关键规则**：
- 步骤来自推理链（研究者做了什么）
- 方法/工具来自论文（如何做的）
- 严禁虚构或假设未在原始材料中出现的细节

---

### 阶段四：生成可视化 HTML
**详细说明**：`scripts/04_generate_visualization.md`

基于阶段三的两个 JSON 文件，生成单个自包含的 `workflow/workflow_visualization.html`：

- **区块一**：工作流步骤（可折叠卡片，展示工具/参数/子步骤/输入输出）
- **区块二**：决策节点（若有）
- **区块三**：代表性论文（只展示方法/工具相关字段和关键发现）

所有数据内联到 `<script>` 中，无外部依赖，可直接在浏览器打开。

---

## 质量检查清单

完成阶段三前，验证：

### workflow_metadata.json
- [ ] `workflow_metadata.json` 中的步骤均可在推理链中找到依据
- [ ] 步骤依赖关系明确且可验证
- [ ] 无虚构细节或主观假设
- [ ] **⚠️ `workflow_metadata` 顶层有 `paper_refs` 字段且非空**

### papers_metadata.json
- [ ] `papers_metadata.json` 中的方法/参数均可在论文中找到依据
- [ ] 所有 `experimental_methods` 字段有具体值（非通用占位符）
- [ ] **⚠️ 所有 `paper_refs` 中的论文 ID 都存在于 `papers_metadata.json` 中**

### ARM 环境配置（新增）
- [ ] **⚠️ `papers_metadata.json` 顶层有 `environment` 字段**
- [ ] **⚠️ `environment.python_version` 已指定**
- [ ] **⚠️ `environment.required_packages` 列表非空，所有包都有版本约束**
- [ ] **⚠️ `environment.computational_tools` 包含论文中使用的 DFT/分析工具**
- [ ] **⚠️ `environment.hardware_requirements` 已填写（内存、CPU、磁盘）**
- [ ] 每篇论文有 `computational_setup` 字段（如为计算类工作流）
- [ ] 环境配置信息完整，agent 能根据此搭建运行环境

### 可视化
- [ ] `workflow_visualization.html` 可在浏览器中直接打开

---

## 相关 Skill

- **Workflow2Code**：基于提取的工作流生成复现代码并进行测试验证

---

## 示例文件

- `examples/papers_metadata_with_environment.json` - 完整的 papers_metadata.json 示例，包含 ARM 环境配置

**示例展示**：
- 顶层 `environment` 字段的完整结构
- Python 依赖包配置（必需 + 可选）
- 计算工具配置（DFT 代码、分析工具、后处理工具）
- 硬件需求估算
- 每篇论文的 `computational_setup` 字段（计算参数详情）

---

## 使用流程

1. **准备输入**：确保有 `selected_chains.json` 和原始论文 markdown 文件
2. **阶段一**：判断是否可提取工作流（GO/NO-GO 决策）
3. **阶段二**：筛选核心推理链（≥10 条）
4. **阶段三**：交织式提取元数据（5 轮迭代）
   - 第一轮：步骤框架
   - 第二轮：方法与工具
   - 第三轮：子步骤细化
   - 第四轮：知识库构建（如适用）
   - 第五轮：papers_metadata.json + ARM 环境配置
5. **阶段四**：生成可视化 HTML
6. **质量检查**：验证所有检查项（包括 ARM 环境配置）
7. **交付**：`workflow/` 目录下的 3 个文件（JSON × 2 + HTML × 1）
