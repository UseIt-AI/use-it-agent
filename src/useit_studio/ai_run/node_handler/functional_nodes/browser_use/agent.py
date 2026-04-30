"""
Browser Agent - 浏览器自动化 Agent

Agent 职责：
1. 接收前端返回的页面状态（PageState）
2. 调用 Planner 进行规划
3. 将 Planner 输出转换为 BrowserAction
4. 输出 tool_call 事件给前端执行

注意：后端不执行浏览器操作，只生成指令。
"""

import re
from typing import Dict, Any, Optional, AsyncGenerator

from useit_studio.ai_run.utils.logger_utils import LoggerUtils

from .models import (
    BrowserContext,
    BrowserAgentStep,
    BrowserPlannerOutput,
    BrowserAction,
    BrowserActionType,
    PageState,
)
from .core.planner import BrowserPlanner


logger = LoggerUtils(component_name="BrowserAgent")


class BrowserAgent:
    """
    Browser Agent
    
    职责：
    1. 接收前端返回的页面状态
    2. 调用 Planner 规划下一步
    3. 将自然语言动作转换为 BrowserAction
    4. 通过事件流输出 tool_call
    """
    
    def __init__(
        self,
        planner_model: str = "gpt-4o",
        api_keys: Optional[Dict[str, str]] = None,
        node_id: str = "",
    ):
        self.node_id = node_id
        
        # Planner
        self.planner = BrowserPlanner(
            model=planner_model,
            api_keys=api_keys,
            node_id=node_id,
        )
        
        logger.logger.info(f"[BrowserAgent] 初始化完成 - Planner: {planner_model}")
    
    def set_node_id(self, node_id: str):
        """更新节点 ID"""
        self.node_id = node_id
        self.planner.set_node_id(node_id)
    
    async def step(
        self,
        context: BrowserContext,
        log_dir: Optional[str] = None,
    ) -> BrowserAgentStep:
        """
        执行单步（非流式）
        
        Args:
            context: 浏览器上下文（包含前端返回的 PageState）
            log_dir: 日志目录
            
        Returns:
            BrowserAgentStep
        """
        logger.logger.info(f"[BrowserAgent] 开始执行步骤 - Node: {context.node_id}")
        
        try:
            # 检查 PageState
            if not context.page_state:
                raise ValueError("No page state provided. Frontend must return page state.")
            
            # 调用 Planner 规划
            planner_output = await self.planner.plan(
                page_state=context.page_state,
                task_description=context.task_description,
                milestone_objective=context.milestone_objective,
                history_md=context.history_md,
                log_dir=log_dir,
                extracted_content=context.extracted_content,
                collected_data=context.collected_data,
            )
            
            logger.logger.info(
                f"[BrowserAgent] Planner 完成 - MilestoneCompleted: {planner_output.is_milestone_completed}"
            )
            
            # 如果里程碑已完成
            if planner_output.is_milestone_completed:
                # 即使任务完成，也要检查是否有需要执行的动作（如 switch_tab, close_tab）
                action_text = planner_output.next_action.strip()
                if action_text:
                    action = self._parse_action(planner_output)
                else:
                    action = BrowserAction.stop()
                return BrowserAgentStep(
                    planner_output=planner_output,
                    browser_action=action,
                    reasoning_text="Milestone completed",
                )
            
            # 解析并生成动作
            action = self._parse_action(planner_output)
            
            logger.logger.info(
                f"[BrowserAgent] 生成动作: {action.action_type.value}"
            )
            
            return BrowserAgentStep(
                planner_output=planner_output,
                browser_action=action,
            )
        
        except Exception as e:
            logger.logger.error(f"[BrowserAgent] 执行失败: {e}", exc_info=True)
            return BrowserAgentStep(
                planner_output=BrowserPlannerOutput(
                    observation="Error occurred",
                    reasoning=str(e),
                    next_action="",
                    is_milestone_completed=False,
                ),
                error=str(e),
            )
    
    async def step_streaming(
        self,
        context: BrowserContext,
        log_dir: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行单步（流式）
        
        Yields:
            - {"type": "status", "content": str}
            - {"type": "reasoning_delta", "content": str, "source": "planner"}
            - {"type": "plan_complete", "content": {...}}
            - {"type": "action", "action": {...}}
            - {"type": "step_complete", "content": {...}}
            - {"type": "error", "content": str}
        """
        logger.logger.info(f"[BrowserAgent] 开始流式执行 - Node: {context.node_id}")
        
        planner_output: Optional[BrowserPlannerOutput] = None
        
        try:
            # 检查 PageState
            if not context.page_state:
                yield {"type": "error", "content": "No page state provided. Frontend must return page state."}
                return
            
            # 流式 Planner
            yield {"type": "status", "content": "Planning next action..."}
            
            async for event in self.planner.plan_streaming(
                page_state=context.page_state,
                task_description=context.task_description,
                milestone_objective=context.milestone_objective,
                history_md=context.history_md,
                log_dir=log_dir,
                extracted_content=context.extracted_content,
                collected_data=context.collected_data,
            ):
                yield event
                
                if event.get("type") == "plan_complete":
                    content = event.get("content", {})
                    planner_output = BrowserPlannerOutput(
                        observation=content.get("Observation", ""),
                        reasoning=content.get("Reasoning", ""),
                        next_action=content.get("Action", ""),
                        target_element=content.get("TargetElement"),
                        is_milestone_completed=content.get("MilestoneCompleted", False),
                        completion_summary=content.get("node_completion_summary"),
                        output_filename=content.get("output_filename"),
                        result_markdown=content.get("result_markdown"),
                    )
            
            if not planner_output:
                yield {"type": "error", "content": "Planner did not return a valid result"}
                return
            
            # 如果里程碑已完成
            if planner_output.is_milestone_completed:
                # 即使任务完成，也要检查是否有需要执行的动作（如 switch_tab, close_tab）
                # Planner 可能在同一步说 "Switch to tab1" + MilestoneCompleted=true
                action_text = planner_output.next_action.strip()
                if action_text:
                    action = self._parse_action(planner_output)
                else:
                    action = BrowserAction.stop()
                
                yield {"type": "action", "action": action.to_dict()}
                yield {
                    "type": "step_complete",
                    "content": BrowserAgentStep(
                        planner_output=planner_output,
                        browser_action=action,
                        reasoning_text="Milestone completed",
                    ).to_dict(),
                }
                return
            
            # 解析并生成动作
            action = self._parse_action(planner_output)
            
            yield {"type": "action", "action": action.to_dict()}
            
            # 发送完成事件
            yield {
                "type": "step_complete",
                "content": BrowserAgentStep(
                    planner_output=planner_output,
                    browser_action=action,
                ).to_dict(),
            }
        
        except Exception as e:
            logger.logger.error(f"[BrowserAgent] 流式执行失败: {e}", exc_info=True)
            yield {"type": "error", "content": str(e)}
    
    def _parse_action(self, planner_output: BrowserPlannerOutput) -> BrowserAction:
        """
        解析 Planner 输出为 BrowserAction
        
        基于 Planner 的自然语言描述和目标元素索引，
        推断具体的动作类型和参数。
        """
        action_text = planner_output.next_action.lower()
        target_index = planner_output.target_element
        
        # 点击
        if "click" in action_text:
            if target_index is not None:
                return BrowserAction.click(target_index)
            # 尝试从文本中提取索引
            index_match = re.search(r'\[(\d+)\]', planner_output.next_action)
            if index_match:
                return BrowserAction.click(int(index_match.group(1)))
            logger.logger.warning(f"[BrowserAgent] Click action without target index: {action_text}")
            return BrowserAction.stop()
        
        # 输入
        elif any(kw in action_text for kw in ["type", "input", "enter text", "fill"]):
            # 提取要输入的文本
            text_match = re.search(r"['\"](.+?)['\"]", planner_output.next_action)
            text = text_match.group(1) if text_match else ""
            
            if target_index is not None:
                return BrowserAction.input_text(target_index, text)
            # 尝试从文本中提取索引
            index_match = re.search(r'\[(\d+)\]', planner_output.next_action)
            if index_match:
                return BrowserAction.input_text(int(index_match.group(1)), text)
            logger.logger.warning(f"[BrowserAgent] Input action without target index: {action_text}")
            return BrowserAction.stop()
        
        # 提取内容
        elif any(kw in action_text for kw in ["extract content", "extract text", "get content", "get text", "read content", "read text"]):
            # 尝试从动作描述中提取 CSS 选择器
            selector_match = re.search(r"(?:selector|using)\s*['\"]([^'\"]+)['\"]", planner_output.next_action)
            if not selector_match:
                # 尝试匹配引号中的 CSS 选择器样式（以 . # 或标签名开头）
                selector_match = re.search(r"['\"]([.#][\w\-]+(?:\s+[\w\-]+)*)['\"]", planner_output.next_action)
            selector = selector_match.group(1) if selector_match else None
            return BrowserAction.extract_content(selector)
        
        # 滚动
        elif "scroll down" in action_text:
            return BrowserAction.scroll_down()
        elif "scroll up" in action_text:
            return BrowserAction.scroll_up()
        
        # 导航
        elif any(kw in action_text for kw in ["go to", "navigate", "open url", "visit"]):
            url_match = re.search(r"(https?://\S+)", planner_output.next_action)
            if url_match:
                url = url_match.group(1).rstrip("'\".,;)")
                return BrowserAction.go_to_url(url)
            logger.logger.warning(f"[BrowserAgent] Navigate action without URL: {action_text}")
            return BrowserAction.stop()
        
        # 按键
        elif "press" in action_text or "key" in action_text:
            key_keywords = ["enter", "tab", "escape", "backspace", "delete", "space"]
            for key in key_keywords:
                if key in action_text:
                    return BrowserAction.press_key(key.capitalize())
            key_match = re.search(r"press\s+(\w+)", action_text)
            if key_match:
                return BrowserAction.press_key(key_match.group(1).capitalize())
            logger.logger.warning(f"[BrowserAgent] Press key action without key name: {action_text}")
            return BrowserAction.stop()
        
        # 等待
        elif "wait" in action_text:
            time_match = re.search(r"(\d+)\s*(?:second|sec|s)", action_text)
            seconds = int(time_match.group(1)) if time_match else 2
            return BrowserAction.wait(seconds)
        
        # 后退/前进
        elif "back" in action_text and "go" in action_text:
            return BrowserAction.go_back()
        elif "forward" in action_text:
            return BrowserAction.go_forward()
        
        # 刷新
        elif "refresh" in action_text or "reload" in action_text:
            return BrowserAction.refresh()
        
        # Tab 管理
        elif "switch" in action_text and "tab" in action_text:
            tab_match = re.search(r'tab(\d+)', action_text)
            if not tab_match:
                tab_match = re.search(r'tab[_\s]?(\d+)', planner_output.next_action, re.IGNORECASE)
            if tab_match:
                tab_id = f"tab{tab_match.group(1)}"
                return BrowserAction.switch_tab(tab_id)
            logger.logger.warning(f"[BrowserAgent] Switch tab action without tab ID: {action_text}")
            return BrowserAction.stop()
        
        elif "close" in action_text and "tab" in action_text:
            tab_match = re.search(r'tab(\d+)', action_text)
            if not tab_match:
                tab_match = re.search(r'tab[_\s]?(\d+)', planner_output.next_action, re.IGNORECASE)
            if tab_match:
                tab_id = f"tab{tab_match.group(1)}"
                return BrowserAction.close_tab(tab_id)
            # 没有指定 tab ID 时，关闭当前标签页（使用 "current" 让前端处理）
            logger.logger.info(f"[BrowserAgent] Close tab without explicit ID, closing current tab")
            return BrowserAction.close_tab("current")
        
        # 默认
        else:
            if target_index is not None:
                return BrowserAction.click(target_index)
            logger.logger.warning(f"[BrowserAgent] 无法解析动作: {planner_output.next_action}")
            return BrowserAction.stop()
