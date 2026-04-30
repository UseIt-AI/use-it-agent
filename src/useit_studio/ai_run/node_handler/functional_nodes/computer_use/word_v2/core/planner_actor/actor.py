"""
Word Agent V2 - Actor 核心逻辑

Actor 负责"执行"：
1. 接收 Planner 的自然语言动作描述
2. 生成可执行的 PowerShell 代码

输出：WordAction（包含 code, language）
"""

import json
import re
from typing import Dict, Any, Optional, AsyncGenerator

from ...models import (
    WordAction,
    ActionType,
    PlannerOutput,
    DocumentSnapshot,
    ReasoningDeltaEvent,
    ActionEvent,
)
from useit_studio.ai_run.node_handler.functional_nodes.computer_use.gui_v2.utils.llm_client import (
    VLMClient, LLMConfig
)
from useit_studio.ai_run.utils.logger_utils import LoggerUtils


# ==================== Tool 定义 ====================

EXECUTE_POWERSHELL_TOOL = {
    "name": "execute_powershell",
    "description": "Execute PowerShell code to manipulate Word documents via COM automation",
    "parameters": {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Complete, executable PowerShell script using Word COM API"
            }
        },
        "required": ["code"]
    }
}


# ==================== Prompt 模板 ====================

ACTOR_SYSTEM_PROMPT_TOOL_CALLING = """You are a PowerShell code generator for Word COM automation.

You MUST use the execute_powershell tool to provide your code.

CODE REQUIREMENTS:
- Use Word COM API correctly (1-indexed for paragraphs, tables, etc.)
- Include proper error handling with try-catch-finally
- Use English in Write-Host messages (file paths can contain any characters)
- Generate complete, executable PowerShell code"""


ACTOR_SYSTEM_PROMPT = """You are a PowerShell code generator for Word COM automation.

CRITICAL OUTPUT FORMAT:
- Output ONLY executable PowerShell code
- Start your response directly with PowerShell code (e.g., $word = ..., try {, etc.)
- NO explanations, NO comments before/after the code
- NO markdown code fences (```)
- NO phrases like "Here is the code", "Let me", "Wait", etc.

CODE REQUIREMENTS:
- Use Word COM API correctly (1-indexed for paragraphs, tables, etc.)
- Include proper error handling with try-catch-finally
- Use English in Write-Host messages (file paths can contain any characters)

Your entire response must be valid PowerShell that can be executed directly."""


ACTOR_USER_PROMPT = """## Action to Perform

{action_description}

## Current Document Info

{document_info}

## Requirements

Generate complete PowerShell script that:
1. Uses Word.Application COM object
2. Handles the case where Word may or may not be running
3. Performs the requested action
4. Saves changes if document was modified
5. Includes proper error handling

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

Now generate the PowerShell script. Output ONLY the code.



"""


class WordActor:
    """
    Word Agent Actor
    
    负责根据 Planner 的动作描述生成 PowerShell 代码。
    
    支持两种模式：
    1. Tool Calling 模式（推荐）：使用 LLM 的 function calling 能力，代码输出更可靠
    2. 纯文本模式（兼容）：直接生成代码文本，需要后处理提取
    """
    
    def __init__(
        self,
        model: str = "gpt-4o-mini",
        api_keys: Optional[Dict[str, str]] = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        node_id: str = "",
        use_tool_calling: bool = True,  # 默认启用 tool calling
    ):
        self.logger = LoggerUtils(component_name="WordActor")
        self.node_id = node_id
        self.use_tool_calling = use_tool_calling
        
        # 初始化 VLM 客户端
        config = LLMConfig(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            role="word_actor",
            node_id=node_id,
        )
        self.vlm = VLMClient(config=config, api_keys=api_keys, logger=self.logger)
    
    def set_node_id(self, node_id: str):
        """更新节点 ID"""
        self.node_id = node_id
        self.vlm.config.node_id = node_id
    
    async def act(
        self,
        planner_output: PlannerOutput,
        document_snapshot: Optional[DocumentSnapshot] = None,
        log_dir: Optional[str] = None,
    ) -> WordAction:
        """
        生成代码
        
        根据 use_tool_calling 设置自动选择模式：
        - Tool Calling 模式：使用 LLM function calling，输出更可靠
        - 纯文本模式：直接生成代码，需要后处理
        
        Args:
            planner_output: Planner 的输出
            document_snapshot: 当前文档快照
            log_dir: 日志目录
            
        Returns:
            WordAction 对象
        """
        # 如果任务已完成，返回 stop
        if planner_output.is_milestone_completed:
            return WordAction.stop()
        
        if self.use_tool_calling:
            return await self._act_with_tool_calling(planner_output, document_snapshot, log_dir)
        else:
            return await self._act_text_mode(planner_output, document_snapshot, log_dir)
    
    async def _act_with_tool_calling(
        self,
        planner_output: PlannerOutput,
        document_snapshot: Optional[DocumentSnapshot] = None,
        log_dir: Optional[str] = None,
    ) -> WordAction:
        """
        使用 Tool Calling 模式生成代码
        
        优点：代码直接从 tool_calls 参数中获取，不会混入解释文字
        """
        # 构建 prompt
        document_info = self._format_document_info(document_snapshot)
        user_prompt = ACTOR_USER_PROMPT.format(
            action_description=planner_output.next_action,
            document_info=document_info,
        )
        
        # 获取截图（如果有）
        screenshot_base64 = document_snapshot.screenshot if document_snapshot else None
        
        try:
            response = await self.vlm.call_with_tools(
                prompt=user_prompt,
                tools=[EXECUTE_POWERSHELL_TOOL],
                system_prompt=ACTOR_SYSTEM_PROMPT_TOOL_CALLING,
                tool_choice="required",  # 强制使用工具
                screenshot_base64=screenshot_base64,
                log_dir=log_dir,
            )
            
            # 从 tool_calls 中提取代码
            if response["has_tool_calls"] and response["tool_calls"]:
                tool_call = response["tool_calls"][0]
                code = tool_call.get("args", {}).get("code", "")
                
                if code:
                    self.logger.logger.info(f"[WordActor] Tool calling 成功，代码长度: {len(code)}")
                    code = self._validate_and_clean_code(code)
                    return WordAction.execute_code(code=code, language="PowerShell")
            
            # 如果 tool calling 失败，回退到文本模式
            self.logger.logger.warning("[WordActor] Tool calling 未返回代码，回退到文本提取")
            if response["content"]:
                code = self._extract_code(response["content"])
                code = self._validate_and_clean_code(code)
                return WordAction.execute_code(code=code, language="PowerShell")
            
            # 完全失败
            self.logger.logger.error("[WordActor] Tool calling 失败，无法获取代码")
            return WordAction.execute_code(
                code="Write-Host 'Error: Failed to generate code'",
                language="PowerShell"
            )
            
        except Exception as e:
            self.logger.logger.error(f"[WordActor] Tool calling 异常: {e}", exc_info=True)
            # 回退到纯文本模式
            return await self._act_text_mode(planner_output, document_snapshot, log_dir)
    
    async def _act_text_mode(
        self,
        planner_output: PlannerOutput,
        document_snapshot: Optional[DocumentSnapshot] = None,
        log_dir: Optional[str] = None,
    ) -> WordAction:
        """
        纯文本模式生成代码（旧方法，作为回退）
        """
        # 构建 prompt
        document_info = self._format_document_info(document_snapshot)
        user_prompt = ACTOR_USER_PROMPT.format(
            action_description=planner_output.next_action,
            document_info=document_info,
        )
        
        # 获取截图（如果有）
        screenshot_base64 = document_snapshot.screenshot if document_snapshot else None
        
        response = await self.vlm.call(
            prompt=user_prompt,
            system_prompt=ACTOR_SYSTEM_PROMPT,
            screenshot_base64=screenshot_base64,
            log_dir=log_dir,
        )
        
        # 提取代码
        code = self._extract_code(response["content"])
        
        # 验证和清理代码
        code = self._validate_and_clean_code(code)
        
        return WordAction.execute_code(code=code, language="PowerShell")
    
    async def act_streaming(
        self,
        planner_output: PlannerOutput,
        document_snapshot: Optional[DocumentSnapshot] = None,
        log_dir: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式生成代码
        
        注意：Tool Calling 模式不支持流式输出，会使用非流式调用然后一次性返回结果。
        纯文本模式支持真正的流式输出。
        
        Yields:
            ReasoningDeltaEvent - 代码生成过程
            ActionEvent - 最终动作
        """
        # 如果任务已完成，直接返回 stop
        if planner_output.is_milestone_completed:
            action = WordAction.stop()
            yield ActionEvent(action=action).to_dict()
            return
        
        if self.use_tool_calling:
            # Tool Calling 模式：非流式调用，然后一次性返回
            async for event in self._act_streaming_with_tool_calling(
                planner_output, document_snapshot, log_dir
            ):
                yield event
        else:
            # 纯文本模式：真正的流式输出
            async for event in self._act_streaming_text_mode(
                planner_output, document_snapshot, log_dir
            ):
                yield event
    
    async def _act_streaming_with_tool_calling(
        self,
        planner_output: PlannerOutput,
        document_snapshot: Optional[DocumentSnapshot] = None,
        log_dir: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Tool Calling 模式的"流式"输出
        
        实际上是非流式调用，但为了保持接口一致，包装成流式事件
        """
        # 构建 prompt
        document_info = self._format_document_info(document_snapshot)
        user_prompt = ACTOR_USER_PROMPT.format(
            action_description=planner_output.next_action,
            document_info=document_info,
        )
        
        # 获取截图（如果有）
        screenshot_base64 = document_snapshot.screenshot if document_snapshot else None
        
        try:
            # 发送一个开始事件
            yield ReasoningDeltaEvent(content="Generating PowerShell code...", source="actor").to_dict()
            
            response = await self.vlm.call_with_tools(
                prompt=user_prompt,
                tools=[EXECUTE_POWERSHELL_TOOL],
                system_prompt=ACTOR_SYSTEM_PROMPT_TOOL_CALLING,
                tool_choice="required",
                screenshot_base64=screenshot_base64,
                log_dir=log_dir,
            )
            
            # 从 tool_calls 中提取代码
            if response["has_tool_calls"] and response["tool_calls"]:
                tool_call = response["tool_calls"][0]
                code = tool_call.get("args", {}).get("code", "")
                
                if code:
                    self.logger.logger.info(f"[WordActor] Tool calling 成功，代码长度: {len(code)}")
                    code = self._validate_and_clean_code(code)
                    
                    # 发送代码内容作为 delta（让前端能看到生成的代码）
                    yield ReasoningDeltaEvent(content=code, source="actor").to_dict()
                    
                    # 发送最终动作
                    action = WordAction.execute_code(code=code, language="PowerShell")
                    yield ActionEvent(action=action).to_dict()
                    return
            
            # Tool calling 失败，回退
            self.logger.logger.warning("[WordActor] Tool calling 未返回代码，尝试从 content 提取")
            if response["content"]:
                code = self._extract_code(response["content"])
                code = self._validate_and_clean_code(code)
                yield ReasoningDeltaEvent(content=code, source="actor").to_dict()
                action = WordAction.execute_code(code=code, language="PowerShell")
                yield ActionEvent(action=action).to_dict()
                return
            
            # 完全失败
            yield {"type": "error", "content": "Failed to generate code via tool calling"}
            
        except Exception as e:
            self.logger.logger.error(f"[WordActor] Tool calling 异常: {e}", exc_info=True)
            # 回退到纯文本模式
            async for event in self._act_streaming_text_mode(
                planner_output, document_snapshot, log_dir
            ):
                yield event
    
    async def _act_streaming_text_mode(
        self,
        planner_output: PlannerOutput,
        document_snapshot: Optional[DocumentSnapshot] = None,
        log_dir: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        纯文本模式的流式输出（旧方法）
        """
        # 构建 prompt
        document_info = self._format_document_info(document_snapshot)
        user_prompt = ACTOR_USER_PROMPT.format(
            action_description=planner_output.next_action,
            document_info=document_info,
        )
        
        # 获取截图（如果有）
        screenshot_base64 = document_snapshot.screenshot if document_snapshot else None
        
        full_content = ""
        
        async for chunk in self.vlm.stream(
            prompt=user_prompt,
            system_prompt=ACTOR_SYSTEM_PROMPT,
            screenshot_base64=screenshot_base64,
            log_dir=log_dir,
        ):
            if chunk["type"] == "delta":
                content = chunk["content"]
                if isinstance(content, list):
                    content = "".join(str(c) for c in content)
                full_content += content
                yield ReasoningDeltaEvent(content=content, source="actor").to_dict()
                
            elif chunk["type"] == "complete":
                code = self._extract_code(full_content)
                code = self._validate_and_clean_code(code)
                action = WordAction.execute_code(code=code, language="PowerShell")
                yield ActionEvent(action=action).to_dict()
                
            elif chunk["type"] == "error":
                yield {"type": "error", "content": chunk["content"]}
    
    def _format_document_info(self, snapshot: Optional[DocumentSnapshot]) -> str:
        """
        格式化文档信息（包含详细的段落内容）
        
        使用 snapshot.to_context_format() 获取完整的文档上下文，
        这样 Actor 可以看到段落内容，更准确地生成代码。
        """
        if not snapshot or not snapshot.has_data:
            return "No document currently open. Word may need to be started."
        
        # 使用 to_context_format 获取完整的文档信息（包含段落内容）
        return snapshot.to_context_format(max_paragraphs=50, max_text_length=200)
    
    def _extract_code(self, text: str) -> str:
        """从 LLM 响应中提取代码"""
        text = text.strip()
        
        # 尝试提取 markdown 代码块
        patterns = [
            r'```powershell\s*\n(.*?)\n```',
            r'```ps1\s*\n(.*?)\n```',
            r'```\s*\n(.*?)\n```',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        # 如果没有代码块，检查是否整个响应就是代码
        if "$word" in text or "Word.Application" in text:
            return text
        
        return text
    
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
        
        # 注意：不要用正则清理所有中文！文件路径可能包含中文。
        # 如果 LLM 生成了中文注释，保留它们也没问题。
        
        return code
