---
name: question-refiner
description: 面向 LKM 检索入口的研究问题澄清 Skill。通过 2-4 轮问答把用户粗问题澄清到“研究对象 + 研究目标”可检索状态，并在阶段1产出英文检索问题与关键词，交由用户确认和补充。
language: zh-CN
---

# QuestionRefiner: 研究问题澄清 Skill

用于把用户输入的粗问题（例如“我想研究钙钛矿太阳能电池”）转成可用于后续检索的高质量问题描述。

## 适用场景

- 用户问题过于笼统，缺少明确目标。
- 需要在 workflow 检索和链库检索前，先确认检索意图。
- 需要控制交互轮次，避免长对话。

## 核心目标

在最多 2-4 轮问答内，确保至少明确以下两项：

1. **研究对象**（research_object）
2. **研究目标**（research_goal）

然后在阶段1一次性输出：

1. 中文 refined query（给用户阅读）
2. 英文 refined query（给链库检索）
3. 英文关键词包（给 BM25/规则召回）
4. 用户确认/补充后的最终版本（confirmed）

> 强约束：在用户确认前，不得进入后续检索阶段。

---

## 执行流程（必须遵守）

### Step 1: 识别缺失信息

读取用户原始问题后，先判断：

- 是否明确了“研究对象”？
- 是否明确了“研究目标”（机制解释/性能优化/验证/预测等）？

若两者都已明确，可直接进入 Step 3。

### Step 2: 多轮澄清问答（最多 4 轮）

若缺失信息，按优先级追问：

1. 研究对象（若缺）
2. 研究目标（若缺）
3. 可选补充：任务范围、偏好证据类型、硬约束

问答原则：

- 每轮只问 1-2 个关键信息点。
- 优先使用单选/多选式提问（减少用户负担）。
- 不要问与检索无关的细节。
- 达到最小门槛后立即收敛，不继续追问。

### Step 3: 生成 refined query

把用户原始问题与补充信息融合，输出：

- 中文自然语言 `refined_query_zh`
- 英文自然语言 `refined_query_en`
- 英文关键词包：
  - `keywords_core`（核心关键词，5-12 个）
  - `keywords_must`（必须命中词，2-6 个）
  - `keywords_avoid`（应降权词，0-6 个）

### Step 3.5: 用户确认与补充（必须）

向用户明确展示以下内容并请求确认：

1. 英文研究问题（`refined_query_en`）
2. 提取关键词（`keywords_core/must/avoid`）
3. 允许用户直接补充/删改关键词与英文描述

确认规则：

- 用户明确确认“可用/OK/继续” -> `user_confirmed=true`
- 用户提出修改 -> 根据反馈回到 Step 3 重生并再次确认
- 最多迭代 2 次确认；仍未确认则 `low_confidence=true` 并提示风险

### Step 4: 异常与降级

若用户拒绝继续回答，或多轮后仍不完整：

- 允许低置信度继续（low-confidence）
- 但必须明确告诉用户“当前结果可能降低检索准确率”

---

## 输入输出约定

## 输入

- 用户原始问题（必需）
- （可选）用户补充偏好与约束

## 输出（给后续检索）

最少包含：

- `refined_query`（兼容字段，默认等于 `refined_query_zh`）
- `refined_query_zh`
- `refined_query_en`
- `research_object`
- `research_goal`
- `keywords_core`
- `keywords_must`
- `keywords_avoid`
- `user_confirmed`（布尔）
- `low_confidence`（布尔）

给用户展示时必须显示：

- 英文版研究问题（可编辑）
- 关键词包（可补充/删减）
- 一句确认状态说明（是否已确认）

---

## 质量标准

- 澄清轮次不超过 4 轮。
- 必须确认对象+目标后再进入检索。
- 产出的中英文 refined query 语义一致，不引入新约束。
- 英文关键词覆盖核心检索意图，避免仅中文 BM25 造成召回偏移。
- 在 `user_confirmed=true` 前，不得进入 workflow/chain 检索。

---

## 示例

用户输入：

> 我想研究下钙钛矿太阳能电池

澄清问答（示例）：

1. 你主要想研究哪一类问题：效率优化、稳定性、机理解释还是工艺放大？
2. 你更关注实验路径还是计算模拟路径？

输出 refined query（示例）：

> 我希望研究钙钛矿太阳能电池的稳定性提升问题，重点关注材料组成和界面工程对器件衰减机理的影响，并优先检索可落地的实验工作流与关键验证步骤。

输出英文版（示例）：

> I want to study stability improvement strategies for perovskite solar cells, focusing on how material composition and interface engineering affect device degradation mechanisms, and prioritize actionable experimental workflows with key validation steps.

关键词包（示例）：

- `keywords_core`: perovskite solar cell stability, degradation mechanism, interface engineering, material composition, experimental workflow
- `keywords_must`: perovskite, stability, degradation
- `keywords_avoid`: pure simulation without validation

