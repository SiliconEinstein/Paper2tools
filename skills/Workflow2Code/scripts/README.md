# Workflow2Code Scripts

本目录包含 Workflow2Code skill 的执行脚本，按照 ARM 流程的 4 个阶段组织。

---

## 脚本列表

### Phase 1: 生成测试题目与复现计划
**文件**: `01_generate_problems_and_plan.md`

**任务**:
1. 从 papers_metadata.json 随机选择 3 篇论文
2. 读取论文 markdown，生成测试题目
3. 理解题目、workflow 和 metadata
4. 制定代码实现计划

**输出**:
- `dataset/problems/problem_{1,2,3}.md`
- `dataset/test_cases.json`
- `plan/understanding.md`
- `plan/implementation_plan.md`

---

### Phase 2: 代码实现与测试
**文件**: `02_implement_and_test.md`

**任务**:
1. 根据 implementation_plan.md 实现代码
2. 创建测试运行器
3. 运行 v1 测试
4. 生成测试报告和可视化

**输出**:
- `code/workflow.py` (及其他代码文件)
- `code/test_runner.py`
- `code/run_tests_v1.py`
- `result/v1_baseline/TEST_REPORT.md`
- `result/v1_baseline/TEST_REPORT_DETAILED.md`
- `result/v1_baseline/*.png`
- `trace/TRACE.md`

---

### Phase 3: 迭代优化
**文件**: `03_iterate.md`

**任务**:
1. 分析测试报告，识别失败原因
2. 回到论文补充 metadata
3. 修复代码
4. 运行 v{N+1} 测试
5. 生成新版本报告

**输出**:
- 更新的 `papers_metadata.json` 和/或 `workflow_metadata.json`
- 更新的 `code/workflow.py`
- `code/run_tests_v{N+1}.py`
- `result/v{N+1}/TEST_REPORT*.md`
- 更新的 `trace/TRACE.md`
- `report/PROGRESS_SUMMARY.md`

**注意**: 每次迭代后暂停，等待用户确认。

---

### Phase 4: 最终报告
**文件**: `04_final_report.md`

**任务**:
1. 生成可读性强的完整过程报告
2. 总结 metadata 发现和经验教训
3. 归档整个 ARM 过程

**输出**:
- `report/ARM_Notebook.md`
- `information/lessons_learned.md`

---

## 执行顺序

```
01_generate_problems_and_plan.md
    ↓
02_implement_and_test.md
    ↓
03_iterate.md  ←─┐
    ↓            │
  [用户确认]     │
    ↓            │
  继续迭代? ─────┘
    ↓ 否
04_final_report.md
```

---

## 使用方法

### 方式 1: 手动执行（推荐用于学习）

按顺序阅读每个脚本文件，手动执行其中的步骤。

### 方式 2: 通过 Skill 调用（推荐用于生产）

```bash
# 在项目根目录
/workflow2code <workflow_dir>
```

Skill 会自动执行所有阶段，并在每次迭代后暂停等待确认。

---

## 关键原则

1. **不作弊**: 代码生成时不得查看论文原文
2. **metadata 优先**: 优先修复 metadata 缺失问题
3. **完整性**: 代码必须完整可运行，不能有 TODO
4. **可读性**: 报告要面向人类读者
5. **版本管理**: 每个版本独立目录，不覆盖旧版本

---

## 相关文档

- `../SKILL.md` - Workflow2Code skill 的完整说明
- `../../Workflower/SKILL.md` - 工作流提取 skill（前置步骤）
