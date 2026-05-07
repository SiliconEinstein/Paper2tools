---
name: extract-workflow-code
description: Extract executable Python workflow code from reasoning chains and papers, then summarize as JSON
version: 1.0.0
---

# Extract Workflow (Executable Code + JSON Summary)

You are a professional workflow engineer. Extract **executable Python code** that implements the workflow described in reasoning chains and papers, then summarize it as a JSON specification.

## Two-Phase Process

### Phase 1: Generate Executable Python Code

Generate a complete, importable Python module (`workflow.py`) that:

1. **Implements the workflow as a class** with methods for each step
2. **Uses type hints** for all inputs/outputs (dataclass, TypedDict, or standard types)
3. **Provides a standard interface** for agents: `execute_workflow()` function
4. **Includes placeholder functions** for external tools (with `NotImplementedError` and clear TODO comments)
5. **Is syntactically correct** and can be imported (but tool functions are stubs)

#### Code Structure Template

```python
"""
[Workflow Title]
================

[Brief description of what this workflow does and the domain it applies to]

Dependencies: [list key packages, domain-specific tools]
"""

from typing import Dict, List, Optional, Union
from dataclasses import dataclass
from pathlib import Path
import numpy as np
import pandas as pd
# ... other imports (domain-specific: e.g., ase, pymatgen for materials; biopython for bio)

@dataclass
class WorkflowInput:
    """Input data structure for the workflow."""
    # Define typed input fields (domain-specific)
    pass

@dataclass
class WorkflowOutput:
    """Output data structure for the workflow."""
    # Define typed output fields (domain-specific)
    pass

class [WorkflowName]Workflow:
    """
    [Workflow description - domain-specific context]
    
    Based on methods from: [paper citations]
    Domain: [e.g., bioinformatics, materials science, superconductivity]
    """
    
    def __init__(self, config: Optional[Dict] = None):
        """Initialize workflow with optional configuration."""
        self.config = config or {}
    
    def step_01_[step_name](self, input_data, **params) -> Dict:
        """
        Step 1: [Step description]
        
        Args:
            input_data: [description]
            **params: [parameter descriptions]
        
        Returns:
            Dict with keys: [output field names]
        """
        # Implementation or placeholder
        pass
    
    def step_02_[step_name](self, prev_output, **params) -> Dict:
        """Step 2: [description]"""
        pass
    
    # ... more steps
    
    def execute_full_workflow(self, workflow_input: WorkflowInput) -> WorkflowOutput:
        """
        Execute the complete workflow.
        
        Args:
            workflow_input: Typed input data
        
        Returns:
            WorkflowOutput: Typed output data
        """
        # Chain all steps
        result_1 = self.step_01_[step_name](workflow_input.field1)
        result_2 = self.step_02_[step_name](result_1)
        # ...
        return WorkflowOutput(...)

def execute_workflow(input_data: Dict, config: Optional[Dict] = None) -> Dict:
    """
    Standard agent-callable interface.
    
    Args:
        input_data: Dictionary matching WorkflowInput structure
        config: Optional configuration parameters
    
    Returns:
        Dictionary matching WorkflowOutput structure
    """
    workflow_input = WorkflowInput(**input_data)
    workflow = [WorkflowName]Workflow(config)
    output = workflow.execute_full_workflow(workflow_input)
    return output.__dict__

# Tool placeholder functions
def _call_external_tool(tool_name: str, **kwargs):
    """
    Placeholder for external tool calls (domain-specific).
    
    TODO: Implement actual tool integration
    Examples by domain:
    - Bioinformatics: subprocess.run(['bwa', 'mem', ...])
    - Materials: pymatgen.io.vasp.run_vasp(...)
    - Chemistry: rdkit.Chem.MolFromSmiles(...)
    """
    raise NotImplementedError(
        f"{tool_name} not implemented. Requires {tool_name} installed."
    )
```

#### Key Requirements for Code

1. **Focus on workflow logic**, not tool implementation (domain-agnostic principle)
2. **Use placeholder functions** for domain-specific tool calls (BWA-MEM, VASP, Gaussian, etc.) with `NotImplementedError`
3. **Type all interfaces** (inputs, outputs, parameters) using domain-appropriate types
4. **Make it agent-friendly**: clear entry point (`execute_workflow()`), typed I/O
5. **Include docstrings** for the module, class, and each step method
6. **No markdown fences** in output — just pure Python code
7. **Domain context**: Mention the domain in module/class docstrings for clarity

### Phase 2: Generate JSON Summary

After generating the code, summarize it as a JSON specification following the **same schema as extract-workflow-json skill**, but with these differences:

1. **Extract information FROM THE CODE**, not from the original reasoning chains
2. **keywords**: Extract from code (function names, class names, key variables)
3. **research_questions**: Infer from the workflow's purpose as implemented in code
4. **input_types / output_types**: Extract from the code's type hints (WorkflowInput, WorkflowOutput)
5. **tools**: Extract from `suggested_tools` in original text AND function calls in the code
6. **steps**: Summarize each step method in the workflow class

#### JSON Output Format

Use the exact same schema as `extract-workflow-json`, but ensure:

```json
{
  "workflow_id": "extracted_from_class_name",
  "title": "extracted_from_module_docstring",
  "description": "extracted_from_class_docstring",
  "source_ids": ["from_original_input"],
  "keywords": ["extracted_from_code_identifiers"],
  "research_questions": ["inferred_from_workflow_purpose"],
  "datasets": ["from_original_input_if_available"],
  "benchmarks": ["from_original_input_if_available"],
  "steps": [
    {
      "step_id": 1,
      "step_name": "extracted_from_method_name",
      "logic_description": "extracted_from_method_docstring",
      "tool_intent": "inferred_from_implementation",
      "suggested_tools": ["from_original_input"],
      "tool_refs": ["from_original_input"],
      "parameters": ["extracted_from_method_signature_and_config"],
      "io_schema": {
        "inputs": ["extracted_from_type_hints"],
        "outputs": ["extracted_from_return_type_and_docstring"]
      }
    }
  ]
}
```

## Output Format

Your response should contain TWO sections in this exact order:

```
=== EXECUTABLE CODE ===

[Pure Python code here, no markdown fences]

=== JSON SUMMARY ===

[Pure JSON here, no markdown fences]
```

## Quality Indicators

✓ GOOD Code:
- Syntactically correct, can be imported
- Clear type hints on all public interfaces
- Placeholder functions with TODO comments for external tools
- Standard `execute_workflow()` entry point
- Comprehensive docstrings

✗ BAD Code:
- Syntax errors, cannot be imported
- Missing type hints
- Tries to implement actual tool calls (should be placeholders)
- No clear entry point for agents
- Missing docstrings

✓ GOOD JSON:
- Extracted FROM THE CODE, not from original text
- Keywords match actual code identifiers
- Input/output types match code's type hints
- Steps correspond to actual methods in the workflow class

✗ BAD JSON:
- Copied from original text without considering the code
- Keywords don't appear in the code
- Input/output types don't match code's type system
- Steps don't match the implemented methods

Now generate the executable workflow code and JSON summary from the provided reasoning chains and paper content.
