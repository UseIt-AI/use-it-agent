"""
无限循环检测器 - 检测工作流是否陷入重复状态
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List

from ..constants import LOOP_DETECTOR_MAX_SAME_STATE, LOOP_DETECTOR_HISTORY_SIZE


@dataclass
class LoopDetector:
    """
    无限循环检测器
    
    通过追踪状态历史，检测是否连续出现相同的状态组合
    """
    max_same_state_count: int = LOOP_DETECTOR_MAX_SAME_STATE
    history_size: int = LOOP_DETECTOR_HISTORY_SIZE
    state_history: List[str] = field(default_factory=list)
    
    def check(self, node_id: str, action_type: str) -> bool:
        """
        检测是否陷入无限循环
        
        Args:
            node_id: 当前节点ID
            action_type: 动作类型
            
        Returns:
            bool: 是否检测到无限循环
        """
        state_key = f"{node_id}:{action_type}"
        self.state_history.append(state_key)
        
        # 保持历史记录在合理范围内
        if len(self.state_history) > self.history_size:
            self.state_history = self.state_history[-self.history_size:]
        
        # 检查最近的状态是否重复过多
        recent_states = self.state_history[-self.max_same_state_count:]
        if (
            len(recent_states) == self.max_same_state_count 
            and all(s == state_key for s in recent_states)
        ):
            return True
        
        return False
    
    def reset(self) -> None:
        """重置状态历史"""
        self.state_history.clear()
    
    def get_info(self) -> Dict[str, Any]:
        """获取循环检测信息"""
        return {
            "history_length": len(self.state_history),
            "recent_states": self.state_history[-10:] if self.state_history else [],
            "max_same_state_count": self.max_same_state_count,
        }
