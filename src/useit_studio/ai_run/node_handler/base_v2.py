"""
Node Handler V2 - 统一的节点处理器接口

这是新架构的核心接口定义，所有节点处理器都应该实现这个接口。

设计原则：
1. 统一接口 - 所有节点类型使用相同的 async generator 接口
2. 上下文对象 - 使用 NodeContext 封装所有参数
3. 统一事件 - 所有 handler 输出相同格式的事件
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import (
    Dict,
    List,
    Any,
    Optional,
    AsyncGenerator,
    TYPE_CHECKING,
)

import logging
import os

if TYPE_CHECKING:
    from useit_studio.ai_run.agent_loop.workflow.flow_processor import FlowProcessor
    from useit_studio.ai_run.skills.skill_loader import SkillContent

logger = logging.getLogger(__name__)


# ==================== 统一的上下文对象 ====================

# 不需要截图的节点类型（含 agent，便于无显示器环境）
SCREENSHOT_NOT_REQUIRED_TYPES = frozenset({"start", "end", "loop-start", "agent", "agent-node"})


@dataclass
class NodeContext:
    """
    统一的节点执行上下文
    
    封装所有节点执行需要的参数，避免 17 个参数的函数签名。
    
    使用方式：
        ctx = NodeContext(
            flow_processor=fp,
            node_id="node_1",
            node_dict={...},
            node_state={...},
            node_type="computer-use-gui",
            screenshot_path="/path/to/screenshot.png",
        )
    """
    # ===== 必需参数 =====
    flow_processor: "FlowProcessor"
    node_id: str
    node_dict: Dict[str, Any]
    node_state: Dict[str, Any]
    node_type: str
    screenshot_path: str = ""  # 可选：某些节点类型不需要截图（如 start, end, loop-start）
    
    # ===== 环境数据 =====
    uia_data: Optional[Dict[str, Any]] = None
    
    # ===== 历史数据 =====
    action_history: Dict[str, List[str]] = field(default_factory=dict)
    history_md: Optional[str] = None
    
    # ===== 任务信息 =====
    task_id: str = ""
    query: str = ""  # 用户的原始查询/任务描述
    log_folder: str = "./logs"
    project_id: Optional[str] = None  # 用于 S3 输出上传 (projects/project_id/outputs)
    chat_id: Optional[str] = None   # 用于 RAG 检索范围等

    # 用户机器上项目根目录的绝对路径（如 `D:\Workspace\useit-studio`），由前端从
    # currentProject.path 透传。注意这只在 *prompt* 里用 —— planner 需要把
    # attached_files[].path（相对路径，如 `workspace/test.pptx`）拼成用户机器
    # 上的真实绝对路径塞进 ## Attached Files 段，让它生成 ppt_document open
    # 时直接用现成的字符串（而不是瞎编 C:\Users\Administrator\Desktop\...）。
    # 后端进程本身不会去 stat / open 这条路径 —— Linux 容器里没有 D:\ 盘。
    project_path: Optional[str] = None

    # ===== 模型配置 =====
    planner_model: str = "gpt-4o-mini"
    planner_api_keys: Optional[Dict[str, str]] = None
    actor_model: str = "oai-operator"
    
    # ===== 可选组件（按需注入） =====
    gui_parser: Optional[Any] = None
    actor: Optional[Any] = None
    
    # ===== 执行结果（tool_call 回调） =====
    execution_result: Optional[Dict[str, Any]] = None  # Backend 传递的 tool_call 执行结果
    
    # ===== 附件文件 =====
    attached_files: Optional[List[Dict[str, Any]]] = None  # 用户附加的文件列表，每个包含 path, name, type, local_path
    attached_images: Optional[List[Dict[str, Any]]] = None  # 用户附加的图片列表，每个包含 name, base64, mime_type
    
    # ===== 项目上下文 =====
    additional_context: Optional[str] = None  # 项目目录结构等额外上下文信息

    # ===== 跨层 Clarifications =====
    # 用户在 orchestrator 层或更早 agent_node 里已经回答过的 ask_user Q&A。
    # 由 FlowProcessor.step(clarifications=...) 注入；planner 在 prompt 里
    # 看到 "## User Clarifications" 时就当作既定事实处理，不要再重新问一遍。
    # 具体数据结构见 ``useit_ai_run.agent_loop.action_models.Clarification``
    # （保留为 ``Any`` 避免 node_handler -> agent_loop 的循环导入）。
    clarifications: List[Any] = field(default_factory=list)

    # ===== 日志组件 =====
    run_logger: Optional[Any] = None  # RunLogger 实例，用于日志落盘和 S3 上传

    # ===== Skills 支持 =====
    skills: List[str] = field(default_factory=list)
    """配置的 skill 名称列表"""

    skill_contents: Optional[Dict[str, 'SkillContent']] = None
    """加载后的 skill 内容映射(只包含 SKILL.md)"""

    # ===== 辅助方法 =====
    
    def get_node_title(self) -> str:
        """获取节点标题"""
        data = self.node_dict.get("data", {})
        return (
            data.get("title") or
            self.node_dict.get("title") or
            self.node_id
        )
    
    def get_base_instruction(self) -> str:
        """获取节点的原始指令（不含循环上下文）
        
        返回节点配置中的静态指令。
        """
        data = self.node_dict.get("data", {})
        return (
            data.get("instruction") or
            data.get("description") or
            self.node_dict.get("description") or
            self.query or
            ""
        )
    
    def get_loop_context_prompt(self) -> str:
        """获取循环上下文的 prompt 片段
        
        如果不在循环中或没有迭代计划，返回空字符串。
        返回格式化的循环信息，包括当前迭代、总迭代数、当前任务和整体计划。
        """
        loop_ctx = self.get_loop_context()
        if not loop_ctx:
            return ""
        
        iteration_plan = loop_ctx.get("iteration_plan", [])
        if not iteration_plan:
            return ""
        
        current = loop_ctx["current_iteration"]
        total = len(iteration_plan)
        current_subtask = loop_ctx.get("current_subtask", "")
        loop_goal = loop_ctx.get("loop_goal", "")
        
        # 构建计划概览
        plan_lines = []
        for i, task in enumerate(iteration_plan):
            marker = " ← Current" if i == current else ""
            status = "✓" if i < current else ("→" if i == current else " ")
            plan_lines.append(f"  {status} {i+1}. {task}{marker}")
        plan_overview = "\n".join(plan_lines)
        
        return f"""## Loop Context
You are executing iteration {current + 1} of {total} in a loop.

### Loop Goal
{loop_goal}

### Current Task (Iteration {current + 1})
{current_subtask}

### Overall Plan
{plan_overview}

**Important**: Focus on completing the current task above. Do not attempt other iterations.
"""
    
    def get_node_instruction(self) -> str:
        """获取节点指令
        
        如果在循环中，自动拼接循环上下文和原始指令。
        这样所有节点无需修改即可获得循环信息。
        """
        base_instruction = self.get_base_instruction()
        loop_prompt = self.get_loop_context_prompt()
        
        if loop_prompt:
            # 在循环中：拼接循环上下文 + 原始指令
            return f"""{loop_prompt}
## Node Instruction
{base_instruction}
"""
        
        # 不在循环中：返回原始指令
        return base_instruction
    
    def get_action_history_for_node(self) -> List[str]:
        """获取当前节点的动作历史"""
        return self.action_history.get(self.node_id, [])
    
    def is_in_loop(self) -> bool:
        """检查是否在循环中"""
        return bool(
            self.node_state.get("loop_id") or
            self.node_dict.get("parentNode") or
            self.node_dict.get("parentId")
        )
    
    def get_loop_context(self) -> Optional[Dict[str, Any]]:
        """获取循环上下文，包括当前迭代的具体子任务"""
        loop_id = (
            self.node_state.get("loop_id") or
            self.node_dict.get("parentNode") or
            self.node_dict.get("parentId")
        )
        if not loop_id:
            return None
        
        # 从 flow_processor 获取循环节点信息
        loop_node = self.flow_processor.graph_manager.get_milestone_by_id(loop_id)
        if not loop_node:
            return None
        
        loop_data = loop_node.get("data", {})
        
        # 从 flow_processor.node_states 获取循环状态（包含 iteration_plan）
        loop_state = {}
        if self.flow_processor:
            loop_state = self.flow_processor.node_states.get(loop_id, {})
        
        # 获取迭代计划和当前迭代索引
        iteration_plan = loop_state.get("iteration_plan", [])
        current_iteration = loop_state.get("iteration", 0)
        
        # 获取当前迭代的具体子任务
        current_subtask = ""
        if iteration_plan and current_iteration < len(iteration_plan):
            current_subtask = iteration_plan[current_iteration]
        
        return {
            "loop_id": loop_id,
            "current_iteration": current_iteration,
            "max_iterations": loop_data.get("max_iteration", loop_data.get("max_iterations", 1)),
            "loop_goal": (
                loop_data.get("instruction") or
                loop_data.get("condition") or
                loop_data.get("description") or
                loop_data.get("title") or
                ""
            ),
            "iteration_plan": iteration_plan,
            "current_subtask": current_subtask,
            "total_iterations": len(iteration_plan) if iteration_plan else loop_data.get("max_iteration", loop_data.get("max_iterations", 1)),
        }
    
    async def get_attached_files_content(
        self,
        max_chars_per_file: int = 150000,  # ~35K tokens
        max_files: int = 3,
        skip_routing: bool = False,
    ) -> str:
        """
        读取 attached_files 的内容并格式化为 prompt 可用的文本
        
        包含智能路由：使用小模型判断当前请求是否需要加载文件内容，
        避免在不需要文件的步骤中浪费 token。
        
        支持的文件类型：
        - 文本文件: .py, .txt, .json, .md, .yaml, .yml, .csv, .xml, .html, .css, .js, .ts, .jsx, .tsx, .sql, .sh, .bash, .log, .ini, .cfg, .conf, .toml
        
        暂不支持（需要用其他工具预处理）：
        - Office 文件: .docx, .xlsx, .pptx
        - PDF 文件: .pdf
        - 图片文件: .png, .jpg, .jpeg, .gif, .webp
        
        Args:
            max_chars_per_file: 每个文件的最大字符数，默认 150000（约 35K tokens）
            max_files: 最多读取的文件数，默认 3
            skip_routing: 是否跳过智能路由判断，直接加载文件（默认 False）
            
        Returns:
            格式化的文件内容字符串，如果没有附件或不需要加载则返回空字符串
        """
        if not self.attached_files:
            return ""

        import os

        # Office 扩展名 → 必须用哪个 agent tool 来 open 它。这是修复
        # "用户上传了 test.pptx 但 planner 选 system_process_control
        # launch PowerPoint，而不是 ppt_document open" 的关键提示 ——
        # 我们直接把这条 hard rule 写进 prompt 段。
        OFFICE_OPEN_TOOL = {
            ".pptx": "ppt_document",
            ".ppt": "ppt_document",
            ".docx": "word_document",
            ".doc": "word_document",
            ".xlsx": "excel_document",
            ".xls": "excel_document",
        }

        # 这些类型必须无条件出现在 prompt 里 —— 它们没有第二个通道告诉
        # planner "用户附了哪个文件、放在哪"，路由一刀切就等于消失。
        FORCE_INCLUDE_EXTS = set(OFFICE_OPEN_TOOL.keys()) | {".pdf"}

        # 先扫一遍，看本批附件里是不是有强制注入的类型。
        has_force_include = False
        for fi in self.attached_files:
            if fi.get("type") != "file":
                continue
            fname = fi.get("name", fi.get("path", ""))
            _, ext_low = os.path.splitext(fname.lower())
            if ext_low in FORCE_INCLUDE_EXTS:
                has_force_include = True
                break

        # ===== Step 1: 永远先生成"附件路径清单"（即使内容不被加载） =====
        # 上层的 should_include_attached_files 路由只决定是否把文件
        # *内容* 塞进 prompt；但文件 *路径* 必须无条件地告诉 planner —
        # 否则像 .pptx / .docx 这种不可读类型会被完全丢弃，planner 根本
        # 不知道用户 attach 过什么。
        listing_sections: List[str] = []
        for file_info in self.attached_files:
            if file_info.get("type") != "file":
                continue
            fname = file_info.get("name", file_info.get("path", "unknown"))
            # 优先用 path（前端发的相对路径，需要拼 project_path），其次
            # local_path（S3 下载的本地缓存路径，绝对路径）。注意这里
            # 解析出的是 *用户机器上* 的路径 —— 后端不会去访问。
            raw_rel = file_info.get("path") or fname
            user_path = self._resolve_user_path(raw_rel)

            _, ext = os.path.splitext(fname.lower())

            block = [f"### File: {fname}", f"**Path on user's machine:** `{user_path}`"]

            if ext in OFFICE_OPEN_TOOL:
                tool = OFFICE_OPEN_TOOL[ext]
                tool_prefix = tool.split("_")[0]  # ppt / word / excel
                block.append(
                    f"**To open:** call `{tool}` with `action=\"open\"` and "
                    f"`file_path=\"{user_path}\"` BEFORE any other "
                    f"`{tool_prefix}_*` tool. Use this exact string verbatim "
                    f"as `file_path`; do NOT invent a different absolute "
                    f"path (no `C:\\Users\\Administrator\\Desktop\\…`)."
                )
            elif ext == ".pdf":
                block.append(
                    f"**To extract text:** call `doc_extract` with "
                    f"`pdf_path=\"{user_path}\"`."
                )

            listing_sections.append("\n".join(block) + "\n")

        listing_section = ""
        if listing_sections:
            listing_section = (
                "## Attached Files\n\n"
                "The user attached the following file(s) on this turn. "
                "**Treat them as the user's intended targets** — when the "
                "goal involves a desktop app whose document type matches "
                "an attachment below, open that exact file (using the "
                "tool hinted on each block) instead of launching a blank "
                "instance of the app.\n\n"
                + "\n".join(listing_sections)
            )

        # ===== Step 2: 智能路由：判断是否需要 *加载文件内容* =====
        # （路径清单 listing_section 已经无条件准备好了；这里只决定是否
        # 把文本文件的 body 也塞进去。）
        #
        # 关键：当本批包含 Office / PDF 这类 "路径就是核心信号" 的附件时，
        # 直接 bypass 路由 —— 路由是基于 file_names 的小模型判断，对
        # `test.pptx` 这种泛文件名很可能返回 False，从而把整段 listing
        # 也吞掉（return ""）。我们让它走 listing-only 分支，至少
        # planner 能看见路径和 ppt_document open 指引。
        if not skip_routing and not has_force_include:
            from useit_studio.ai_run.utils.attached_files_router import should_include_attached_files

            file_names = [
                f.get("name", f.get("path", "unknown"))
                for f in self.attached_files
                if f.get("type") == "file"
            ]

            if file_names:
                history_md = self.get_history_md()
                need_files = await should_include_attached_files(
                    query=self.query,
                    history_md=history_md,
                    file_names=file_names,
                    api_keys=self.planner_api_keys,
                )

                if not need_files:
                    # 仍然返回路径清单，避免 .pptx / .docx 这种附件
                    # 在 planner 视野里完全消失。
                    return listing_section

        TEXT_EXTENSIONS = {
            '.py', '.txt', '.json', '.md', '.yaml', '.yml', '.csv', '.xml',
            '.html', '.css', '.js', '.ts', '.jsx', '.tsx', '.sql', '.sh',
            '.bash', '.log', '.ini', '.cfg', '.conf', '.toml', '.env',
            '.gitignore', '.dockerignore', '.editorconfig', '.prettierrc',
            '.eslintrc', '.babelrc', '.nvmrc', '.ruby-version', '.python-version',
            '.c', '.cpp', '.h', '.hpp', '.java', '.go', '.rs', '.swift', '.kt',
            '.scala', '.r', '.R', '.m', '.mm', '.pl', '.pm', '.rb', '.php',
            '.vue', '.svelte', '.astro',
        }
        
        # 不支持的文件类型（需要预处理）
        UNSUPPORTED_EXTENSIONS = {
            '.docx', '.xlsx', '.pptx', '.doc', '.xls', '.ppt',
            '.pdf',
            '.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.ico', '.svg',
            '.zip', '.tar', '.gz', '.rar', '.7z',
            '.exe', '.dll', '.so', '.dylib',
            '.mp3', '.mp4', '.wav', '.avi', '.mov', '.mkv',
        }
        
        # PDF 专用扩展名集合
        PDF_EXTENSIONS = {'.pdf'}
        
        sections = []
        files_processed = 0

        for file_info in self.attached_files:
            if files_processed >= max_files:
                break

            # 只处理 type="file" 的项
            if file_info.get("type") != "file":
                continue

            file_name = file_info.get("name", file_info.get("path", "unknown"))
            _, ext = os.path.splitext(file_name.lower())

            local_path = file_info.get("local_path")
            
            # ===== PDF 文件：确保已下载到本地，暴露 local_path 给 doc_extract =====
            if ext in PDF_EXTENSIONS:
                # 如果 local_path 缺失或文件不存在，尝试从 S3 下载
                if not local_path or not os.path.exists(local_path):
                    local_path = await self._ensure_pdf_downloaded(file_info)
                    if local_path:
                        # 回写 local_path 到 file_info，供后续 agent 使用
                        file_info["local_path"] = local_path
                
                if local_path and os.path.exists(local_path):
                    sections.append(
                        f"### File: {file_name}\n"
                        f"**Local Path:** `{local_path}`\n"
                        f"(PDF file — use the `doc_extract` tool to extract text and figures. "
                        f"Pass the local path above as the `pdf_path` argument.)\n"
                    )
                else:
                    sections.append(
                        f"### File: {file_name}\n"
                        f"(PDF file — failed to download from S3. "
                        f"The file is not available for local processing.)\n"
                    )
                files_processed += 1
                continue
            
            # Office files (.pptx / .docx / .xlsx) 已经在上方 listing_section
            # 里给出了 "use ppt_document open ..." 的明确提示；不需要在这里
            # 再追加一个让人困惑的 "convert to text/markdown" 占位条目。
            if ext in OFFICE_OPEN_TOOL:
                continue

            # 其它不支持类型（.zip/.exe/媒体等）：以前 local_path 缺失会被
            # 静默 drop，planner 完全看不到。改成无条件输出一条 "用户机器
            # 上的路径在这里" 的 stub，至少保留可见性 —— listing_section 里
            # 已经有了，但内容块这里再补一条更明确的 "不可直接读取" 说明
            # 仅在 local_path 存在时；否则 listing_section 已经覆盖了。
            if ext in UNSUPPORTED_EXTENSIONS:
                if local_path:
                    sections.append(
                        f"### File: {file_name}\n"
                        f"**Local Path:** `{local_path}`\n"
                        f"(This file type '{ext}' is not supported for direct "
                        f"reading. Please use appropriate tools to convert it "
                        f"to text/markdown first.)\n"
                    )
                    files_processed += 1
                continue

            # 文本类型但 local_path 缺失：跳过（无法读取内容，但 listing_section
            # 已经把路径暴露给 planner 了）。
            if not local_path:
                continue
            
            # 尝试读取文件
            try:
                if not os.path.exists(local_path):
                    sections.append(
                        f"### File: {file_name}\n"
                        f"(File not found at: {local_path})\n"
                    )
                    files_processed += 1
                    continue
                
                # 检查文件大小
                file_size = os.path.getsize(local_path)
                
                # 读取文件内容
                with open(local_path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read(max_chars_per_file)
                
                # 检查是否被截断
                truncated = len(content) >= max_chars_per_file
                
                # 格式化输出
                section = f"### File: {file_name}\n"
                if truncated:
                    section += f"(Truncated: showing first {max_chars_per_file} characters of {file_size} bytes)\n"
                section += f"```\n{content}\n```\n"
                
                sections.append(section)
                files_processed += 1
                
            except UnicodeDecodeError:
                sections.append(
                    f"### File: {file_name}\n"
                    f"(Unable to read file: binary or non-UTF8 encoding)\n"
                )
                files_processed += 1
            except Exception as e:
                sections.append(
                    f"### File: {file_name}\n"
                    f"(Error reading file: {str(e)})\n"
                )
                files_processed += 1
        
        # 拼装最终输出：listing_section（路径清单 + 工具提示）始终在最前；
        # sections 里是文本/PDF 的内容详细块，路径已经被 listing_section
        # 覆盖，不再重复 "## Attached Files" 标题。
        if not sections:
            return listing_section
        body = "\n".join(sections)
        if listing_section:
            return listing_section + "\n" + body
        return "## Attached Files\n\n" + body
    
    async def _ensure_pdf_downloaded(self, file_info: Dict[str, Any]) -> Optional[str]:
        """
        确保 PDF 文件已从 S3 下载到本地
        
        当 attached_files 中的 PDF 缺少 local_path 或文件不存在时，
        尝试通过 S3Downloader 下载到本地缓存。
        
        Args:
            file_info: 附件信息字典，包含 path, name, type 等字段
            
        Returns:
            本地文件绝对路径，下载失败返回 None
        """
        import os
        
        relative_path = file_info.get("path", "")
        if not relative_path or not self.project_id:
            return None
        
        try:
            from useit_studio.ai_run.utils.s3_downloader import get_s3_downloader
            
            s3_downloader = get_s3_downloader()
            local_path = await s3_downloader.download_file_async(
                relative_path=relative_path,
                project_id=self.project_id,
            )
            
            if local_path and os.path.exists(local_path):
                file_name = file_info.get("name", relative_path)
                logger.info(f"[NodeContext] PDF downloaded from S3: {file_name} -> {local_path}")
                return local_path
            else:
                logger.warning(f"[NodeContext] Failed to download PDF from S3: {relative_path}")
                return None
                
        except Exception as e:
            logger.warning(f"[NodeContext] S3 download error for PDF '{relative_path}': {e}")
            return None

    def _resolve_user_path(self, relative_or_abs_path: str) -> str:
        """
        把 attached_files[].path 解析成用户机器上的绝对路径，仅用于 prompt。

        前端在发请求前会做 `path.replace(projectPath, '')`，所以传到后端的
        通常是 `workspace/test.pptx` 这种相对项目根的路径。planner 在生成
        ppt_document/word_document/excel_document 的 file_path 参数时必须
        用绝对路径，否则用户那边的 desktop_use 拿不到对的文件。

        规则：
        - 输入已经是绝对路径（Windows: `C:\\...` / `D:\\...`，Unix: `/...`），
          直接归一化为 Windows 反斜杠形式后返回。
        - self.project_path 缺失：保底返回原始相对路径（前端会用 projectPath
          作为兜底拼一次，但那是 fallback，主流程仍然依赖这里的 prompt）。
        - 正常情况：把 project_path 和 relative_path 用反斜杠拼起来。

        注意：这里 *只是构造字符串*，不去 stat / 检查文件是否存在 —— 后端
        Linux 容器里压根没有 `D:\\` 盘。真正打开文件是用户那边的 desktop_use
        干的活。
        """
        import os
        import re

        if not relative_or_abs_path:
            return ""

        def _to_backslash(p: str) -> str:
            # Windows 路径用反斜杠；正斜杠 / 混合分隔符 / 多余的连续 \
            # 全部归一化，避免 prompt 里出现 `D:\Workspace/useit-studio\workspace/test.pptx`
            # 这种 planner 会复制粘贴的丑陋字符串。
            return re.sub(r"[\\/]+", "\\\\", p).rstrip("\\")

        s = relative_or_abs_path.strip()

        # 已经是绝对路径就不再拼。Windows 盘符：`C:\` / `D:/`；Unix：`/abs`。
        if re.match(r"^[a-zA-Z]:[\\/]", s) or s.startswith("/") or s.startswith("\\\\"):
            return _to_backslash(s)

        if not self.project_path:
            # 没有 project_path 就只能把原字符串返出去 —— planner 看到相对路径
            # 至少不会编出错的绝对路径，前端 fallback 还能救。
            return s.replace("/", "\\")

        return _to_backslash(self.project_path + "/" + s)

    def get_history_md(self) -> str:
        """
        从 RuntimeStateManager 生成 AI 上下文 Markdown

        直接使用 AIMarkdownTransformer，避免维护多套数据结构。

        Returns:
            格式化的 Markdown 字符串，包含：
            - 已完成节点的摘要
            - 当前节点的状态
            - 待执行节点（如果有图定义）
        """
        try:
            from useit_studio.ai_run.runtime.transformers.ai_markdown_transformer import AIMarkdownTransformer

            # 获取 runtime state
            runtime_state = self.flow_processor.runtime_state.state

            # 获取图定义（用于显示待执行节点）
            graph_nodes = None
            graph_edges = None
            if hasattr(self.flow_processor, 'graph_manager'):
                graph_nodes = self.flow_processor.graph_manager.nodes
                graph_edges = self.flow_processor.graph_manager.edges

            # 使用 AIMarkdownTransformer 生成
            transformer = AIMarkdownTransformer(
                state=runtime_state,
                include_variables=False,  # Planner 不需要变量
                include_history=False,    # 历史已在 plan tree 中
                graph_nodes=graph_nodes,
                graph_edges=graph_edges,
            )

            return transformer.transform()

        except Exception as e:
            # 如果出错，返回空字符串（降级处理）
            return f"(History generation failed: {str(e)})"

    # ===== Skills 访问方法 =====

    def get_skills_prompt(self) -> str:
        """
        获取 skills 的初始 prompt 内容

        ⚠️ 只包含 SKILL.md 的内容！

        其他文件（scripts, references）由 AI 按需读取。
        在 SKILL.md 中应该包含：
        - 简介和使用说明
        - 告诉 AI 哪些文件可用（如 "See scripts/helper.py"）
        - AI 会自己决定是否需要读取这些文件

        Returns:
            格式化的 skills prompt（只包含 SKILL.md）
        """
        if not self.skill_contents:
            return ""

        sections = []

        for skill_name, skill in self.skill_contents.items():
            sections.append(f"## Skill: {skill.metadata.name}\n")
            sections.append(f"**Base Directory**: `{skill.base_dir}`\n")

            if skill.metadata.context:
                sections.append(f"**Context**: {skill.metadata.context}\n")

            # 只包含 SKILL.md 的内容
            sections.append(f"\n{skill.content}\n")
            sections.append("\n---\n")

        if not sections:
            return ""

        header = "# Available Skills\n\n"
        header += "The following skills are available. Each skill provides guidance and references to additional resources.\n"
        header += "If you need to access scripts or detailed documentation mentioned in the skills, use the read_file tool.\n\n"

        return header + "\n".join(sections)

    def get_skill(self, skill_name: str) -> Optional['SkillContent']:
        """
        获取特定的 skill

        Args:
            skill_name: skill 名称

        Returns:
            SkillContent（只包含 SKILL.md 内容）
        """
        if not self.skill_contents:
            return None
        return self.skill_contents.get(skill_name)

    def get_skill_resource_path(self, skill_name: str, relative_path: str) -> Optional[str]:
        """
        获取 skill 资源的绝对路径

        这个路径可以传递给 AI，AI 可以用 read_file tool 读取。

        Args:
            skill_name: skill 名称
            relative_path: 资源相对路径，如 "scripts/helper.py"

        Returns:
            绝对路径字符串，如果 skill 不存在返回 None
        """
        skill = self.get_skill(skill_name)
        if not skill:
            return None
        return skill.get_resource_path(relative_path)


# ==================== 统一的事件类型 ====================

@dataclass
class NodeEvent:
    """
    节点事件基类
    
    所有 handler yield 的事件都应该继承这个类或使用 to_dict() 格式。
    """
    type: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.type}


@dataclass
class StreamingEvent(NodeEvent):
    """流式输出事件（推理过程）"""
    type: str = "streaming"
    content: str = ""
    source: str = "planner"  # "planner" | "actor"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "content": self.content,
            "source": self.source,
        }


@dataclass
class NodeStartEvent(NodeEvent):
    """节点开始事件"""
    type: str = "node_start"
    node_id: str = ""
    node_type: str = ""
    title: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "nodeId": self.node_id,
            "nodeType": self.node_type,
            "title": self.title,
        }


@dataclass
class NodeCompleteEvent(NodeEvent):
    """
    节点完成事件
    
    这是最重要的事件，包含：
    - 节点是否完成
    - handler 的返回结果（用于流程推进）
    - 流程控制字段（if-else 分支、loop break 等）
    - 可选的 markdown 输出（用于生成 XML 格式的 summary）
    """
    type: str = "node_complete"
    node_id: str = ""
    node_type: str = ""
    is_node_completed: bool = False
    is_workflow_completed: bool = False  # End 节点设置为 True 表示工作流完成
    handler_result: Dict[str, Any] = field(default_factory=dict)
    
    # 流程控制字段
    chosen_branch_id: Optional[str] = None  # if-else 选择的分支
    break_loop: Optional[bool] = None  # loop-end 是否跳出循环
    next_node_id: Optional[str] = None  # 显式指定下一个节点
    
    # 摘要信息
    action_summary: str = ""
    node_completion_summary: str = ""
    
    # Markdown 输出字段（用于生成 XML 格式的 summary）
    output_filename: Optional[str] = None  # 输出文件名，如 "report.md"
    result_markdown: Optional[str] = None  # markdown 内容
    
    def to_dict(self) -> Dict[str, Any]:
        # 构建最终的 node_completion_summary（可能是 XML 格式）
        final_summary = self._build_final_summary()
        
        result = {
            "type": self.type,
            "content": {
                "node_id": self.node_id,
                "node_type": self.node_type,
                "is_node_completed": self.is_node_completed,
                "is_workflow_completed": self.is_workflow_completed,
                "vlm_plan": self.handler_result,
                "action_summary": self.action_summary,
                "node_completion_summary": final_summary,
            }
        }
        
        # 添加流程控制字段（如果有）
        if self.chosen_branch_id:
            result["content"]["chosen_branch_id"] = self.chosen_branch_id
        if self.break_loop is not None:
            result["content"]["break_loop"] = self.break_loop
        if self.next_node_id:
            result["content"]["next_node_id"] = self.next_node_id
        
        return result
    
    def _build_final_summary(self) -> str:
        """
        构建最终的 node_completion_summary（统一使用 XML 格式）
        
        XML 格式:
        <result>
            <summary>简洁的摘要</summary>
            <output_file>filename.md</output_file>        <!-- 可选 -->
            <content><![CDATA[markdown 内容]]></content>  <!-- 可选 -->
        </result>
        """
        # 如果没有任何内容，返回空字符串
        if not self.node_completion_summary and not self.output_filename and not self.result_markdown:
            return ""
        
        # 统一构建 XML 格式
        lines = ["<result>"]
        
        if self.node_completion_summary:
            lines.append(f"    <summary>{self.node_completion_summary}</summary>")
        
        if self.output_filename:
            lines.append(f"    <output_file>{self.output_filename}</output_file>")
        
        if self.result_markdown:
            lines.append("    <content><![CDATA[")
            lines.append(self.result_markdown)
            lines.append("    ]]></content>")
        
        lines.append("</result>")
        
        return "\n".join(lines)


@dataclass
class WorkflowProgressEvent(NodeEvent):
    """工作流进度事件（由 StepExecutor 发出）"""
    type: str = "workflow_progress"
    next_node_id: Optional[str] = None
    is_workflow_completed: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "content": {
                "next_node_id": self.next_node_id,
                "is_workflow_completed": self.is_workflow_completed,
            }
        }


@dataclass
class ErrorEvent(NodeEvent):
    """错误事件"""
    type: str = "error"
    message: str = ""
    node_id: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "content": self.message,
            "nodeId": self.node_id,
        }


# ==================== 统一的 Handler 基类 ====================

class BaseNodeHandlerV2(ABC):
    """
    统一的节点处理器基类（V2）
    
    所有节点处理器都应该继承这个类并实现：
    1. supported_types() - 返回支持的节点类型列表
    2. execute() - 执行节点逻辑，yield 事件流
    
    使用方式：
        class MyHandler(BaseNodeHandlerV2):
            @classmethod
            def supported_types(cls) -> List[str]:
                return ["my-node-type"]
            
            async def execute(self, ctx: NodeContext) -> AsyncGenerator[Dict[str, Any], None]:
                yield NodeStartEvent(node_id=ctx.node_id).to_dict()
                # ... 执行逻辑 ...
                yield NodeCompleteEvent(
                    node_id=ctx.node_id,
                    is_node_completed=True,
                ).to_dict()
    """
    
    @classmethod
    @abstractmethod
    def supported_types(cls) -> List[str]:
        """
        返回此 Handler 支持的 node_type 列表
        
        Returns:
            List[str]: 支持的节点类型，如 ["computer-use-gui", "computer-use"]
        """
        pass
    
    @abstractmethod
    async def execute(self, ctx: NodeContext) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行节点逻辑
        
        Args:
            ctx: 节点执行上下文
            
        Yields:
            Dict[str, Any]: 事件字典，格式为 {"type": "...", ...}
            
        注意：
        - 最后一个事件应该是 NodeCompleteEvent
        - 所有事件都应该有 "type" 字段
        """
        pass
    
    # ==================== 辅助方法 ====================
    
    def _is_first_call(self, ctx: NodeContext) -> bool:
        """检查是否是节点的第一次调用"""
        step_count = ctx.node_state.get("_step_count", 0)
        return step_count == 0
    
    def _increment_step_count(self, ctx: NodeContext) -> int:
        """增加步数计数并返回新值
        
        直接从 exec_node.step_count 读取，避免依赖 ctx.node_state 快照
        （ctx.node_state 可能在 _update_node_state_dict 中被意外修改）
        """
        exec_node = ctx.flow_processor.runtime_state.state.get_node(ctx.node_id)
        if exec_node:
            step_count = exec_node.step_count + 1
            exec_node.step_count = step_count
            return step_count
        
        # fallback：从 node_state 快照读取
        step_count = ctx.node_state.get("_step_count", 0) + 1
        ctx.flow_processor.node_states[ctx.node_id] = {"_step_count": step_count}
        return step_count
    
    def _build_node_complete_event(
        self,
        ctx: NodeContext,
        is_completed: bool,
        handler_result: Dict[str, Any],
        action_summary: str = "",
        node_completion_summary: str = "",
        **kwargs,
    ) -> Dict[str, Any]:
        """构建节点完成事件的辅助方法"""
        return NodeCompleteEvent(
            node_id=ctx.node_id,
            node_type=ctx.node_type,
            is_node_completed=is_completed,
            handler_result=handler_result,
            action_summary=action_summary,
            node_completion_summary=node_completion_summary,
            **kwargs,
        ).to_dict()
    
    def _build_error_event(self, ctx: NodeContext, message: str) -> Dict[str, Any]:
        """构建错误事件的辅助方法"""
        return ErrorEvent(
            message=message,
            node_id=ctx.node_id,
        ).to_dict()
