# paper2tools_v2 过程日志

> 记录项目开发过程中遇到的问题、做出的决策、变更记录。具体事件写这里，提炼出的判断准则归入 `CLAUDE.md`。

---

## 2026-04-21

### 项目初始化 - 框架搭建

**背景**: 新建 paper2tools_v2 项目，独立于 paper2tools，用于学术论文推理步骤的深度分析。

**决策**:
1. **项目独立性**: 与 paper2tools 完全解耦，不复用代码，只消费其输出数据
2. **三步骤架构**:
   - Step1: 推理步骤文本 → 向量化 → 语义聚类
   - Step2: reasoning_chain XML + 工具信息 → 增强 XML
   - Step3: 增强数据 → 典型工作流总结
3. **模块化设计**: 每个 Step 独立目录，共享功能放 `common/`
4. **测试优先**: 每个模块都预留对应的测试文件

**输入数据格式**（来自 paper2tools）:
- `reasoning_chain.xml`: 包含 `<conclusion_reasoning>` → `<reasoning>` → `<step id="N">` 结构
- `_tools_extract_result.json`: 包含 `tools[]`（工具列表）和 `ptlink[]`（工具链）
- 新 Schema 中 tools 有 `var[]` 版本粒度结构，ptlink 有 `prereq[]` + `compute[]`

**创建的文件**: 完整项目框架，包括：
- 源码文件（src/ 下 17 个 Python 文件）
- 测试文件（tests/ 下 14 个 Python 文件）
- 配置文件（configs/ 下 3 个 YAML 文件）
- 项目文件（README.md, requirements.txt, .gitignore）
- 文档文件（.claude/CLAUDE.md, .claude/TRACE.md）
