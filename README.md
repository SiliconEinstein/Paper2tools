# Paper2tools

学术论文推理步骤深度分析工具（paper2tools_v2）

## 项目概述

paper2tools_v2 是一个独立的分析工具，专注于学术论文中推理步骤的语义理解、工具关联和工作流总结。

### 核心功能

- **Step1: 文本向量化与语义聚类** - 对推理步骤进行向量化并按语义相似度聚类
- **Step2: 工具信息注入** - 在 reasoning_chain XML 中为每个推理步骤补充关联的工具信息
- **Step3: 工作流总结** - 基于增强后的数据总结典型工作流模式

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 运行示例

```bash
# 运行 Step1: 文本向量化与聚类
python -m src.main --step 1 --config configs/step1_config.yaml

# 运行 Step2: 工具信息注入
python -m src.main --step 2 --config configs/step2_config.yaml

# 运行 Step3: 工作流总结
python -m src.main --step 3 --config configs/step3_config.yaml

# 运行全部步骤
python -m src.main --step all
```

## 项目结构

```
paper2tools_v2/
├── src/
│   ├── step1/          # Step1: 文本向量化与聚类
│   ├── step2/          # Step2: 工具信息注入
│   ├── step3/          # Step3: 工作流总结
│   ├── common/         # 共享工具模块
│   └── main.py         # CLI 主入口
├── tests/              # 单元测试
├── data/               # 数据目录
│   ├── input/          # 输入数据
│   ├── step1_output/   # Step1 输出
│   ├── step2_output/   # Step2 输出
│   └── step3_output/   # Step3 输出
├── configs/            # 配置文件
└── notebooks/          # Jupyter notebooks
```

## 数据流

```
输入数据 (data/input/)
  ├─ reasoning_chain.xml
  └─ _tools_extract_result.json
       ↓
Step1: 向量化与聚类
  └─→ step_embeddings.npy, clusters.json
       ↓
Step2: 工具信息注入
  └─→ reasoning_chain.enriched.xml
       ↓
Step3: 工作流总结
  └─→ workflows.json, workflow_stats.json
```

## 配置

每个步骤都有独立的配置文件：

- `configs/step1_config.yaml` - Step1 配置（向量化模型、聚类算法等）
- `configs/step2_config.yaml` - Step2 配置（匹配策略、置信度阈值等）
- `configs/step3_config.yaml` - Step3 配置（聚合策略、输出格式等）

## 测试

```bash
# 运行所有测试
pytest tests/

# 运行特定模块测试
pytest tests/test_step1/
pytest tests/test_step2/
pytest tests/test_step3/
```

## 开发指南

### 模块职责

- **step1/vectorizer.py** - 封装多种 embedding 模型
- **step1/clustering.py** - 实现聚类算法
- **step2/tool_matcher.py** - 工具与步骤的匹配逻辑
- **step2/xml_enricher.py** - XML 增强器
- **step3/workflow_extractor.py** - 从单篇论文提取 workflow
- **step3/workflow_aggregator.py** - 跨论文聚合 workflow

### 代码风格

- 使用 `pathlib.Path` 处理文件路径
- 所有批处理操作打印进度信息
- 函数和类都要有清晰的 docstring

## 文档

- `.claude/CLAUDE.md` - 项目经验法则和架构设计
- `.claude/TRACE.md` - 开发过程日志

## License

MIT
