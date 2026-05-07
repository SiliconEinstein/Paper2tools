"""Step3 数据结构定义"""

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class IOField:
    """IO 参数描述"""
    name: str
    type: str
    description: str
    column_hints: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "name": self.name,
            "type": self.type,
            "description": self.description,
        }
        if self.column_hints:
            d["column_hints"] = list(self.column_hints)
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "IOField":
        hints = d.get("column_hints") or []
        if not isinstance(hints, list):
            hints = []
        return cls(
            name=d["name"],
            type=d["type"],
            description=d.get("description", ""),
            column_hints=[str(x) for x in hints],
        )


@dataclass
class IOSchema:
    """一个 step 的输入输出 schema"""
    inputs: List[IOField] = field(default_factory=list)
    outputs: List[IOField] = field(default_factory=list)

    def to_dict(self) -> Dict[str, list]:
        return {
            "inputs": [f.to_dict() for f in self.inputs],
            "outputs": [f.to_dict() for f in self.outputs],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "IOSchema":
        return cls(
            inputs=[IOField.from_dict(f) for f in d.get("inputs", [])],
            outputs=[IOField.from_dict(f) for f in d.get("outputs", [])],
        )


@dataclass
class WorkflowStep:
    """Workflow 中的一个步骤"""
    step_id: int
    logic_description: str
    tool_intent: str
    suggested_tools: List[str] = field(default_factory=list)
    io_schema: IOSchema = field(default_factory=IOSchema)
    step_name: str = ""
    parameters: List[str] = field(default_factory=list)
    tool_refs: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "step_id": self.step_id,
            "logic_description": self.logic_description,
            "tool_intent": self.tool_intent,
            "suggested_tools": self.suggested_tools,
            "io_schema": self.io_schema.to_dict(),
        }
        if self.step_name:
            d["step_name"] = self.step_name
        if self.parameters:
            d["parameters"] = list(self.parameters)
        if self.tool_refs:
            d["tool_refs"] = list(self.tool_refs)
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "WorkflowStep":
        params = d.get("parameters") or []
        if not isinstance(params, list):
            params = []
        refs = d.get("tool_refs") or []
        if not isinstance(refs, list):
            refs = []
        return cls(
            step_id=d["step_id"],
            logic_description=d["logic_description"],
            tool_intent=d.get("tool_intent", ""),
            suggested_tools=d.get("suggested_tools", []),
            io_schema=IOSchema.from_dict(d.get("io_schema", {})),
            step_name=str(d.get("step_name") or ""),
            parameters=[str(x) for x in params],
            tool_refs=[str(x) for x in refs],
        )


@dataclass
class Workflow:
    """从文本中提取的完整 workflow"""
    workflow_id: str
    title: str
    description: str
    source_ids: List[str] = field(default_factory=list)
    steps: List[WorkflowStep] = field(default_factory=list)
    provenance: Dict[str, Any] = field(default_factory=dict)
    keywords: List[str] = field(default_factory=list)
    research_questions: List[str] = field(default_factory=list)
    datasets: List[Dict[str, Any]] = field(default_factory=list)
    benchmarks: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "workflow_id": self.workflow_id,
            "title": self.title,
            "description": self.description,
            "source_ids": self.source_ids,
            "steps": [s.to_dict() for s in self.steps],
        }
        if self.provenance:
            d["provenance"] = self.provenance
        if self.keywords:
            d["keywords"] = list(self.keywords)
        if self.research_questions:
            d["research_questions"] = list(self.research_questions)
        if self.datasets:
            d["datasets"] = list(self.datasets)
        if self.benchmarks:
            d["benchmarks"] = list(self.benchmarks)
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Workflow":
        def _str_list(key: str) -> List[str]:
            v = d.get(key) or []
            if not isinstance(v, list):
                return []
            return [str(x) for x in v]

        def _dict_list(key: str) -> List[Dict[str, Any]]:
            v = d.get(key) or []
            if not isinstance(v, list):
                return []
            out: List[Dict[str, Any]] = []
            for item in v:
                if isinstance(item, dict):
                    out.append(dict(item))
            return out

        return cls(
            workflow_id=d["workflow_id"],
            title=d["title"],
            description=d.get("description", ""),
            source_ids=d.get("source_ids", []),
            steps=[WorkflowStep.from_dict(s) for s in d.get("steps", [])],
            provenance=d.get("provenance") or {},
            keywords=_str_list("keywords"),
            research_questions=_str_list("research_questions"),
            datasets=_dict_list("datasets"),
            benchmarks=_dict_list("benchmarks"),
        )
