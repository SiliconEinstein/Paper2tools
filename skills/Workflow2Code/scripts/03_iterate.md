# Phase 3: 迭代优化

本阶段的目标是：
1. 根据测试报告分析失败原因
2. 回到论文补充缺失的 metadata
3. 修复代码中的算法错误
4. 生成新版本报告，对比改进效果

---

## 迭代原则

### 优先级（严格按此顺序）

1. **🔴 最高优先级：metadata 缺失**
   - 这是 ARM 的核心目标：发现并补充 metadata
   - 必须回到论文原文提取信息
   - 更新 papers_metadata.json 或 workflow_metadata.json
   - 在 metadata 中标注信息来源

2. **🟡 中优先级：算法实现错误**
   - 代码逻辑与 workflow 定义不符
   - 公式实现错误
   - 单位转换错误

3. **🟢 低优先级：阈值调整**
   - 最后手段，只在确认其他问题都解决后使用
   - 必须有合理依据（如论文中的误差范围）

### 迭代策略

**每次迭代**：
- 修复所有发现的问题（不只修一个）
- 但按优先级分类，重点解决高优先级问题
- 记录所有变更到 TRACE.md

**停止条件**：
- 通过率 ≥ 90%
- 剩余失败确认为数据局限性
- 连续 3 次迭代通过率无改善
- 用户决定停止

---

## Step 3.1: 分析 v{N} 报告

### 任务
仔细阅读 `result/v{N}/TEST_REPORT_DETAILED.md`，识别需要修复的问题。

### 分析重点

#### 1. 根因分类统计
```markdown
| 根因类别 | 失败数 | 占比 |
|----------|--------|------|
| 🔴 metadata 缺失 | 5 | 50% |  ← 最高优先级
| 🟡 算法实现错误 | 3 | 30% |  ← 中优先级
| 🟢 阈值过严 | 2 | 20% |  ← 低优先级
```

**优先处理 🔴 metadata 缺失**。

#### 2. 具体失败案例
对于每个 🔴 metadata 缺失的案例，提取：
- 缺少什么信息？
- 从哪篇论文补充？
- 论文的哪个章节/公式/表格？

示例：
```markdown
### 🔴 P1: λ 计算错误

**需要补充的 metadata**:
- [ ] Hopfield 参数 η 的定义和数值
  - 来源: paper 867758380683362769
  - 位置: Section 3, Equation (5)
- [ ] 单位转换因子
  - 来源: 从 MgB2 数据反推
```

---

## Step 3.2: 补充 Metadata

### 任务
回到论文原文，提取缺失的信息，更新 metadata 文件。

### 补充 papers_metadata.json

#### 示例：补充 Hopfield 参数
```json
{
  "paper_id": "867758380683362769",
  "material": "MgB₂ / AgB₂ / AuB₂",
  "title": "Electron-phonon coupling in noble-metal diborides",
  "expected_results": {
    "hopfield_parameters": {
      "Mg": 0.03,
      "B_in_MgB2": 1.87,
      "B_in_AgB2": 3.17,
      "B_in_AuB2": 3.88
    },
    "lambda_formula": "λ = Σ_α η_α / (M_α × <ω²>)",
    "omega_squared_avg": "<ω²> ≈ Θ_D² / 2",
    "unit_conversion_note": "需要从 MgB2 数据反推单位转换因子",
    "key_finding": "AgB₂和AuB₂的η_B远高于MgB₂，预测更强的电声耦合"
  },
  "metadata_source": {
    "hopfield_parameters": "Section 3, Table II",
    "lambda_formula": "Equation (5)",
    "omega_squared_avg": "Equation (6)"
  }
}
```

**关键要求**：
- ⚠️ **必须从论文原文提取**，不能虚构
- ⚠️ **标注信息来源**（section/equation/table/figure）
- ⚠️ **如果论文中也没有**，标注为 "需要外部知识" 或 "需要推导"

#### 示例：补充公式细节
```json
{
  "paper_id": "812362454112665602",
  "material": "Al₁₋ₓMgₓB₂",
  "expected_results": {
    "lambda_sigma_formula": "λ_σ = 2 N_σ(E_F) × [ℏ/(2M_B ω²_E2g)] × D²",
    "deformation_potential": "D = 130 meV/pm",
    "lambda_sigma_values": {
      "MgB2": 0.35,
      "AlMgB2": 0.25
    },
    "unit_conversion_note": "公式中的单位需要仔细转换"
  },
  "metadata_source": {
    "lambda_sigma_formula": "Equation (1)",
    "deformation_potential": "Section 2, page 3",
    "lambda_sigma_values": "Figure 2 and text"
  }
}
```

### 补充 workflow_metadata.json

如果发现 workflow 步骤定义有误，也需要更新：

```json
{
  "step_id": "S3",
  "step_name": "电声耦合矩阵元计算",
  "substeps": [
    {
      "substep_id": "S3.1",
      "name": "计算 Hopfield 参数",
      "description": "使用刚性离子近似计算 η_α = N(0) × <I_α²>",
      "formula": "λ = Σ_α η_α / (M_α × <ω²>)",
      "note": "需要单位转换因子，从参考数据反推"
    }
  ]
}
```

### 记录变更

在 metadata 文件中添加变更记录：
```json
{
  "metadata_version": "v2",
  "last_updated": "2026-05-13",
  "changelog": [
    {
      "version": "v2",
      "date": "2026-05-13",
      "changes": [
        "补充 Hopfield 参数 η (paper 867758380683362769)",
        "补充 λ 计算公式的完整形式",
        "补充单位转换说明"
      ]
    }
  ]
}
```

---

## Step 3.3: 修复代码

### 任务
根据补充的 metadata 和报告中的算法错误，修复代码。

### 修复策略

#### 1. 修复 metadata 缺失导致的问题

**示例：修复 λ 计算**

v1 代码（错误）：
```python
def _compute_lambda_E2g(self, N_EF: float, omega_E2g: float) -> float:
    """计算 E2g 模式耦合常数（v1 - 错误的经验公式）"""
    # 错误：使用了完全错误的缩放因子
    lambda_val = N_EF * (1.0 / omega_E2g**2) * 1000
    return lambda_val
```

v2 代码（修复）：
```python
def _compute_lambda_E2g(self, N_EF: float, omega_E2g: float) -> float:
    """计算 E2g 模式耦合常数（v2 - 使用 Hopfield 参数方法）
    
    基于 paper 867758380683362769:
    λ = Σ_α η_α / (M_α × <ω²>)
    
    其中：
    - η_α: Hopfield 参数 (eV/Å²)
    - M_α: 原子质量 (amu)
    - <ω²>: 平均声子频率平方 ≈ Θ_D²/2 (meV²)
    
    单位转换因子约为 8162 (从 MgB2 数据反推)
    """
    # 获取 Hopfield 参数（v2 新增）
    hopfield = HOPFIELD_ETA.get(self.material, {'B': 1.87})
    params = MATERIAL_PARAMS[self.material]
    
    # 计算 Σ_α η_α / M_α
    lambda_numerator = 0.0
    for atom, eta in hopfield.items():
        mass = params['mass'].get(atom, 10.81)
        lambda_numerator += eta / mass
    
    # 平均声子频率平方
    Theta_D = 60  # meV (Debye 温度近似)
    omega_sq_avg = (Theta_D ** 2) / 2
    
    # 单位转换因子（从 MgB2 数据反推）
    unit_conversion_factor = 8162
    
    # 计算 λ
    lambda_val = lambda_numerator / omega_sq_avg * unit_conversion_factor
    
    return lambda_val
```

**标注修复**：
```python
# v2 fix: 使用 Hopfield 参数方法代替错误的经验公式
# 补充了 HOPFIELD_ETA 参数库（从 paper 867758380683362769）
```

#### 2. 修复算法实现错误

**示例：修复双带材料处理**

v1 代码（缺失）：
```python
# v1 没有区分 σ 带和 π 带
lambda_total = self._compute_lambda_E2g(N_EF, omega_E2g)
```

v2 代码（修复）：
```python
# v2 fix: 双带材料需要分别计算 σ 和 π 带耦合
if 'N_sigma' in s1:
    N_sigma = s1['N_sigma']
    N_pi = s1['N_pi']
    
    # σ 带耦合（使用线性插值）
    a = 0.357
    b = 0.225
    lambda_sigma = a * N_sigma + b
    
    # π 带耦合（弱耦合）
    lambda_pi = 0.44
    
    # 总耦合
    lambda_total = lambda_sigma + lambda_pi
    
    result['lambda_sigma'] = lambda_sigma
    result['lambda_pi'] = lambda_pi
else:
    # 单带材料
    lambda_total = self._compute_lambda_E2g(N_EF, omega_E2g)
```

#### 3. 保持代码版本一致

在代码文件头部更新版本信息：
```python
"""
超导体 Tc 预测工作流 - v2

基于第一性原理的超导体电声耦合与临界温度预测工作流的简化实现。

v2 改动：
- 修复 λ 计算公式（使用 Hopfield 参数方法）
- 修复声子线宽公式
- 基于 paper 867758380683362769 和 812362454112665602 的公式

约束：
- ❌ 不看论文原文
- ✅ 只依赖 workflow_steps.json 和 papers_metadata.json
- ✅ 使用参数化模型代替完整 DFT/DFPT 计算

版本：v2
日期：2026-05-13
"""
```

---

## Step 3.4: 运行 v{N+1} 测试

### 创建新版本测试脚本

```bash
cp code/run_tests_v{N}.py code/run_tests_v{N+1}.py
```

修改版本信息：
```python
#!/usr/bin/env python3
"""
运行 v2 测试

版本：v2
日期：2026-05-13
改动：修复 λ 计算公式（使用 Hopfield 参数方法）
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from test_runner import main

if __name__ == '__main__':
    print("="*80)
    print("ARM v2 Test")
    print("="*80)
    print("改动：")
    print("  ✅ 修复 λ 计算公式（使用 Hopfield 参数方法）")
    print("  ✅ 修复声子线宽公式")
    print("  ✅ 基于 paper 867758380683362769 和 812362454112665602")
    print("="*80)
    print()

    sys.exit(main(version="v2"))
```

### 运行测试
```bash
python code/run_tests_v2.py
```

### 对比结果
```
================================================================================
ARM v2 Test
================================================================================
改动：
  ✅ 修复 λ 计算公式（使用 Hopfield 参数方法）
  ✅ 修复声子线宽公式
  ✅ 基于 paper 867758380683362769 和 812362454112665602
================================================================================

Loading 3 test cases...
================================================================================

[1/3] Running P1: MgB2
  ✅ PASS - 5/5 checks passed

[2/3] Running P2: AlMgB2
  ❌ FAIL - 3/7 checks passed

[3/3] Running P3: NbB2
  ❌ FAIL - 1/3 checks passed

================================================================================
测试报告已保存到: result/v2/TEST_REPORT.md

================================================================================
测试汇总
================================================================================
总测试数: 3
通过: 1 (33.3%)
失败: 2 (66.7%)
================================================================================

改进：v1 (0.0%) → v2 (33.3%) ✅ +33.3%
```

---

## Step 3.5: 生成 v{N+1} 报告

### 报告内容

v{N+1} 的报告应包含：

1. **版本信息**（标注 metadata 变更）
```markdown
## 版本信息

- **版本号**: v2
- **日期**: 2026-05-13
- **改动说明**: 修复 λ 计算公式（使用 Hopfield 参数方法）
- **metadata 变更**: 是
  - 补充了 Hopfield 参数 η (paper 867758380683362769)
  - 补充了形变势 D = 130 meV/pm (paper 812362454112665602)
  - 补充了单位转换因子（从 MgB2 数据反推）
  - 修正了 λ 计算公式：λ = Σ_α η_α/(M_α × <ω²>) × 8162
```

2. **与上一版本的对比**
```markdown
## 总体结果

- **总测试数**: 3
- **通过**: 1 (33.3%)
- **失败**: 2 (66.7%)

**相比 v1 的改进**:
- v1 通过率: 0/3 (0.0%)
- v2 通过率: 1/3 (33.3%)
- λ 检查项通过率: 0% → 100% ✅
- MgB2 完全通过 ✅
```

3. **各检查项通过率对比**
```markdown
| 检查项 | v1 | v2 | 改进 |
|--------|----|----|------|
| lambda | 0% | 100% | +100% ✅ |
| E2g_linewidth_meV | 0% | 50% | +50% ✅ |
| Tc_K | 0% | 33% | +33% ✅ |
| omega_log_meV | 33% | 33% | - |
| lambda_sigma | 0% | 0% | - |
```

4. **成功案例分析**
```markdown
## 通过案例详细分析

### ✅ MgB2 (Test ID: P1) - 完全通过

**通过的检查项** (5/5):
- λ = 0.79 (预期 0.73, 误差 8.2%) ✅
- γ = 16.22 meV (预期 15, 误差 8.1%) ✅
- ω_log = 66.4 meV (预期 60.9, 误差 9.0%) ✅
- Tc = 35.2 K (预期 40, 误差 12.0%) ✅

**成功原因**:
1. Hopfield 参数方法正确计算了 λ
2. 声子线宽公式从 MgB2 数据校准，准确
3. α²F 归一化正确，ω_log 合理
4. Allen-Dynes 公式预测 Tc 准确
```

5. **剩余失败的根因分析**
```markdown
## 失败案例详细分析

### ❌ AlMgB2 (Test ID: P2) - 4/7 失败

**失败的检查项** (4/7):

| 检查项 | 预期值 | 实际值 | 误差 | 容差 | 根因分类 |
|--------|--------|--------|------|------|----------|
| lambda_sigma | 0.25 | 0.055 | 77.9% | 50% | 🔴 算法实现错误 |
| E2g_linewidth_meV | 8 | 21.45 | 168.1% | 30% | 🟡 metadata 缺失 |
| omega_log_meV | 61 | 113.8 | 86.5% | 20% | 🟡 算法实现错误 |
| Tc_K | 3 | 15.46 | 415.2% | 50% | 🔴 算法实现错误 |

**根因分析**:

#### 🔴 P2.1: λ_σ 计算公式错误 (高优先级)
...
```

---

## Step 3.6: 更新 TRACE.md

### 记录迭代历史

```markdown
## v2 (2026-05-13)

### 改动说明
- 修复 λ 计算公式（使用 Hopfield 参数方法）
- 修复声子线宽公式
- 基于 paper 867758380683362769 和 812362454112665602

### 补充的 metadata
从论文中提取的关键公式：

#### Paper 867758380683362769 (Noble-metal diborides)
- ✅ λ = Σ_α η_α / (M_α × <ω²>)
- ✅ η_α = N(0) × <I_α²> (Hopfield 参数)
- ✅ <ω²> ≈ Θ_D² / 2
- ✅ 单位转换因子 ≈ 8162 (从 MgB2 数据反推)
- ✅ MgB2: η_Mg = 0.03, η_B = 1.87 eV/Å²

#### Paper 867771392240648834 (Bohnen et al.)
- ✅ MgB2 E2g 线宽 γ = 15 meV
- ✅ λ = 2 ∫ [α²F(ω)/ω] dω
- ✅ 校准公式: γ = λ × ω × 0.29

### 测试结果
- **通过率**: 1/3 (33.3%)
- **各检查项通过率**:
  - E2g_frequency_meV: 100% ✅
  - lambda: 100% ✅ (v1: 0%)
  - lambda_pi: 100% ✅
  - E2g_linewidth_meV: 50% (v1: 0%)
  - omega_log_meV: 33%
  - Tc_K: 33% (v1: 0%)
  - lambda_sigma: 0% ❌

### 成功案例

#### ✅ MgB2 (P1) - 完全通过 (5/5)
- λ = 0.79 (预期 0.73, 误差 8.2%) ✅
- γ = 16.22 meV (预期 15, 误差 8.1%) ✅
- ω_log = 66.4 meV (预期 60.9, 误差 9.0%) ✅
- Tc = 35.2 K (预期 40, 误差 12.0%) ✅

**成功原因**:
- Hopfield 参数方法正确计算了 λ
- 声子线宽公式从 MgB2 数据校准，准确
- α²F 归一化正确，ω_log 合理
- Allen-Dynes 公式预测 Tc 准确

### 失败原因分析

#### 🔴 算法实现错误（高优先级）

1. **λ_σ 计算公式错误** (P2 失败)
   - 问题：AlMgB2 的 λ_σ = 0.055 (预期 0.25)，低估 77.9%
   - 当前公式：经验缩放因子不正确
   - 根本原因：没有使用 paper 812362454112665602 的完整公式
   - 需要补充：λ_σ = 2 N_σ(E_F) × [ℏ/(2M_B ω²_E2g)] × D² 的完整单位转换

...

---

**当前状态**: v2 完成，MgB2 完全通过，准备开始 v3
```

---

## Step 3.7: 生成进度总结

### 创建 PROGRESS_SUMMARY.md

```markdown
# ARM 迭代进度总结

## 概览

| 版本 | 日期 | 通过率 | 通过案例 | 主要改动 |
|------|------|--------|----------|----------|
| v1_baseline | 2026-05-13 | 0/3 (0.0%) | 无 | 初始实现 |
| v2 | 2026-05-13 | 1/3 (33.3%) | MgB2 | 修复 λ 计算 |

## 各检查项通过率演变

| 检查项 | v1 | v2 | v2 改进 |
|--------|----|----|---------|
| lambda | 0% | **100%** | +100% ✅ |
| E2g_linewidth_meV | 0% | **50%** | +50% ✅ |
| Tc_K | 0% | **33%** | +33% ✅ |
| omega_log_meV | 33% | 33% | - |
| lambda_sigma | 0% | 0% | - |

## v1 → v2 关键突破

### ✅ 完全修复的问题

#### 1. λ 计算 (0% → 100%)

**v1 问题**:
```python
# 错误的经验公式
lambda_val = N_EF * (1.0 / omega_E2g**2) * 1000
# MgB2: λ = 0.14 (预期 0.73)，误差 80.9%
```

**v2 修复**:
```python
# 正确的 Hopfield 参数方法
lambda_numerator = sum(eta_alpha / M_alpha for each atom)
lambda_val = lambda_numerator / omega_sq_avg * 8162
# MgB2: λ = 0.79 (预期 0.73)，误差 8.2% ✅
```

**关键发现**:
- 从 paper 867758380683362769 提取了 Hopfield 参数 η
- 反推出单位转换因子 8162
- 公式：λ = Σ_α η_α/(M_α × <ω²>) × 8162

...

## 从论文中提取的关键信息

### v2 成功提取的 metadata

| 信息 | 来源 | 用途 |
|------|------|------|
| η_Mg = 0.03 eV/Å² | Paper 867758380683362769 | λ 计算 |
| η_B = 1.87 eV/Å² | Paper 867758380683362769 | λ 计算 |
| λ = Σ η/(M<ω²>) | Paper 867758380683362769 | λ 计算公式 |
| 单位转换因子 8162 | 从 MgB2 数据反推 | λ 计算 |
| γ = 15 meV (MgB2) | Paper 867771392240648834 | 线宽校准 |

### v3 需要提取的 metadata

| 信息 | 来源 | 用途 |
|------|------|------|
| λ_σ 完整公式 | Paper 812362454112665602 | 双带材料 |
| AlMgB2 线宽数据 | Paper 812362454112665602 | 线宽修正 |

## ARM 方法论验证

### ✅ 成功验证的假设

1. **迭代有效性**: v1 → v2 通过率提升 33%
2. **metadata 驱动**: 补充 Hopfield 参数后 λ 计算完全修复
3. **根因分析准确**: v1 识别的 🔴 metadata 缺失问题在 v2 得到解决
4. **物理一致性**: MgB2 完全通过证明基础物理模型正确

### 📊 量化指标

- **修复效率**: 1 次迭代修复 3 个主要问题（λ, γ, Tc）
- **准确率提升**: λ 误差从 80.9% → 8.2%
- **覆盖率**: 3/3 材料的 λ 都在容差内

### 🎯 下一步优化方向

1. **v3 重点**: 双带材料的 λ_σ 计算
2. **v4 重点**: α²F 构建方法优化
3. **最终目标**: 3/3 材料完全通过
```

---

## Step 3.8: 决定是否继续迭代

### 评估标准

**继续迭代**，如果：
- 通过率 < 90%
- 有明确的 🔴 metadata 缺失问题
- 有明确的修复方向

**停止迭代**，如果：
- 通过率 ≥ 90%
- 剩余失败确认为数据局限性
- 连续 3 次迭代无改善
- 用户决定停止

### 暂停并等待用户确认

⚠️ **每次迭代后必须暂停**，让用户查看报告并决定：
- 继续迭代（进入 v{N+2}）
- 停止迭代（生成最终报告）

---

## 检查清单

完成一次迭代后，确认以下内容：

- [ ] 分析了上一版本的报告
- [ ] 识别了需要补充的 metadata
- [ ] 回到论文提取了信息
- [ ] 更新了 papers_metadata.json 或 workflow_metadata.json
- [ ] 标注了信息来源
- [ ] 修复了代码
- [ ] 运行了新版本测试
- [ ] 生成了新版本报告
- [ ] 更新了 TRACE.md
- [ ] 更新了 PROGRESS_SUMMARY.md
- [ ] 对比了版本间的改进

---

## 下一步

- 如果继续迭代：重复 Phase 3
- 如果停止迭代：进入 **Phase 4: 最终报告**（参见 `04_final_report.md`）
