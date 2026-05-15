# Workflow2Code - 基于 ARM 规范的工作流复现

**用途**：基于工作流元数据和论文语料，自动生成测试题目、实现代码、运行测试、分析结果，并通过迭代优化发现 metadata 的不足。

**使用者**：执行 Workflow2Code 流程的 AI agent

**ARM (Agent-Ready Manuscript)**：一种标准化的文件格式规范，定义了 agent 能直接使用的研究包结构。ARM 包含：
- 环境配置（依赖、参数）
- 可执行代码（workflow 实现）
- 测试数据集（问题定义、测试用例）
- 执行轨迹（版本迭代记录）
- 分析报告（测试结果、经验总结）

Agent 拿到一个 ARM 包后，能够：
1. 理解研究任务（读取 problems 和 metadata）
2. 直接运行代码（执行 workflow.py）
3. 复现结果（运行测试并验证）
4. 查看完整轨迹（从 v1 到 vN 的迭代过程）

**核心目标**：
1. 验证 workflow_metadata 和 papers_metadata 的完整性和正确性
2. 发现 metadata 中缺失的关键信息（公式、参数、约束）
3. 通过迭代补充 metadata，提升工作流的可复现性
4. 生成符合 ARM 规范的标准化研究包

---

## 输入文件

**必需输入**：
- `workflow_metadata.json` - 工作流结构（步骤、方法、工具、依赖关系）
- `papers_metadata.json` - 论文元信息（参数、公式、实验数据）
- `md/{paper_id}.md` - 原论文 markdown 文件（用于生成题目和补充 metadata）

**输入位置**：
- 通常位于 `data/{domain}/workflows_top50/cluster_{N}/workflow/`

---

## 输出结构（ARM 标准目录）

```
ARM{N}/
├── plan/                          # 复现计划
│   ├── understanding.md           # 题目理解、workflow 理解
│   └── implementation_plan.md     # 代码实现计划
├── code/                          # 代码文件
│   ├── workflow.py                # 主工作流实现
│   ├── test_runner.py             # 测试运行器
│   ├── run_tests_v{N}.py          # 版本化测试脚本
│   └── ...                        # 其他辅助模块
├── dataset/                       # 测试数据
│   ├── problems/                  # 测试题目
│   │   ├── problem_1.md
│   │   ├── problem_2.md
│   │   └── problem_3.md
│   └── test_cases.json            # 机器可读测试用例
├── result/                        # 测试结果
│   ├── v1_baseline/
│   │   ├── TEST_REPORT.md         # 简要报告
│   │   ├── TEST_REPORT_DETAILED.md # 详细分析
│   │   └── *.png                  # 可视化图表
│   ├── v2/
│   └── v3/
├── trace/                         # 迭代日志
│   └── TRACE.md                   # 版本变更记录
├── report/                        # 总结报告
│   ├── ARM_Notebook.md            # 完整过程报告
│   └── PROGRESS_SUMMARY.md        # 进度总结
├── information/                   # 经验总结
│   └── lessons_learned.md         # 人类可读的经验
└── others/                        # 其他文件
    └── ...
```

---

## 核心流程

### Phase 1: 题目生成（Generate Problems）

**目标**：从论文中提取实验场景，生成 3 道测试题目

**步骤**：
1. 从 `papers_metadata.json` 中随机选择 3 篇论文
2. 读取每篇论文的 markdown 文件
3. 用 LLM 分析论文，生成题目（`dataset/problems/problem_{N}.md`）

**题目格式**：
```markdown
# Problem {N}: {材料/实验名称}

## 背景
{从论文中提取的实验背景，1-2 段}

## 任务
复现论文中的 {具体实验/计算}，得到 {具体结果}。

## 输入参数
{实验的输入参数，如材料成分、晶格常数、温度等}

## 预期输出
{要复现的结果，分为数值结果和图表结果}

### 数值结果
- `lambda`: 0.73 ± 0.22 (tolerance: 30%)
- `Tc_K`: 40 ± 20 (tolerance: 50%)
- ...

### 图表结果（可选）
- `alpha2F_curve.png`: α²F(ω) 曲线
- `phonon_dispersion.png`: 声子色散关系
- ...

## 评分标准
- 数值结果：在 tolerance 范围内视为通过
- 图表结果：生成即通过（内容正确性暂不自动评分）

## 论文来源
- Paper ID: {paper_id}
- 相关章节：{section/figure/table}
```

**约束**：
- 题目必须基于论文原文，不能虚构数据
- 预期输出的数值必须从论文中提取（表格、图表、结论）
- tolerance 根据论文中的误差范围或领域惯例设定
- 3 道题目应覆盖不同材料/场景（如简单案例、复杂案例、边界案例）

**输出**：
- `dataset/problems/problem_{1,2,3}.md`
- `dataset/test_cases.json`（机器可读格式）

---

### Phase 2: 复现计划（Planning）

**目标**：在写代码前，明确理解题目、workflow 和 metadata

**步骤**：
1. 分析每道题目的要求
2. 分析 workflow_metadata 的步骤结构
3. 规划如何用 papers_metadata 中的信息实现每个步骤
4. 识别可能缺失的 metadata

**输出**：`plan/understanding.md` 和 `plan/implementation_plan.md`

**understanding.md 内容**：
```markdown
# 题目理解

## Problem 1: {标题}
- 核心任务：{一句话概括}
- 关键输入：{列出}
- 预期输出：{列出}
- 难点：{预判可能的困难}

## Problem 2: ...
## Problem 3: ...

# Workflow 理解

## 步骤结构
{列出 S1-SN 的步骤及其职责}

## 数据流
{画出数据流向图，文本形式}

## 关键方法
{列出每个步骤使用的核心方法}

# Metadata 可用性分析

## papers_metadata.json 提供的信息
{列出可用的参数、公式、实验数据}

## workflow_metadata.json 提供的信息
{列出步骤定义、方法、工具}

## 可能缺失的信息
{预判哪些信息可能不足}
```

**implementation_plan.md 内容**：
```markdown
# 代码实现计划

## 文件结构
{规划需要创建哪些文件}

## 模块职责
{每个模块负责什么}

## 实现策略

### Step 1: {步骤名}
- 输入：{列出}
- 输出：{列出}
- 实现方法：{简述}
- 依赖的 metadata：{列出}

### Step 2: ...

## 参数化策略
{说明如何用参数化模型代替完整计算}

## 测试策略
{说明如何验证每个步骤的输出}
```

---

### Phase 3: v1 代码生成（Implementation）

**目标**：根据 metadata 生成可运行的代码

**约束**：
- ❌ 不得查看论文原文（markdown）
- ✅ 只能使用 workflow_metadata.json 和 papers_metadata.json
- ❌ 不得根据预期输出反推参数（不作弊）
- ✅ 使用参数化模型代替完整 DFT/DFPT 计算
- ✅ 代码必须完整可运行，不能有 TODO 占位

**代码组织**：
- 根据问题复杂度自由设计文件结构
- 简单问题：单文件 `workflow.py`
- 复杂问题：多模块（如 `step1.py`, `step2.py`, ...）
- 必须包含：
  - 主工作流实现
  - 测试运行器（`test_runner.py`）
  - 版本化测试脚本（`run_tests_v1.py`）

**代码质量要求**：
- 每个函数有清晰的 docstring（职责、参数、返回值）
- 关键计算步骤有注释说明公式来源
- 参数来源标注（如 `# From paper 867758380683362769`）
- 错误处理（避免除零、数组越界等）

**输出**：
- `code/workflow.py`（及其他必要文件）
- `code/test_runner.py`
- `code/run_tests_v1.py`

---

### Phase 4: 测试与报告（Testing & Reporting）

**目标**：运行测试，生成详细报告，分析错误原因

**步骤**：
1. 运行 `run_tests_v1.py`
2. 对比实际输出与预期输出
3. 分析失败原因（根因分类）
4. 生成可视化图表
5. 生成测试报告

**根因分类**（按优先级）：
- 🔴 **metadata 缺失**（最高优先级）：papers_metadata 或 workflow_metadata 中缺少关键信息
- 🟡 **算法实现错误**：代码逻辑与 workflow 定义不符
- 🟢 **阈值过严**：tolerance 设置不合理
- 🔵 **数据局限性**：论文本身数据不足或矛盾

**测试报告结构**：

**TEST_REPORT.md**（简要版）：
```markdown
# 测试报告 - v{N}

## 版本信息
- 版本号: v{N}
- 日期: {YYYY-MM-DD}
- 改动说明: {本版本的主要改动}
- metadata 变更: {是/否，如果是，列出变更内容}

## 总体结果
- 总测试数: {N}
- 通过: {M} ({M/N}%)
- 失败: {N-M} ({(N-M)/N}%)

## 各检查项通过率
| 检查项 | 通过/总数 | 通过率 |
|--------|----------|--------|
| ... | ... | ... |

## 失败案例详细分析
### {材料名} (Test ID: {ID})
**描述**: {题目描述}
**失败检查**:
- **{检查项}**: 预期 {X}, 实际 {Y} (容差 {Z}%)
  - **原因**: Error {E}% > tolerance {Z}%
...

## 通过案例
- {列出通过的案例}
```

**TEST_REPORT_DETAILED.md**（详细版）：
```markdown
# 测试报告 - v{N}（详细分析）

{包含 TEST_REPORT.md 的所有内容，额外增加：}

## 根本原因分类统计
| 根因类别 | 失败数 | 占比 | 严重程度 | 修复优先级 |
|----------|--------|------|----------|------------|
| 🔴 metadata 缺失 | {N} | {%} | 高 | P1 |
| 🟡 算法实现错误 | {N} | {%} | 中 | P2 |
| 🟢 阈值过严 | {N} | {%} | 低 | P3 |
| 🔵 数据局限性 | {N} | {%} | - | - |

## 失败案例根因分析
### 🔴 {案例}: {检查项失败}
**现象**: {描述}
**根本原因**: {详细分析}
**需要补充的 metadata**: {具体列出}
**修复方向**: {建议}

...

## 修复建议
### v{N+1} 计划（高优先级）
**目标**: {本次迭代的目标}
**需要回到论文补充的信息**:
- [ ] {具体信息 1}
- [ ] {具体信息 2}
**预期改进**: {通过率目标}

### v{N+2} 计划（中优先级）
...
```

**可视化图表**：
- `pass_rate_evolution.png`: 通过率演变曲线（v1 → v2 → v3）
- `check_item_pass_rate.png`: 各检查项通过率对比
- `failure_root_cause.png`: 失败根因分布饼图
- 题目要求的图表（如 `alpha2F_curve.png`）

**输出**：
- `result/v1_baseline/TEST_REPORT.md`
- `result/v1_baseline/TEST_REPORT_DETAILED.md`
- `result/v1_baseline/*.png`

---

### Phase 5: 迭代优化（Iteration）

**目标**：根据测试报告，补充 metadata 并修复代码

**迭代触发**：
- ⚠️ **每次迭代后暂停，等待用户确认**
- 用户查看报告后，决定是否继续迭代

**迭代步骤**：
1. 根据 TEST_REPORT_DETAILED.md 中的根因分析
2. 回到论文 markdown 文件，提取缺失的 metadata
3. 更新 `papers_metadata.json` 和/或 `workflow_metadata.json`
4. 修复代码中的算法错误
5. 重新运行测试，生成 v{N+1} 报告
6. 更新 `trace/TRACE.md`

**metadata 更新原则**：
- 优先补充 🔴 metadata 缺失的信息
- 从论文原文中提取，不虚构
- 记录信息来源（paper ID + section/equation）
- 如果论文中也没有，标注为"需要外部知识"

**代码修复原则**：
- 修复所有发现的问题（不只修一个）
- 保持代码版本号与测试版本号一致
- 在代码中标注修复内容（如 `# v2 fix: ...`）

**停止条件**：
- 通过率 ≥ 90%
- 剩余失败确认为数据局限性（非 metadata 问题）
- 连续 3 次迭代通过率无改善
- 用户决定停止

**输出**：
- 更新的 `papers_metadata.json` 和/或 `workflow_metadata.json`
- 更新的 `code/workflow.py`
- `result/v{N+1}/TEST_REPORT*.md`
- 更新的 `trace/TRACE.md`

---

## 最终报告（Final Report）

**目标**：生成可读性强的完整过程报告

**report/ARM_Notebook.md 结构**：
```markdown
# ARM Notebook - {Workflow Name}

## 1. 概述
- 工作流名称
- 测试日期
- 最终通过率
- 迭代次数

## 2. 测试题目
{列出 3 道题目的简要描述}

## 3. 迭代历史
| 版本 | 日期 | 通过率 | 主要改动 | metadata 变更 |
|------|------|--------|----------|---------------|
| v1 | ... | ... | ... | ... |
| v2 | ... | ... | ... | ... |

## 4. 关键发现
### metadata 缺失分析
{总结发现的 metadata 不足}

### 算法实现挑战
{总结实现过程中的难点}

## 5. 最终结果
### 通过案例
{列出通过的案例及其关键指标}

### 失败案例
{列出失败的案例及其原因}

## 6. 可视化
{嵌入关键图表}

## 7. 经验总结
{人类可读的经验教训}

## 8. 未来改进方向
{如果未达到 90%，说明下一步方向}
```

**report/PROGRESS_SUMMARY.md 结构**：
```markdown
# ARM 迭代进度总结

## 概览
| 版本 | 日期 | 通过率 | 通过案例 | 主要改动 |
|------|------|--------|----------|----------|
| v1 | ... | ... | ... | ... |
| v2 | ... | ... | ... | ... |

## 各检查项通过率演变
| 检查项 | v1 | v2 | v3 | 改进 |
|--------|----|----|----|----|
| ... | ... | ... | ... | ... |

## v1 → v2 关键突破
{详细说明}

## v2 → v3 关键突破
{详细说明}

## metadata 补充记录
{列出所有补充的 metadata 及其来源}

## 经验总结
{提炼的可复用经验}
```

---

## 关键规则

### 1. 不作弊原则
- ❌ 代码生成时不得查看论文原文
- ❌ 不得根据预期输出反推参数
- ✅ 只能使用 metadata 中的信息
- ✅ 如果 metadata 不足导致失败，这正是我们要发现的

### 2. metadata 优先原则（严格执行）

**核心约束**：
- 🔴 metadata 缺失是最高优先级问题
- ❌ **绝对禁止在代码中硬编码从论文提取的参数、公式、常数**
- ✅ **所有参数必须从 `workflow/papers_metadata.json` 读取**
- ✅ **发现 metadata 不足时，必须先更新 metadata 文件，再修改代码**

**metadata 更新流程**（强制执行）：
```
发现 metadata 缺失（测试失败）
  ↓
回到论文原文提取信息
  ↓
⚠️ 更新 workflow/papers_metadata.json（添加新字段）
  ↓
在 metadata 中记录：
  - metadata_version: "v{N}"
  - last_updated: "YYYY-MM-DD"
  - changelog: "补充了什么信息"
  - source_paper: "paper_id 或 derived"
  ↓
代码从 metadata 读取（通过 load_metadata() 函数）
  ↓
记录到 ARM/trace/TRACE.md
```

**禁止的做法**：
```python
# ❌ 错误：硬编码参数
HOPFIELD_ETA = {
    'MgB2': {'Mg': 0.03, 'B': 1.87},  # 从论文提取但硬编码
}

MATERIAL_PARAMS = {
    'MgB2': {'N_EF': 0.35, 'omega_E2g': 70.8},  # 硬编码
}
```

**正确的做法**：
```python
# ✅ 正确：从 metadata 读取
def load_metadata(material):
    metadata_path = '../../workflow/papers_metadata.json'
    with open(metadata_path) as f:
        data = json.load(f)
    for paper in data['papers']:
        if material in paper['material']:
            return paper
    raise ValueError(f"No metadata found for {material}")

# 使用
metadata = load_metadata('MgB2')
hopfield = metadata['expected_results']['hopfield_parameters']
```

**metadata 完整性检查**：
每次迭代开始前，检查 metadata 是否包含所需字段：
```python
required_fields = ['hopfield_parameters', 'lambda_formula', 'debye_temperature_K']
missing = [f for f in required_fields 
           if f not in metadata.get('expected_results', {})]
if missing:
    raise MetadataIncompleteError(
        f"Missing fields in papers_metadata.json: {missing}\n"
        f"Please update workflow/papers_metadata.json first."
    )
```

**metadata 版本追踪**：
每次补充 metadata 时，必须更新版本信息：
```json
{
  "paper_id": "867758380683362769",
  "material": "MgB₂",
  "expected_results": {
    "hopfield_parameters": {
      "Mg": 0.03,
      "B": 1.87,
      "unit": "eV/Å²"
    },
    "lambda_formula": {
      "description": "λ = Σ_α η_α/(M_α × <ω²>) × unit_factor",
      "unit_conversion_factor": 8162,
      "derivation": "从 MgB₂ 数据反推"
    }
  },
  "metadata_version": "v2",
  "last_updated": "2026-05-14",
  "changelog": "补充 Hopfield 参数和 λ 计算公式的单位转换因子",
  "updated_by": "ARM iteration v2"
}
```

### 3. 完整性原则
- 代码必须完整可运行，不能有 TODO
- 测试报告必须包含根因分析
- 每次迭代必须更新 TRACE.md

### 4. 可读性原则
- ARM_Notebook.md 要面向人类读者
- 图表要清晰美观
- 经验总结要具体可操作

### 5. 版本管理原则
- 每个版本独立目录，不覆盖旧版本
- 版本号递增（v1, v2, v3, ...）
- TRACE.md 记录所有版本的变更

---

## 并行加速

对于独立的操作，使用并行执行：
- 生成 3 道题目：并行读取 3 篇论文
- 运行测试：并行测试 3 个案例（如果测试独立）
- 生成图表：并行生成多张图

---

## 适用范围

本 skill 适用于：
- 可量化验证的工作流（有明确输入输出）
- 有参考论文的工作流（可生成测试题目）
- 任何科学计算领域（物理、化学、生物、材料等）

不适用于：
- 纯定性的工作流（无法构造测试）
- 无参考论文的工作流（无法生成题目）

---

## 相关 Skill

- **Workflower_v2**: 提取工作流和元数据（本 Skill 的前置）
- **WorkflowChallenger**: 生成挑战性测试案例（可选的后续）
