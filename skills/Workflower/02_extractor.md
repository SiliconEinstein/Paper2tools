---
name: workflower-extractor
description: 深度阅读论文并提取3层信息，支持并行处理多篇论文（优化原03）
language: zh-CN
---

# 02 深度提取器

## 功能概述

**优化原 03_deep_reader**

深度阅读 A-主线论文的 XML 和 MD，提取算法层和实现层信息。

**优化点**：
- **并行处理**：自动将论文列表分批，并行启动多个 subagent
- **智能批次划分**：根据论文数量自动决定批次大小
- **进度追踪**：每批完成后立即写入，支持断点续传

## 输入要求

| 文件 | 必须 | 说明 |
|------|------|------|
| `chain_classification.json` | 是 | 从中获取 A-主线论文列表 |
| `paper_mapping.json` | 是 | **新增**：论文元数据映射（用于嵌入 short_name 和 title） |
| `md/` 目录 | 是 | 论文原文 markdown（需要读 Methods 部分） |
| `xml/` 目录 | 是 | 论文完整推理链 XML（所有 conclusions） |

## 输出产物

| 文件 | 格式 | 说明 |
|------|------|------|
| `paper_extractions.yaml` | YAML | 每篇论文一个 YAML 块，包含双层提取 |
| `.extraction_progress.json` | JSON | 进度追踪（隐藏文件，用于断点续传） |

## 关键约束

1. **语言**：所有描述性字段使用中文
2. **必须读 Methods**：不能只依赖 chain_text
3. **未提及即记录**：论文未提及的维度记录为"未提及"
4. **定量优先**：优先提取具体数值
5. **并行友好**：支持多批次并行处理

## 执行步骤

### Step 1: 确定待提取论文列表

从 `chain_classification.json` 中筛选：
- grade="A" 且 subtype="主线"
- 去重后得到论文 ID 列表

**加载 paper_mapping.json**：
```python
paper_mapping = load_json("paper_mapping.json")
# 用于在 YAML 中嵌入 short_name 和 title
```

### Step 2: 检查断点续传

```python
if exists(".extraction_progress.json"):
    已完成论文 = load_progress()
    待处理论文 = 全部论文 - 已完成论文
else:
    待处理论文 = 全部论文
```

### Step 3: 智能批次划分（并行优化）

```python
论文总数 = len(待处理论文)

if 论文总数 <= 3:
    批次数 = 1
    批次大小 = 论文总数
elif 论文总数 <= 8:
    批次数 = 2
    批次大小 = ceil(论文总数 / 2)
elif 论文总数 <= 15:
    批次数 = 3
    批次大小 = ceil(论文总数 / 3)
else:
    批次数 = 4
    批次大小 = ceil(论文总数 / 4)

批次列表 = split_into_batches(待处理论文, 批次大小)
```

**示例**：
- 13 篇论文 → 3 批（5, 4, 4）
- 20 篇论文 → 4 批（5, 5, 5, 5）

### Step 4: 并行处理（核心优化）

```python
for batch_id, batch_papers in enumerate(批次列表):
    # 启动 subagent 处理该批次
    subagent_prompt = f"""
    深度提取以下论文的信息：
    {batch_papers}
    
    对每篇论文：
    1. 读取 xml/{paper_id}_*.xml（所有 conclusions）
    2. 读取 md/{paper_id}.md（重点：Methods 部分）
    3. 提取算法层信息（核心公式、机制细节、方法族）
    4. 提取实现层信息（9个维度）
    5. 提取定量结果
    6. 列出工具和缺口
    
    输出 YAML 格式。
    """
    
    启动 Agent(
        subagent_type="general-purpose",
        prompt=subagent_prompt,
        run_in_background=True  # 并行执行
    )

# 等待所有批次完成
等待所有 subagent 完成()

# 合并结果
合并所有批次的 YAML 到 paper_extractions.yaml
```

**预期加速**：
- 13 篇论文，3 批并行 → 理论加速 **3倍**
- 实际加速约 **2-2.5倍**（考虑启动开销）

### Step 5: 算法层提取（从 XML）

读取完整 XML（该论文**所有** conclusions），提取：

| 字段 | 说明 |
|------|------|
| `core_formula` | 核心算法/公式，**所有符号必须有定义** |
| `mechanism_detail` | 方法的具体机制——**精确到子步骤** |
| `method_family` | 所属方法族 |

**精确性要求**：
- 不能停留在一句话概括
- 必须展开到可执行的子步骤
- 公式符号必须定义

### Step 6: 实现层提取（从 MD Methods）

在 `md/{paper_id}.md` 中搜索 Methods 部分，提取 9 个维度：

| 维度 | 要提取的信息 |
|------|-------------|
| **输入预处理与 QC** | 缺失值处理、异常值过滤、归一化、数据清洗 |
| **标识符协调** | 不同数据源之间的 ID/名称/编码映射规则 |
| **外部资源规格** | 数据库/知识库的名称、版本、子集选择、过滤条件 |
| **领域特定偏差控制** | 针对该领域已知偏差的处理 |
| **统计校准：null 模型** | null 模型类型 |
| **统计校准：多重检验** | 多重检验校正方法 |
| **内部验证** | 交叉验证、held-out、ablation |
| **外部验证** | 独立数据集、跨机构/跨时间泛化 |
| **计算环境** | 硬件、运行时间、并行策略 |

**领域特异性展开**：
- 材料科学：晶体结构格式、DFT 基组、烧结条件
- 基因组学：gene ID 映射、text-mining 偏差
- NLP：tokenizer 一致性、label 分布偏差

### Step 7: 定量结果提取

从论文中提取具体数值：
- 性能指标（精度、误差、相关系数）
- 关键参数值
- 与基线的对比数据

### Step 8: 工具列表和缺口标注

- **tools**：论文中使用的工具/仪器/软件列表
- **gaps_noted**：论文未报告的维度列表，格式为"未提及 X"

### Step 9: 进度保存（断点续传）

每批完成后立即保存：

```json
{
  "completed_papers": ["paper_id_1", "paper_id_2"],
  "total_papers": 13,
  "last_update": "2026-04-27T20:30:00Z"
}
```

## 输出格式

### paper_extractions.yaml

```yaml
---
# cluster_N 论文深度提取

- paper_id: "812491390918328320"
  short_name: "Zhang_2023"
  title: "BaTiO3 基铁电陶瓷的位点选择性掺杂策略"
  bibitem_key: "Zhang2023"
  algorithm_layer:
    core_formula: >-
      位点选择性掺杂：Ce³⁺ 占据 Ba 位（A 位），Ce⁴⁺ 占据 Ti 位（B 位）；
      Raman 820-840 cm⁻¹ 谱带强度 ∝ Ce³⁺ A 位含量；
      XPS O 1s 卫星峰/主峰比值指示氧空位浓度
    mechanism_detail: >-
      合成（前驱体控制）→ Raman 光谱识别占位（820-840 cm⁻¹ 谱带用于 A 位 Ce³⁺）
      → XPS 分析氧化态和空位 → XRD Rietveld 精修测相比例
      → 性能测量（电卡效应、电致伸缩）→ 占位-性能关联
    method_family: "多技术联合占位表征"
  implementation_layer:
    input_qc: "高纯度 BaCO3、TiO2、CeO2 前驱体；1000°C 煅烧 4h；1320-1360°C 烧结 3h"
    id_mapping: "空间群：P4mm（四方）、Amm2（正交）、Pm-3m（立方）"
    external_resource_spec: "Shannon 离子半径表（配位数相关）；JCPDS 卡片（未提及具体编号）"
    domain_bias_control: "空气气氛烧结；极化条件：A 位 3-5 kV/mm 120°C，B 位 80°C"
    null_model: "未提及"
    multiple_testing: "未提及"
    internal_validation: "多个组分（x=0.02, 0.04, 0.06）；Rietveld 精修 Rw 因子"
    external_validation: "与 La³⁺、Nd³⁺、Eu³⁺ A 位掺杂文献对比"
    compute_env: "XRD: Cu Kα；Raman: 532 nm 激光；XPS: Al Kα 源"
  quantitative_results:
    - "A 位掺杂（BT-A-0.06）：ΔT_max=1.3K，37-70°C 范围"
    - "B 位掺杂（BT-B-0.06）：电致伸缩应变 S>0.17%，滞后 <5%"
    - "四方度（c/a）随 A 位掺杂降低；B 位掺杂晶格膨胀"
  tools:
    - "X 射线衍射仪（含 Rietveld 精修）"
    - "拉曼光谱仪"
    - "X 射线光电子能谱仪（XPS）"
    - "扫描电子显微镜（SEM）"
    - "透射电子显微镜（TEM）"
    - "阻抗分析仪"
    - "铁电测试仪"
  gaps_noted:
    - "未提及直接占位证据（中子衍射、EXAFS）"
    - "未提及样品批次间重复性"
    - "未提及统计误差分析"
    - "电卡效应采用间接法（Maxwell 关系）而非直接测温"
```

## 并行处理示例

### 场景：13 篇论文

```
批次划分：
- Batch 1: papers 1-5  (5篇)
- Batch 2: papers 6-9  (4篇)
- Batch 3: papers 10-13 (4篇)

并行执行：
[Batch 1 Agent] ─┐
[Batch 2 Agent] ─┼─→ 等待所有完成 ─→ 合并 YAML
[Batch 3 Agent] ─┘

时间对比：
- 串行：13篇 × 3分钟 = 39分钟
- 并行：max(5, 4, 4)篇 × 3分钟 = 15分钟
- 加速：2.6倍
```

## 性能优化总结

| 优化项 | 原方案（串行） | 新方案（并行） | 改善 |
|--------|--------------|---------------|------|
| 13篇论文处理时间 | 39分钟 | 15分钟 | **-62%** |
| 20篇论文处理时间 | 60分钟 | 15分钟 | **-75%** |
| 支持断点续传 | 否 | 是 | ✅ |
| 进度可见性 | 低 | 高 | ✅ |

## 验证清单

- [ ] paper_extractions.yaml 存在
- [ ] 包含所有 A-主线论文的提取
- [ ] **每篇论文都有 paper_id, short_name, title, bibitem_key 字段**
- [ ] 每篇论文都有 algorithm_layer 和 implementation_layer
- [ ] 描述字段使用中文
- [ ] 公式符号都有定义
- [ ] mechanism_detail 精确到子步骤
- [ ] 未提及的维度标注为"未提及"
- [ ] quantitative_results 包含具体数值
- [ ] gaps_noted 非空
- [ ] 并行处理正确合并结果
- [ ] **short_name 与 paper_mapping.json 一致**
