# Phase 2: 代码实现与测试

本阶段的目标是：
1. 根据 implementation_plan.md 实现代码
2. 运行测试，生成 v1 报告
3. 分析失败原因，为迭代做准备

---

## Step 2.1: 代码实现

### 约束条件（严格遵守）

**❌ 禁止事项**：
- 不得查看论文原文（markdown 文件）
- 不得根据预期输出反推参数
- 不得硬编码测试用例的数值
- 不得写 TODO 占位符

**✅ 允许事项**：
- 使用 workflow_metadata.json 和 papers_metadata.json
- 使用参数化模型代替完整计算
- 从 metadata 中查表获取参数
- 添加合理的默认值和边界检查

### 代码质量要求

#### 1. 文档注释
```python
def step3_electron_phonon_coupling(self, input_data: Dict, s1: Dict, s2: Dict) -> Dict:
    """S3: 电声耦合矩阵元计算（简化：Hopfield 参数）
    
    基于 paper 867758380683362769 的 Hopfield 参数方法计算总耦合常数 λ。
    
    公式：λ = Σ_α η_α / (M_α × <ω²>) × unit_factor
    
    Args:
        input_data: 用户输入（如 mu_star）
        s1: Step 1 输出（N_EF）
        s2: Step 2 输出（声子频率、态密度）
    
    Returns:
        {
            'lambda_E2g': float,  # 总耦合常数
            'E2g_linewidth_meV': float,  # 声子线宽
            'hopfield_eta_B': float,  # B 原子的 Hopfield 参数
            ...
        }
    """
```

#### 2. 参数来源标注
```python
# Hopfield 参数（从 paper 867758380683362769）
HOPFIELD_ETA = {
    'MgB2': {'Mg': 0.03, 'B': 1.87},
    'AlMgB2': {'Al': 0.05, 'Mg': 0.03, 'B': 1.5},  # 估计
}

# E2g 模式频率（从 papers_metadata.json）
E2G_FREQUENCIES = {
    'MgB2': 70.8,      # meV (paper 867771392240648834)
    'AlB2': 125.0,     # meV
}
```

#### 3. 单位转换说明
```python
# 单位转换因子（从 MgB2 数据反推）
# 对于 MgB2: λ = 0.79
# (η_Mg/M_Mg + η_B/M_B) = 0.1742 eV/amu/Å²
# <ω²> = 1800 meV²
# factor = 0.79 × 1800 / 0.1742 ≈ 8162
unit_conversion_factor = 8162
```

#### 4. 错误处理
```python
# 检查分母是否为零
if denominator <= 0:
    return 0.0  # 无超导

# 检查数组越界
if len(omega_grid) == 0:
    raise ValueError("omega_grid is empty")
```

### 实现步骤

#### Step 1: 创建主工作流类
```python
class SuperconductorWorkflow:
    """超导体 Tc 预测工作流（简化版本）"""
    
    def __init__(self, material: str, config: Optional[Dict] = None):
        self.material = material
        self.config = config or {}
        self.results = {}
        
        # 检查材料是否支持
        if material not in MATERIAL_PARAMS:
            raise ValueError(f"Material {material} not supported")
    
    def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """运行完整工作流（S1-S6）"""
        s1 = self.step1_electronic_structure(input_data)
        s2 = self.step2_phonon_calculation(input_data)
        s3 = self.step3_electron_phonon_coupling(input_data, s1, s2)
        s4 = self.step4_eliashberg_function(input_data, s2, s3)
        s5 = self.step5_coupling_constants(input_data, s3, s4)
        s6 = self.step6_Tc_prediction(input_data, s5)
        
        # 合并所有结果
        self.results = {**s1, **s2, **s3, **s4, **s5, **s6}
        return self.results
```

#### Step 2: 实现各个步骤
按照 implementation_plan.md 中的顺序实现 S1-S6。

#### Step 3: 创建测试运行器
```python
# code/test_runner.py
import json
from pathlib import Path
from workflow import run_workflow

def load_test_cases(test_file: Path) -> dict:
    """加载测试用例"""
    with open(test_file) as f:
        return json.load(f)

def run_single_test(test_case: dict) -> dict:
    """运行单个测试"""
    material = test_case['material']
    input_data = test_case['input']
    expected = test_case['expected_output']
    tolerance = test_case['tolerance']
    
    # 运行工作流
    result = run_workflow(material, input_data)
    
    # 对比结果
    checks = {}
    for key, expected_val in expected.items():
        actual_val = result.get(key)
        if actual_val is None:
            checks[key] = {'status': 'missing', 'error': None}
        else:
            error = abs(actual_val - expected_val) / expected_val
            tol = tolerance.get(key, 0.3)
            checks[key] = {
                'status': 'pass' if error <= tol else 'fail',
                'expected': expected_val,
                'actual': actual_val,
                'error': error,
                'tolerance': tol
            }
    
    return checks

def main(version: str = "v1"):
    """主测试函数"""
    # 加载测试用例
    test_file = Path(__file__).parent.parent / 'dataset' / 'test_cases.json'
    test_data = load_test_cases(test_file)
    
    # 运行所有测试
    results = []
    for test_case in test_data['test_cases']:
        print(f"Running {test_case['test_id']}: {test_case['material']}...")
        checks = run_single_test(test_case)
        results.append({
            'test_id': test_case['test_id'],
            'material': test_case['material'],
            'checks': checks
        })
    
    # 生成报告
    generate_report(results, version)
    
    return 0 if all_passed(results) else 1
```

#### Step 4: 创建版本化测试脚本
```python
# code/run_tests_v1.py
#!/usr/bin/env python3
"""
运行 v1 测试

版本：v1
日期：{YYYY-MM-DD}
改动：初始实现，使用参数化模型
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from test_runner import main

if __name__ == '__main__':
    print("="*80)
    print("ARM v1 Test - Baseline")
    print("="*80)
    print("改动：")
    print("  ✅ 初始实现")
    print("  ✅ 基于 workflow_metadata 和 papers_metadata")
    print("  ✅ 使用参数化模型")
    print("="*80)
    print()
    
    sys.exit(main(version="v1_baseline"))
```

---

## Step 2.2: 运行测试

### 执行测试
```bash
cd code/
python run_tests_v1.py
```

### 预期输出
```
================================================================================
ARM v1 Test - Baseline
================================================================================
改动：
  ✅ 初始实现
  ✅ 基于 workflow_metadata 和 papers_metadata
  ✅ 使用参数化模型
================================================================================

Loading 3 test cases...
================================================================================

[1/3] Running P1: MgB2
  ❌ FAIL - 2/5 checks passed

[2/3] Running P2: AlMgB2
  ❌ FAIL - 1/7 checks passed

[3/3] Running P3: NbB2
  ❌ FAIL - 0/3 checks passed

================================================================================
测试报告已保存到: result/v1_baseline/TEST_REPORT.md
================================================================================
```

**注意**：v1 通常会有较多失败，这是正常的。我们的目标是发现 metadata 的不足。

---

## Step 2.3: 生成测试报告

### 报告生成逻辑

#### 1. 简要报告（TEST_REPORT.md）
```python
def generate_simple_report(results: list, version: str, output_dir: Path):
    """生成简要测试报告"""
    
    # 统计通过率
    total = len(results)
    passed = sum(1 for r in results if all_checks_passed(r))
    
    # 统计各检查项通过率
    check_stats = calculate_check_stats(results)
    
    # 生成 Markdown
    report = f"""# 测试报告 - {version}

## 版本信息

- **版本号**: {version}
- **日期**: {datetime.now().strftime('%Y-%m-%d')}
- **改动说明**: 初始实现，使用参数化模型
- **metadata 变更**: 否

## 总体结果

- **总测试数**: {total}
- **通过**: {passed} ({passed/total*100:.1f}%)
- **失败**: {total-passed} ({(total-passed)/total*100:.1f}%)

## 各检查项通过率

| 检查项 | 通过/总数 | 通过率 |
|--------|----------|--------|
"""
    
    for check_name, stats in check_stats.items():
        report += f"| {check_name} | {stats['passed']}/{stats['total']} | {stats['rate']:.1f}% |\n"
    
    # 失败案例
    report += "\n## 失败案例详细分析\n\n"
    for result in results:
        if not all_checks_passed(result):
            report += format_failure_case(result)
    
    # 通过案例
    report += "\n## 通过案例\n\n"
    for result in results:
        if all_checks_passed(result):
            report += f"- {result['material']} (Test ID: {result['test_id']})\n"
    
    # 写入文件
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / 'TEST_REPORT.md').write_text(report)
```

#### 2. 详细报告（TEST_REPORT_DETAILED.md）
包含简要报告的所有内容，额外增加：

**根因分析**：
```markdown
## 根本原因分类统计

| 根因类别 | 失败数 | 占比 | 严重程度 | 修复优先级 |
|----------|--------|------|----------|------------|
| 🔴 metadata 缺失 | 5 | 50% | 高 | P1 |
| 🟡 算法实现错误 | 3 | 30% | 中 | P2 |
| 🟢 阈值过严 | 2 | 20% | 低 | P3 |

## 失败案例根因分析

### 🔴 P1: λ 计算错误

**现象**: λ = 0.14 (预期 0.73)，低估 80.9%

**根本原因**: 
- 当前使用的经验公式不正确
- papers_metadata 中缺少 Hopfield 参数 η 的完整计算方法
- 缺少单位转换因子

**需要补充的 metadata**:
- [ ] Hopfield 参数 η 的定义和数值（从 paper 867758380683362769）
- [ ] λ = Σ η/(M<ω²>) 的完整公式
- [ ] 单位转换因子的推导

**修复方向**:
- 回到 paper 867758380683362769 提取 Hopfield 参数
- 从 MgB2 数据反推单位转换因子
- 更新 papers_metadata.json

...
```

**修复建议**：
```markdown
## 修复建议

### v2 计划（高优先级 - 修复 metadata 缺失）

**目标**: 补充 Hopfield 参数和 λ 计算公式

**需要回到论文补充的信息**:

#### Paper 867758380683362769 (Noble-metal diborides)
- [ ] Hopfield 参数 η 的定义
- [ ] MgB2: η_Mg = ?, η_B = ?
- [ ] λ = Σ η/(M<ω²>) 的完整公式
- [ ] <ω²> 的计算方法（Debye 近似？）

#### Paper 867771392240648834 (Bohnen et al.)
- [ ] 声子线宽 γ 的计算公式
- [ ] MgB2 E2g 线宽的实验值

**预期改进**:
- λ 通过率: 0% → 100%
- 总通过率: 0% → 33% (1/3)
```

#### 3. 可视化图表

**通过率图**（pass_rate_chart.png）：
```python
import matplotlib.pyplot as plt

def plot_pass_rate(results: list, output_dir: Path):
    """绘制通过率柱状图"""
    
    # 统计数据
    check_stats = calculate_check_stats(results)
    
    # 绘图
    fig, ax = plt.subplots(figsize=(10, 6))
    
    check_names = list(check_stats.keys())
    pass_rates = [stats['rate'] for stats in check_stats.values()]
    
    bars = ax.bar(check_names, pass_rates, color='steelblue')
    
    # 标注数值
    for bar, rate in zip(bars, pass_rates):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{rate:.1f}%',
                ha='center', va='bottom')
    
    ax.set_ylabel('Pass Rate (%)')
    ax.set_title('v1 Baseline - Check Item Pass Rate')
    ax.set_ylim(0, 110)
    ax.grid(axis='y', alpha=0.3)
    
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    plt.savefig(output_dir / 'pass_rate_chart.png', dpi=150)
    plt.close()
```

**失败原因分布图**（failure_root_cause.png）：
```python
def plot_failure_root_cause(root_causes: dict, output_dir: Path):
    """绘制失败原因分布饼图"""
    
    labels = list(root_causes.keys())
    sizes = list(root_causes.values())
    colors = ['#ff6b6b', '#feca57', '#48dbfb', '#1dd1a1']
    
    fig, ax = plt.subplots(figsize=(8, 8))
    
    wedges, texts, autotexts = ax.pie(
        sizes, labels=labels, colors=colors,
        autopct='%1.1f%%', startangle=90
    )
    
    ax.set_title('v1 Baseline - Failure Root Cause Distribution')
    
    plt.tight_layout()
    plt.savefig(output_dir / 'failure_root_cause.png', dpi=150)
    plt.close()
```

---

## Step 2.4: 更新 TRACE.md

### 记录 v1 结果
```markdown
# ARM 迭代追踪日志

**工作流**: 超导体 Tc 预测  
**Cluster**: 627  
**开始日期**: {YYYY-MM-DD}

---

## v1_baseline ({YYYY-MM-DD})

### 改动说明
- 初始实现，使用参数化模型
- 不看论文原文，只依赖 workflow_metadata.json 和 papers_metadata.json

### 测试结果
- **通过率**: 0/3 (0.0%)
- **各检查项通过率**:
  - E2g_frequency_meV: 100% ✅
  - lambda_pi: 100% ✅
  - omega_log_meV: 33%
  - E2g_linewidth_meV: 0% ❌
  - lambda: 0% ❌
  - Tc_K: 0% ❌

### 失败原因分析

#### 🔴 metadata 缺失（高优先级）

1. **λ 计算公式错误** (P1, P2, P3 全部失败)
   - 问题：使用了完全错误的经验缩放因子
   - 实际值：MgB2 λ=0.14 (预期 0.73)，误差 80.9%
   - 根本原因：metadata 中没有提供 λ 的完整计算公式
   - 需要补充：
     - McMillan-Hopfield 参数 η 的正确计算
     - λ = η / (M <ω²>) 的完整公式
     - <ω²> 的计算方法

2. **声子线宽公式缺少参数** (P1, P2 失败)
   - 问题：γ_E2g 低估约 75%
   - 实际值：MgB2 γ=3.8 meV (预期 15 meV)
   - 根本原因：公式的单位和缩放因子错误
   - 需要补充：正确的单位转换和物理常数

...

---

**当前状态**: v1 完成，准备开始 v2
```

---

## 检查清单

完成 Phase 2 后，确认以下内容：

- [ ] 代码完整可运行（无 TODO）
- [ ] 所有步骤都有 docstring
- [ ] 参数来源有标注
- [ ] 单位转换有说明
- [ ] 测试运行成功（即使失败率高）
- [ ] 生成了 TEST_REPORT.md
- [ ] 生成了 TEST_REPORT_DETAILED.md
- [ ] 生成了可视化图表
- [ ] 更新了 TRACE.md
- [ ] 根因分析完整（每个失败都有分类）
- [ ] 修复建议明确（列出需要补充的 metadata）

---

## 下一步

完成本阶段后，**暂停并等待用户确认**。

用户查看报告后，如果决定继续迭代，进入 **Phase 3: 迭代优化**（参见 `03_iterate.md`）
