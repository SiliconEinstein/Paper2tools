---
name: workflow-visualizer
description: Generate visual representations (flowcharts, DAGs) of workflows from JSON or code
version: 1.0.0
---

# Workflow Visualizer

Generate visual representations of workflows to help users understand the data flow and dependencies between steps.

## Input

Either:
- `workflow_json`: The JSON workflow specification (from extract-workflow-json)
- `workflow_code`: The Python workflow code (from extract-workflow-code)
- Or both

## Output Format

Multiple visualization formats:

### 1. Mermaid Flowchart
```mermaid
flowchart TD
    A[Input: Raw Data] --> B[Step 1: Preprocess]
    B --> C[Step 2: Analysis]
    C --> D[Output: Results]
```

### 2. DAG Representation (Graphviz DOT)
```dot
digraph Workflow {
    rankdir=LR;
    node [shape=box];
    
    input [label="Input Data"];
    step1 [label="Step 1: Process"];
    step2 [label="Step 2: Analyze"];
    output [label="Output"];
    
    input -> step1;
    step1 -> step2;
    step2 -> output;
}
```

### 3. ASCII Art (for terminal display)
```
┌─────────────┐
│  Input Data │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Step 1     │
│  Process    │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Step 2     │
│  Analyze    │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Output     │
└─────────────┘
```

## Generation Rules

1. **Extract steps from input**: Parse workflow_json['steps'] or workflow_code class methods
2. **Identify dependencies**: Match output names from step N to input names in step N+1
3. **Draw data flow**: Show how data transforms through each step
4. **Highlight I/O**: Clearly mark external inputs and final outputs
5. **Keep it simple**: Max 10-15 nodes for readability

## Output Structure

```
=== MERMAID FLOWCHART ===
[mermaid code]

=== GRAPHVIZ DOT ===
[dot code]

=== ASCII DIAGRAM ===
[ascii art]
```

## Example

Input workflow with 3 steps:
1. Load data → 2. Process → 3. Analyze → Output

Output:
```mermaid
flowchart LR
    A[Load Data] -->|raw_data| B[Process]
    B -->|processed_data| C[Analyze]
    C -->|results| D[Output]
```
