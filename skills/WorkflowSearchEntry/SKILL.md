---
name: workflow-search-entry
description: Workflow库检索入口型Skill。用于在“研究问题已可检索”时，指导agent调用现有Step3检索代码，输出候选workflow与下一步建议（是否进入链库检索）。
language: zh-CN
---

# WorkflowSearchEntry: Workflow 库检索入口

## 这个 Skill 做什么

这是一个**入口编排 Skill**，不是算法实现本体。  
作用是告诉 agent：

1. 在什么时机触发 workflow 检索；
2. 应执行哪些现有代码/命令；
3. 如何把检索结果组织成可决策输出（继续复用 workflow，或建议进入链库检索）。

---

## 触发时机（必须满足）

满足以下条件时使用本 Skill：

- 用户给出研究问题，且问题已达到最小门槛：
  - 已明确**研究对象**；
  - 已明确**研究目标**；
- 用户希望先判断“是否有现成 workflow 可复用”。

若问题仍然粗糙（对象/目标缺失），先使用 `QuestionRefiner` 类 Skill 做澄清，再回到本 Skill。

---

## 执行顺序

### Step 0: 前置检查

1. 确认配置文件存在：`configs/step3_config.yaml`
2. 确认 workflow 索引目录是否存在（配置中的 `index_building.index_dir`）
3. 如果索引不存在，先执行 build：

```bash
python -m src.main --step 3 --action build_index --config configs/step3_config.yaml
```

### Step 1: 执行 workflow 检索

```bash
python -m src.main --step 3 --action search --config configs/step3_config.yaml --query "<研究问题>" --top-k 20
```

> 可选：若用户限定领域，加 `--domain <domain>`。

### Step 2: 结果整理（给用户看的证据简报）

至少输出：

- Top 3 workflow 名称
- 每个 workflow 的匹配要点（来自 score/match details/stages）
- 每个 workflow 的明显缺口（如果有）

### Step 3: 下一步判定建议

按检索结果给出建议：

- **strong**：建议复用现有 workflow；
- **borderline/weak**：建议进入思维链向量库检索（调用 `ChainSearchEntry`）。

注意：这里是入口 Skill，不强制在本 Skill 内实现 LLM 三分类器；若项目内有独立判定模块，调用该模块；否则给出基于候选质量的人工判断建议。

---

## 输出约定（给上游编排器）

建议输出结构：

```json
{
  "stage": "workflow_search",
  "query": "<refined_query>",
  "top_workflows": [
    {
      "workflow_id": "...",
      "workflow_name": "...",
      "score": 0.82,
      "match_points": ["..."],
      "gaps": ["..."]
    }
  ],
  "recommendation": "use_workflow | go_chain_search",
  "reason": "..."
}
```

---

## 失败与降级

- 检索命令失败：返回错误摘要 + 建议重试一次；
- workflow 候选为空：直接建议进入 `ChainSearchEntry`；
- 索引构建失败：返回明确错误，不要编造结果。

