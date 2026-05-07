"""Step3.5 数据结构定义"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class GenerationStatus(Enum):
    """单个 workflow 的生成状态"""
    PENDING = "pending"
    CODE_GENERATED = "code_generated"
    TEST_GENERATED = "test_generated"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class GeneratedWorkflow:
    """一个 workflow 的完整生成结果"""
    workflow_id: str
    title: str
    status: GenerationStatus = GenerationStatus.PENDING
    workflow_code: Optional[str] = None
    test_code: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    errors: List[str] = field(default_factory=list)

    def to_index_entry(self) -> Dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "title": self.title,
            "status": self.status.value,
            "errors": self.errors,
        }
