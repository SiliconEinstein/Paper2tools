---
name: chain-search-entry
description: 思维链向量库检索入口型Skill。用于在workflow候选弱相关或用户明确要求深挖时，触发链库多路召回与重排流程，并产出Top100候选链供workflow抽取。
language: zh-CN
---

# ChainSearchEntry: 思维链向量库检索入口

## 这个 Skill 做什么

这是一个**入口编排 Skill**，不承担底层召回算法实现。  
作用是告诉 agent 在何时切换到链库检索、执行哪些代码、如何组织 Top100 输出供后续 workflow 抽取使用。

---

## 触发时机

满足任一条件时使用：

1. Workflow 库检索返回候选，但结论为 `borderline/weak`；
2. 用户明确要求“不要复用已有 workflow，直接从思维链抽取新 workflow”；
3. Workflow 库命中为空。

前置要求：

- 研究问题已具备最小可检索质量（对象 + 目标）。

---

## 执行顺序（入口编排）

### Step 0: 仅使用统一接口（强约束）

`ChainSearchEntry` **只能**通过统一接口触发链库检索，不允许在 Skill 中展开内部算法步骤。  
统一接口如下：

- Python API：`src.step3.chain_search_api.search_reasoning_chains(config, req)`
- Pipeline Action：`python -m src.main --step 3 --action chain_search --query "<query>" --top-k 100`

对外 agent 只关心：

1. 输入是什么（query/top_k/table/allow_degraded）；
2. 输出是什么（候选链 + 路由健康状态）。

### Step 0.5: 环境预检（执行前必须）

在发起 `chain_search` 前，先检查以下配置是否可读（来自环境变量或项目根目录 `.env`）：

- ByteHouse：`LKM_BYTEHOUSE_HOST` / `LKM_BYTEHOUSE_USER` / `LKM_BYTEHOUSE_PASSWORD` / `LKM_BYTEHOUSE_DATABASE`
- Embedding：`DASHSCOPE_API_KEY` 或 `ACCESS_KEY`

若缺失任一必需键：

1. 先尝试从 `.env` 读取（统一接口已内置自动读取）；
2. 仍缺失则中止调用，并在回复中明确列出缺失键名；
3. 禁止悄悄切换到“本地单路检索”替代正式接口。

建议先执行一次连通性预检（失败则不要进入正式检索）：

```bash
python - <<'PY'
import yaml
from src.step3.chain_search_api import ChainSearchRequest, search_reasoning_chains

cfg = yaml.safe_load(open("configs/step3_config.yaml", "r", encoding="utf-8"))
try:
    # 用 top_k=1 做最小探测
    resp = search_reasoning_chains(cfg, ChainSearchRequest(query="test query", top_k=1, allow_degraded=True))
    print({"ok": True, "total": resp.total, "degraded": resp.degraded, "failed_routes": resp.failed_routes})
except Exception as e:
    print({"ok": False, "error": str(e)})
    raise
PY
```

若提示 endpoint 超时，可补充以下配置后重试：

- `LKM_BYTEHOUSE_ENDPOINT`（完整 URL，最高优先级）
- 或 `LKM_BYTEHOUSE_HOST + LKM_BYTEHOUSE_PORT + LKM_BYTEHOUSE_HTTPS`

### Step 1: 输入协议

最小输入：

- `query`（必填）：优化后的研究问题
- `top_k`（选填，默认 100）
- `table`（选填，默认 `lkm_reasoning_chain_embeddings_v2`）
- `allow_degraded`（选填，默认 `true`）

### Step 2: 输出协议

结果必须返回：

- `query`
- `total`
- `degraded`（是否降级）
- `enabled_routes`（实际成功路由）
- `failed_routes`（失败路由）
- `candidates[]`（候选链）

候选链字段至少包含：

- `chain_id`、`paper_id`、`conclusion_id`
- `conclusion_title`、`conclusion_text`、`reasoning_text`
- `num_steps`、`created_at`
- `final_score`
- `route_hits`

### Step 3: 交给 workflow 抽取阶段

将 `candidates` 直接作为“workflow 抽取输入集”传递，不暴露内部召回细节。

---

## 输出约定（给下游抽取）

建议输出结构：

```json
{
  "stage": "chain_search",
  "query": "<refined_query>",
  "total": 100,
  "degraded": false,
  "enabled_routes": ["ann", "lexical", "rule"],
  "failed_routes": [],
  "candidates": [
    {
      "chain_id": "...",
      "paper_id": "...",
      "conclusion_id": "...",
      "conclusion_title": "...",
      "conclusion_text": "...",
      "reasoning_text": "...",
      "num_steps": 7,
      "final_score": 0.74,
      "route_hits": ["ann", "lexical"]
    }
  ]
}
```

---

## 失败与降级

- 链库连接失败：返回明确错误（配置缺失/认证失败/超时）；
- 某一路失败：允许降级返回，并在 `degraded=true` + `failed_routes` 中体现；
- 若调用方要求严格模式（`allow_degraded=false`）：任一路失败即整体报错；
- 最终候选不足 `top_k`：按实际数量返回，不补空数据。
- 若报错包含 `ByteHouse connection is not fully configured`：必须把错误中的 `Missing: ...` 原样回传给调用方，便于一次性补齐。

---

## 与其它 Skill 的关系

- 上游：`QuestionRefiner`（问题澄清）
- 平级：`WorkflowSearchEntry`（先检索现有 workflow）
- 下游：workflow 抽取/回灌 Skill（不在本 Skill 范围）

