---
name: workflower-llm
description: 高性能版 Workflower：两阶段流程，Phase 1 快速分析 + Phase 2/3 深度提取与生成
language: zh-CN
---

# Workflower_LLM: 高性能工作流提取系统

## 架构说明（优化版）

### 两阶段流程

**Stage 1: 快速分析（仅基于 selected_chains.json）**
- Phase 1a: 快速分析器 - 识别工作流主线、分类推理链、推荐深度阅读论文
- 输入：`selected_chains.json`（推理链文本）
- 输出：`chain_classification.json`, `workflow_structure.json`, `workflow_meta.json`, `paper_mapping.json`, `paper_inventory.md`
- 耗时：~30秒

**Stage 2: 深度提取与生成（仅读取推荐论文）**
- Phase 2: 并行提取器 - 仅提取 A-主线论文的详细信息
- Phase 3: 并行生成器 - 生成 LaTeX 综述、决策树、3层文档
- 输入：Phase 1a 输出 + 推荐论文的 MD/XML
- 输出：`paper_extractions.yaml`, `review_cluster_N.pdf`, `decision_tree.png`, `workflow_3layer.md`
- 耗时：~2-3分钟

| 阶段 | 执行方式 | 输入 | 耗时 |
|------|---------|------|------|
| Phase 1a: 快速分析 | LLM API 并行（2个调用） | selected_chains.json | ~30秒 |
| Phase 2: 提取器 | LLM API 并行（N篇论文） | A-主线论文 MD/XML | ~1-2分钟 |
| Phase 3: 生成器 | LLM API 并行（章节+决策树） | Phase 1/2 输出 | ~1-2分钟 |

## 输入结构

```
cluster_N/
├── selected_chains.json      # Phase 1 输入
├── xml/                      # Phase 1 输入
├── md/                       # Phase 1 输入
├── chain_classification.json # Phase 1 输出 → Phase 2 输入
├── paper_mapping.json        # Phase 1 输出 → Phase 2/3 输入
├── workflow_structure.json   # Phase 1 输出 → Phase 3 输入
├── workflow_meta.json        # Phase 1 输出 → Phase 3 输入
├── paper_extractions.yaml   # Phase 2 输出 → Phase 3 输入
└── ...
```

## 执行流程

### Phase 1a: 快速分析器（新增）

```bash
cd <cluster_dir>
python /personal/paper2tools_v2/skills/Workflower_LLM/01_fast_analyzer.py .
```

**内部流程**：
1. 读取 `selected_chains.json`（仅推理链文本，不读 MD）
2. 构建推理链摘要（最多50条，每条800字符）
3. 并行调用 LLM API（2个调用）：
   - 工作流分析：识别核心阶段、分类推理链（A/B/C + 主线/变体/边缘）
   - 论文元数据：从推理链引用中提取作者、年份、标题
4. 生成输出文件：
   - `chain_classification.json`: 推理链分类结果
   - `workflow_structure.json`: 核心阶段定义
   - `workflow_meta.json`: 工作流元信息 + 推荐深度阅读论文列表
   - `paper_mapping.json`: 论文元数据
   - `paper_inventory.md`: 论文清单（标记推荐阅读）

**输出示例**：
```json
{
  "workflow_name": "DOM分子量表征",
  "research_problem": "如何通过分子量/尺寸分级表征DOM组成...",
  "recommended_deep_read": ["paper_id1", "paper_id2", ...]  // 最多5篇
}
```

### Phase 2: 并行提取器（优化）

```bash
cd <cluster_dir>
python /personal/paper2tools_v2/skills/Workflower_LLM/02_extractor.py .
```

**内部流程**：
1. 读取 `chain_classification.json` 获取 A-主线论文列表
2. **仅为 A-主线论文**构建独立 prompt（chain_text + Methods 摘要）
3. `asyncio.gather` 并行调用 LLM API
4. 解析 YAML 响应，合并写入 `paper_extractions.yaml`
5. 支持断点续传（`.extraction_progress.json`）

**优化点**：只提取 A-主线论文（通常 10-20 篇），不再处理所有论文

**输出**：`paper_extractions.yaml`

### Phase 3: 并行生成器（无变化）

```bash
cd <cluster_dir>
python /personal/paper2tools_v2/skills/Workflower_LLM/03_writer.py .
```

**内部流程**：
1. 读取所有 Phase 1/2 输出文件
2. 并行生成（一次 `asyncio.gather`）：
   - 引言章节
   - 每个阶段章节（含彩色框）
   - 结论章节
   - 决策树 DOT 代码
   - 3层工作流文档
3. Agent 负责：
   - 拼装完整 LaTeX（preamble + 各章节 + 参考文献）
   - `dot -Tpng -Gdpi=150` 渲染决策树
   - `xelatex` 两遍编译 PDF
   - 清理编译产物

**输出**：`workflow_3layer.md`, `review_cluster_N.tex`, `decision_tree.dot`, `decision_tree.png`, `review_cluster_N.pdf`

## 完整执行示例

```bash
CLUSTER_DIR=/personal/paper2tools_v2/data/environmental_science/workflows/cluster_100

# Phase 1a: 快速分析（~30秒）
python /personal/paper2tools_v2/skills/Workflower_LLM/01_fast_analyzer.py $CLUSTER_DIR

# 检查 workflow_meta.json 中的 recommended_deep_read 列表
# 如果工作流主线清晰且推荐论文合理，继续 Phase 2/3

# Phase 2: LLM 并行提取 A-主线论文（~1-2 分钟）
python /personal/paper2tools_v2/skills/Workflower_LLM/02_extractor.py $CLUSTER_DIR

# Phase 3: LLM 并行生成综述与决策树（~1-2 分钟）
python /personal/paper2tools_v2/skills/Workflower_LLM/03_writer.py $CLUSTER_DIR
```

**总耗时**：~3-5 分钟/cluster（Phase 1a: 30秒 + Phase 2: 1-2分钟 + Phase 3: 1-2分钟）

## 优化效果对比

| 版本 | Phase 1 | Phase 2 | Phase 3 | 总耗时 | 说明 |
|------|---------|---------|---------|--------|------|
| 原版 Workflower | Agent 读 50 MD | Agent 串行提取 | Agent 串行生成 | 10-20 分钟 | 全部由 Agent 处理 |
| Workflower_LLM v1 | Agent 读 50 MD | LLM 并行提取 | LLM 并行生成 | 5-8 分钟 | Phase 2/3 并行化 |
| **Workflower_LLM v2** | **LLM 快速分析** | **LLM 并行提取** | **LLM 并行生成** | **2-3 分钟** | **Phase 1 不读 MD** |

**实测数据（cluster_100, 50条链, 14篇A-主线论文）**：
- Phase 1a: 61秒（快速分析，不读 MD）
- Phase 2: 24秒（并行提取 14 篇论文）
- Phase 3: 53秒（并行生成 5 个阶段 + 决策树 + 编译 PDF）
- **总计: 138秒 (2分18秒)**

**关键优化**：
1. ✅ Phase 1a 不读取任何 MD 文件，仅基于 `selected_chains.json` 中的推理链文本
2. ✅ Phase 2 仅提取 A-主线论文（14篇 vs 原来的 50篇）
3. ✅ 所有 LLM 调用都是并行的（asyncio.gather）
4. ✅ 中文字体正确渲染（AR PL UMing CN）
5. ✅ 决策树图片高分辨率（DPI=150）+ 自适应页面尺寸

## 环境要求

`.env` 文件需包含：
```
GPUGEEK_API_KEY=<your_key>
GPUGEEK_API_BASE=<api_base_url>
```

依赖：
```bash
pip install openai httpx tenacity python-dotenv pyyaml
```

## 质量保证

Phase 2 和 Phase 3 的 LLM prompt 均包含明确的格式约束：
- 所有描述字段使用中文
- 禁止"详见原文"等占位文本
- 每个阶段末尾必须有彩色框
- 引言必须包含决策树图片
- 参考文献由 Agent 从 `paper_mapping.json` 直接生成（不经过 LLM，避免幻觉）

## 文件说明

| 文件 | 说明 |
|------|------|
| `llm_client.py` | LLM 客户端（自包含，读取 .env） |
| `02_extractor.py` | Phase 2 并行提取脚本 |
| `03_writer.py` | Phase 3 并行生成脚本 |
