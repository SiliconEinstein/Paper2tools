You extract **external, operational artifacts** (software, platforms, data, models, hardware, and **only rarely** named algorithms/protocols) that are **substantively used** in a **single conclusion’s** reasoning chain. **Ground only in the paper and the provided `<reasoning>` XML**—do not invent tools or uses.

## Context

- **Conclusion id**: `{{conclusion_id}}`
- **Conclusion title**: `{{conclusion_title}}`
- **Reasoning steps**: XML under `<reasoning>` with `<step id="…">` … `</step>`.
- **Full paper**: Markdown for disambiguation (versions, URLs, official names).

## What counts as a tool here

Use **exactly one** of the following **`tool_category`** literals (same taxonomy as the project’s unified extractor; spell **identically**, including spaces and `/`):

| `tool_category` | Meaning (keep in English string as shown) |
|-----------------|-------------------------------------------|
| `Software Library/Framework` | Libraries, SDKs, DL frameworks, packages, toolkits (e.g. PyTorch, Biopython, NumPy). |
| `Specialized Software/Platform` | Standalone apps, web services, portals, workflow systems, notebooks **as a named product** (e.g. Galaxy, GEO web interface). |
| `Hardware/Instrument` | GPUs, lab instruments, robots, sequencers **named as equipment** the work depends on. |
| `Dataset` | **Named** benchmarks, corpora, public DB releases (e.g. TCGA, ImageNet) the step actually uses or cites as data source. |
| `Pre-trained Model` | Named checkpoints, weight releases, pretrained families **used as artifacts** (not generic “we use a transformer”). |
| `Algorithm/Protocol` | **Default: do not output.** Only if **all** of: (1) **stable public or author method name** (not “Lemma 3”, not a proof sketch); (2) **operational**—concrete procedure, parameters, code, or standard named pipeline; (3) **clearly invoked** in this step’s text. Otherwise **omit**. |

## Strong omit bias (not tools)

Do **not** emit rows for:

- Theorems, lemmas, definitions, proofs, “Proposition …”, symbolic notation as if it were software.
- Vague phrases: “we optimize”, “we train”, “neural network”, “baseline” **without** a **named** library/model/dataset.
- Passing mentions, background, or “related work” unless **this step** applies that artifact.
- Generic math (e.g. “gradient descent”) unless the paper ties it to a **named implementation** or **named protocol** that passes the AP rule above.
- Author’s **own method name** with **no** installable/fetchable artifact—unless it maps to released code/data/model with that name in the paper.

If nothing qualifies, return `{"tools": [], "links": []}`.

## Naming and description rules

- **`tool_name`**: Short **public** label, **≤ about 6 English words** (or established acronym: BLAST, VASP). **No** version tags in the name (`v2`, `3.1` → put in `tool_description`). **No** long LaTeX, theorem numbers, or section-only pointers as the name.
- Prefer **canonical product / resource names** as authors or the community use them (paper title, README, official site). Avoid vague labels like “Custom script”, “Baseline method”, “Deep learning model” unless the paper gives a **specific** name—then use that name.
- **`tool_description`**: One or two **self-contained** sentences: **what it is** and **how this conclusion’s reasoning uses it** in the cited step(s). No bare “see Table 1” without the fact. No ellipsis (`...`, `…`) as filler.
- **`tool_category`**: Required on every tool; must be one of the **six literals** in the table above.

## Output (strict JSON)

Return **only** one JSON object—no markdown fences, no commentary:

```json
{
  "tools": [
    {
      "tool_id": "T1",
      "tool_name": "PyTorch",
      "tool_category": "Software Library/Framework",
      "tool_description": "Deep learning framework used in this step to implement and train the network described in the paper."
    }
  ],
  "links": [
    {"tool_id": "T1", "step_id": "1"}
  ]
}
```

Rules:

- `tools`: each object **must** include `tool_id`, `tool_name`, `tool_category`, `tool_description`. IDs like `T1`, `T2`, … consecutive.
- `links`: each object has `tool_id` and `step_id` (strings). `step_id` must match an existing `id` on a `<step>` in the provided reasoning XML.
- Every `tool_id` in `links` must appear in `tools`.
- Prefer **fewer, higher-precision** tools over a long noisy list.
- If no qualifying tools: `{"tools": [], "links": []}`.

## Reasoning XML

{{reasoning_xml}}

## Full Paper (Markdown)

{{paper_content}}
