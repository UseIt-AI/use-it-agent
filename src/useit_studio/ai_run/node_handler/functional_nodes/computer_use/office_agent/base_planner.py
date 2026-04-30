"""
Office Agent - 通用 Planner 基类

Planner 负责分析当前状态并决定下一步动作。
单阶段模式下直接输出可执行代码。

各应用通过提供不同的 System Prompt（COM API 参考）来定制行为。
"""

import json
import re
from dataclasses import dataclass
from typing import Dict, Any, Optional, AsyncGenerator, Callable

from .models import (
    PlannerOutput,
    AgentContext,
    OfficeAppType,
    ReasoningDeltaEvent,
    PlanCompleteEvent,
)
from useit_studio.ai_run.node_handler.functional_nodes.computer_use.gui_v2.utils.llm_client import (
    VLMClient, LLMConfig
)
from useit_studio.ai_run.utils.logger_utils import LoggerUtils


@dataclass
class OfficePlannerConfig:
    """Planner 配置"""
    model: str = "gpt-4o-mini"
    max_tokens: int = 4096
    temperature: float = 0.0
    app_type: OfficeAppType = OfficeAppType.WORD


class OfficePlanner:
    """
    Office Planner - 通用规划器
    
    职责：
    1. 分析用户指令和应用状态
    2. 决定下一步动作
    3. 生成可执行的 PowerShell 代码
    
    定制方式：
    - 通过 system_prompt 和 user_prompt_template 参数定制
    - 或通过 set_prompts() 方法设置
    """
    
    def __init__(
        self,
        config: OfficePlannerConfig,
        api_keys: Optional[Dict[str, str]] = None,
        node_id: str = "",
        system_prompt: str = "",
        user_prompt_template: str = "",
    ):
        """
        初始化 Planner
        
        Args:
            config: Planner 配置
            api_keys: API 密钥
            node_id: 节点 ID
            system_prompt: 系统提示（包含 COM API 参考）
            user_prompt_template: 用户提示模板
        """
        self.config = config
        self.node_id = node_id
        self.system_prompt = system_prompt
        self.user_prompt_template = user_prompt_template
        self.logger = LoggerUtils(component_name=f"{config.app_type.value.title()}Planner")
        
        # 初始化 VLM 客户端
        llm_config = LLMConfig(
            model=config.model,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
            role=f"{config.app_type.value}_planner",
            node_id=node_id,
        )
        self.vlm = VLMClient(config=llm_config, api_keys=api_keys, logger=self.logger)
    
    def set_node_id(self, node_id: str):
        """更新节点 ID"""
        self.node_id = node_id
        self.vlm.config.node_id = node_id
    
    def set_prompts(self, system_prompt: str, user_prompt_template: str):
        """设置 prompts"""
        self.system_prompt = system_prompt
        self.user_prompt_template = user_prompt_template
    
    async def plan(
        self,
        context: AgentContext,
        log_dir: Optional[str] = None,
    ) -> tuple[PlannerOutput, Dict[str, int]]:
        """
        非流式规划
        
        Args:
            context: Agent 上下文
            log_dir: 日志目录
            
        Returns:
            (PlannerOutput 对象, token_usage 字典)
        """
        user_prompt = self._build_user_prompt(context)
        
        # 从 context 中提取截图
        screenshot_base64 = None
        if context.current_snapshot and hasattr(context.current_snapshot, 'screenshot'):
            screenshot_base64 = context.current_snapshot.screenshot
        attached_images_base64 = context.attached_images if context.attached_images else None
        
        response = await self.vlm.call(
            prompt=user_prompt,
            system_prompt=self.system_prompt,
            screenshot_base64=screenshot_base64,
            attached_images_base64=attached_images_base64,
            log_dir=log_dir,
        )
        
        planner_output = self._parse_response(response["content"])
        token_usage = response.get("token_usage", {})
        
        return planner_output, token_usage
    
    async def plan_streaming(
        self,
        context: AgentContext,
        log_dir: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式规划

        只将 ``<thinking>`` 标签内的内容作为 ReasoningDeltaEvent 发送到前端，
        JSON 结果部分（Action / Code / SVG 等）不会发送，避免在前端显示大段
        机器可读内容。全部文本仍会被累积到 ``full_content`` 用于解析。

        Yields:
            ReasoningDeltaEvent - 推理过程增量（仅 <thinking> 内部）
            PlanCompleteEvent - 规划完成
        """
        user_prompt = self._build_user_prompt(context)
        
        # 从 context 中提取截图
        screenshot_base64 = None
        if context.current_snapshot and hasattr(context.current_snapshot, 'screenshot'):
            screenshot_base64 = context.current_snapshot.screenshot
            self.logger.logger.info(f"[{self.config.app_type.value.title()}Planner] Using screenshot for planning")
        attached_images_base64 = context.attached_images if context.attached_images else None
        
        full_content = ""
        _thinking_open = False   # 已在累积文本中见到 <thinking>
        _thinking_close = False  # 已在累积文本中见到 </thinking>
        
        async for chunk in self.vlm.stream(
            prompt=user_prompt,
            system_prompt=self.system_prompt,
            screenshot_base64=screenshot_base64,
            attached_images_base64=attached_images_base64,
            log_dir=log_dir,
        ):
            if chunk["type"] == "delta":
                content = chunk["content"]
                if isinstance(content, list):
                    content = "".join(str(c) for c in content)
                full_content += content

                # 检测 <thinking> / </thinking> 标签（基于累积文本）
                if not _thinking_open and "<thinking>" in full_content:
                    _thinking_open = True

                # 只在 <thinking> 打开且未关闭时，才把 delta 发给前端
                should_send = _thinking_open and not _thinking_close
                
                if not _thinking_close and "</thinking>" in full_content:
                    _thinking_close = True

                if should_send:
                    yield ReasoningDeltaEvent(content=content, source="planner").to_dict()
                
            elif chunk["type"] == "complete":
                planner_output = self._parse_response(full_content)
                token_usage = chunk.get("token_usage", {})
                event = PlanCompleteEvent(planner_output=planner_output).to_dict()
                event["token_usage"] = token_usage
                yield event
                
            elif chunk["type"] == "error":
                yield {"type": "error", "content": chunk["content"]}
    
    def _build_user_prompt(self, context: AgentContext) -> str:
        """
        构建用户提示

        ⚠️ Skills 必须追加在最后（KV Cache 友好）
        """
        context_text = context.to_prompt(self.config.app_type)

        if self.user_prompt_template:
            user_prompt = self.user_prompt_template.format(context=context_text)
        else:
            # 默认模板
            user_prompt = f"""{context_text}

## Your Task

Complete the "Current Node Instruction" shown above. That is your ONLY goal.

## Response Format

First, think freely in a <thinking> block. Then output your decision as JSON.

<thinking>
Think step by step here. You should:
1. If there was a previous step, evaluate its result by comparing the current state with what was expected
2. Observe the current application state
3. Reason about what needs to be done next
4. Decide if the task is complete or what action to take
5. If action needed, plan the PowerShell code to execute
</thinking>

```json
{{
  "Action": "execute_code OR stop",
  "Title": "Short title (max 5 words)",
  "Code": "PowerShell code here (empty string if Action is stop)",
  "MilestoneCompleted": false,
  "node_completion_summary": null
}}
```

Now think and respond."""

        # ⚠️ 关键：Skills 追加在最后（KV Cache 友好）
        if context.skills_prompt:
            user_prompt += f"\n\n{context.skills_prompt}\n"

        return user_prompt
    
    def _parse_response(self, response: str) -> PlannerOutput:
        """
        解析 LLM 响应为 PlannerOutput
        
        支持格式：<thinking>...</thinking> + JSON
        """
        try:
            # 1. 提取 <thinking> 内容
            thinking = self._extract_thinking(response)
            
            # 2. 提取 JSON
            parsed = self._extract_json(response)
            
            # 3. 提取并清理代码
            code = parsed.get("Code", "")
            if code:
                code = self._validate_and_clean_code(code)
            
            # 4. 创建 PlannerOutput（通过 from_dict 确保所有字段都被解析）
            parsed["Thinking"] = thinking
            if code:
                parsed["Code"] = code
            output = PlannerOutput.from_dict(parsed, thinking=thinking)
            
            # 强制校验：有执行动作时 MilestoneCompleted 必须为 false
            if output.next_action in ("execute_code", "actions", "skill") and output.is_milestone_completed:
                self.logger.logger.warning(
                    f"[Planner] 修正 MilestoneCompleted: Action='{output.next_action}'，强制设为 false"
                )
                output.is_milestone_completed = False

            actions_count = len(output.actions) if output.actions else 0
            self.logger.logger.info(
                f"[Planner] Parsed - Thinking: {len(thinking)} chars, "
                f"Action: {output.next_action}, Code: {len(code)} chars, "
                f"Actions: {actions_count} items"
            )
            return output
            
        except Exception as e:
            self.logger.logger.error(f"解析 Planner 响应失败: {e}")
            return PlannerOutput(
                thinking=f"Parse error: {str(e)}",
                next_action="execute_code",
                code="Write-Host 'Error: Failed to parse planner response'",
                is_milestone_completed=False,
            )
    
    def _extract_thinking(self, text: str) -> str:
        """提取 <thinking> 标签内容"""
        thinking_match = re.search(r'<thinking>(.*?)</thinking>', text, re.DOTALL | re.IGNORECASE)
        if thinking_match:
            return thinking_match.group(1).strip()
        
        # 如果没有标签，提取 JSON 之前的内容
        json_start = text.find("{")
        if json_start > 0:
            potential_thinking = text[:json_start]
            potential_thinking = re.sub(r'```(?:json)?\s*$', '', potential_thinking, flags=re.MULTILINE)
            potential_thinking = potential_thinking.strip()
            if potential_thinking and len(potential_thinking) > 20:
                return potential_thinking
        
        return ""
    
    def _extract_json(self, text: str) -> Dict[str, Any]:
        """从文本中提取 JSON，支持嵌套结构、多 JSON 块和截断修复"""
        text = text.strip()

        # 直接尝试解析
        if text.startswith("{"):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass

        # 从 ```json 块中提取 — 逐块尝试，处理模型输出多个 JSON 块的情况
        # 使用非贪婪匹配 [\s\S]+? 确保每对 ``` 独立匹配
        json_blocks = re.findall(r'```(?:json)?\s*([\s\S]+?)\s*```', text)
        for block in json_blocks:
            block = block.strip()
            if block.startswith('{'):
                try:
                    return json.loads(block)
                except json.JSONDecodeError:
                    continue

        # 提取第一个 { 到最后一个 }
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass

        # 截断修复：响应可能因 max_tokens 被截断导致 JSON 不完整
        if start != -1:
            fragment = text[start:]
            repaired = self._try_repair_truncated_json(fragment)
            if repaired is not None:
                self.logger.logger.warning(
                    "[Planner] JSON was truncated (likely max_tokens limit). "
                    "Repaired by closing open brackets. SVG content may be incomplete."
                )
                return repaired

        raise ValueError(f"无法从响应中提取 JSON: {text[:200]}...")

    @staticmethod
    def _try_repair_truncated_json(fragment: str) -> Optional[Dict[str, Any]]:
        """
        尝试修复被截断的 JSON。
        关闭未闭合的字符串、数组、对象，使其可解析。
        返回 None 表示无法修复。
        """
        in_string = False
        escape_next = False
        stack: list = []

        for ch in fragment:
            if escape_next:
                escape_next = False
                continue
            if ch == '\\' and in_string:
                escape_next = True
                continue
            if ch == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch in ('{', '['):
                stack.append(ch)
            elif ch == '}':
                if stack and stack[-1] == '{':
                    stack.pop()
            elif ch == ']':
                if stack and stack[-1] == '[':
                    stack.pop()

        if not stack:
            return None

        # 如果截断在字符串中间，先闭合字符串
        suffix = ""
        if in_string:
            suffix += '"'

        # 反向闭合未匹配的括号
        for opener in reversed(stack):
            suffix += ']' if opener == '[' else '}'

        try:
            return json.loads(fragment + suffix)
        except json.JSONDecodeError:
            return None
    
    def _validate_and_clean_code(self, code: str) -> str:
        """验证和清理代码"""
        # 替换常见的中文输出字符串
        replacements = {
            "操作完成": "Operation completed",
            "操作成功": "Operation successful", 
            "操作失败": "Operation failed",
            "错误": "Error",
            "成功": "Success",
            "失败": "Failed",
        }
        
        for cn, en in replacements.items():
            code = code.replace(cn, en)
        
        return code
