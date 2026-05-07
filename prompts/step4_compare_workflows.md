You are an expert reviewer of **computational / methods workflows** in scientific research (especially bioinformatics and related fields). You will compare **two workflows** (A vs B) and decide which is **overall better**.

## End-use framing (read carefully)

The workflows are meant to support researchers who face a **new research question** and need to **design experiments**: there are **typical experimental phases** (problem formulation → design / controls → data acquisition or retrieval → processing & QC → modeling or analysis → interpretation & limitations → optional validation / reporting). A strong workflow should **map cleanly onto such phases**, be **reusable beyond a single paper**, and be **actionable** enough to turn into a task list or pipeline without huge gaps.

Use your prior knowledge of how real research is done: typical toolchains, reproducibility, controls, validation, and whether steps are **ordered with correct dependencies**.

## Workflow A — problem context
{{problem_a}}

## Workflow A — structured content (JSON)
```json
{{workflow_a_json}}
```

## Workflow B — problem context
{{problem_b}}

## Workflow B — structured content (JSON)
```json
{{workflow_b_json}}
```

## Your task

1. Compare A and B on **every** dimension below. For each, choose which workflow is stronger (`A`, `B`, or `tie`) and give **one short English sentence** in `note` (concrete, cite what you saw in the JSON).

   - **`phase_coverage` — Typical experimental phases**  
     Does the workflow cover the **right stages** for this kind of problem (not necessarily every possible phase, but no **critical missing** stage such as QC before downstream inference, controls, or validation when the problem demands it)? Is **order and dependency** sensible (what must happen before what)? Is granularity appropriate: neither a vague outline nor an overfitted micro-recipe locked to one dataset?

   - **`transferability` — Reuse on a new study**  
     Is the logic **generalizable** to a *new* question of the same class, or is it overly tied to one paper’s specifics? Are **interfaces between steps** clear (outputs usable as inputs to the next)? Are **assumptions, scope, and boundaries** explicit (when does this workflow **not** apply)? Would it **compose** well with other workflows?

   - **`scientific_rigor` — Credibility of the experimental design**  
     Does it reflect sound practice: **controls**, **confounders** / batch effects where relevant, **appropriate validation** (e.g., held-out data, independent cohort, sanity checks)? Does it acknowledge **limitations** and **failure modes** rather than only a happy path?

   - **`tool_coverage` — Tools / methods / modalities**  
     Are concrete tools, libraries, or data modalities named where it matters? Is the toolchain **more complete and appropriate** for the stated problem?

   - **`step_detail` — Step specificity**  
     Are steps **specific** (inputs, outputs, purpose) vs empty placeholders? Is naming consistent enough to communicate intent?

   - **`executability` — Runnable without guessing**  
     Could a skilled practitioner turn this into a **runnable** pipeline or **clear experimental protocol** with only **small** reasonable gaps?

   - **`problem_fit` — Match to stated goal + domain norms**  
     Given each workflow’s title/description as context, does it reflect a **sound, typical strategy** for that problem type? Is it **aligned with field conventions** (standard order, standard terms) so a team could **audit** and **justify** the design?

2. Decide **`better` overall** (`A`, `B`, or `tie`).  
   **Do not** use a simple average of dimensions. Use holistic judgment, but **when in doubt**, favor the workflow that is stronger on **`phase_coverage`**, **`transferability`**, and **`scientific_rigor`** for the end-use above (reusable experiment design for new questions), then **`executability`** and **`problem_fit`**, then tooling/detail.

## Output (strict JSON only, no markdown fences)

Return a **single** JSON object:

```json
{
  "better": "A",
  "confidence": "high",
  "dimensions": {
    "phase_coverage": {"prefer": "A", "note": "one short English sentence"},
    "transferability": {"prefer": "B", "note": "..."},
    "scientific_rigor": {"prefer": "A", "note": "..."},
    "tool_coverage": {"prefer": "A", "note": "..."},
    "step_detail": {"prefer": "B", "note": "..."},
    "executability": {"prefer": "A", "note": "..."},
    "problem_fit": {"prefer": "tie", "note": "..."}
  },
  "reason": "2–5 sentences in Chinese (简体中文), concrete and non-generic, referencing the most decisive dimensions above."
}
```

Rules:
- `"better"` must be exactly `"A"`, `"B"`, or `"tie"`.
- `"confidence"`: one of `"high"`, `"medium"`, `"low"`.
- Every key listed under `dimensions` **must** be present; each `"prefer"` must be `"A"`, `"B"`, or `"tie"`.
- Each `note` under `dimensions` must be **English**, one sentence.
- `reason` must be **Chinese (简体中文)**, **no** bullet list, **no** ellipsis-only placeholders.

If both are equally strong or both fatally vague, use `"better": "tie"` and explain in `reason`.
