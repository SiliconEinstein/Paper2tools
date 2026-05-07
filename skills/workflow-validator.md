---
name: workflow-validator
description: Validate extracted workflows by attempting to reproduce paper results
type: validation
version: 1.0.0
---

# Workflow Validator

Validate extracted workflows by selecting a source paper and attempting to reproduce the computational process described in the workflow.

## Validation Process

### Step 1: Paper Selection
Randomly select one paper from `workflow_json['source_ids']` for validation.

### Step 2: Attempt Reproduction
Try to reproduce the workflow using the extracted code:

1. **Gather required inputs**
   - Identify input data types from workflow steps
   - Create synthetic/mock data if real data unavailable
   
2. **Execute workflow steps**
   - Run through each step sequentially
   - Check intermediate outputs match expected types
   
3. **Compare with paper claims**
   - Check if results align with paper's reported outcomes
   - Verify key metrics or findings are reproducible

### Step 3: Validation Report

Output validation result as JSON:

```json
{
  "workflow_id": "extracted_workflow_id",
  "validation_paper": "selected_paper_id",
  "validation_status": "PASS|PARTIAL|FAIL",
  "reproduction_score": 0.0-1.0,
  "steps_validated": [
    {
      "step_id": 1,
      "step_name": "load_data",
      "status": "PASS|FAIL|SKIP",
      "execution_time_ms": 123,
      "output_valid": true,
      "notes": "Successfully loaded synthetic data"
    }
  ],
  "issues": [
    {
      "severity": "ERROR|WARNING|INFO",
      "step_id": 2,
      "message": "Step failed due to missing tool implementation"
    }
  ],
  "recommendations": [
    "Add error handling for missing input files",
    "Implement missing external tool calls"
  ]
}
```

## Validation Criteria

### PASS
- All critical steps execute without errors
- Outputs match expected types and formats
- Results align with paper's general findings

### PARTIAL
- Most steps execute
- Some outputs approximate expected results
- Minor discrepancies with paper claims

### FAIL
- Critical steps fail to execute
- Results fundamentally different from paper
- Missing essential implementations

## Reproduction Score Calculation

```
reproduction_score = (
  steps_passed * 0.4 +
  output_correctness * 0.3 +
  paper_alignment * 0.3
)
```

- `steps_passed`: Fraction of steps that executed
- `output_correctness`: Output format/type correctness
- `paper_alignment`: Qualitative match with paper results

## Implementation Approach

1. **Input**: workflow_json + workflow_code
2. **Select paper**: Random.choice(source_ids)
3. **Create test data**: Generate synthetic inputs matching schema
4. **Execute**: Run workflow.execute_workflow() with test data
5. **Evaluate**: Check outputs, compare with expected
6. **Report**: Generate validation JSON

## Output Format

```
=== VALIDATION REPORT ===
[JSON report]

=== EXECUTION LOG ===
[Step-by-step execution trace]

=== SUMMARY ===
Validation Status: PASS/PARTIAL/FAIL
Reproduction Score: X.XX
Critical Issues: N
Warnings: N
```

## Notes

- Use synthetic/mock data when real datasets unavailable
- External tools may be stubbed (NotImplementedError expected)
- Focus on workflow logic correctness, not absolute numerical accuracy
- Document which steps require real data/tools for full validation
