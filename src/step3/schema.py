"""Step3 数据结构定义"""

from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class IOField:
    """IO 参数描述"""
    name: str
    type: str
    description: str

    def to_dict(self) -> Dict[str, str]:
        return {"name": self.name, "type": self.type, "description": self.description}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "IOField":
        return cls(name=d["name"], type=d["type"], description=d.get("description", ""))


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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "logic_description": self.logic_description,
            "tool_intent": self.tool_intent,
            "suggested_tools": self.suggested_tools,
            "io_schema": self.io_schema.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "WorkflowStep":
        return cls(
            step_id=d["step_id"],
            logic_description=d["logic_description"],
            tool_intent=d.get("tool_intent", ""),
            suggested_tools=d.get("suggested_tools", []),
            io_schema=IOSchema.from_dict(d.get("io_schema", {})),
        )


@dataclass
class Workflow:
    """从文本中提取的完整 workflow"""
    workflow_id: str
    title: str
    description: str
    source_ids: List[str] = field(default_factory=list)
    steps: List[WorkflowStep] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "title": self.title,
            "description": self.description,
            "source_ids": self.source_ids,
            "steps": [s.to_dict() for s in self.steps],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Workflow":
        return cls(
            workflow_id=d["workflow_id"],
            title=d["title"],
            description=d.get("description", ""),
            source_ids=d.get("source_ids", []),
            steps=[WorkflowStep.from_dict(s) for s in d.get("steps", [])],
        )
