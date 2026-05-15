# Phase 1: 生成测试题目与复现计划

本阶段的目标是：
1. 从论文中生成 3 道测试题目
2. 理解题目、workflow 和 metadata
3. 制定代码实现计划

---

## Step 1.1: 生成测试题目

### 输入
- `papers_metadata.json` - 用于选择论文
- `md/{paper_id}.md` - 论文原文

### 任务
从 `papers_metadata.json` 中随机选择 3 篇论文，为每篇论文生成一道测试题目。

### 题目生成指南

**选择论文**：
```python
import json
import random

with open('papers_metadata.json') as f:
    metadata = json.load(f)
    papers = metadata['papers']
    
# 随机选择 3 篇
selected = random.sample(papers, 3)
```

**题目要求**：
1. **基于论文原文**：必须读取 `md/{paper_id}.md`，从中提取实验场景
2. **任务明确**：清楚说明要复现什么实验/计算
3. **输入完整**：列出所有必要的输入参数
4. **输出可验证**：预期输出必须是可量化的（数值或图表）
5. **难度适中**：不要选择论文中最复杂的实验，选择有代表性的核心实验

**题目结构**（参考 SKILL.md 中的模板）：
```markdown
# Problem {N}: {材料/实验名称}

## 背景
{1-2 段，说明实验背景和科学问题}

## 任务
复现论文中的 {具体实验}，得到 {具体结果}。

## 输入参数
{列出所有输入，如：}
- 材料成分: MgB₂
- 晶格常数: a = 3.086 Å, c = 3.524 Å
- 计算方法: DFT + DFPT
- ...

## 预期输出

### 数值结果
- `lambda`: 0.73 ± 0.22 (tolerance: 30%)
  - 来源: 论文 Table 2
- `Tc_K`: 40 ± 20 (tolerance: 50%)
  - 来源: 论文 Figure 5
- ...

### 图表结果（可选）
- `alpha2F_curve.png`: α²F(ω) 曲线
  - 要求: 峰值在 60-70 meV 范围
  - 参考: 论文 Figure 3

## 评分标准
- 数值结果: 在 tolerance 范围内视为通过
- 图表结果: 生成即通过（内容正确性暂不评分）

## 论文来源
- Paper ID: {paper_id}
- Title: {title}
- 相关章节: {section/figure/table}
```

**关键注意事项**：
- ⚠️ **预期输出的数值必须从论文原文提取**，不能从 `papers_metadata.json` 复制
- ⚠️ **tolerance 设置要合理**：
  - 基础物理量（如频率、质量）：10-20%
  - 计算量（如 λ, ω_log）：20-30%
  - 预测量（如 Tc）：30-50%
  - 如果论文给出误差范围，使用论文的值
- ⚠️ **标注数据来源**：每个预期输出都要注明来自论文的哪个表格/图/段落

### 输出
- `dataset/problems/problem_1.md`
- `dataset/problems/problem_2.md`
- `dataset/problems/problem_3.md`
- `dataset/test_cases.json`（机器可读格式）

**test_cases.json 格式**：
```json
{
  "test_cases": [
    {
      "test_id": "P1",
      "problem_file": "problem_1.md",
      "paper_id": "867771392240648834",
      "material": "MgB2",
      "description": "MgB₂ baseline case - E₂g mode softening",
      "input": {
        "material": "MgB2",
        "lattice": {"a": 3.086, "c": 3.524},
        "mu_star": 0.10
      },
      "expected_output": {
        "lambda": 0.73,
        "Tc_K": 40,
        "E2g_frequency_meV": 70.8,
        "E2g_linewidth_meV": 15,
        "omega_log_meV": 60.9
      },
      "tolerance": {
        "lambda": 0.30,
        "Tc_K": 0.50,
        "E2g_frequency_meV": 0.10,
        "E2g_linewidth_meV": 0.30,
        "omega_log_meV": 0.20
      }
    },
    ...
  ]
}
```

---

## Step 1.2: 理解题目与 Workflow

### 任务
在写代码前，先理解题目要求、workflow 结构和可用的 metadata。

### 输出文件
`plan/understanding.md`

### 内容结构

#### 1. 题目理解
对每道题目进行分析：
```markdown
## Problem 1: MgB₂ 电声耦合与 Tc 预测

### 核心任务
从晶体结构出发，计算电声耦合常数 λ 和临界温度 Tc。

### 关键输入
- 材料: MgB₂
- 晶格参数: a = 3.086 Å, c = 3.524 Å
- Coulomb 赝势: μ* = 0.10

### 预期输出
- λ = 0.73 (±30%)
- Tc = 40 K (±50%)
- E2g 频率 = 70.8 meV (±10%)
- E2g 线宽 = 15 meV (±30%)
- ω_log = 60.9 meV (±20%)

### 难点预判
- 需要计算 Hopfield 参数 η
- 需要构建 Eliashberg 函数 α²F(ω)
- 需要正确处理 E2g 模式的主导作用
```

#### 2. Workflow 理解
分析 `workflow_metadata.json`：
```markdown
## Workflow 步骤结构

### S1: 电子结构计算（DFT）
- 输入: 晶体结构
- 输出: N(EF), 能带结构
- 关键方法: DFT-LDA/GGA

### S2: 声子计算（DFPT）
- 输入: 电子基态
- 输出: 声子频率 ω_qν, 声子态密度 F(ω)
- 关键方法: DFPT

### S3: 电声耦合矩阵元
- 输入: 电子波函数 + 声子模式
- 输出: g_qν, λ_qν
- 关键方法: 线性响应理论

### S4: Eliashberg 函数
- 输入: λ_qν, F(ω)
- 输出: α²F(ω)
- 关键公式: α²F(ω) = Σ_qν λ_qν δ(ω - ω_qν)

### S5: 总耦合常数与特征频率
- 输入: α²F(ω)
- 输出: λ, ω_log
- 关键公式: λ = 2∫[α²F(ω)/ω]dω

### S6: Tc 预测
- 输入: λ, ω_log, μ*
- 输出: Tc
- 关键公式: Allen-Dynes 公式

## 数据流
S1 → S2 → S3 → S4 → S5 → S6
     ↓         ↓
     └─────────┘
```

#### 3. Metadata 可用性分析
```markdown
## papers_metadata.json 提供的信息

### 可用参数
- Hopfield 参数: η_Mg = 0.03, η_B = 1.87 (paper 867758380683362769)
- E2g 频率: 70.8 meV (MgB₂), 115 meV (AlMgB₂)
- 形变势: D = 130 meV/pm (paper 812362454112665602)
- Debye 温度: Θ_D = 700 K
- 原子质量: M_Mg = 24.305, M_B = 10.81

### 可用公式
- λ = Σ_α η_α/(M_α × <ω²>) (paper 867758380683362769)
- λ_σ = 2N_σ(E_F) × [ℏ/(2M_B ω²)] × D² (paper 812362454112665602)
- Allen-Dynes: Tc = (ω_log/1.2) × exp[-1.04(1+λ)/(λ-μ*(1+0.62λ))]

## workflow_metadata.json 提供的信息

### 步骤定义
- 6 个主要步骤 (S1-S6)
- 每个步骤的输入输出明确
- 依赖关系清晰

### 方法指导
- DFT: LDA/GGA
- DFPT: 线性响应
- Eliashberg 理论

## 可能缺失的信息

### 高风险缺失
- [ ] 单位转换因子（如 Hopfield 公式中的常数）
- [ ] 声子线宽的计算公式
- [ ] α²F(ω) 的归一化条件

### 中风险缺失
- [ ] 双带材料的处理方法（σ 带 vs π 带）
- [ ] 声子态密度的参数化模型
- [ ] ω_log 的积分方法

### 低风险缺失
- [ ] 具体的数值积分方法
- [ ] 收敛判据
```

---

## Step 1.3: 制定实现计划

### 输出文件
`plan/implementation_plan.md`

### 内容结构

#### 1. 文件结构设计
```markdown
## 代码文件结构

### 主工作流
- `code/workflow.py` - 主类 `SuperconductorWorkflow`
  - 包含 S1-S6 的所有步骤
  - 参数库（MATERIAL_PARAMS, HOPFIELD_ETA 等）
  - 辅助函数

### 测试框架
- `code/test_runner.py` - 测试运行器
  - 加载 test_cases.json
  - 运行工作流
  - 对比结果
  - 生成报告

- `code/run_tests_v1.py` - v1 测试脚本
  - 调用 test_runner
  - 打印版本信息

### 可视化（如需要）
- `code/visualizer.py` - 生成图表
  - 通过率图
  - 失败分析图
  - 领域特定图（如 α²F 曲线）
```

#### 2. 参数化策略
```markdown
## 如何用参数化模型代替完整计算

### S1: 电子结构（查表）
- 不运行 DFT
- 从 papers_metadata 中查表获取 N(EF)
- 对于双带材料，区分 N_σ 和 N_π

### S2: 声子计算（多峰 Lorentzian 模型）
- 不运行 DFPT
- 用 3 峰 Lorentzian 拟合声子态密度
- 参数从 papers_metadata 提取（E2g 频率、声学峰位置）

### S3: 电声耦合（Hopfield 参数方法）
- 不计算矩阵元
- 用 Hopfield 公式: λ = Σ η/(M<ω²>)
- η 从 papers_metadata 查表

### S4: Eliashberg 函数（加权构建）
- 用声子态密度 F(ω) 加权
- 在 E2g 频率附近加强权重
- 归一化: 2∫[α²F/ω]dω = λ

### S5: 积分计算
- 数值积分（梯形法则）
- ω_log = exp[(2/λ)∫(α²F/ω)ln(ω)dω]

### S6: Allen-Dynes 公式
- 直接套用公式
- 注意单位转换（meV → K）
```

#### 3. 实现步骤
```markdown
## 实现顺序

### Phase 1: 基础框架（1-2 小时）
1. 创建 `SuperconductorWorkflow` 类
2. 定义参数库（MATERIAL_PARAMS, HOPFIELD_ETA 等）
3. 实现 S1-S6 的函数签名

### Phase 2: 核心计算（2-3 小时）
1. 实现 S1: 查表获取 N(EF)
2. 实现 S2: Lorentzian 声子态密度
3. 实现 S3: Hopfield λ 计算
4. 实现 S4: α²F 构建
5. 实现 S5: λ 和 ω_log 积分
6. 实现 S6: Allen-Dynes Tc

### Phase 3: 测试框架（1 小时）
1. 实现 test_runner.py
2. 实现 run_tests_v1.py
3. 测试基本功能

### Phase 4: 调试与优化（1-2 小时）
1. 运行测试，查看初步结果
2. 修复明显的 bug
3. 生成 v1 报告
```

#### 4. 依赖的 Metadata
```markdown
## 每个步骤依赖的 Metadata

### S1: 电子结构
- papers_metadata: N(EF) 值
- 对于双带: N_σ, N_π

### S2: 声子计算
- papers_metadata: E2g_frequency_meV
- papers_metadata: 声学峰频率（如有）

### S3: 电声耦合
- papers_metadata: hopfield_parameters (η)
- papers_metadata: 原子质量
- papers_metadata: Debye 温度（用于 <ω²>）

### S4: Eliashberg 函数
- S2 输出: F(ω)
- S3 输出: λ

### S5: 总耦合常数
- S4 输出: α²F(ω)

### S6: Tc 预测
- S5 输出: λ, ω_log
- test_cases: μ*
```

#### 5. 风险与应对
```markdown
## 潜在风险

### 风险 1: 单位转换错误
- 症状: 计算结果数量级错误
- 应对: 从论文数据反推单位转换因子

### 风险 2: 公式理解错误
- 症状: 结果趋势错误
- 应对: 对照论文公式，逐项检查

### 风险 3: Metadata 不足
- 症状: 缺少关键参数
- 应对: 标记为 metadata 缺失，等待迭代补充

### 风险 4: 数值不稳定
- 症状: 除零、负数开方
- 应对: 添加边界检查和默认值
```

---

## 检查清单

完成 Phase 1 后，确认以下内容：

- [ ] 生成了 3 道题目（problem_1.md, problem_2.md, problem_3.md）
- [ ] 生成了 test_cases.json
- [ ] 所有预期输出都从论文原文提取（不是从 papers_metadata 复制）
- [ ] tolerance 设置合理
- [ ] 完成了 understanding.md
- [ ] 完成了 implementation_plan.md
- [ ] 理解了每个步骤的输入输出
- [ ] 识别了可能缺失的 metadata
- [ ] 制定了参数化策略
- [ ] 准备好开始写代码

---

## 下一步

完成本阶段后，进入 **Phase 2: 代码实现与测试**（参见 `02_implement_and_test.md`）
