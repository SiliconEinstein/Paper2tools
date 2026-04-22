You extract **tools, methods, software, datasets, and benchmarks** used in a specific reasoning chain from a research paper.

## Context

- **Conclusion id**: `{{conclusion_id}}`
- **Conclusion title**: `{{conclusion_title}}`
- **Reasoning steps**: A sequence of reasoning steps (provided as XML) that lead to this conclusion.
- **Full paper**: The complete paper content in Markdown format.

## Task

For each reasoning step in the provided `<reasoning>` block, identify which tools/methods/software/datasets/benchmarks are **substantively used** in that step. A tool is "used" if:
- The step describes applying the tool to compute results
- The step references data/models/parameters produced by the tool
- The step explains methodology involving the tool

Do **not** mark a tool just because its name appears in passing or in background discussion.

## Output (strict JSON)

Return **only** one JSON object, no markdown fences, no commentary:

```json
{
  "tools": [
    {
      "tool_id": "T1",
      "tool_name": "Density Functional Theory",
      "tool_description": "Used to compute adsorption structures, energies, and electronic properties."
    },
    {
      "tool_id": "T2",
      "tool_name": "VASP",
      "tool_description": "DFT software package used for all electronic structure calculations."
    }
  ],
  "links": [
    {"tool_id": "T1", "step_id": "1"},
    {"tool_id": "T1", "step_id": "2"},
    {"tool_id": "T2", "step_id": "1"}
  ]
}
```

Rules:
- `tools`: Array of tool objects, each with `tool_id` (e.g. "T1", "T2"), `tool_name` (canonical name), and `tool_description` (brief description of how it's used in this conclusion).
- `links`: Array of tool-step associations. Each object has `tool_id` and `step_id` (both strings).
- `step_id` must match an existing `id` attribute in the `<step>` elements.
- `tool_id` must be consistent across `tools` and `links` arrays.
- If no tools are found, return `{"tools": [], "links": []}`.

## Reasoning XML

{{reasoning_xml}}

## Full Paper (Markdown)

{{paper_content}}
