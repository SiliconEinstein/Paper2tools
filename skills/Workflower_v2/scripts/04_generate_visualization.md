# 阶段四：生成可视化 HTML

**目标**：基于阶段三生成的 `workflow_metadata.json` 和 `papers_metadata.json`，生成一个自包含的 `workflow_visualization.html` 文件，用于在浏览器中可视化展示工作流结构和论文方法信息。

**前置条件**：阶段三已完成（`workflow_metadata.json` 和 `papers_metadata.json` 均已生成）

---

## 输出文件

`workflow/workflow_visualization.html` — 单个自包含 HTML 文件，无外部依赖

---

## 生成规则

### 1. 数据嵌入

将 JSON 数据直接内联到 `<script>` 标签中：

```html
<script>
const workflowData = { /* workflow_metadata.json 内容 */ };
const papersData = [ /* papers_metadata.json 中的 papers 数组 */ ];
</script>
```

### 2. 页面结构（三个区块）

**区块一：工作流步骤**
- 每个步骤为可折叠卡片（点击展开/收起）
- 展开后显示：
  - 所需工具（`required_tools.software` / `required_tools.hardware` / `required_tools.methods`）
  - 典型参数（`typical_parameters`）
  - 子步骤列表（含 `frequency`、`formula`）
  - 输入/输出

**区块二：决策节点**（若 `decision_nodes` 非空）
- 每个节点显示：判断条件 + 各分支说明

**区块三：代表性论文**
- 每篇论文显示与方法/工具相关的字段：
  - DFT/计算设置（`dft_code`、`xc_functional`、`k_points`、`cutoff_energy` 等）
  - 实验硬件（`experimental_methods.hardware`）
  - 分析方法（`experimental_methods.analysis_methods`）
  - 计算结果（`computed_lambda`、`predicted_Tc_K` 等数值结果字段）
  - 关键发现（`expected_results.key_finding`）
- **不展示**：`paper_id`、`expected_results` 中的非 `key_finding` 字段

### 3. 样式要求

- 渐变色 Header（含工作流标题、描述、统计数字）
- 步骤卡片使用与 Header 相同的渐变色
- 决策节点使用黄色警示风格（`#fff3cd` 背景）
- 论文卡片使用白色背景 + 悬停边框高亮
- 工具/方法使用 badge 样式展示

---

## 生成流程

### 第一步：读取数据

读取 `workflow/workflow_metadata.json` 和 `workflow/papers_metadata.json`，提取：
- `workflow_metadata`（标题、描述、统计）
- `workflow_steps`（步骤列表）
- `decision_nodes`（决策节点，可能为空）
- `papers`（论文列表）

### 第二步：构建 HTML

按以下模板生成完整 HTML，将数据内联到 `<script>` 中：

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>{workflow_metadata.title}</title>
    <style>/* 样式 */</style>
</head>
<body>
    <!-- Header：标题 + 描述 + 统计（source_papers、core_chains、步骤数） -->
    <!-- 区块一：工作流步骤 -->
    <!-- 区块二：决策节点（若有） -->
    <!-- 区块三：代表性论文 -->
    <script>
        const workflowData = { ... };
        const papersData = [ ... ];
        // renderWorkflowSteps()
        // renderDecisionNodes()
        // renderPapers()
        // toggleStep(index)
        // DOMContentLoaded 初始化
    </script>
</body>
</html>
```

### 第三步：论文字段渲染逻辑

论文卡片只渲染以下类别的字段（跳过 `paper_id`、`title`/`paper_title` 以外的标识字段）：

| 优先级 | 字段来源 | 展示标题 |
|--------|----------|----------|
| 1 | `dft_code`、`xc_functional`、`k_points`、`q_points`、`cutoff_energy`、`smearing` | 💻 计算设置 |
| 2 | `experimental_methods.hardware` | 🔧 实验硬件 |
| 3 | `experimental_methods.analysis_methods` | 🔬 分析方法 |
| 4 | `computed_lambda`、`predicted_Tc_K`、`omega_log_meV`、`mu_star` 等数值结果 | 📊 计算结果 |
| 5 | `expected_results.key_finding` | 关键发现（蓝色高亮块） |

若某类字段在该论文中不存在，则跳过该区块。

---

## 质量检查

- [ ] HTML 文件可在浏览器中直接打开（无外部依赖）
- [ ] 所有工作流步骤均可展开/收起
- [ ] 论文卡片只展示方法/工具相关字段，不展示原始 ID 或冗余字段
- [ ] 决策节点区块：若 `decision_nodes` 为空则不渲染该区块
- [ ] Header 统计数字与 `workflow_metadata` 中的 `source_papers`、`core_chains` 一致
