"""
Word Agent V2 - Planner Only 模式

单阶段架构：Planner 直接输出可执行代码
1. 分析用户指令和文档状态
2. 决定下一步做什么
3. 直接生成 PowerShell 代码（无需 Actor）

输出格式：<thinking> 自由推理 + JSON（包含 Code 字段）
"""

import json
import re
from typing import Dict, Any, Optional, AsyncGenerator

from ...models import (
    PlannerOutput,
    AgentContext,
    ReasoningDeltaEvent,
    PlanCompleteEvent,
)
from useit_studio.ai_run.node_handler.functional_nodes.computer_use.gui_v2.utils.llm_client import (
    VLMClient, LLMConfig
)
from useit_studio.ai_run.utils.logger_utils import LoggerUtils


# ==================== Prompt 模板 ====================

PLANNER_SYSTEM_PROMPT = """You are a Word automation expert. Your job is to analyze the current document state and decide the next action, then generate the PowerShell code to execute it.

## Input Structure

You will receive:
1. **User's Overall Goal** (Context Only) - The user's high-level task description. This may span multiple nodes. **IMPORTANT: If the user mentions a specific file path, you MUST use that file path when opening documents.**
2. **Current Node Instruction** (YOUR GOAL) - The SPECIFIC task you must complete for THIS node. This comes from the workflow definition and is your ONLY goal.
3. **Current Document State** - Document info and paragraphs with full formatting (font.size, font.bold, etc.)
4. **Workflow Progress** - Shows the overall plan with completed/pending nodes

## CRITICAL BOUNDARIES

- **Current Node Instruction is your ONLY goal**. Complete it and mark MilestoneCompleted=true.
- The "User's Overall Goal" provides context (especially file paths!) - but do NOT try to complete the entire goal.
- Do NOT perform tasks from pending nodes ([ ]) - those will be handled by subsequent nodes.
- Look at the [-->] marker in Workflow Progress to confirm your current node.
- When the "Current Node Instruction" is fulfilled, mark MilestoneCompleted=true immediately.

## FILE PATH HANDLING

**CRITICAL: When opening documents, ALWAYS check User's Overall Goal for the target file path!**
- If User's Overall Goal mentions a file path like "C:\\Users\\...\\xxx.docx", you MUST open THAT specific file.
- Do NOT create a new blank document when a target file is specified.
- Do NOT open a random file - use the exact path from User's Overall Goal.

Example:
- User's Overall Goal: "打开C:\\Users\\test\\report.docx，修改标题"
- Current Node Instruction: "打开Word文档"
- Correct action: Open "C:\\Users\\test\\report.docx"
- WRONG action: Create new document or open Word without the file

Response format: <thinking> block followed by JSON decision with executable PowerShell code."""


PLANNER_USER_PROMPT = """{context}

## Your Task

Complete the "Current Node Instruction" shown above. That is your ONLY goal.

## Response Format

First, think freely in a <thinking> block. Then output your decision as JSON.

<thinking>
Think step by step here. You should:
1. If there was a previous step, evaluate its result by comparing the current state with what was expected
2. Observe the current document state (check font sizes, styles, formatting, etc.)
3. Reason about what needs to be done next
4. Decide if the task is complete or what action to take
5. If action needed, plan the PowerShell code to execute

Be thorough - examine the document state carefully. For example:
- Check paragraph 1's font.size to see if it changed
- Compare before/after states when evaluating previous actions
</thinking>

```json
{{
  "Action": "execute_code OR stop",
  "Title": "Short title (max 5 words), e.g. 'Increase title font'",
  "Code": "PowerShell code here (empty string if Action is stop)",
  "MilestoneCompleted": false,
  "node_completion_summary": null
}}
```

## Action Types

**execute_code** - Execute PowerShell code to manipulate the document
**stop** - Task is complete, no more actions needed

## PowerShell Word COM Reference

### Opening Word and Documents
```powershell
# Get existing Word instance or create new one
try {{
    $word = [System.Runtime.InteropServices.Marshal]::GetActiveObject("Word.Application")
}} catch {{
    $word = New-Object -ComObject Word.Application
}}
$word.Visible = $true

# Open existing document
$doc = $word.Documents.Open("C:\\path\\to\\document.docx")

# Get active document
$doc = $word.ActiveDocument

# Create new document
$doc = $word.Documents.Add()
```

### Paragraph Operations (1-indexed)
```powershell
$para = $doc.Paragraphs(1)
$para.Range.Font.Bold = $true
$para.Range.Font.Italic = $true
$para.Range.Font.Size = 14
$para.Range.Font.Name = "Arial"
$para.Range.Font.Color = 255  # Red (BGR format)
$para.Alignment = 1  # 0=Left, 1=Center, 2=Right, 3=Justify
```

### Find and Replace
```powershell
$find = $doc.Content.Find
$find.ClearFormatting()
$find.Replacement.ClearFormatting()
$find.Execute($findText, $false, $false, $false, $false, $false, $true, 1, $false, $replaceText, 2)
```

### Tables
```powershell
# Add table at end
$range = $doc.Content
$range.Collapse(0)  # 0 = wdCollapseEnd
$table = $doc.Tables.Add($range, 3, 4)  # 3 rows, 4 columns

# Access existing table
$table = $doc.Tables(1)
$table.Cell(1, 1).Range.Text = "Header"
```

### Headers and Footers
```powershell
$section = $doc.Sections(1)
$section.Headers(1).Range.Text = "Header Text"
$section.Footers(1).Range.Text = "Footer Text"

# Add page numbers
$section.Footers(1).PageNumbers.Add()
```

### Save and Cleanup
```powershell
$doc.Save()
# or SaveAs
$doc.SaveAs([ref]"C:\\path\\to\\new.docx")

# Cleanup (if you created Word instance)
# $doc.Close()
# $word.Quit()
# [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
```

## Color Reference (BGR format for Word COM)
- Red: 255
- Green: 65280
- Blue: 16711680
- Black: 0
- White: 16777215

## CRITICAL RULES

1. **Code must be complete and executable** - Include error handling with try-catch
2. **Use Word COM API correctly** - Paragraphs are 1-indexed
3. **NEVER set MilestoneCompleted=true if Action is execute_code!**
4. **If Action is "stop", Code should be empty string**
5. All output must be in English

## WHEN TO MARK TASK COMPLETE (MilestoneCompleted=true)

**You MUST mark the task complete when the Current Document State shows the expected result.**

Examples of when to mark complete:
- Node instruction: "打开Word" → Document State shows Word is open with a document → COMPLETE
- Node instruction: "标题放大一号" → Document State shows paragraph 1 font.size increased → COMPLETE
- Node instruction: "把第一段加粗" → Document State shows paragraph 1 font.bold=true → COMPLETE

**How to decide:**
1. Look at the Current Node Instruction
2. Check the Current Document State - does it already satisfy the instruction?
3. If YES → Action="stop", MilestoneCompleted=true
4. If NO → Action="execute_code", MilestoneCompleted=false

**IMPORTANT: If you already executed code in a previous step, and now the Document State shows the change was successful, you MUST mark complete. Do NOT keep executing the same action repeatedly.**

Now think and respond."""


class WordPlanner:
    """
    Word Agent Planner (Unified Mode)
    
    单阶段模式：直接输出可执行代码，无需 Actor。
    """
    
    def __init__(
        self,
        model: str = "gpt-4o-mini",
        api_keys: Optional[Dict[str, str]] = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        node_id: str = "",
    ):
        self.logger = LoggerUtils(component_name="WordPlanner")
        self.node_id = node_id
        
        # 初始化 VLM 客户端
        config = LLMConfig(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            role="word_planner_unified",
            node_id=node_id,
        )
        self.vlm = VLMClient(config=config, api_keys=api_keys, logger=self.logger)
    
    def set_node_id(self, node_id: str):
        """更新节点 ID"""
        self.node_id = node_id
        self.vlm.config.node_id = node_id
    
    async def plan(
        self,
        context: AgentContext,
        log_dir: Optional[str] = None,
    ) -> PlannerOutput:
        """
        非流式规划
        
        Args:
            context: Agent 上下文
            log_dir: 日志目录
            
        Returns:
            PlannerOutput 对象（包含 code）
        """
        user_prompt = PLANNER_USER_PROMPT.format(context=context.to_prompt())
        
        # 从 context 中提取截图
        screenshot_base64 = None
        if context.current_snapshot and context.current_snapshot.screenshot:
            screenshot_base64 = context.current_snapshot.screenshot
            self.logger.logger.info("[WordPlanner] Using screenshot for planning")
        
        response = await self.vlm.call(
            prompt=user_prompt,
            system_prompt=PLANNER_SYSTEM_PROMPT,
            screenshot_base64=screenshot_base64,
            log_dir=log_dir,
        )
        
        return self._parse_response(response["content"])
    
    async def plan_streaming(
        self,
        context: AgentContext,
        log_dir: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式规划
        
        Yields:
            ReasoningDeltaEvent - 推理过程增量
            PlanCompleteEvent - 规划完成（包含 code）
        """
        user_prompt = PLANNER_USER_PROMPT.format(context=context.to_prompt())
        
        # 从 context 中提取截图
        screenshot_base64 = None
        if context.current_snapshot and context.current_snapshot.screenshot:
            screenshot_base64 = context.current_snapshot.screenshot
            self.logger.logger.info("[WordPlanner] Using screenshot for streaming planning")
        
        full_content = ""
        
        async for chunk in self.vlm.stream(
            prompt=user_prompt,
            system_prompt=PLANNER_SYSTEM_PROMPT,
            screenshot_base64=screenshot_base64,
            log_dir=log_dir,
        ):
            if chunk["type"] == "delta":
                content = chunk["content"]
                if isinstance(content, list):
                    content = "".join(str(c) for c in content)
                full_content += content
                yield ReasoningDeltaEvent(content=content, source="planner").to_dict()
                
            elif chunk["type"] == "complete":
                planner_output = self._parse_response(full_content)
                yield PlanCompleteEvent(planner_output=planner_output).to_dict()
                
            elif chunk["type"] == "error":
                yield {"type": "error", "content": chunk["content"]}
    
    def _parse_response(self, response: str) -> PlannerOutput:
        """
        解析 LLM 响应为 PlannerOutput
        
        支持格式：<thinking>...</thinking> + JSON（包含 Code 字段）
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
            
            # 4. 创建 PlannerOutput
            output = PlannerOutput(
                thinking=thinking,
                next_action=parsed.get("Action", ""),
                title=parsed.get("Title"),
                code=code,
                language="PowerShell",
                is_milestone_completed=parsed.get("MilestoneCompleted", False),
                completion_summary=parsed.get("node_completion_summary"),
            )
            
            # ===== 强制校验 MilestoneCompleted 逻辑 =====
            # 如果 Action 是 execute_code，MilestoneCompleted 必须为 false
            if output.next_action == "execute_code":
                if output.is_milestone_completed:
                    self.logger.logger.warning(
                        f"[WordPlanner] 修正 MilestoneCompleted: Action='execute_code'，强制设为 false"
                    )
                    output.is_milestone_completed = False
            
            self.logger.logger.info(
                f"[WordPlanner] Parsed - Thinking: {len(thinking)} chars, "
                f"Action: {output.next_action}, Code: {len(code)} chars"
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
        """提取 <thinking> 标签内的内容"""
        thinking_match = re.search(r'<thinking>(.*?)</thinking>', text, re.DOTALL | re.IGNORECASE)
        if thinking_match:
            return thinking_match.group(1).strip()
        
        # 如果没有 <thinking> 标签，尝试提取 JSON 之前的所有内容作为 thinking
        json_start = text.find("{")
        if json_start > 0:
            potential_thinking = text[:json_start]
            potential_thinking = re.sub(r'```(?:json)?\s*$', '', potential_thinking, flags=re.MULTILINE)
            potential_thinking = potential_thinking.strip()
            if potential_thinking and len(potential_thinking) > 20:
                return potential_thinking
        
        return ""
    
    def _extract_json(self, text: str) -> Dict[str, Any]:
        """从文本中提取 JSON"""
        text = text.strip()
        
        # 直接尝试解析（纯 JSON 响应）
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
    
    def _validate_and_clean_code(self, code: str) -> str:
        """
        验证和清理代码
        
        注意：不要清理文件路径中的中文！
        只清理 Write-Host 等输出语句中的中文。
        """
        # 只替换常见的中文输出字符串
        replacements = {
            "操作完成": "Operation completed",
            "操作成功": "Operation successful", 
            "操作失败": "Operation failed",
            "错误": "Error",
            "成功": "Success",
            "失败": "Failed",
            "打开文档": "Opening document",
            "文档已打开": "Document opened",
        }
        
        for cn, en in replacements.items():
            code = code.replace(cn, en)
        
        return code
