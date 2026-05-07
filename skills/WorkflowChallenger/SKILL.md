---
name: workflow-challenger
description: 基于 cluster_N workflow + 1 篇主论文，分**两部分**交付：(I) 半开放题目 `{标题}.md`；(II) **单一**出题人手册 `{标题}_solution.md`（内嵌：6 类 ground truth、推理路径、与提交物同结构的参考 JSON 代码块、评分用 YAML 代码块、人工等级表、grading_result 示例）。**铁律**：题目与提交字段都**不得**出现 `paper_id` / `quote` / `reason` / `rationale` 等自由文本或论文身份字段——提交字段只允许 numeric / boolean / enum / numeric-array。Use when "出题"、"workflow 挑战"、"solution"、"评分细则"、"自动评分"。
language: zh-CN
---

# WorkflowChallenger: 工作流半开放命题器

把"cluster_N workflow 产物 + 1 篇主论文"转成一道**半开放、workflow 依赖型**推理题，并可选生成**阅卷用资产**。**保存路径由用户指定**——若用户未指定，先询问用户希望保存到哪个目录，不要假设默认路径。

---

## 铁律：题目与提交字段政策（必读，一切其它规则之上）

> 这一节的每一条都是**硬约束**。Phase 5 / Phase 6 的自检会逐条 grep；命中即必须返工。**subagent 出题前先把本节通读一遍。**

### R1. **不得**在题目正文出现 `paper_id` 字面值

参赛 agent 看不到 cluster 内部的 paper_id 索引体系，**让它"引用 paper_id"就是凭空考记忆**。

- ❌ 题目正文写 `主论文 paper_id: 812367014646513665`
- ❌ 题目"主论文"表格放一列 `| paper_id | 主题 | … |`
- ❌ 题目"答题要求"写 `必须引用具体的 paper_id`
- ✅ 用**学术引用**指代主论文：`N. Tani et al., IEEE Trans. Appl. Supercond. 24(3), 2014, DOI:10.1109/TASC.2013.2288419`
- ✅ 主论文原文路径写 `<workflow_dir>/md/<main_paper>.md`（用占位词 `<main_paper>` 或 `主论文` 而非真实 paper_id）；如确需写出真实路径，paper_id **只能**作为文件名出现，不再额外强调
- ✅ 跨论文证据要求改为"从 `paper_extractions.yaml` 中提取 ≥ N 个数值"（数量约束 + 数值字段，不要求 agent 报出 paper_id）

### R2. **不得**在提交物 JSON 的字段中出现 `paper_id` / 引文 / 自由文本理由

提交字段**只**允许以下 4 种类型：

| 类型 | 例 |
|---|---|
| **numeric**（标量数值） | `"T_kinetic_MeV": 180.0` |
| **boolean** | `"does_attribution_affect_inversion": false` |
| **enum**（小写下划线） | `"verdict": "physical_signal"`（白名单：`physical_signal` / `measurement_noise` / `comparable`） |
| **numeric-array**（数值数组） | `"cross_paper_precision_percentages": [0.1, 0.001, 0.5, 0.35]` |

**禁列字段名**（grep 命中即返工）：

```
paper_id  quote  citation  reason  rationale  rationale_one_sentence
explanation  argument  comparison_argument  attribution_quote_from_paper
paper_attribution_quote_with_section  precision_quote  yaml_field
key_difference_from_main_paper  pitfall_source  advantage  disadvantage
beta_*_rationale  *_assumption_text  *_combination_assumption  description
```

**禁列字段类型**：任何"自由文本说明 / 引文摘录 / 论证段落 / 步骤叙述"都不许进 JSON——它们既无法机判，又会让评分依赖 NLP/LLM。

### R3. BAD ↔ GOOD：典型重写对照

下面 4 类是 subagent 最常踩的坑（实际命中过：fluid_mechanics_2、早期 PSTR 草稿等）。新题写完后**逐条对照**：

| BAD（旧式复现题 / 字面引用题） | GOOD（半开放数值题） |
|---|---|
| `"paper_id": "...", "quote": "..."` | 删掉 paper_id 与 quote。要数值证据就用 `"BL_per_mm_percent_from_workflow": 0.84`（数字本身就是从 yaml 抽出的事实） |
| `"cross_paper_comparison": [{"paper_id": "...", "key_difference": "..."}, ...]` | `"cross_paper_precision_percentages": [<float>, <float>, <float>, <float>]`（统一折成无量纲百分数） |
| `"attribution_quote_from_paper": "<≤30 词原文>", "rationale_one_sentence": "..."` | `"does_attribution_affect_inversion": <bool>`（agent 读了主论文 md 之后给布尔判定即可，理由不进 JSON） |
| `"main_paper_method": "Vlasov / 流体", "alternative_method_paper": {"paper_id":"...", "advantage":"...", "disadvantage":"..."}` | 改为可机判的数值/枚举，例如 `"alternative_method_found": <bool>` + `"method_class": "kinetic" \| "fluid" \| "hybrid"` + 具体一个**数值对照**（如增长率比、计算复杂度指数）；不要"优势/劣势"自由文本 |

### R4. 主论文身份的合规写法

题面一定需要让 agent 知道"读哪个 md"。合规模板：

```markdown
## 主论文

> N. Tani, T. Takayanagi, T. Ueno, …, *Field Measurement of Pulse Steering
> Magnet for J-PARC 3 GeV Rapid Cycling Synchrotron*, **IEEE Trans. Appl.
> Supercond.** **24**(3), 2014. DOI: 10.1109/TASC.2013.2288419.

主论文原文位于 `<workflow_dir>/md/<main_paper>.md`（同目录其它 `*.md` 为
cluster 内的对照文献，按需查阅）。
```

- 学术引用承担"指代"职责；
- `<main_paper>` 用占位词，**不写**真实 paper_id；
- 出题人手册（`_solution.md`）内部记账可以、也应当写真实 paper_id（仅用于评分人 / 内部追溯，不分发参赛者）。

### R5. Phase 5 / Phase 6 强制 grep 自检（命中必须返工）

Part I 收尾 与 Part II 收尾都要跑：

```bash
# (A) 题目正文：除"参考资源"段的 md 路径外，不得提 paper_id 字面值
rg -n 'paper_id'  {标题}.md

# (B) 题目正文 fenced 代码块（提交物 JSON skeleton）：禁列字段一律 0 命中
rg -n -P '"(paper_id|quote|citation|reason|rationale|explanation|argument|comparison_argument|attribution_quote_from_paper|paper_attribution_quote_with_section|precision_quote|yaml_field|key_difference_from_main_paper|pitfall_source|advantage|disadvantage)"\s*:' {标题}.md

# (C) 解决方案的参考 JSON 与评分 YAML：同样 0 命中
rg -n -P '"(paper_id|quote|citation|reason|rationale|explanation|argument|comparison_argument)"\s*:' {标题}_solution.md

# (D) 题面禁用"必须引用 paper_id"类硬约束
rg -n '必须引用.*paper_id|引用具体的 paper_id' {标题}.md
```

任何一条命中 ≥ 1 → **返工题面 / JSON schema / YAML 评分规则**，直到全部 0 命中。

## 本 Skill 的两部分（必读）

| 部分 | 面向 | 交付物（均在用户指定目录下） | 是否给参赛者 |
|------|------|------------------------------|:--:|
| **Part I — 出题** | 命题 | `{标题}.md` | ✅ 仅该文件 |
| **Part II — Solution 与评分细则** | 阅卷 / 评分 agent | **`{标题}_solution.md` 一个文件**（内嵌 § 参考 JSON + § 评分 YAML；不向参赛者分发） | ❌ 全部 |

**默认执行顺序**：先完成 **Part I**，再完成 **Part II**。若用户明确只要题目、不要阅卷包，可止于 Part I，但须在对话中说明「未生成评分资产，无法自动阅卷」。

**职责划分**：

- **Part I** 只保证题目正文符合骨架、参赛者视角措辞、信息缺口与硬约束可验证；**不在此阶段要求**写完长篇 `_solution.md` 全文（但 Phase 3 的内部核账表、Phase 4 的 ground truth 草稿仍必须做，作为 Part II 输入）。
- **Part II** 把核账结果**固化**为**一个** `{标题}_solution.md`：其中用 ` ```json ` 块给出各任务标准答案（字段与题目「交付物」一致），用**单个** ` ```yaml ` 块给出 `reference_values`、`global_fail`、`scoring.checks`、加权与 `implementation_notes`。实现评分时从该 Markdown **提取** YAML 字符串解析；**正文叙述与 fenced YAML 冲突 → 以 YAML 块为准**。

---

## 核心理念（区别于"复现题"）

题目**不是**让参赛者按编号步骤复现一个已知结果，而是：

| 维度 | 旧式复现题（不要） | 半开放推理题（本 skill 出的） |
|---|---|---|
| **输入信息** | 题目正文给完整数据 + 完整公式 + 完整路径示意 | 题目正文只给少量锚点 + 硬约束；其它信息埋在 workflow 里 |
| **推理路径** | 题目规定"步骤 1 → 2 → 3" | 题目只给目标 + 验收标准，路径由参赛者自己设计 |
| **agent 解题方式** | 不打开 workflow 也能照题正文 90% 还原结果 | 不打开 workflow 几乎无法完成；必须查 yaml/chain/md |
| **评分** | 数值精度 | 数值精度 + 路径质量（引用 workflow 资源数、对比深度、不确定度） |

题目主题与任务数量由主论文与 workflow 的实际内容决定，**不固定任务数量、不固定每个任务内容**。本 skill 规定"如何用好 workflow"、"核账流程"、"信息缺口设计"与"题目应有的最小骨架"。

---

## 输入文件映射

Workflower 管线产出以 `cluster_N/` 为根目录。**3 个核心 workflow 资产**：`paper_extractions.yaml`（逐论文事实）、`decision_tree.{dot,pdf,png}`（流程拓扑）、`review_cluster_N.{tex,pdf}`（综述）——分别承载"已知什么 / 怎么做 / 怎么连起来讲"，出题前应**全部读过**，构成对该 cluster 的三角理解。

| 文件 | 出题用途 | 使用阶段 |
|------|---------|---------|
| `paper_extractions.yaml` | **核心 1**：每篇论文的 `core_formula`、`quantitative_results`、`algorithm_layer`、`gaps_noted` 等结构化提取——写题与跨论文对账的事实底座 | Phase 1 选题、Phase 2 选论文、Phase 3 核账 |
| `decision_tree.dot` / `.pdf` / `.png` | **核心 2**：cluster 的"阶段 → 决策 → 方法 → 参数"拓扑图（节点带覆盖率，如 `[5/5, 100%]`）；用于看清主线路径、高频分支与覆盖率薄弱处 | Phase 1 选题（选高覆盖率分支）、Phase 5 设计任务边界 |
| `review_cluster_N.tex` / `.pdf` | **核心 3**：基于 cluster 全部论文合成的领域综述（关键阶段、典型参数区间、常见陷阱）；题目背景叙述与"已知 / 留白"判断最权威的单文件 | Phase 1 选题（领域定位）、Phase 4 留白决策 |
| `md/{paper_id}.md` | 主论文原文 Markdown，用于核对 yaml 提取的字面值与单位 | Phase 3 核账（必做） |
| `paper_inventory.md` | cluster 内论文清单（paper_id + 链数），供抽样与覆盖率核对 | Phase 1（可选） |
| `selected_chains.json` | 逐链推理步骤（`paper_id`、`conclusion_id`、`steps`） | Phase 3 核账、跨论文细节查证 |
| `chain_classification.json` | A/B/C 类链分类（信息多已被 `review` / `decision_tree` 综合） | Phase 1（可选辅助） |
| `step_statistics.json` | 阶段覆盖率与方法频次统计（信息多已被 `decision_tree` 节点权重综合） | Phase 1（可选辅助） |
| `workflow_structure.json` | 决策树原始 JSON（与 `decision_tree.dot` 同源；机读用） | Phase 5 如需脚本化引用 |
| `review_plan.json` | 审阅计划（如有子主题分裂） | Phase 1（如有） |
| `workflow_3layer.md` | 旧版三层文档；第三层"输入示例"常为 LLM 编造**不可信**——若与 `decision_tree` / `review` 冲突，以后两者为准 | 仅供对比，不作为权威 |
| `xml/{paper_id}_{chain_idx}.xml` | 推理链 XML 原文（可选） | 仅在需逐步证据时回查 |

**重要提示**：
- **3 个核心文件**——`paper_extractions.yaml` / `decision_tree.{dot,pdf,png}` / `review_cluster_N.{tex,pdf}`——出题前应**全部读过**；遗漏任意一个都会带来盲区（只看 yaml 容易错估覆盖率与流程衔接；只看 review 拿不到字面数值；只看 decision_tree 缺乏论文级证据）。
- `md/{paper_id}.md` 是**所选主论文**的核账必读文件，不可跳过。
- `workflow_3layer.md` 是旧版冗余文件，第三层"输入示例"常为 LLM 编造，**不能**作原文数据使用；遇到与"模式 / 实现"相关的信息，优先查 `decision_tree` 与 `review_cluster_N`。

---

## Part I — 出题（交付物：`{标题}.md`）

以下 **Phase 1–5** 仅针对**题目正文**。内部核账草稿（`_verification_table.md`、`_ground_truth_draft.md`）在 Part I 生成，供 **Part II** 消费。**`{标题}_solution.md` 全文**（含内嵌的参考 JSON 块与评分 YAML 块）一律在 **Part II** 编写，勿与题目正文混在同一文件。

### Phase 1 — 选题方向（用 `paper_extractions.yaml` + `decision_tree` + `review_cluster_N`）

**目标**：从 3 个核心 workflow 资产中选一条高覆盖率的科学路径作为题目主线。开始之前**先把核心 3 件全部过一遍**：`review_cluster_N.{tex,pdf}` 给出领域语境与典型参数；`decision_tree.{dot,pdf,png}` 给出"阶段→决策→方法→参数"拓扑与覆盖率；`paper_extractions.yaml` 给出可对账的论文级数值。`step_statistics.json` / `chain_classification.json` 仅作为**可选辅助**指标——多数信息已被 review 与 decision_tree 综合。

**步骤**：

1. **读 `review_cluster_N.tex` / `.pdf`** 与 **`decision_tree.{dot,pdf,png}`**，建立 cluster 全景：

   - `review_cluster_N` 摘要段、各 \section 标题与 `\begin{parambox}` / `\begin{pitfallbox}` 即"领域核心阶段、关键参数区间、典型陷阱"——选题应**对齐这些核心阶段**之一作为主线，并避免与已写过的题目主题重叠。
   - `decision_tree.dot` 的节点标签包含覆盖率（如 `[5/5, 100%]`、`[3/5, 60%]`）与分支决策（菱形 `D*`）。**选择标准**：主线应跨越覆盖率 ≥ 60% 的若干阶段，且包含至少 1 个决策分支节点（让题目自然引向"为什么走这条分支"）。

2. **辅助核对**（可选：`step_statistics.json`、`chain_classification.json`）：

   仅当 review / decision_tree 信息不足时才回查，**避免重复劳动**。

   - `step_statistics.json` → 量化覆盖率：`stage_coverage`（各阶段被多少条链覆盖）、`method_frequency`（高频方法 Top 10）、`path_patterns`（如有）、`total_chains` / `unique_papers`。**选择标准**：主线阶段覆盖率 ≥ 50%，覆盖至少 3 个高频方法（频次 ≥ 5）。
   - `chain_classification.json` → 筛 A 类主线链：遍历 `classification = "A-主线"` 的链条，提取 `stages` / `methods_used`；A 类链 < 3 条时警告"素材不足"，考虑纳入 B 类链。

3. **抽样 `paper_extractions.yaml` 与 `md/{paper_id}.md`**（为 Phase 2/3 选论文做准备）：

   - 在 yaml 中按 `paper_id` 抽样 3–5 篇，确认主线方法在多篇论文中**字面**出现且 `quantitative_results` 含可用的字面值（公式系数、参数区间、误差预算等）。
   - 命中候选主论文后，开 `md/{paper_id}.md` 看 §I / §III 是否有清晰的"实验装置 + 测量值 + 反推关系"链——这是 Phase 4 设计任务的素材。
   - **不要**用 `workflow_3layer.md` 第三层那种"输入示例"代码块作题目数据；如需"模式 / 实现"层细节，回查 `decision_tree` 的方法节点标签或 `review_cluster_N` 对应章节。

4. **去重检查**（如果用户指定了保存目录）：
   
   - 扫描保存目录下已有题目的文件名和"任务目标"段落
   - 如果本次选定主题与已有题目相近（如都是"临界电流密度"或都是"占位判定"），换另一条主线
   - 去重标准：主题词重叠 ≥ 50% 视为相近

**输出**（内部记录，不写入文件）：

```
选定主线: "离子半径分析 → 容忍因子计算 → 晶格参数趋势预判 → Rietveld 相分数核验 → 活化能提取 → 缺陷机制归因"
覆盖率: A 类链 8/8 (100%)，总链条 8/50 (16%)
核心方法: Shannon 离子半径查表、Goldschmidt 公式、Arrhenius 拟合
主题: 钙钛矿陶瓷掺杂占位与缺陷归因
```

**重要**：最终题目中**不暴露 cluster 编号**，只写"来源于材料科学 workflow"。

---

### Phase 2 — 选主论文（用 paper_extractions.yaml）

**目标**：从 yaml 中选一篇公式与数值最丰富的论文作为题目主体。

**步骤**：

1. **打开 `paper_extractions.yaml`**，逐篇检查：

   **筛选条件**（按优先级排序）：
   
   | 筛选条件 | 最低要求 | 检查方法 |
   |---------|---------|---------|
   | `algorithm_layer.core_formula` | ≥ 2 个公式 | 统计 `core_formula` 列表长度 |
   | `quantitative_results`（或等价字段如 `implementation_layer.quantitative_results`） | ≥ 5 项具体数值 | 统计数值型结果数量，排除"显著提升"等定性描述 |
   | 论文方向与 Phase 1 主线匹配 | 必须匹配 | 检查论文标题/摘要是否包含主线关键词 |
   | `gaps_noted` 字段 | 越少越好 | 遗漏信息少的论文更适合出题 |

2. **排序与选择**：
   
   - 在满足最低要求的论文中，按以下优先级排序：
     1. 公式数量（多者优先）
     2. 数值结果数量（多者优先）
     3. `gaps_noted` 少的优先
   
   - **选择第 1 名作为主论文**
   
   - **记录备选论文**：排名 2-3 的论文作为 Phase 4 的"W 类"（跨论文对照）数据源

3. **确认主论文 paper_id**：
   
   - 记录 `paper_id`（如 `812491390918328320`）
   - 记录论文标题、期刊、年份（从 yaml 的 `metadata` 或 `citation` 字段提取）
   - 记录核心公式列表（从 `algorithm_layer.core_formula` 提取）
   - 记录关键数值列表（从 `quantitative_results` 提取）

**输出**（内部记录）：

```
主论文 paper_id: 812491390918328320
标题: Huang et al., Acta Materialia (2021)
核心公式: 
  - Goldschmidt 容忍因子: t = (r_A + r_O) / [√2 · (r_B + r_O)]
  - Arrhenius 电导率: σ = σ₀ · exp(-E_a / k_B T)
关键数值: 
  - Ba²⁺ 半径 1.61 Å (12配位)
  - Ce³⁺ 半径 1.34 Å (12配位)
  - E_a(A-0.06) = 1.43 eV
  - ... (共 12 项)
备选论文: paper_id_2, paper_id_3（用于 W 类跨论文对照）
```

**注意**：后续所有公式与数值以这一篇为主，其它 cluster 内论文仅作辅助参考（W 类）。

---

### Phase 3 — md 核账（必做，用 md/{paper_id}.md 对照 yaml）

**目标**：验证 yaml 提取的公式与数值与原文一致，标记差异为 E 类。

> **为什么不能跳过**：yaml 是一次 LLM 提取，可能存在字面失真、区间被压窄、常数遗漏。跳过核账会导致题目内数值自相矛盾。

**步骤**：

#### 3a. 公式字面对照（必做）

**操作流程**：

1. **提取 yaml 中的所有公式**：
   - 从 `algorithm_layer.core_formula` 提取公式列表
   - 记录每个公式的变量定义和物理含义

2. **在原文 md 中定位对应段落**：
   - 用公式中的关键变量（如 `t =`、`σ =`）在 md 中搜索
   - 记录原文段落位置（Section X, 行号 L##）

3. **逐项对照，填写核账表**：

| # | yaml 公式 | 原文对应段落 | 一致？ | 差异说明 | 类别 |
|---|----------|-------------|--------|---------|------|
| 1 | t = (r_A + r_O) / [√2·(r_B + r_O)] | Section 3.2, L76 | Y | — | A |
| 2 | α = (k_B·T/U_p)·ln(E₀/E) | Section 3.2, L88 | N | 原文写 T，物理一致性要求 T_c | E |

**常见失真模式 Checklist**（逐项排查）：

- [ ] **变量混淆**：如 `T` 与 `T_c`（Tinkham 蠕变）、`r` 与 `r_eff`、`B` 与 `B_peak`
- [ ] **漏抄常数**：如 4π、ln(E₀/E)、几何因子 e^(-1/2)·π/2、√2
- [ ] **单位混淆**：如 emu 与 A·m²、Å 与 cm、mV/T 与 V/T、meV 与 eV
- [ ] **区间被压窄**：yaml 把 `0.1–0.15 eV` 写成 `≈100 meV`（丢失不确定度）
- [ ] **指数/对数遗漏**：如 `exp(-E_a/kT)` 写成 `E_a/kT`

**判定标准**：
- **A 类**（原文直接报告）：yaml 与 md 字面一致，无需修改
- **E 类**（题目作者诠释性修改）：yaml 与 md 有偏差，但修改后物理一致性更好
  - 必须在核账表的"差异说明"列写明修改理由
  - 在题目的"附录 A"中标注为 E 类

#### 3b. 端到端反算（必做，防数量级偏差）

**操作流程**：

1. **提取 yaml 中的所有中间量报告值**：
   - 从 `quantitative_results` 提取数值型结果
   - 排除定性描述（如"显著提升"）

2. **用 yaml 公式 + 输入参数反向计算**：
   - 对每个中间量，找到对应的公式
   - 代入输入参数，计算理论值
   - 与 yaml 报告值对比

3. **填写反算表**：

| # | 量 | yaml 报告值 | 反算值 | 偏差倍数 | 通过？ | 备注 |
|---|---|-----------|--------|---------|--------|------|
| 1 | U_p | 100 meV | 99.7 meV | 1.003× | ✓ | 用 T_c=87K, α=1, ln(E₀/E)=13.3 |
| 2 | Jc^dp | 1.5×10⁸ A/cm² | 1.48×10⁸ A/cm² | 1.014× | ✓ | 用 λ=250nm, ξ=1.5nm |

**判定规则**：
- **偏差 ≤ 2×**：✓ 通过，数值可用
- **2× < 偏差 ≤ 10×**：⚠️ 警告，检查是否有已知近似（如 π ≈ 3、√2 ≈ 1.4）
  - 如果是已知近似，标注并通过
  - 如果无法解释，标记为疑点，考虑换主论文
- **偏差 > 10×**：❌ 停止，回头检查公式形式或单位换算
  - 检查是否漏了常数项（如 4π、ln 项）
  - 检查单位是否一致（如 Å vs nm、eV vs meV）
  - 如果无法修复，**换主论文**

**实战案例**（cluster_12 发现的 100× 偏差）：

```
yaml 公式: α = (k_B · T / U_p) · ln(E₀/E)
yaml 报告: α≈1, U_p≈100 meV, T_c=87 K
yaml 缺失: ln(E₀/E) 未给出

错误尝试 1: 取 T=10 K（测量温度）, ln(E₀/E)=1（猜测）
→ U_p = k_B · 10 · 1 / 1 = 0.86 meV ❌（差 100 倍）

诊断: 
- α 是温度无关常数（原文明确说明），但公式中有 T
- 物理一致性要求 T 应为 T_c（来自小 t 展开）

修复: T → T_c（E 类诠释），ln(E₀/E)=13.3（反算所得）
→ U_p = k_B · 87 · 13.3 / 1 = 99.7 meV ✓

标注: 在题目中标注公式 (3) 为 E 类，说明原文字面 T 改为 T_c 的理由
```

#### 3c. 核账输出（必须生成）

**生成两个文件**（内部使用，不交付给参赛者）：

1. **`_verification_table.md`**（公式对照 + 反算结果合并）：
   ```markdown
   # Phase 3 核账表
   
   ## 公式对照
   | # | yaml 公式 | 原文段落 | 一致？ | 差异说明 | 类别 |
   |---|----------|---------|--------|---------|------|
   | ... |
   
   ## 端到端反算
   | # | 量 | yaml 报告值 | 反算值 | 偏差倍数 | 通过？ | 备注 |
   |---|---|-----------|--------|---------|--------|------|
   | ... |
   
   ## E 类修改清单
   - 公式 (3): 原文 T → 本题 T_c，理由：α 为常数要求
   - ...
   ```

2. **`_ground_truth_draft.md`**（Phase 4 的输入）：
   ```markdown
   # Ground Truth 草稿（Phase 4 用）
   
   ## A 类（原文直接报告）
   - Ba²⁺ 半径 = 1.61 Å (12配位) | 来源: Section 3.2, L76
   - ...
   
   ## E 类（题目作者诠释性修改）
   - 公式 (3) 中 T → T_c | 理由: α 为常数
   - ...
   
   ## 待补充（Phase 4 生成）
   - B 类（原文派生）
   - C 类（题目作者反算自洽）
   - D 类（题目作者凭空设定）
   - W 类（跨论文派生）
   ```

**检查点**：
- [ ] 所有 yaml 公式都已在原文 md 中定位
- [ ] 所有失真模式都已逐项检查
- [ ] 所有中间量都已反算，偏差 ≤ 2×
- [ ] E 类修改都已记录理由
- [ ] 生成了 `_verification_table.md` 和 `_ground_truth_draft.md`

**如果核账失败**（偏差 > 10× 且无法修复）：
- 返回 Phase 2，选择备选论文
- 重新执行 Phase 3

---

### Phase 4 — 设计信息缺口（半开放题的核心）

**目标**：把 Phase 3 核账后的完整推理链**故意拆开**，只把最少必要的"锚点"留在题目正文，其余推到 workflow 里让参赛者去查。

**为什么这样做**：如果题目正文写完整公式 + 完整数据 + 完整步骤，agent 不打开 workflow 也能 90% 还原结果——workflow 沦为可有可无的装饰。半开放题靠"故意留白"把 workflow 变成解题硬依赖。

**步骤**：

#### 4a. 列出题目"完整 ground truth"

把 Phase 3 核账后获得的所有数值与中间量列成一张表。这是**出题人内部持有**的草稿：

| 量 | 值 | A/B/C/D/E/W 类 | 来源 |
|---|---|---|---|
| Ba²⁺ 半径 (12配位) | 1.61 Å | A | 主论文 §3.2, L76 |
| t(BaTiO₃) | 1.062 | B | 由 A 类参数 + 公式 (1) 反推 |
| ln(E₀/E) | 13.3 | C | 由 α=1, U_p=100meV, T_c=87K 反算自洽 |
| a (边缘势垒参数) | 0.010 | D | 题目作者凭空设定（无原文依据） |
| 公式 (3) 中 T → T_c | — | E | 题目作者诠释性修改 |
| 同主题 paper Y 的灵敏度参数 | 7.07 mV/T | W | cluster 内 paper_id_2 的 quantitative_results |

**6 类可信度定义**（详见后文"数值的 6 类可信度"章节）：
- **A**：原文直接报告（yaml 与 md 字面一致）
- **B**：原文派生（由 A 类参数 + 公式反推）
- **C**：题目作者反算自洽（依赖 A 类参数让 reverse-derived 自洽）
- **D**：题目作者凭空设定（无原文/yaml 依据，仅作 ground truth）
- **E**：题目作者诠释性修改（与原文字面有偏差但物理一致性更好）
- **W**：Workflow 跨论文派生（来自 cluster 内**非主论文**的 yaml/md）

#### 4b. 决定哪些"暴露"到题目正文，哪些"留白"到 workflow

按下表分类（**这是 Phase 4 的核心决策**）：

| 类别 | 是否暴露到题目正文 | 来源 | 暴露条件 |
|---|:-:|---|---|
| **题目锚点**（最多 3 个） | ✅ 暴露 | 必须是 A 类，且是回答任务的"目标值"或"硬约束" | 作为题目的"已知条件" |
| **A 类辅助参数** | ❌ 留白 | 在主论文 md / yaml 里能找到 | 让参赛者自己查主论文 |
| **W 类（cluster 其它论文）** | ❌ 留白 | 跨论文方法对照、共识参数等 | 让参赛者查 paper_extractions.yaml |
| **B 类派生量** | ❌ 留白 | 让参赛者从 A + W 派生 | 考察公式应用能力 |
| **C/D/E 类** | ❌ 仅在出题人 ground truth 中保留 | 用于评分时核对参赛者答案 | **不暴露**，避免泄露答案 |

**目标比例**（半开放题的强制要求）：
- 题目正文给 ≤ 3 个 A 类锚点
- 至少 1 个任务必须依赖 W 类（≥ 1 篇 cluster 其它论文）
- 总数值 ground truth 中题目正文暴露 ≤ 25%

**示例**（BaTiO₃ 占位判定题）：

```
完整 ground truth: 20 个数值
题目正文暴露: 3 个 A 类锚点（Ba²⁺ 半径、Ti⁴⁺ 半径、Tc）
留白到 workflow: 17 个数值
  - 10 个 A 类辅助参数（在主论文 md 中）
  - 2 个 W 类（在 paper_extractions.yaml 的其它论文中）
  - 5 个 B/C/D 类（参赛者需自己推导）

暴露率: 3/20 = 15% ✓（< 25%）
```

#### 4c. 写"Workflow 资源索引"

题目正文里要明确告诉参赛者**哪些信息埋在 workflow 哪些文件里**——但**只指向位置，不给具体值**。例如：

```markdown
## Workflow 资源索引（必查）

完成本题需要从下列 workflow 资源中提取信息：

| 需要的信息类型 | 在哪查 | 具体位置 |
|---|---|---|
| 主论文公式与中间量 | `cluster_N/md/{paper_id}.md` | §III–§IV（离子半径与容忍因子） |
| 同主题其它论文的灵敏度参数（≥ 2 篇） | `cluster_N/paper_extractions.yaml` | `quantitative_results` 字段，搜索"sensitivity"或"灵敏度" |
| 决策树 / 方法选择依据 | `cluster_N/workflow_structure.json` | 阶段 3-5 的方法节点 |
| 推理链片段（用于 sanity check） | `cluster_N/selected_chains.json` | chain_id 范围 [10-25]（A 类主线链） |
```

> **关键**：不要在指针里写"这里能找到 X = 3.14"——只写"X 类参数在哪类文件里"。具体值的获取就是题目对参赛者的考核。

**资源索引必须包含的 3 类指针**：
1. **主论文指针**：指向 `md/{paper_id}.md` 的具体章节
2. **跨论文指针**：指向 `paper_extractions.yaml` 的字段名（至少 1 个 W 类任务）
3. **决策树指针**：指向 `workflow_structure.json` 或 `selected_chains.json`（用于验证推理路径）

#### 4d. 与 Part II 的交接（不在此步写长篇 `_solution.md`）

- Part I 在本步结束时必须已有：**完整 ground truth 表草稿**（6 类齐全，可写在 `_ground_truth_draft.md` 或 Part II 将粘贴的临时块），以及**留白/已知条件决策**。
- **`{标题}_solution.md` 全文**（含内嵌 JSON + YAML）在 **Part II — Phase 6** 一次写清，避免多文件与题目 JSON 契约漂移。
- 题目交付给参赛者时**仍只给** `{标题}.md`。

**检查点**（Part I 侧）：
- [ ] ground truth 草稿包含所有 6 类数值（A/B/C/D/E/W）
- [ ] 题目正文暴露率 ≤ 25%
- [ ] 至少 1 个任务依赖 W 类（跨论文对照）
- [ ] 「参考资源」段包含 3 类指针（主论文 + 跨论文 + 决策树/链）

---

### Phase 5 — 组装题目（仅 Part I 交付物）

**目标**：按骨架填充完整题目 Markdown（参赛者视角，见后文「题目骨架」）。

**文件命名**（Part I）：
- 题目正文：`{标题}.md`（**不带数字编号、不带 cluster 编号**）

**Part II 交付物**仅为 **`{标题}_solution.md`**，在 **Part II** 生成；**不要**把它与 `{标题}.md` 合并，也**不要**再拆出独立 `*.yaml` / `reference_answers/`（除非用户明确要求多文件流水线）。

标题应反映题目内容本身（核心方法 + 材料/系统），例如：
- `Bean模型磁滞回线宽度推导MgB₂临界电流密度.md`
- `边缘势垒+磁通蠕变拟合YBCO窄条带临界电流密度.md`
- `BaTiO₃位选择掺杂中Ce占位判定与缺陷机制归因.md`
- `霍尔探针校准扩展与积分场线性度验证.md`

**如果用户没有事先告诉保存路径，写题前必须先问一次**。

**步骤**：

#### 5a. 确定任务数量与内容（灵活，不固定）

**重要**：题目任务数量由主论文与 workflow 的实际内容决定，**不固定为 N 个任务**。

**任务设计原则**：
1. **每个任务对应科学路径的一个关键环节**（如"容忍因子计算"、"活化能提取"）
2. **任务之间有逻辑递进关系**（如任务 2 依赖任务 1 的结果）
3. **至少 1 个任务必须依赖 W 类**（跨论文对照）
4. **推荐 2-4 个任务**（太少缺乏挑战，太多参赛者负担重）

**任务三段式结构**（每个任务必须包含）：
```markdown
### 任务 X：{1 句话目标}

**目标**：要回答的具体问题（仍是粗粒度，不给步骤）

**硬约束**：最终结果必须满足的条件
- 数值区间：如"最终 Jc 应落在 [1.0, 2.0]×10⁸ A/cm² 范围内"
- 单位要求：如"必须用 SI 单位，最后换算到 CGS"
- 跨论文证据数量：如"从 `paper_extractions.yaml` 中提取 ≥ 4 个独立精度量级（百分数）"——**注意**：要求"数值数量"，**不**要求 paper_id（违反铁律 §R1）
- 精度要求：如"相对误差 ≤ 5%"

**验收**：交付物清单（文件名、字段名、格式）
- 如"`tolerance_factor.json`，包含字段 `t_pure_BT`、`delta_r_A_site_Å`、`preferred_site_by_size`"
- 如"`phase_analysis.csv`，包含列 `sample`、`P4mm_pct`、`Amm2_pct`"
```

**禁止写的内容**（会让题目退化为复现题）：
- ❌ 步骤 1/2/3（如"步骤 1：读取数据；步骤 2：计算容忍因子"）
- ❌ 推荐方法清单（如"可用 scipy.optimize.curve_fit 或 lmfit"）
- ❌ 推荐函数清单（如"用 numpy.trapz 做积分"）
- ❌ 伪代码（如"for each sample: calculate t = ..."）

#### 5b. 按骨架填充题目正文

**题目骨架**（半开放题统一格式）：

```markdown
# {标题}

> 难度 | 预计耗时 | 标签

## 任务目标
1-2 段，粗粒度目标。**只说要回答什么，不说怎么回答**。
例如："目标是沿着 workflow 的主线路径——离子半径分析 → 容忍因子计算 → 晶格参数趋势预判 → Rietveld 相分数核验 → 活化能提取 → 缺陷机制归因——复现从 Shannon 离子半径出发，判定 Ce 在 BaTiO₃ 中的优先占位，并通过活化能数据交叉验证缺陷补偿机制的完整推理过程。"

## 来源信息
| 维度 | 内容 |
|------|------|
| 生成时间 | YYYY-MM-DD |
| 来源 | XX workflow 中的 `cluster_N`（或"来源于材料科学 workflow"，不暴露编号） |
| 主论文 | Author et al., *Journal* (Year), paper_id = `...` |
| workflow 主题 | 一句话描述（如"钙钛矿陶瓷中掺杂离子的占位判定与缺陷机制归因"） |
| 科学路径类型 | 箭头链（如"离子半径 → 容忍因子 → 晶格趋势 → 相分数 → 活化能 → 缺陷机制"） |

## 题目锚点
**本节是题目正文唯一直接给数值的地方**（≤ 3 个 A 类核心数）。

格式：
- 量名 = 数值 + 单位 + 量纲约束
- 必须包含至少 1 条"硬约束"（如"最终结果应落入区间 [x, y]"）

例如：
- Ba²⁺ 离子半径（12 配位）= 1.61 Å
- Ti⁴⁺ 离子半径（6 配位）= 0.605 Å
- 零电阻 Tc = 87 K
- **硬约束**：容忍因子 t 应落在钙钛矿稳定范围 0.88 < t < 1.06

## Workflow 资源索引
**★ 半开放题的核心入口**

表格列出"完成本题需要查的 workflow 资源"：
| 需要的信息类型 | 在哪查 | 具体位置 |
|---|---|---|
| 主论文公式与中间量 | `cluster_N/md/{paper_id}.md` | §III–§IV（离子半径与容忍因子） |
| 同主题其它论文的灵敏度参数（≥ 2 篇） | `cluster_N/paper_extractions.yaml` | `quantitative_results` 字段，搜索"sensitivity" |
| 决策树 / 方法选择依据 | `cluster_N/workflow_structure.json` | 阶段 3-5 的方法节点 |
| 推理链片段（用于 sanity check） | `cluster_N/selected_chains.json` | chain_id 范围 [10-25] |

**只指向位置，不给具体值**。

必须包含 3 类指针：
1. 主论文指针（md 文件 + 章节）
2. 跨论文指针（paper_extractions.yaml + 字段名）
3. 决策树指针（workflow_structure.json 或 selected_chains.json）

## 任务（Tasks）
**★ 数量自由（推荐 2-4 个），统一节奏**

每个任务严格按"目标 / 硬约束 / 验收"三段式：

### 任务 X：{1 句话目标}
**目标**：要回答的具体问题（仍是粗粒度）

**硬约束**：最终结果必须满足的条件（数值区间/单位/最少引用论文数）

**验收**：交付物清单（文件名、字段名、格式）

**禁止写**：步骤 1/2/3、伪代码、推荐方法清单、推荐函数清单。

**至少 1 个任务的"答题要求"包含"从 `paper_extractions.yaml` 中提取 ≥ N 个独立数值（精度 / 灵敏度 / 比例 等）"**——这是把 W 类信息变成解题硬依赖的机制。**禁止**改写为"引用 ≥ N 篇非主论文 paper_id"——见铁律 §R1/R2。

## 不需要做的事情
至少 5 条边界（参赛者不必做的事），例如：
- 不需要从头做 Rietveld 精修——直接使用题目提供的数据
- 不需要 digitize 原文的图表——数值已直接给出
- 不需要做 DFT 计算验证缺陷形成能
- 不需要覆盖 cluster_N 中的所有论文
- 不需要讨论 XX 的完整热力学

## 提交物
CSV/JSON/PNG/report.md 等文件清单 + 必含字段

例如：
- `tolerance_factor.csv`
- `tolerance_factor.json`（包含字段 `t_pure_BT`、`delta_r_A_site_Å`、`preferred_site_by_size`）
- `phase_analysis.csv`
- `phase_plot.png`
- ...

> 注：内容由 AI 生成，部分 ground truth 为 reverse-derived（公式反向生成），非原文实测值。

## 附录 A：题目正文暴露的数值溯源
**★ 强制：仅列题目正文出现过的 A 类锚点（通常 ≤ 3 行）**

| 数值 | 类别 | 来源 | 说明 |
|------|------|------|------|
| r(Ba²⁺) = 1.61 Å (12-coord) | **A** 原文直接报告 | Section 3.2, L76 | 原文明确给出 |
| r(Ti⁴⁺) = 0.605 Å (6-coord) | **A** 原文直接报告 | Section 3.2, L88 | 原文明确给出 |
| Tc = 87 K | **A** 原文直接报告 | Section 3.1, L13 | 零电阻 Tc |

**完整 ground truth（B/C/D/E/W）不在此处，在 `_solution.md`**。
```

#### 5c. 进入 Part II

题目正文定稿并通过 §5d 自检后，执行 **Part II — Phase 6**，生成**一份** `{标题}_solution.md`（内嵌参考 JSON 与评分 YAML）。若用户不需要阅卷包，可跳过 Part II，但不得声称具备自动评分能力。

#### 5d. 最终检查（必做，仅题目正文）

**自检清单**（写完题目正文后逐条核对）：

**自检 A：内容与措辞**

- [ ] **暴露率检查**：题目正文里的 A 类数值 ≤ 3 个？
- [ ] **任务格式检查**：任务段是否还有"步骤 1：… 步骤 2：…"或推荐方法/函数清单？应该全是"目标 / 答题要求 / 交付物"。
- [ ] **W 类任务检查**：至少 1 个任务的"答题要求"写了"从 yaml 中提取 ≥ N 个独立数值（精度 / 灵敏度 / 比例 等）"？（**注意**：要求**数值**而非"paper_id"）
- [ ] **资源索引检查**："参考资源"段是否给出了 ≥ 3 类资源（yaml + chain + md/decision_tree/review）的指针？
- [ ] **workflow 依赖检查**：关掉 workflow 文件夹，**仅看题目正文**，能不能完成任意一个任务的最终数值？能 → 回 Phase 4b 精简。
- [ ] **硬约束检查**：每个任务的"答题要求"包含**至少 1 个可验证条件**（数值区间 / 最少数据点数 / 精度要求）？
- [ ] **文件命名检查**：题目文件名**不带数字编号、不带 cluster 编号**？
- [ ] **引用与免责声明检查**：末尾仅列已知条件来源（≤ 3 行量级）？6 类溯源完整表只放 `_solution.md`？

**自检 B：字段政策（铁律 R1–R5 grep 自检——0 命中才能进 Part II）**

```bash
# (B1) 题面不得出现 paper_id 字面值（即使作为标识列）
rg -n 'paper_id' {标题}.md | rg -v '<workflow_dir>/md/<main_paper>'    # 期望 0 行

# (B2) 题面 fenced JSON skeleton 中不得出现禁列字段
rg -n -P '"(paper_id|quote|citation|reason|rationale|explanation|argument|comparison_argument|attribution_quote_from_paper|paper_attribution_quote_with_section|precision_quote|yaml_field|key_difference_from_main_paper|pitfall_source|advantage|disadvantage)"\s*:' {标题}.md   # 期望 0 行

# (B3) 题面 JSON skeleton 中不得出现自由文本占位（"<…>" / "<≤N 词>"）
rg -n -P ':\s*"<[^"]*(原文|说明|理由|引文|论述|≤\s*\d+\s*词)[^"]*>"' {标题}.md   # 期望 0 行

# (B4) 任何"必须引用 paper_id"类硬约束必须改写
rg -n '必须引用.*paper_id|引用具体的 paper_id|引用 yaml 字段名' {标题}.md   # 期望 0 行
```

**如果任何一项命中，返回 Phase 4 / Phase 5 修复**。修复方法见铁律 §R3 BAD↔GOOD 对照表。

---

## 数值的 6 类可信度

每个出现在题目 ground truth 里的数值都标注 1 类（在题目末尾的"附录 A"或 `_solution.md` 集中列出）。注意半开放题新增 **W 类**：

| 类 | 含义 | 是否暴露到题目正文 | 例子 |
|----|------|:-:|------|
| **A** 原文直接报告 | yaml 与主论文 md 字面一致 | 仅当作"题目锚点"时（≤ 3 个） | λ=2500 Å（原文 L27） |
| **B** 原文派生 | 由 A 类参数 + 公式反推 | ❌ | Jc(0)=1.02×10⁷ A/cm²（由原文 6μm@10K=9×10⁶ + 公式 (2) 反推） |
| **C** 题目作者反算自洽 | 依赖 A 类参数让 reverse-derived 自洽 | ❌ | ln(E₀/E)=13.3 |
| **D** 题目作者凭空设定 | 无原文/yaml 依据，仅作 ground truth | ❌ | a=0.010、Jc^b=6×10⁶ |
| **E** 题目作者诠释性修改 | 与原文字面有偏差但物理一致性更好 | ❌ | 公式 (3) 中 T → T_c |
| **W** Workflow 跨论文派生 | 来自 cluster 内**非主论文**的 yaml/md，参赛者必须自己查 | ❌（必须留白，否则跨论文对照任务退化为送分） | 同主题 paper Y 报告的 a=0.012、paper Z 报告的方法选择规则 |

**半开放题的强制要求**：
- 出题人 ground truth 中至少有 **2 个 W 类数值**（确保至少 1 个任务依赖 cluster 其它论文）
- 题目正文中暴露的 A 类锚点 ≤ 3 个
- 暴露率（题目正文 ground truth 数 / 总 ground truth 数）≤ 25%

---

## 题目骨架（半开放，统一题型）

**关键写作纪律——参赛者视角原则**：

题目正文是**交付给参赛者的科研挑战说明书**，不是出题设计文档。措辞必须以参赛者第二人称为准，**不能出现任何描述出题过程的元语言**。常见出题人术语 vs 参赛者视角措辞对照：

| 出题人术语（**禁止**出现在题目正文中） | 参赛者视角措辞（**应该**用） |
|---|---|
| "题目正文""本题正文""题目正文唯一直接给数值的部分" | 直接用段落标题（"已知条件"等）承担说明，不再加这种 meta 语句 |
| "锚点""暴露""留白""暴露率" | "已知条件""给定""所有其它…请从…获取" |
| "ground truth""溯源对照""A/B/C/D/E/W 类" | "已知值""引用与免责声明"；不在题目正文出现可信度分类 |
| "出题人""我们" | 不出现；用第三人称或祈使句 |
| "半开放""复现题""与旧版的差别" | 不出现版本对比 |
| "你必须打开 workflow""逼你自己拼出推理路径""具体值的获取本身就是考核" | 不出现；让"参考资源"段自然承担引导 |
| "本节是…唯一直接给数值的地方""本表仅指向位置，不给具体值" | 删除整句 meta；让段落本身的内容承担说明 |
| "故意留白""故意拆开" | 不出现；让任务的"答题要求"自然约束 |
| "附录 A：题目正文暴露的数值溯源""暴露率检查" | 改名为"引用与免责声明"，仅列已知条件来源；**没有**暴露率统计 |
| 任务正文中的"提示：思考 X 是从 Y 还是 Z 得到——两者差 N 倍" | 删除；这种泄答提示属于评分内部，应放到 `_solution.md` |

下面是骨架，**段落名以参赛者友好的名字命名**，每节按主题需要扩充/合并，但**任何一节都不能退化成"完整公式 + 完整数据 + 完整步骤"**：

```markdown
# {标题}

> 难度 | 预计耗时 | 标签
> （**不写**cluster 编号）

## 概述              # 1–2 段。第一段：系统/物理背景 + 主论文报告了什么；
                     # 第二段：本题要求完成 N 件什么工作（粗粒度，不规定步骤）。
                     # 不写"任务目标""半开放""旧版差别"等元语言。

## 主论文            # **学术引用**（作者 + 期刊 + 年 + DOI）+ 一句话主题。
                     # **禁止**写 paper_id 列、cluster 编号；
                     # 主论文 md 路径用占位词，例如：
                     #   主论文原文位于 `<workflow_dir>/md/<main_paper>.md`
                     # 不在题面写出真实 paper_id（即使作为文件名也优先用占位词）。

## 已知条件          # ≤ 3 个 A 类核心数（参考值 / 包络 / 标定常数）+ 必备公式（≤ 2 个）。
                     # 用中性子标题命名各组数（"参考值""包络""物理常数""公式"），
                     # **不写**"题目正文唯一直接给数值的部分""锚点 1/2/3"等 meta 描述。

## 参考资源          # ★ 半开放题的核心入口。
                     # 引导句：随题分发的工作流产物目录记为 `<workflow_dir>/`，结构如下：
                     # 表格列出资源类型 + 路径，每行说明该资源用于哪个任务。
                     #   - 主论文 md 的哪些章节
                     #   - paper_extractions.yaml 的字段结构（不点名具体值）
                     #   - selected_chains.json 的索引方式
                     #   - decision_tree.{dot,pdf,png} 与 review_cluster_N.{tex,pdf}
                     #   （workflow_3layer.md / workflow_structure.json / step_statistics.json 为可选辅助）
                     # **不写**"只指向位置不给具体值""具体值的获取本身就是考核"等 meta；
                     # 用一句中性的"提取的数值需在交付物中标注来源"自然承担同等约束。
                     # 用 `<workflow_dir>/` 变量名而非具体 cluster_N 路径。

## 任务（Tasks）       # ★ 数量自由（推荐 2–4 个），统一节奏。
                     # 每个任务严格按"目标 / 答题要求 / 交付物"三段式：
                     #
                     #   ### 任务 X：{1 句话目标}
                     #   **目标**：要回答的具体问题（仍是粗粒度）
                     #   **答题要求**：最终结果必须满足的条件（数值区间/单位/最少引用论文数）
                     #   **交付物**：交付清单（文件名、JSON 字段示例、必含字段）
                     #
                     # **禁止写**：
                     #   - 步骤 1/2/3、伪代码、推荐方法清单、推荐函数清单
                     #   - "提示：思考 X 是从 Y 还是 Z 得到——两者差 N 倍"等泄答式提示
                     #   - "必须引用具体的 paper_id"、"引用 yaml 字段名"等违 R1/R2 的措辞
                     # 跨论文证据要求改为**数量 + 数值**形式：
                     #   ✅ "从 paper_extractions.yaml 中提取 ≥ 4 个独立精度量级（百分数）"
                     #   ❌ "必须引用至少 4 个非主论文 paper_id"
                     # 提交字段（JSON skeleton）严格遵守 R2：仅 numeric / boolean / enum / numeric-array。

## 不需要做的事情    # 至少 5 条边界（参赛者不必做的事）

## 提交物            # CSV/JSON/PNG/report.md 等文件清单 + 必含字段

## 引用与免责声明    # 简短一段：主论文学术引用 + 物理常数来源 + 1 句免责声明
                     # （"内容由 AI 综合生成，部分派生量为反向推算所得，非独立实测"）。
                     # **不写**"附录 A""暴露率检查""6 类溯源对照表"。
                     # 完整 ground truth（A/B/C/D/E/W 分类、推理路径、评分维度）
                     # **全部**只在 `_solution.md`，不在题目正文。
```

**`{标题}_solution.md` 及内嵌 JSON/YAML 的章节骨架**见下文 **Part II — Phase 6**（此处不重复，避免 Part I / Part II 内容分叉）。

**关键说明**：

- "主论文"表格保留 paper_id 与论文学术引用，但**不写 cluster 编号**。
- "已知条件"段是题目正文**事实上**唯一直接给数值的段落，但**段落标题不写"唯一直接给数值"**——让段落本身承担说明。任何超过 3 个 A 类数值的题目都需要回到 Phase 4b 重新精简。
- "参考资源"是题目的**进入门槛**——没有它，题目退化为单论文复现题。引导句自然描述"完成本题需要查阅以下资源"，**不**用"必须打开 workflow""具体值的获取本身就是考核"等出题意图陈述。约束改用中性的"提取的数值需在交付物中标注来源"承担。
- 任务三段式"目标 / 答题要求 / 交付物"**不写步骤**。如果你发现自己在写"步骤 1：…步骤 2：…"，停下来，把它移到 `_solution.md` 的"推理路径参考"。
- 题目正文**不出现**"附录 A""暴露率""6 类溯源"等出题人术语。引用与免责声明段只列已知条件出现的常数和论文引用。完整 ground truth、暴露/留白决策记录、推理路径、评分维度**全部**只在 `_solution.md`。
- **每个任务的"交付物"应包含具体的文件名和 JSON 字段示例**，让参赛者知道要提交什么。

---

## Part II — Solution 与评分细则（交付物：**仅** `{标题}_solution.md`）

### 与 Part I 的衔接

| 输入（Part I 已具备） | 用途 |
|----------------------|------|
| `{标题}.md` 定稿 | 提取「提交物」文件名与 JSON 字段契约（**唯一字段真相来源**） |
| `_verification_table.md`、`_ground_truth_draft.md`（或等价核账输出） | 填写 ground truth 表与参考数值 |
| Phase 4 留白决策 | 「暴露/留白决策记录」章节 |

| 输出 | 说明 |
|------|------|
| **`{标题}_solution.md`（单文件）** | 含：① 文首说明与配套题目名；② 完整 6 类 ground truth 表；③ 暴露/留白记录；④ 推理路径；⑤ **多个** ` ```json ` 块——每块对应题目要求的一个提交文件名（如 `task1_….json`），块标题注明文件名；⑥ **一个** ` ```yaml ` 块——完整评分规格（`meta`、`reference_values`、`global_fail`、`scoring`、`final_score`、`implementation_notes`）；⑦ 人工 Pass/Good/Excellent 表；⑧ `grading_result` 示例 JSON。**不向参赛者分发本文件。** |

**铁律**：题目正文**不得**出现本 `_solution.md` 的路径、不得出现「内嵌 YAML / 标准答案」等泄题表述。实现自动评分时：**先**从 `_solution.md` 提取 fenced YAML **字符串**解析；**正文叙述与 YAML 块冲突 → 以 YAML 块为准**；JSON schema **以题目「交付物」为准**，与 §⑤ 各 ` ```json ` 块对齐。

---

### Phase 6 — 编写 `{标题}_solution.md`（一步完成）

1. **§1–§2**：ground truth 表 + 暴露/留白记录 + 推理路径（可含泄答级提示）。
2. **§3 参考答案**：对每个题目要求的 `*.json` 交付物，写一个 **三级标题**（如 `### 3.1 task1_self_consistency.json`）+ **一个** ` ```json … ``` ` 块；块内对象与题目 schema **字段级一致**。
3. **§4 自动评分规格**：**一个** ` ```yaml … ``` ` 块，包含与题目硬约束对齐的 `global_fail`、`scoring.tasks.*.checks`、`task_weights`、`final_score`、`implementation_notes`。`reference_values` 应与 §3 核心数一致。
4. **§5–§7**（可选）：人工等级表、`grading_result` 示例、优先级声明（§4 YAML 块为机读单一事实来源）。

**勿**默认再创建同目录 `*_scoring.yaml` 或 `reference_answers/`——除非用户显式要求多文件 CI。**范例（单文件全套）**：`data/Superconductivity/workflows_top50/cluster_60/challenge/PSTR泄漏场踢角自洽闭环与跨论文测量精度对账_solution.md`。

---

### Phase 6 自检清单

**自检 A：解析与对齐**

- [ ] `_solution.md` 中每个 ` ```json ` 块可被 `json.loads` 解析；字段集合与题目「交付物」schema **完全一致**（无缺漏、无多余）
- [ ] `_solution.md` 中**唯一的** ` ```yaml ` 块可被 `yaml.safe_load` 解析；`reference_values` 字段与各 ` ```json ` 参考答案核心数一致；`global_fail` 覆盖题目全部硬约束；`task_weights` 之和 = 1.0；每 task 各 `checks.points` 之和 = `max_points`
- [ ] 题目正文**零提及** `_solution.md` 内具体数值、路径或"评分 YAML"字样
- [ ] 文内声明：**正文与 §4 YAML 块冲突时以 YAML 块为准**

**自检 B：字段政策（铁律 R1–R5 grep 自检——0 命中才能定稿）**

```bash
# (B1) 解决方案的参考 JSON / 评分 YAML 中不得出现禁列字段
rg -n -P '"(paper_id|quote|citation|reason|rationale|explanation|argument|comparison_argument|attribution_quote_from_paper|paper_attribution_quote_with_section|precision_quote|yaml_field|key_difference_from_main_paper|pitfall_source|advantage|disadvantage)"\s*:' {标题}_solution.md   # 期望 0 行

# (B2) 评分 check 不得依赖自由文本（substring_any / string_length_min / custom_note 等 NLP 类型必须有数值替代）
rg -n -P 'type:\s*(substring_any|string_length_min|custom_note|nlp_match)' {标题}_solution.md   # 期望 0 行；
                                                                                                # 如需"判断 agent 是否读到主论文 PBH2 段"，
                                                                                                # 改用 boolean_equals + agent 给出的 boolean 答案

# (B3) 评分字段类型只能用 numeric_close / numeric_pair / range / abs_threshold /
#      array_length_min / array_distinct_min / array_min_below_field / array_all_in_range /
#      enum_equals / enum_in / boolean_equals / required_fields / nested_required /
#      ratio_cluster_tolerance —— 见铁律 §R5
```

**自检 C：交叉一致**

- [ ] 题目正文 §"答题要求"出现"≥ N 个数值/精度/比例"，对应 §4 YAML 中**每条**都有可机判 check（无悬空硬约束）
- [ ] `_solution.md` §1 ground truth 表的 W 类条目（来自非主论文的 yaml）已在内部记账列出真实 paper_id —— **仅供出题人/评分人内部追溯**，不向参赛者分发
- [ ] 跑过 PSTR 类型快验：解析所有 fenced JSON / YAML，对每 task 校验 schema 字段一致 + 权重和 = 1.0 + checks 总分 = max_points

---

## 关键陷阱（必看）

> 陷阱 1–11 主要作用于 **Part I（出题）**；陷阱 12 作用于 **Part II（`{标题}_solution.md` 内嵌 JSON/YAML）**。

### 陷阱 1：跳过 md 核账，仅用 yaml

**后果**：yaml 字面失真或单位错抄会原样进入题目。

**防护**：Phase 3 必做，不可跳过。

**实例**：cluster_12 中 yaml 公式 `α = (k_B·T/U_p)·ln(E₀/E)` 字面有 T，但 α 是常数，物理一致性要求 T → T_c。不核账会导致 U_p 反推偏差 100 倍。

---

### 陷阱 2：把 Layer3 / workflow_3layer 第三层的"输入示例"当原文实测

**症状**：`workflow_3layer.md` 第三层（实现层）中**带 `# 表格格式: ...` 注释的代码块通常是 LLM 编造的占位**，不是 digitize 的原文图表数据。

**识别特征**：
- 标题写"输入格式"或"数据预处理"
- 第一个数据点恰好等于原文文字的某个值，其余圆整或完美单调
- 数据点数量恰好是 5 或 10（LLM 喜欢的数量）

**防护**：第三层中的具体数字默认视为 LLM 编造，除非能在原文 md 找到逐字对应。

**正确做法**：只从第三层提取**方法名、参数名、公式形式**，具体数值必须从 Phase 2 的 `paper_extractions.yaml` 或 Phase 3 的原文 md 中提取。

---

### 陷阱 3：D 类参数数量级与同 cluster 其它论文相差太多

**症状**：题目作者凭空设定的 D 类参数（如边缘势垒参数 `a = 0.010`）与同 cluster 其它论文报告的数量级相差 >10 倍。

**后果**：参赛者查 workflow 时发现数量级矛盾，怀疑题目数据错误。

**防护**：D 类参数应在同 cluster 其它论文 yaml 里找到数量级背书。若材料/几何不同导致差异大，可接受但需在附录 A 注明。

**实例**：cluster_12 中 YBCO 的 `a = 0.010`，Kim 等人对 Nb 薄膜报告 `a ∈ [2.2×10⁻⁵, 1.7×10⁻³]`。虽然材料不同，但数量级在同一区间（10⁻³ ~ 10⁻²），可接受。

---

### 陷阱 4：yaml 区间被压窄

**症状**：yaml 经常把 `0.1–0.15 eV` 抽成 `≈100 meV`，丢失不确定度信息。

**后果**：题目给出的"硬约束"过于严格（如"U_p 应等于 100 meV"），参赛者算出 110 meV 被判错。

**防护**：看到 `≈` 形式的值时，回原文 md 找完整区间，写题时**用区间**而非点估值。

**正确写法**：
- ❌ "U_p 应等于 100 meV"
- ✓ "U_p 应落在 0.1–0.15 eV 范围内"

---

### 陷阱 5：step_statistics.json 中低覆盖率路径被选为主线

**症状**：选择了覆盖率 < 20% 的路径作为题目主线。

**后果**：该路径可能只出现在 1-2 篇论文中，缺乏 workflow 内交叉验证，题目素材不足。

**防护**：优先选覆盖率 ≥ 50% 的阶段组合作为主线。如果所有阶段覆盖率都 < 50%，选覆盖率最高的 3-4 个阶段，并在题目中标注"本题基于 A 类主线链（覆盖率 X%）"。

---

### 陷阱 6：遗漏 reverse-derived 标注

**症状**：题目中的 benchmark 数据（如 Jc(w) 5 个点）是由公式反向生成的，但题目没有标注。

**后果**：参赛者误以为是独立实测值，尝试用不同公式拟合，发现拟合不上，怀疑题目数据错误。

**防护**：所有 benchmark 数据必须在题目中明确标注为 reverse-derived（公式反向生成），不能让参赛者误以为是独立实测值。在"题目锚点"和"附录 A"中都要标注。

**正确写法**：
```markdown
## 数据与资源

### 1. Jc(w) 基准（reverse-derived，T = 10 K）

| 条带宽度 w (μm) | reverse-derived Jc (10⁶ A/cm²) |
|----------------:|-------------------------------:|
| 2.0             | 14.75                          |
| ...             | ...                            |

> **数据生成参数（同时也是 Milestone 1 的 ground truth）**：
> `Jc^e = 1.50×10⁸ A/cm²`、`Jc^b = 6.00×10⁶ A/cm²`、`a = 0.010`、`λ⊥ = 0.75 μm`。
> 由公式 (1) 反向计算得到。**不要**将这些参数直接写入拟合输出，需通过对 benchmark 的拟合复原它们。
```

---

### 陷阱 7：题目正文泄露太多，workflow 沦为装饰

**症状**：题目正文写完了完整公式列表 + 完整 benchmark 数据 + 5–7 步箭头路径——agent 不打开 workflow 也能 90% 还原。

**后果**：workflow 沦为可有可无的装饰，题目退化为单论文复现题。

**自检清单**（写完题目正文后逐条核对）：
1. 题目正文里的 A 类数值 ≤ 3 个？
2. 任务段是否还有"步骤 1：… 步骤 2：…"或推荐方法/函数清单？应该全是"目标 / 硬约束 / 验收"。
3. 至少 1 个任务的"答题要求"写了"从 yaml 中提取 ≥ N 个独立数值（不是 paper_id）"？
4. "Workflow 资源索引"段是否给出了≥ 3 类资源（yaml + chain + md/decision_tree）的指针？
5. 关掉 workflow 文件夹，**仅看题目正文**，能不能完成任意一个任务的最终数值？如果能 → 题目泄露过多，回 Phase 4b 重新精简。

**防护**：严格执行 Phase 4b 的暴露率控制（≤ 25%）和 Phase 5d 的自检清单。

---

### 陷阱 8：硬约束太松，半开放变没约束

**症状**：任务只写"自由探索 X 现象"，没有任何最终交付的数值/区间约束——参赛者交什么都说得过去，无法评分。

**后果**：题目变成开放式研究题，失去"半开放"的精确性。

**防护**：每个任务的"硬约束"必须包含**至少 1 个可验证条件**，例如：
- 最终结果落入区间 [x, y]（必给区间）
- 至少给出 ≥ N 个对比数值（数组形式提交）
- 必须报告不确定度估计
- 从 `paper_extractions.yaml` 中提取 ≥ M 个独立数值（**不**要求 paper_id）

**正确写法**：
```markdown
**答题要求**：
- 最终 t(BaTiO₃) 应落在钙钛矿稳定范围 0.88 < t < 1.06
- 从 `paper_extractions.yaml` 中提取 ≥ 2 组离子半径数据（数值数组形式提交，元素 ≥ 2 个 distinct）
- 相对误差 ≤ 5%
```

**反例**（违反铁律 §R1）：

```markdown
- ❌ 必须引用 ≥ 2 篇 cluster 内非主论文 paper_id
- ❌ 必须给出 yaml 字段名与原文引文片段
```

**半开放 ≠ 无约束**。开放在"路径"上（不规定步骤），不在"答案区间"上（必须给验收标准）。

---

### 陷阱 9（新增）：Phase 1 选题时未检查 A 类链数量

**症状**：选定的主线只有 1-2 条 A 类链支撑，素材不足。

**后果**：Phase 2 深度提取时发现可用论文 < 3 篇，无法构造跨论文对照（W 类）任务。

**防护**：Phase 1 结束时检查 A 类主线链数量：
- A 类链 ≥ 3 条：✓ 素材充足，继续
- A 类链 < 3 条：⚠️ 素材不足，考虑：
  1. 纳入 B 类链作为阶段内案例补充
  2. 或换另一条覆盖率更高的主线
  3. 或向用户报告"该 cluster 素材不足以出半开放题"

---

### 陷阱 10（新增）：Phase 2 选主论文时未记录备选论文

**症状**：只选了 1 篇主论文，Phase 4 构造 W 类任务时发现没有其它论文可用。

**后果**：无法满足"至少 1 个任务依赖 W 类"的强制要求。

**防护**：Phase 2 选主论文时，同时记录排名 2-3 的备选论文作为 W 类数据源。确保备选论文与主论文在同一主题下（如都研究 BaTiO₃ 掺杂，或都研究 YBCO 临界电流）。

---

### 陷阱 11：题目正文混入出题人元语言

**症状**：题目正文里出现"题目正文""锚点""暴露/留白""ground truth""出题人""半开放""与旧版差别""你必须打开 workflow""具体值的获取本身就是考核""暴露率检查""附录 A：题目正文暴露的数值溯源"等出题设计文档术语，把"科研挑战说明书"伪装成"出题工程文档"。

**后果**：

1. 参赛者读题时立刻能感觉"这是个特殊设计的题"，破坏自然科研挑战感；
2. 暴露出题意图（如"故意留白""逼你查 workflow"），让参赛者从一开始就调整策略，反而降低题目区分度；
3. 任务正文里的"提示：思考 X 是从 Y 还是 Z 得到——两者差 N 倍"等泄答式提示，直接降低任务难度。

**自检**（写完题目正文后**必做**，用以下 grep 命令扫一遍，命中即修）：

```bash
rg -n '题目正文|本题正文|本节是.*唯一直接给|锚点|暴露|留白|出题人|ground truth|溯源对照|6 类|半开放|与同主题旧版|与上一版|工作流产物中——|你必须打开 workflow|具体值的获取本身就是|本表仅指向位置|附录 A.*暴露|暴露率' {题目文件}.md
```

期望输出：**0 行命中**。任何命中都需修复或迁移到 `_solution.md`。

**正确替换措辞**（参赛者视角）：

| 反例（删除） | 正例（替换） |
|---|---|
| "题目正文唯一直接给数值的部分" | 删除整段，让"已知条件"标题自然承担 |
| "本题正文只给 3 个数值锚点 + 2 个公式" | 删除整段；让"已知条件"段直接列出 3 个值 + 2 个公式 |
| "**资源指针只指向位置，不暴露具体数值**——具体值的获取本身就是题目对你的考核" | "提取的数值需在交付物中标注来源，以便核对引用" |
| "**关键约束**：本表仅指向位置" | 删除；让段落本身的内容承担说明 |
| "其余推理所需的全部实测值、定义公式、方法选择与跨论文对照量级，**均散布在工作流产物中**——你必须打开 workflow 自己拼出推理路径" | "本题要求结合主论文与工作流产物中的若干其它论文，完成 N 件相互独立但物理上关联的工作" |
| "与同主题旧版题目的差别：旧版直接列出全部 26 个 A 类实测数值..." | 删除整段；版本对比是 `_solution.md` 的内容 |
| "提示：思考 BL_leak 是从场测量直接得到，还是从 beam study 得到——两者差 ~3.4 倍" | 删除整段（泄答提示）；如必要将简化版提示放 `_solution.md` 评分手册 |
| "**(锚点 1) 自洽闭环目标值**" | "**注入能量参考值**"（用物理量名命名，不用"锚点"） |
| "唯二在题目正文给出的公式" | 删除前缀；只写"两个公式"或"必备公式" |
| "## 附录 A：题目正文暴露的数值溯源" | "## 引用与免责声明"（仅列已知条件来源；无暴露率统计） |
| "暴露率检查" 段 | 整段删除；移到 `_solution.md` 的"暴露/留白决策记录" |

**防护**：

1. Phase 5 组装题目时，每写完一段就过一遍上述对照表
2. 写完题目正文整篇后，**强制运行**自检 grep（命中即修）
3. 任何描述"出题过程""暴露/留白决策""我们如何设计这道题"的话，**默认应该在 `_solution.md`**

---

### 陷阱 12：题目或提交字段出现 `paper_id` / 自由文本（违反铁律 R1–R5）

**症状**（任一条命中即陷阱）：

1. 题面"主论文"段写 `paper_id: 812367014646513665` / 表格列里有 `paper_id` 列
2. 题面 "答题要求" 写 `必须引用具体的 paper_id` 或 `引用 yaml 字段名`
3. 提交物 JSON skeleton 含 `"paper_id": "..."` / `"quote": "..."` / `"reason": "..."` / `"rationale": "..."` / `"key_difference_from_main_paper": "..."` / `"advantage": "..."` 等
4. `_solution.md` 的参考 JSON 或评分 YAML 同样出现以上字段；或评分 YAML 用 `substring_any` / `string_length_min` 等 NLP 检查
5. 题目正文 fenced JSON 块内用 `"<≤ 30 词原文>"` / `"<…理由>"` 这种"自由文本占位"

**后果**：

- agent 看不到 cluster 的 paper_id 索引体系，被迫**凭空猜或瞎填**
- 自由文本字段无法机判，评分会退化到 NLP/LLM-as-judge，结果脆弱
- 多次重试时同一道题给不同分

**真实案例**（必须避免）：

- `data/challenge/fluid_mechanics_2/磁化等离子体...md` 把主论文 paper_id 写在题面、提交 JSON 用 `paper_id` / `key_difference_from_main_paper` / `advantage` / `disadvantage` 等自由文本字段——典型反例。

**防护**：

1. **顶部铁律 §R1–R5 必读**：题目+提交字段全部走 numeric / boolean / enum / numeric-array
2. **Phase 5d 自检 B（grep）** + **Phase 6 自检 B（grep）** 必须 0 命中
3. 跨论文证据用**数值数组 / 数量约束**承担，例：`"cross_paper_precision_percentages": [<float>×4+]` + `array_distinct_min: 4`，而非 `"cross_paper_table": [{"paper_id": ..., "quote": ...}]`
4. 出题人内部需要的 paper_id / 引文记账放进 `_solution.md` §1 ground truth 表（W 类条目），**仅供评分人查证**，不进参赛者交付物

**后果**：评分 agent 解析失败、误判 Pass/Fail。

**防护**：

1. **默认单文件**：全部落在 `{标题}_solution.md`，避免多路径同步。
2. 以题目「交付物」为**唯一** JSON schema 契约；Part II 结束跑 **Phase 6 自检**。
3. 题目正文禁止泄题（见 Part II 铁律）。

---

## 标杆产出

### 早期复现题标杆（结构参考，但难度偏低，新题不要直接照搬骨架）

| 文件 | 角色 |
|------|------|
| `docs/2. Bean模型磁滞回线宽度推导MgB₂临界电流密度.pdf` | 题目格式标杆 |
| `docs/3. 边缘势垒+磁通蠕变拟合YBCO窄条带临界电流密度.md` | 标杆，含完整附录 A 五类溯源范例 |
| `docs/BaTiO₃位选择掺杂中Ce占位判定与缺陷机制归因.md` | 标杆，材料科学多维证据整合范例 |
| `data/Superconductivity/workflows_top50/cluster_60/challenge/J-PARC_RCS脉冲偏转磁体涡流漂移与泄漏场分析.md` | 标杆，主论文严格自洽 + 反算闭环示例 |

> 这些早期题目**只用单论文 + 完整公式 + 完整路径**就能解，workflow 沦为可选参考。新题应按半开放骨架出，**不**直接照搬这些骨架。

### 半开放题标杆（Part I + Part II）

| 部分 | 文件 | 角色 |
|------|------|------|
| **Part I** | `data/.../cluster_60/challenge/PSTR泄漏场踢角自洽闭环与跨论文测量精度对账.md` | 题目正文标杆 |
| **Part II** | `.../PSTR泄漏场踢角自洽闭环与跨论文测量精度对账_solution.md` | **单文件**：ground truth + 内嵌参考 JSON + 内嵌评分 YAML + 人工表 + grading 示例 |

**全套应满足**：

1. **Part I**：A 类已知条件 ≤ 3 个；≥ 1 个任务要求"从 yaml 中提取 ≥ N 个**数值**"（不要求 paper_id）；关掉 workflow 后无法仅凭题面完成任一数；陷阱 11 grep 0 命中；**铁律 §R5 grep 自检 B1–B4 全 0 命中**。
2. **Part II**：仅 `_solution.md`；Phase 6 自检 A/B/C 全部通过；陷阱 12 全部 0 命中；提交字段全为 numeric / boolean / enum / numeric-array。

新题目**文件名不要带编号前缀**，**正文不暴露 cluster 编号**（用 `<workflow_dir>/` 变量名）。

---

## 与 Workflower 的关系

```
论文聚类 → Workflower → 工作流产物（含 cluster 编号目录） → WorkflowChallenger
                                                          → Part I: {标题}.md
                                                          → Part II: {标题}_solution.md（内嵌 JSON + YAML）
                                                          ↑
                                                + 1 篇主论文 md
```

WorkflowChallenger 只读 Workflower 的产物（cluster 编号在工程内部使用），不修改任何 workflow 文件；题目正文**不暴露 cluster 编号**；**保存路径完全由用户指定**。
