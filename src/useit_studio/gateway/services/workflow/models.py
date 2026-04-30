"""
Workflow 配置模型

定义 workflow 的 JSON 配置结构
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class StepType(str, Enum):
    """步骤类型"""
    AGENT = "agent"
    NODE = "node"


class InputType(str, Enum):
    """输入类型"""
    USER_INPUT = "user_input"  # 使用用户原始输入
    PREVIOUS_STEP = "previous_step"  # 使用上一步的输出
    STATIC = "static"  # 使用静态值
    COMBINED = "combined"  # 组合多个来源


@dataclass
class StepInput:
    """步骤输入配置"""
    type: InputType
    value: Optional[str] = None  # 用于 STATIC 类型
    step_id: Optional[str] = None  # 用于 PREVIOUS_STEP 类型
    template: Optional[str] = None  # 用于 COMBINED 类型，支持模板替换
    
    def to_dict(self) -> Dict[str, Any]:
        result = {"type": self.type.value}
        if self.value is not None:
            result["value"] = self.value
        if self.step_id is not None:
            result["step_id"] = self.step_id
        if self.template is not None:
            result["template"] = self.template
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StepInput":
        return cls(
            type=InputType(data["type"]),
            value=data.get("value"),
            step_id=data.get("step_id"),
            template=data.get("template"),
        )


@dataclass
class WorkflowStep:
    """工作流步骤"""
    id: str
    type: StepType
    name: str  # Agent/Node 的名称，如 "CUAAgent", "RAGNode"
    description: Optional[str] = None
    config: Dict[str, Any] = field(default_factory=dict)  # Agent/Node 的配置参数
    input: StepInput = field(default_factory=lambda: StepInput(type=InputType.USER_INPUT))
    output_key: Optional[str] = None  # 输出结果的存储键
    enabled: bool = True  # 是否启用该步骤
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "name": self.name,
            "description": self.description,
            "config": self.config,
            "input": self.input.to_dict(),
            "output_key": self.output_key or self.id,
            "enabled": self.enabled,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowStep":
        return cls(
            id=data["id"],
            type=StepType(data["type"]),
            name=data["name"],
            description=data.get("description"),
            config=data.get("config", {}),
            input=StepInput.from_dict(data.get("input", {"type": "user_input"})),
            output_key=data.get("output_key"),
            enabled=data.get("enabled", True),
        )


@dataclass
class WorkflowConfig:
    """工作流配置"""
    name: str
    description: Optional[str] = None
    steps: List[WorkflowStep] = field(default_factory=list)
    version: str = "1.0"
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "steps": [step.to_dict() for step in self.steps],
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowConfig":
        return cls(
            name=data["name"],
            description=data.get("description"),
            version=data.get("version", "1.0"),
            steps=[WorkflowStep.from_dict(s) for s in data.get("steps", [])],
            metadata=data.get("metadata", {}),
        )
    
    def to_json(self) -> str:
        import json
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> "WorkflowConfig":
        import json
        data = json.loads(json_str)
        return cls.from_dict(data)


# ==================== 预定义的示例 Workflow ====================
# 注意：这些是 legacy 模板，实际工作流应从 workflow_templates/ 目录加载

def create_cua_then_rag_workflow(
    task_id: Optional[str] = None,
    cua_provider: str = "openai",
    cua_model: str = "gpt-5.1",
) -> WorkflowConfig:
    """
    创建一个 "先 CUA 再 RAG" 的示例 Workflow (Legacy)
    
    注意：此函数已废弃，实际工作流应从 workflow_templates/ 目录加载
    """
    return WorkflowConfig(
        name="CUA + RAG Workflow (Legacy)",
        description="先使用 Computer Use Agent 执行操作，再使用 RAG Node 生成报告",
        steps=[
            WorkflowStep(
                id="cua_step",
                type=StepType.AGENT,
                name="CUAAgent",
                description="使用 Computer Use Agent 执行计算机操作",
                config={
                    "provider": cua_provider,
                    "model": cua_model,
                },
                input=StepInput(type=InputType.USER_INPUT),
                output_key="cua_result",
            ),
            WorkflowStep(
                id="rag_step",
                type=StepType.NODE,
                name="RAGNode",
                description="基于 CUA 结果进行 RAG 查询和报告生成",
                config={
                    "task_id": task_id,
                    "top_k": 1,
                    "expand_query": True,
                    "include_images": True,
                },
                input=StepInput(
                    type=InputType.COMBINED,
                    template="基于以下操作结果进行分析：\n{cua_result}\n\n用户原始问题：{user_input}",
                ),
                output_key="rag_result",
            ),
        ],
        metadata={
            "author": "system",
            "use_case": "自动化操作后生成分析报告",
            "deprecated": True,
        },
    )


def create_channel_comparison_workflow(
    task_id: Optional[str] = None,
) -> WorkflowConfig:
    """
    创建 "渠道比选报告" 工作流 (Legacy)
    
    注意：此函数已废弃，实际工作流应从 workflow_templates/ 目录加载
    """
    return WorkflowConfig(
        name="渠道比选报告生成工作流 (Legacy)",
        description="自动化执行渠道【线路比选】",
        steps=[
            WorkflowStep(
                id="cua_collect_data",
                type=StepType.AGENT,
                name="CUAAgent",
                description="使用【91卫图助手】软件获取线路信息",
                config={
                    "provider": "openai",
                    "model": "computer-use-preview",
                },
                input=StepInput(type=InputType.USER_INPUT),
                output_key="cua_result",
            ),
            WorkflowStep(
                id="rag_generate_report",
                type=StepType.NODE,
                name="RAGNode",
                description="检索线路数据，生成渠道比选报告",
                config={
                    "task_id": task_id,
                    "top_k": 10,
                    "expand_query": True,
                    "include_images": True,
                },
                input=StepInput(
                    type=InputType.COMBINED,
                    template="基于以下数据生成比选报告：\n{cua_result}",
                ),
                output_key="report_result",
            ),
        ],
        metadata={
            "author": "system",
            "use_case": "渠道【线路比选】报告自动生成",
            "deprecated": True,
        },
    )
