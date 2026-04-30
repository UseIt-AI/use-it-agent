"""
Browser Planner - 高层规划

职责：
1. 观察当前页面状态（截图 + 元素列表，由前端提供）
2. 结合任务目标和历史，推理下一步
3. 输出自然语言的动作描述和目标元素索引

输入：PageState（前端返回） + task_description + history
输出：BrowserPlannerOutput
"""

import json
import re
from typing import Dict, Any, Optional, AsyncGenerator

from useit_studio.ai_run.utils.logger_utils import LoggerUtils

from ..models import BrowserPlannerOutput, PageState


logger = LoggerUtils(component_name="BrowserPlanner")


# ==================== Prompt Templates ====================

BROWSER_PLANNER_SYSTEM_PROMPT = """You are an AI assistant that helps users navigate web pages. You observe the current page state and decide what action to take next.

You will receive:
1. The current page URL and title
2. A list of interactive elements with their indices (from frontend DOM parser)
3. A screenshot of the current page (optional)
4. The user's goal
5. The history of previous actions

Your job is to:
1. Observe the current page state
2. Reason about what to do next
3. Decide on the next action
4. Identify the target element (if any) by its index

## Output Format (JSON)

```json
{
    "Observation": "What you see on the page",
    "Reasoning": "Your thought process",
    "Action": "Natural language description of the action",
    "TargetElement": <element_index or null>,
    "MilestoneCompleted": <true if the milestone is complete, false otherwise>,
    "node_completion_summary": "concise key data collected so far (can be written at ANY step, not just when MilestoneCompleted is true)",
    "result_markdown": "markdown content to save as a file (optional)",
    "output_filename": "descriptive_name.md (optional, used with result_markdown)"
}
```

## Action Types

1. **Click**: Click on an element
   - Action: "Click the search box" or "Click the Submit button"
   - TargetElement: index of the element to click

2. **Type**: Input text into a field
   - Action: "Type 'hello world' in the search box"
   - TargetElement: index of the input field

3. **Navigate**: Go to a URL
   - Action: "Navigate to https://example.com"
   - TargetElement: null

4. **Scroll**: Scroll the page
   - Action: "Scroll down to see more content"
   - TargetElement: null

5. **Press Key**: Press a keyboard key
   - Action: "Press Enter to submit"
   - TargetElement: null

6. **Wait**: Wait for page changes
   - Action: "Wait for the page to load"
   - TargetElement: null

7. **Back/Forward**: Navigate browser history
   - Action: "Go back to previous page"
   - TargetElement: null

8. **Extract Content**: Extract the full text content from the page (READ)
   - Action: "Extract content from the page" (recommended, extracts entire page)
   - Action: "Extract content using selector '.article-body'" (optional, target specific area)
   - TargetElement: null
   - Use this when you need to READ the full text of articles, lists, tables, or any text-heavy content
   - The interactive elements list only shows clickable/input elements with truncated text
   - Extract Content retrieves ALL visible text, bypassing element truncation
   - In most cases, simply use "Extract content from the page" without specifying a selector — the system will extract the entire page body, which works well for most scenarios
   - The extracted content will appear in the "Extracted Page Content" section for your reference
   - **CRITICAL: Extract Content should only be called ONCE per page. If you already see an "Extracted Page Content" section in the input, the extraction is DONE — do NOT extract again.**

9. **Switch Tab**: Switch to a different browser tab
   - Action: "Switch to tab0" (use the tab ID from the Browser Tabs list in page state)
   - TargetElement: null
   - The Browser Tabs section shows all open tabs with their IDs (tab0, tab1, tab2, etc.) and titles
   - Use this to navigate between already-open pages without creating new tabs
   - **Prefer switching to an existing tab over navigating to a URL that's already open in another tab**

10. **Close Tab**: Close a browser tab
   - Action: "Close tab2" (specify tab ID) or "close_tab" (close current tab)
   - TargetElement: null
   - Use this to clean up tabs you no longer need (e.g., after collecting data from a page)
   - If no tab ID is specified, the current active tab will be closed and the browser will automatically switch to the previous tab

11. **Save File**: Save results as a markdown file to the outputs folder (WRITE)
   - This is NOT an Action — instead, include `result_markdown` and `output_filename` in your JSON output when setting MilestoneCompleted to true
   - `result_markdown`: The markdown content you want to save. You write and control the content (e.g., a cleaned-up list, a summary, a report)
   - `output_filename`: A descriptive filename ending with `.md` (e.g., "bilibili_top100.md", "product_comparison.md"). If the instruction specifies a filename, use that exact name
   - Extract Content (action 8) only reads the page text for your reference. To save a file, you must actively write the processed content into `result_markdown`
   - Example workflow: Extract Content → read the extracted data → process/format it → write into `result_markdown` with an `output_filename`

## Important Rules

1. Use the element INDEX (a number) to identify elements, not selectors
2. If the task is complete, set MilestoneCompleted to true and Action to empty string
3. Be concise in your observations and reasoning
4. When typing text, put the text in quotes: Type 'text here'
5. If you cannot find an element, try scrolling first
6. Always check if the current page matches what you expect before acting
7. The element list is provided by the frontend DOM parser, trust the indices
8. **NEVER call Extract Content more than once on the same page.** If the "Extracted Page Content" section is already present, the content has been successfully retrieved. Proceed to complete the task
9. `node_completion_summary` is a KEY-VALUE data store you can write at ANY step (not just when MilestoneCompleted is true). **Keep it to ONE short line** using compact format like `名称:值 | 名称:值 | ...`. Only store essential data (IDs, numbers, names) — no descriptions or sentences. Each write OVERWRITES the previous value, so include ALL key data collected so far. When MilestoneCompleted is true, it is also passed to downstream nodes as Milestone History
"""


BROWSER_PLANNER_USER_PROMPT = """## Current Page State
{page_state}
{extracted_content_section}{collected_data_section}
## Task Goal
{task_goal}

## Milestone Objective
{milestone_objective}

## Previous Actions
{history}

Now analyze the page and decide the next action. Output JSON only:"""


class BrowserPlanner:
    """Browser Planner"""
    
    def __init__(
        self,
        model: str = "gpt-4o",
        api_keys: Optional[Dict[str, str]] = None,
        max_tokens: int = 2048,
        temperature: float = 0.0,
        node_id: str = "",
    ):
        self.model = model
        self.node_id = node_id
        self.api_keys = api_keys or {}
        self.max_tokens = max_tokens
        self.temperature = temperature
        
        # 延迟初始化 VLM 客户端
        self._vlm = None
        
        logger.logger.info(f"[BrowserPlanner] 初始化: model={model}")
    
    def _ensure_vlm(self):
        """确保 VLM 客户端已初始化"""
        if self._vlm is None:
            # 复用 gui_v2 的 VLMClient
            from useit_studio.ai_run.node_handler.functional_nodes.computer_use.gui_v2.utils.llm_client import (
                VLMClient, LLMConfig
            )
            
            config = LLMConfig(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                role="browser_planner",
                node_id=self.node_id,
            )
            self._vlm = VLMClient(
                config=config,
                api_keys=self.api_keys,
                logger=logger,
            )
    
    def set_node_id(self, node_id: str):
        """更新节点 ID"""
        self.node_id = node_id
        if self._vlm:
            self._vlm.config.node_id = node_id
    
    @staticmethod
    def _build_extracted_content_section(extracted_content: Optional[str]) -> str:
        """
        构建 extracted content 区块，明确告诉 Planner 内容已提取完成，不要重复提取。
        """
        if not extracted_content:
            return ""
        return (
            f"\n## Extracted Page Content (ALREADY COMPLETED)\n"
            f"The page text has ALREADY been extracted via extract_content. "
            f"DO NOT call extract_content again. Use this data directly to complete the task.\n"
            f"```\n{extracted_content}\n```\n"
        )
    
    @staticmethod
    def _build_collected_data_section(collected_data: Optional[str]) -> str:
        """
        构建已收集数据区块。此数据通过 node_completion_summary 在之前的步骤中保存，
        供后续步骤使用（如写入文件）。不影响 milestone history 格式。
        """
        if not collected_data:
            return ""
        return (
            f"\n## Collected Data (from previous steps)\n"
            f"Data you have collected so far in this node: `{collected_data}`\n"
        )
    
    async def plan(
        self,
        page_state: PageState,
        task_description: str,
        milestone_objective: str,
        history_md: str = "",
        log_dir: Optional[str] = None,
        extracted_content: Optional[str] = None,
        collected_data: Optional[str] = None,
    ) -> BrowserPlannerOutput:
        """
        非流式规划
        
        Args:
            page_state: 当前页面状态（前端返回）
            task_description: 整体任务描述
            milestone_objective: 当前里程碑目标
            history_md: 历史动作 Markdown
            log_dir: 日志目录
            extracted_content: extract_content 返回的页面文本
            collected_data: 中途收集的数据（来自 node_completion_summary）
            
        Returns:
            BrowserPlannerOutput
        """
        self._ensure_vlm()
        
        # 构建 extracted content 区块
        extracted_content_section = self._build_extracted_content_section(extracted_content)
        collected_data_section = self._build_collected_data_section(collected_data)
        
        # 当存在 extracted_content 时，跳过 Interactive Elements 以节省 token
        # extract_content 后的步骤通常是处理/汇总数据，不需要交互元素
        max_elements = 0 if extracted_content else 50
        
        user_prompt = BROWSER_PLANNER_USER_PROMPT.format(
            page_state=page_state.to_prompt_str(max_elements=max_elements, smart_filter=True),
            extracted_content_section=extracted_content_section,
            collected_data_section=collected_data_section,
            task_goal=task_description,
            milestone_objective=milestone_objective,
            history=history_md or "No previous actions",
        )
        
        logger.logger.info(f"[BrowserPlanner] 开始规划: url={page_state.url}, max_elements={max_elements}")
        
        response = await self._vlm.call(
            prompt=user_prompt,
            system_prompt=BROWSER_PLANNER_SYSTEM_PROMPT,
            screenshot_base64=page_state.screenshot_base64,
            log_dir=log_dir,
        )
        
        planner_output = self._parse_response(response["content"])
        logger.logger.info(
            f"[BrowserPlanner] 规划完成: action={planner_output.next_action[:50] if planner_output.next_action else 'None'}..., "
            f"completed={planner_output.is_milestone_completed}"
        )
        
        return planner_output
    
    async def plan_streaming(
        self,
        page_state: PageState,
        task_description: str,
        milestone_objective: str,
        history_md: str = "",
        log_dir: Optional[str] = None,
        extracted_content: Optional[str] = None,
        collected_data: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式规划
        
        Yields:
            - {"type": "reasoning_delta", "content": str, "source": "planner"}
            - {"type": "plan_complete", "content": {...}}
        """
        self._ensure_vlm()
        
        # 构建 extracted content 区块
        extracted_content_section = self._build_extracted_content_section(extracted_content)
        collected_data_section = self._build_collected_data_section(collected_data)
        
        # 当存在 extracted_content 时，跳过 Interactive Elements 以节省 token
        # extract_content 后的步骤通常是处理/汇总数据，不需要交互元素
        max_elements = 0 if extracted_content else 50
        
        user_prompt = BROWSER_PLANNER_USER_PROMPT.format(
            page_state=page_state.to_prompt_str(max_elements=max_elements, smart_filter=True),
            extracted_content_section=extracted_content_section,
            collected_data_section=collected_data_section,
            task_goal=task_description,
            milestone_objective=milestone_objective,
            history=history_md or "No previous actions",
        )
        
        logger.logger.info(f"[BrowserPlanner] 开始流式规划: url={page_state.url}, max_elements={max_elements}")
        
        full_content = ""
        
        async for chunk in self._vlm.stream(
            prompt=user_prompt,
            system_prompt=BROWSER_PLANNER_SYSTEM_PROMPT,
            screenshot_base64=page_state.screenshot_base64,
            log_dir=log_dir,
        ):
            if chunk["type"] == "delta":
                full_content += chunk["content"]
                yield {
                    "type": "reasoning_delta",
                    "content": chunk["content"],
                    "source": "planner",
                }
            
            elif chunk["type"] == "complete":
                planner_output = self._parse_response(full_content)
                logger.logger.info(
                    f"[BrowserPlanner] 流式规划完成: action={planner_output.next_action[:50] if planner_output.next_action else 'None'}..., "
                    f"completed={planner_output.is_milestone_completed}"
                )
                yield {
                    "type": "plan_complete",
                    "content": planner_output.to_dict(),
                }
    
    def _parse_response(self, response: str) -> BrowserPlannerOutput:
        """解析 LLM 响应"""
        try:
            # 提取 JSON
            parsed = self._extract_json(response)
            
            return BrowserPlannerOutput(
                observation=parsed.get("Observation", ""),
                reasoning=parsed.get("Reasoning", ""),
                next_action=parsed.get("Action", ""),
                target_element=parsed.get("TargetElement"),
                is_milestone_completed=parsed.get("MilestoneCompleted", False),
                completion_summary=parsed.get("node_completion_summary"),
                output_filename=parsed.get("output_filename"),
                result_markdown=parsed.get("result_markdown"),
            )
        
        except Exception as e:
            logger.logger.error(f"[BrowserPlanner] 解析响应失败: {e}, 原始: {response[:300]}")
            return BrowserPlannerOutput(
                observation="Parse error",
                reasoning=str(e),
                next_action="",
                is_milestone_completed=False,
            )
    
    def _extract_json(self, text: str) -> Dict[str, Any]:
        """从文本中提取 JSON"""
        text = text.strip()
        
        # 直接尝试解析
        if text.startswith("{"):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass
        
        # 尝试从 ```json 块中提取
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        # 尝试提取第一个 { 到最后一个 }
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
        
        raise ValueError(f"无法从响应中提取 JSON: {text[:200]}...")
