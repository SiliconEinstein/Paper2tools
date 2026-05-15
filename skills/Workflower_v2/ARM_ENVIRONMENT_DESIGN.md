# ARM 环境配置设计说明

## 目标

为了支持 **ARM (Agent-Ready Manuscript)** 规范，`papers_metadata.json` 需要包含完整的环境配置信息，使 agent 能够：

1. **理解运行环境**：知道需要什么 Python 版本、依赖包、计算工具
2. **搭建环境**：根据 `environment` 字段自动安装依赖
3. **配置工具**：根据 `computational_setup` 设置计算参数
4. **复现结果**：使用与论文相同的计算设置

## 设计原则

### 1. 分层设计

```
environment (顶层)
├── python_version          # Python 运行时
├── required_packages       # 必需的 Python 包
├── optional_packages       # 可选的 Python 包
├── computational_tools     # DFT/DFPT/分析工具
│   ├── dft_codes          # 第一性原理计算代码
│   ├── analysis_tools     # 电声耦合/Wannier 等工具
│   └── post_processing    # 后处理脚本
└── hardware_requirements   # 硬件需求估算

papers[i].computational_setup (论文级)
├── dft_code               # 该论文使用的 DFT 代码
├── xc_functional          # 交换关联泛函
├── pseudopotential        # 赝势类型
├── k_points               # k 点网格
├── q_points               # q 点网格（DFPT）
├── cutoff_energy          # 截断能
├── smearing               # 展宽方法
└── convergence_criteria   # 收敛标准
```

### 2. 通用 vs 特定

- **通用配置** (`environment`)：适用于整个工作流的环境
  - Python 版本、依赖包、工具列表
  - 典型参数范围（如 "ecutwfc: 40-80 Ry"）
  
- **特定配置** (`papers[i].computational_setup`)：每篇论文的具体设置
  - 实际使用的参数值（如 "ecutwfc: 16 Ry"）
  - 可追溯到论文原文

### 3. 版本约束

所有依赖包必须有版本约束：
- `>=1.21.0`：最低版本要求
- `==1.21.0`：精确版本（不推荐，除非有兼容性问题）
- `~=1.21.0`：兼容版本（1.21.x）

### 4. 目的说明

每个包/工具都应说明用途：
```json
{
  "name": "numpy",
  "version": ">=1.21.0",
  "purpose": "数值计算"
}
```

## 字段说明

### environment.python_version

- **格式**：`"3.9+"` 或 `">=3.9,<4.0"`
- **来源**：基于工作流使用的 Python 特性（如 type hints、walrus operator）

### environment.required_packages

- **必需包**：运行工作流代码必须安装的包
- **示例**：numpy, scipy, matplotlib
- **来源**：代码中的 `import` 语句

### environment.optional_packages

- **可选包**：增强功能但非必需的包
- **示例**：ase（结构可视化）、pymatgen（材料分析）
- **用途**：提供额外的分析能力或可视化

### environment.computational_tools

#### dft_codes

- **DFT 计算代码**：Quantum ESPRESSO, VASP, ABINIT 等
- **版本**：基于论文报告的版本或推荐版本
- **模块**：列出使用的可执行文件（如 pw.x, ph.x）
- **典型参数**：汇总论文中的参数范围

#### analysis_tools

- **分析工具**：EPW（电声耦合）、Wannier90（Wannier 函数）等
- **依赖**：列出依赖的其他工具
- **典型参数**：常用的参数设置

#### post_processing

- **后处理工具**：自定义脚本、数据分析工具
- **用途**：Eliashberg 函数分析、Tc 预测等

### environment.hardware_requirements

- **min_memory_gb**：最低内存需求
- **recommended_memory_gb**：推荐内存
- **min_cores**：最低 CPU 核数
- **recommended_cores**：推荐 CPU 核数
- **gpu_required**：是否需要 GPU
- **disk_space_gb**：磁盘空间需求
- **notes**：额外说明（如 HPC 集群推荐）

### papers[i].computational_setup

每篇论文的具体计算设置：
- **dft_code**：使用的 DFT 代码
- **xc_functional**：交换关联泛函（LDA, GGA-PBE 等）
- **pseudopotential**：赝势类型和来源
- **k_points**：k 点网格（如 "36x36x36"）
- **q_points**：q 点网格（DFPT）
- **cutoff_energy**：截断能（Ry 或 eV）
- **smearing**：展宽方法和参数
- **convergence_criteria**：收敛标准

## 提取策略

### 从论文中提取

1. **Methods 章节**：
   - DFT 代码和版本
   - 交换关联泛函
   - 赝势类型
   - k/q 点网格
   - 截断能
   - 收敛标准

2. **Computational Details 章节**：
   - 具体参数值
   - 计算资源（CPU 核数、内存）

3. **Supporting Information**：
   - 详细的输入文件
   - 完整的参数列表

### 汇总策略

1. **收集所有论文的参数**：
   - 列出每篇论文使用的工具和参数

2. **识别共性**：
   - 哪些工具被多篇论文使用？
   - 参数范围是什么？

3. **填充 environment**：
   - `computational_tools.dft_codes`：列出所有使用的 DFT 代码
   - `typical_parameters`：汇总参数范围

4. **填充 computational_setup**：
   - 每篇论文的具体参数值

## 质量检查

### 完整性检查

- [ ] `environment` 字段存在且非空
- [ ] `python_version` 已指定
- [ ] `required_packages` 列表非空
- [ ] `computational_tools.dft_codes` 包含论文中使用的所有 DFT 代码
- [ ] `hardware_requirements` 所有字段已填写

### 一致性检查

- [ ] 每篇论文的 `computational_setup.dft_code` 存在于 `environment.computational_tools.dft_codes` 中
- [ ] 论文的具体参数值在 `environment` 的典型范围内

### 可追溯性检查

- [ ] 所有参数值可在论文中找到依据
- [ ] 版本号基于论文报告或合理推断
- [ ] 硬件需求基于论文报告的计算规模

## 示例

参见 `examples/papers_metadata_with_environment.json`

## 使用场景

### Scenario 1: Agent 搭建环境

```python
# 读取 papers_metadata.json
with open('papers_metadata.json') as f:
    metadata = json.load(f)

env = metadata['environment']

# 检查 Python 版本
required_version = env['python_version']  # "3.9+"
current_version = sys.version_info
# ... 版本检查逻辑

# 安装依赖包
for pkg in env['required_packages']:
    subprocess.run(['pip', 'install', f"{pkg['name']}{pkg['version']}"])

# 检查 DFT 代码
for dft_code in env['computational_tools']['dft_codes']:
    # 检查是否安装
    # 输出配置建议
```

### Scenario 2: Agent 配置计算参数

```python
# 读取特定论文的计算设置
paper = metadata['papers'][0]
setup = paper['computational_setup']

# 生成 Quantum ESPRESSO 输入文件
qe_input = f"""
&control
  calculation = 'scf'
/
&system
  ecutwfc = {parse_cutoff(setup['cutoff_energy'])}
/
&electrons
  conv_thr = {setup['convergence_criteria']['energy']}
/
K_POINTS automatic
{parse_kpoints(setup['k_points'])}
"""
```

### Scenario 3: Agent 验证环境

```python
# 验证环境是否满足要求
def verify_environment(metadata):
    env = metadata['environment']
    
    # 检查 Python 版本
    check_python_version(env['python_version'])
    
    # 检查依赖包
    for pkg in env['required_packages']:
        check_package_installed(pkg['name'], pkg['version'])
    
    # 检查 DFT 代码
    for dft_code in env['computational_tools']['dft_codes']:
        check_dft_code_installed(dft_code['name'], dft_code['version'])
    
    # 检查硬件资源
    check_hardware(env['hardware_requirements'])
    
    return True  # 或抛出异常
```

## 未来扩展

### 容器化支持

未来可以基于 `environment` 字段自动生成：
- **Dockerfile**：构建包含所有依赖的 Docker 镜像
- **Singularity recipe**：HPC 环境的容器
- **conda environment.yml**：Conda 环境配置

### 自动化测试

基于 `computational_setup` 自动生成测试用例：
- 验证参数是否在合理范围内
- 检查计算是否收敛
- 对比结果与 `expected_results`

### 性能优化建议

基于 `hardware_requirements` 提供优化建议：
- k 点并行化策略
- MPI 进程数配置
- 内存优化建议
