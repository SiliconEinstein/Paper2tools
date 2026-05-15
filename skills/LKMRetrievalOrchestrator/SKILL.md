---
name: lkm-retrieval-orchestrator
description: LKM检索总编排入口Skill。负责把问题澄清、workflow库检索、链库检索串成可测试流程，并明确阶段切换条件。
language: zh-CN
---

# LKMRetrievalOrchestrator: 检索总入口

## 目标

用于测试端到端流程时的一站式入口编排：

1. 问题澄清
2. Workflow 库检索
3. 判定是否进入链库检索
4. 输出可用于 workflow 抽取的候选链集合

---

## 编排规则

### 阶段 1：问题澄清

先调用 `QuestionRefiner`：

- 若研究对象 + 研究目标已满足，先生成中英文问题与关键词包；
- 必须向用户展示英文版与关键词，并完成确认/补充；
- 仅当 `user_confirmed=true` 时才进入阶段 2；
- 否则继续澄清，最多 4 轮；
- 若用户拒绝补充，低置信继续并加告警。

### 阶段 2：workflow 检索

调用 `WorkflowSearchEntry`，拿到候选 workflow 摘要与建议。

### 阶段 3：是否进入链库

按以下优先级切换：

1. 用户明确要求“进入链库” -> 直接进入；
2. workflow 命中为空 -> 进入；
3. workflow 判定为 `weak` 或 `borderline` -> 展示证据简报后进入；
4. workflow 判定为 `strong` 且用户接受 -> 停在 workflow 复用。

### 阶段 4：链库检索

调用 `ChainSearchEntry` 时，必须走统一对外接口（而不是在编排层展开内部算法）：

- `python -m src.main --step 3 --action chain_search --query "<query>" --top-k 100`
  或
- `search_reasoning_chains(config, ChainSearchRequest(...))`

在本阶段，编排层只读取接口输出字段：

- `total`
- `degraded`
- `enabled_routes`
- `failed_routes`
- `candidates`

并将 `candidates` 交给下游 workflow 抽取。

调用前必须先完成 `ChainSearchEntry` 的环境预检；若缺失必需连接配置，先返回缺失键名并等待补齐，不得静默改走其他检索实现。

---

## 最终输出形态

输出统一阶段状态，便于测试：

```json
{
  "query": "...",
  "refined_query": "...",
  "refined_query_en": "...",
  "keywords_core": ["..."],
  "keywords_must": ["..."],
  "keywords_avoid": ["..."],
  "user_confirmed": true,
  "workflow_stage": {
    "status": "done",
    "recommendation": "use_workflow | go_chain_search"
  },
  "chain_stage": {
    "status": "skipped | done",
    "total_candidates": 100,
    "degraded": false,
    "failed_routes": []
  },
  "next": "workflow_reuse | workflow_extraction"
}
```

