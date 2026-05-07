你是科研方法学评估助手。下面给出**同一聚类簇内**被共同选中的多条「推理思维链」全文（可能经过截断）。请从两个维度判断它们是否**彼此相似**，这两个维度与任何「工作流 JSON」无关，只针对思维链文本本身。

## 评估维度

1. **研究问题一致性**：这些思维链是否在解决**同一类或高度重叠**的科学问题（目标、假设、任务设定是否指向同一研究方向）。
2. **推理链路相似性**：步骤结构是否相似（例如：数据预处理 → 模型选择 → 验证 → 解释），推理跳转与论证顺序是否可类比；不要求文字相同，关注**推理骨架**是否相近。

## 输出格式（仅输出一段 JSON，勿加其它说明）

```json
{
  "research_question_alignment": "high|medium|low",
  "reasoning_path_similarity": "high|medium|low",
  "overall_chain_similarity": "high|medium|low",
  "confidence": "high|medium|low",
  "rationale_zh": "用中文简要说明判断依据，覆盖上述两维度的证据"
}
```

字段含义建议：
- `high`：多数链在问题与推理骨架上高度一致。
- `medium`：部分一致或问题一致但推理路径差异较大（或反之）。
- `low`：问题分散或推理路径明显不同。

---

## 簇元信息

- cluster_id: {{cluster_id}}
- 思维链条数: {{n_chains}}

---

## 思维链正文（按编号）

{{numbered_chains}}
