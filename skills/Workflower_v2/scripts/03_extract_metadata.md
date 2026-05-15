# 阶段三：交织式提取元数据

**目标**：结合推理链和原始论文，交织生成 `workflow_metadata.json` 和 `papers_metadata.json`。

**前置条件**：阶段二已完成（已确定选中的链和论文）

---

## 关键规则

1. **步骤来自推理链**（研究者做了什么）
2. **方法/工具来自论文**（如何做的）
3. **交织生成**：先从链中提取步骤框架，再从论文中填充每个步骤的具体方法/工具/参数
4. **严禁虚构**原始材料中未出现的细节
5. **要具体**（不得使用"标准方法"等通用占位符）
6. **⚠️ 必须添加 paper_refs**：在 `workflow_metadata` 顶层记录所有相关论文的 ID 列表（溯源）

---

## 生成流程（5 轮迭代）

### 第一轮：从推理链提取步骤框架

#### 输入
- 阶段二输出（selected_chains）

#### 操作

1. **撰写工作流描述**
   - 该工作流**解决什么问题**（问题导向性）
   - 工作流的核心目标是什么
   - 示例：✅ "用于 [具体目标] 的系统性工作流，解决如何 [问题描述] 的问题"

2. **提取核心步骤序列**
   - 从选中的链中识别公共步骤
   - 记录每个步骤的 `frequency`（出现在多少条链中）
   - 标记 `is_required`（是否为必需步骤，通常 frequency ≥80% 为必需）

3. **识别步骤依赖关系**
   - 哪些步骤必须先完成？
   - 数据如何在步骤间流转？

4. **提取判断节点**（如有）
   - 什么条件触发分支？
   - 各分支做什么？

#### 输出（第一轮）
```json
{
  "workflow_metadata": {
    "title": "{工作流标题}",
    "description": "用于 {目标} 的工作流，解决如何 {问题} 的问题",
    "domain": "{领域}",
    "source_papers": {论文数},
    "core_chains": [{链ID列表}],
    "paper_refs": ["{所有相关论文ID列表}"]
  },
  "workflow_steps": [
    {
      "step_id": "S1",
      "step_name": "{步骤名称}",
      "description": "{步骤描述}",
      "frequency": "N/M",
      "is_required": true,
      "required_tools": {},  // 待填充
      "substeps": []  // 待填充
    }
  ]
}
```

---

### 第二轮：从论文中提取每个步骤的方法与工具

#### 输入
- 第一轮输出（步骤框架）
- 原始论文 Markdown 文件

#### 操作

对每个步骤，逐篇阅读论文的相关章节：

1. **识别硬件工具**
   - 该步骤用到什么设备？（具体型号、规格）
   - 示例：`["电阻测量系统", "磁场系统（超导磁体/脉冲磁体）"]`

2. **识别软件工具**
   - 用到什么数据采集/分析软件？
   - 示例：`["数据采集程序", "拟合软件"]`

3. **识别分析方法**
   - 该步骤采用什么方法？（具体算法、公式）
   - 示例：`["四端法", "等温场扫描", "幂律拟合"]`

4. **记录典型参数范围**
   - 该步骤的参数通常在什么范围？
   - 示例：`"typical_field_range": "0-15 T"`

#### 输出（第二轮）
```json
{
  "step_id": "S1",
  "required_tools": {
    "hardware": ["{设备1}", "{设备2}"],
    "software": ["{软件1}"],
    "methods": ["{方法1}", "{方法2}"]
  },
  "typical_parameters": {
    "{参数名}": "{典型范围}"
  }
}
```

---

### 第三轮：细化子步骤

#### 输入
- 第二轮输出（含方法/工具的步骤）
- 推理链（细节）

#### 操作

对每个步骤，从推理链中提取子步骤：

1. **识别子操作**
   - 该步骤可分解为哪些子操作？
   - 每个子操作的 `frequency` 是多少？

2. **提取公式/算法**
   - 子步骤涉及的数学公式
   - 示例：`"formula": "MR = [ρ(H)-ρ(0)]/ρ(0)"`

3. **记录变体**
   - 该子步骤有哪些常见变体？
   - 示例：`"variants": ["Δρ/ρ₀", "(ρ_H-ρ₀)/ρ₀"]`

#### 输出（第三轮）
```json
{
  "substeps": [
    {
      "substep_id": "S1.1",
      "name": "{子步骤名称}",
      "description": "{描述}",
      "frequency": "N/M",
      "formula": "{公式}",
      "variants": ["{变体1}", "{变体2}"]
    }
  ]
}
```

---

### 第四轮：构建知识库（如适用）

#### 输入
- 前三轮输出
- 论文中的理论模型/机制讨论

#### 操作

若工作流包含"机制归因"或"模型选择"步骤：

1. **提取理论模型**
   - 论文中提到了哪些理论模型？
   - 每个模型的特征签名是什么？

2. **记录判断依据**
   - 如何根据实验结果选择模型？
   - 示例：`"signature": {"mr_sign": "positive", "field_dependence": "quadratic"}`

3. **提取关键词**
   - 每个模型的关键词（用于文本匹配）

#### 输出（第四轮）
```json
{
  "mechanism_models": [
    {
      "model_id": "M1",
      "name": "{模型名称}",
      "name_en": "{英文名}",
      "signature": {
        "{特征1}": "{值1}",
        "{特征2}": "{值2}"
      },
      "keywords": ["{关键词1}", "{关键词2}"]
    }
  ]
}
```

---

### 第五轮：生成 papers_metadata.json

#### 输入
- 完整的 workflow_metadata.json
- 原始论文

#### 操作

现在已知工作流的所有步骤和方法，逐篇提取论文级参数：

1. **材料属性**
   - 材料化学式、相变温度等

2. **实验参数**
   - 该论文在每个步骤使用的具体参数值
   - 示例：`"field_max_T": 14.0`

3. **预期结果**
   - 该论文的实验结论（用于测试验证）
   - 示例：`"expected_field_dependence": "quadratic"`

4. **实验方法细节**
   - 该论文使用的具体硬件型号、分析方法参数

5. **⚠️ ARM 环境配置信息（新增）**
   - **计算环境**：DFT/DFPT 代码、版本、编译选项
   - **依赖库**：数值库（BLAS/LAPACK/FFTW）、并行库（MPI/OpenMP）
   - **计算参数**：k点网格、截断能、收敛标准、赝势类型
   - **运行环境**：Python 版本、必需的 Python 包及版本
   - **硬件要求**：内存、CPU 核数、GPU（如需要）

#### 输出（第五轮）
```json
{
  "environment": {
    "description": "ARM 包的运行环境配置",
    "python_version": "3.9+",
    "required_packages": [
      {"name": "numpy", "version": ">=1.21.0"},
      {"name": "scipy", "version": ">=1.7.0"},
      {"name": "matplotlib", "version": ">=3.4.0"}
    ],
    "optional_packages": [
      {"name": "ase", "version": ">=3.22.0", "purpose": "原子结构操作"},
      {"name": "pymatgen", "version": ">=2022.0.0", "purpose": "材料分析"}
    ],
    "computational_tools": {
      "dft_codes": [
        {
          "name": "Quantum ESPRESSO",
          "version": "6.8+",
          "purpose": "DFT 电子结构计算",
          "typical_parameters": {
            "ecutwfc": "40-80 Ry",
            "k_points": "12x12x12 to 24x24x24",
            "conv_thr": "1e-8"
          }
        },
        {
          "name": "VASP",
          "version": "5.4+",
          "purpose": "DFT 结构优化",
          "typical_parameters": {
            "ENCUT": "400-600 eV",
            "KPOINTS": "Gamma-centered Monkhorst-Pack"
          }
        }
      ],
      "analysis_tools": [
        {
          "name": "EPW",
          "version": "5.4+",
          "purpose": "电声耦合计算",
          "dependencies": ["Quantum ESPRESSO", "Wannier90"]
        }
      ]
    },
    "hardware_requirements": {
      "min_memory_gb": 16,
      "recommended_memory_gb": 64,
      "min_cores": 8,
      "recommended_cores": 32,
      "gpu_required": false,
      "disk_space_gb": 50
    },
    "notes": "环境配置基于论文中报告的计算方法汇总，实际需求取决于材料体系大小"
  },
  "papers": [
    {
      "paper_id": "{论文ID}",
      "material": "{材料}",
      "{工作流参数1}": {值1},
      "{工作流参数2}": {值2},
      "expected_results": {
        "{结果1}": "{预期值1}"
      },
      "experimental_methods": {
        "hardware": {
          "{设备类型}": {
            "model": "{型号}",
            "{规格}": {值}
          }
        },
        "analysis_methods": {
          "{方法名}": {
            "{参数}": {值}
          }
        }
      },
      "computational_setup": {
        "dft_code": "{使用的 DFT 代码}",
        "xc_functional": "{交换关联泛函}",
        "pseudopotential": "{赝势类型}",
        "k_points": "{k点网格}",
        "q_points": "{q点网格（DFPT）}",
        "cutoff_energy": "{截断能}",
        "smearing": "{展宽方法和参数}",
        "convergence_criteria": {
          "energy": "{能量收敛标准}",
          "force": "{力收敛标准（如适用）}"
        }
      }
    }
  ]
}
```

---

## 质量检查

### workflow_metadata.json
- [ ] `description` 明确说明解决什么问题
- [ ] 每个步骤有 `frequency` 和 `is_required`
- [ ] 每个步骤的 `required_tools` 具体（非通用占位符）
- [ ] 子步骤包含 `formula`、`variants`（如适用）
- [ ] 机制模型有明确的 `signature` 和 `keywords`（如适用）
- [ ] **⚠️ 顶层 `workflow_metadata` 有 `paper_refs` 字段（包含所有相关论文 ID）**

### papers_metadata.json
- [ ] 所有参数值来自论文（非假设）
- [ ] `expected_results` 与论文结论一致
- [ ] `experimental_methods` 包含具体型号/参数
- [ ] **⚠️ 顶层有 `environment` 字段（ARM 环境配置）**
- [ ] **⚠️ `environment.python_version` 已指定**
- [ ] **⚠️ `environment.required_packages` 列表非空**
- [ ] **⚠️ `environment.computational_tools` 包含论文中使用的 DFT/分析工具**
- [ ] **⚠️ `environment.hardware_requirements` 已填写**
- [ ] 每篇论文有 `computational_setup` 字段（如为计算类工作流）

### 溯源完整性检查
- [ ] **`workflow_metadata.paper_refs` 中的所有论文 ID 都存在于 `papers_metadata.json` 中**
- [ ] **`paper_refs` 列表非空**

### ARM 可复现性检查（新增）
- [ ] **环境配置信息完整**：agent 能根据 `environment` 字段搭建运行环境
- [ ] **依赖版本明确**：所有必需包都有版本约束（>=, ==, ~=）
- [ ] **计算参数可追溯**：每篇论文的 `computational_setup` 能对应到 `environment.computational_tools` 中的工具
- [ ] **硬件需求合理**：`hardware_requirements` 基于论文报告的计算规模估算

---

## 下一步

生成两个文件后，使用 **Workflow2Code** Skill 进行代码实现和测试验证。
