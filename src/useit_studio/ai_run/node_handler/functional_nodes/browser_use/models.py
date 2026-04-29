"""
Browser Use - 数据模型定义

所有数据结构的单一真相来源，清晰定义输入输出格式。

与 GUI 的区别：
- GUI: 使用屏幕坐标 [x, y]
- Browser: 使用 DOM 元素索引 index，前端提供元素列表
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse


class BrowserActionType(str, Enum):
    """浏览器动作类型"""
    
    # ===== 单例模式连接管理 =====
    CONNECT = "connect"           # 启动新浏览器并连接
    ATTACH = "attach"             # 接管用户已打开的浏览器 (CDP)
    DISCONNECT = "disconnect"     # 断开连接
    STATUS = "status"             # 获取连接状态
    
    # ===== Session 管理（多实例模式） =====
    CREATE_SESSION = "create_session"
    ATTACH_SESSION = "attach_session"
    LIST_SESSIONS = "list_sessions"
    CLOSE_SESSION = "close_session"
    
    # ===== Tab 管理 =====
    LIST_TABS = "list_tabs"
    CREATE_TAB = "create_tab"
    SWITCH_TAB = "switch_tab"
    CLOSE_TAB = "close_tab"
    
    # ===== 导航 =====
    GO_TO_URL = "go_to_url"
    GO_BACK = "go_back"
    GO_FORWARD = "go_forward"
    REFRESH = "refresh"
    
    # ===== 元素交互 =====
    CLICK_ELEMENT = "click_element"
    INPUT_TEXT = "input_text"
    
    # ===== 滚动 =====
    SCROLL_DOWN = "scroll_down"
    SCROLL_UP = "scroll_up"
    
    # ===== 键盘 =====
    PRESS_KEY = "press_key"
    
    # ===== 其他 =====
    WAIT = "wait"
    SCREENSHOT = "screenshot"
    PAGE_STATE = "page_state"
    EXTRACT_CONTENT = "extract_content"
    STOP = "stop"


# ==================== 前端返回的数据结构 ====================

@dataclass
class DOMElement:
    """
    DOM 元素（前端解析后返回）
    
    前端通过 DOM Parser 提取可交互元素，返回给后端。
    """
    index: int                           # 元素索引（用于交互）
    tag: str                             # HTML 标签
    text: str                            # 可见文本
    attributes: Dict[str, str] = field(default_factory=dict)  # HTML 属性
    position: Optional[Dict[str, int]] = None  # 位置信息 {x, y, width, height}
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DOMElement":
        return cls(
            index=data.get("index", 0),
            tag=data.get("tag", ""),
            text=data.get("text", ""),
            attributes=data.get("attributes", {}),
            position=data.get("position"),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "tag": self.tag,
            "text": self.text,
            "attributes": self.attributes,
            "position": self.position,
        }
    
    def __str__(self) -> str:
        """
        用于 Prompt 的精简表示
        
        智能选择属性：
        - 保留：语义属性（role, id, aria-*）、状态属性（aria-selected 等）
        - 精简：href/class 截断，过滤装饰性属性
        - 删除：data-*, style, tabindex 等技术细节
        """
        key_attrs = []
        
        # === 核心属性（按重要性排序）===
        
        # 1. role - 定义元素的语义角色
        if 'role' in self.attributes:
            key_attrs.append(f'role="{self.attributes["role"]}"')
        
        # 2. id - 唯一标识
        if 'id' in self.attributes:
            key_attrs.append(f'id="{self.attributes["id"]}"')
        
        # 3. type - input 元素的类型
        if 'type' in self.attributes:
            key_attrs.append(f'type="{self.attributes["type"]}"')
        
        # === ARIA 属性（语义和状态）===
        
        # 按字母顺序遍历所有 aria-* 属性
        aria_attrs = sorted([k for k in self.attributes.keys() if k.startswith('aria-')])
        
        for attr in aria_attrs:
            value = self.attributes[attr]
            
            # aria-label 需要截断
            if attr == 'aria-label' and len(value) > 50:
                value = value[:50] + "..."
            
            key_attrs.append(f'{attr}="{value}"')
        
        # === 链接 href（精简显示）===
        if 'href' in self.attributes:
            href = self.attributes['href']
            # 过滤无意义的 href
            if href and href not in ['#', 'javascript:void(0)', 'javascript:void(0);']:
                # 截断长 URL
                if len(href) > 60:
                    href = href[:60] + "..."
                key_attrs.append(f'href="{href}"')
        
        # === class（智能精简）===
        if 'class' in self.attributes:
            classes = self.attributes['class'].strip()
            class_list = classes.split()
            
            # 保留关键类名：交互相关、状态相关
            important_classes = []
            for cls in class_list:
                cls_lower = cls.lower()
                # 保留状态类名（active, selected, checked, disabled）
                if any(state in cls_lower for state in ['active', 'selected', 'current', 'checked', 'disabled', 'open', 'closed']):
                    important_classes.append(cls)
                # 保留交互类名（button, link, tab, menu）
                elif any(interact in cls_lower for interact in ['button', 'btn', 'link', 'tab', 'menu', 'input']):
                    important_classes.append(cls)
                # 或者是前 2 个类名
                elif len(important_classes) < 2:
                    important_classes.append(cls)
            
            if important_classes:
                key_attrs.append(f'class="{" ".join(important_classes[:3])}"')  # 最多 3 个
        
        # === 组合并输出 ===
        attrs_str = " ".join(key_attrs)
        
        # 文本预览（智能截断）
        # 链接类元素：文本通常短，主要靠 href 标识，截断 50
        # 内容类元素：文本是关键信息来源，截断 150
        _link_tags = {'a'}
        _max_text = 50 if self.tag in _link_tags else 150
        text_preview = self.text[:_max_text] + "..." if len(self.text) > _max_text else self.text
        
        # 生成最终字符串
        if attrs_str:
            return f"[{self.index}] <{self.tag} {attrs_str}>{text_preview}</{self.tag}>"
        else:
            return f"[{self.index}] <{self.tag}>{text_preview}</{self.tag}>"


@dataclass
class PageState:
    """
    页面状态（前端返回）
    
    前端每次执行动作后，返回新的页面状态。
    """
    url: str
    title: str
    elements: List[DOMElement] = field(default_factory=list)
    screenshot_base64: Optional[str] = None
    # 标签页信息（Local Engine 返回）
    tabs: List[Dict[str, Any]] = field(default_factory=list)
    tab_count: int = 0
    active_tab_index: int = 0
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PageState":
        elements = [
            DOMElement.from_dict(e) if isinstance(e, dict) else e
            for e in data.get("elements", [])
        ]
        return cls(
            url=data.get("url", ""),
            title=data.get("title", ""),
            elements=elements,
            screenshot_base64=data.get("screenshot") or data.get("screenshot_base64"),
            # 读取 tabs 信息
            tabs=data.get("tabs", []),
            tab_count=data.get("tab_count", 0),
            active_tab_index=data.get("active_tab_index", 0),
        )
    
    @property
    def element_count(self) -> int:
        return len(self.elements)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "element_count": self.element_count,
            "elements": [e.to_dict() for e in self.elements],
            "tabs": self.tabs,
            "tab_count": self.tab_count,
            "active_tab_index": self.active_tab_index,
        }
    
    def to_prompt_str(self, max_elements: int = 50, smart_filter: bool = True) -> str:
        """
        生成用于 Prompt 的元素列表字符串
        
        Args:
            max_elements: 最大元素数量
            smart_filter: 是否启用智能过滤（去重、优先级排序）
        """
        lines = [f"URL: {self.url}", f"Title: {self.title}"]
        
        # 添加 Tabs 信息（如果有）
        if self.tabs and len(self.tabs) > 1:
            lines.append("")
            lines.append(f"Browser Tabs ({self.tab_count} total, active: tab{self.active_tab_index}):")
            for tab in self.tabs:
                idx = tab.get("tab_index", 0)
                tab_title = tab.get("title", "(untitled)")[:50]
                tab_url = tab.get("url", "")
                is_active = tab.get("is_active", False)
                marker = " [ACTIVE]" if is_active else ""
                
                # 提取域名（如 bing.com, bilibili.com）
                domain = ""
                if tab_url:
                    try:
                        parsed = urlparse(tab_url)
                        domain = parsed.netloc or ""
                        # 移除 www. 前缀
                        if domain.startswith("www."):
                            domain = domain[4:]
                    except:
                        pass
                
                # 格式：tab0: Title [ACTIVE] (domain.com)
                domain_part = f" ({domain})" if domain else ""
                lines.append(f"  - tab{idx}: {tab_title}{marker}{domain_part}")
        
        # 当 max_elements=0 时，完全跳过 Interactive Elements 区块
        # （例如 extract_content 后的步骤不需要交互元素，节省 token）
        if max_elements <= 0:
            return "\n".join(lines)
        
        # 元素过滤
        if smart_filter and self.elements:
            # 使用智能过滤器
            from .core.element_filter import filter_elements
            filtered_elements, _ = filter_elements(self.elements, max_count=max_elements, debug=False)
        else:
            # 简单截断
            filtered_elements = self.elements[:max_elements]
        
        lines.append("")
        lines.append("Interactive Elements:")
        for elem in filtered_elements:
            lines.append(str(elem))
        
        if len(self.elements) > len(filtered_elements):
            lines.append(f"... and {len(self.elements) - len(filtered_elements)} more elements")
        
        return "\n".join(lines)


# ==================== 后端生成的动作 ====================

@dataclass
class BrowserAction:
    """
    浏览器动作
    
    后端 Planner/Actor 生成，通过 tool_call 发送给前端执行。
    """
    action_type: BrowserActionType
    args: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.action_type.value,
            **self.args,
        }
    
    def to_tool_call(self, call_id: str) -> Dict[str, Any]:
        """转换为标准 tool_call 格式"""
        return {
            "type": "tool_call",
            "id": call_id,
            "target": "browser",
            "name": self.action_type.value,
            "args": self.args,
        }
    
    # ==================== 工厂方法 ====================
    
    @classmethod
    def click(cls, index: int) -> "BrowserAction":
        return cls(action_type=BrowserActionType.CLICK_ELEMENT, args={"index": index})
    
    @classmethod
    def input_text(cls, index: int, text: str) -> "BrowserAction":
        return cls(action_type=BrowserActionType.INPUT_TEXT, args={"index": index, "text": text})
    
    @classmethod
    def go_to_url(cls, url: str) -> "BrowserAction":
        return cls(action_type=BrowserActionType.GO_TO_URL, args={"url": url})
    
    @classmethod
    def scroll_down(cls, amount: int = 500) -> "BrowserAction":
        return cls(action_type=BrowserActionType.SCROLL_DOWN, args={"amount": amount})
    
    @classmethod
    def scroll_up(cls, amount: int = 500) -> "BrowserAction":
        return cls(action_type=BrowserActionType.SCROLL_UP, args={"amount": amount})
    
    @classmethod
    def press_key(cls, key: str) -> "BrowserAction":
        return cls(action_type=BrowserActionType.PRESS_KEY, args={"key": key})
    
    @classmethod
    def wait(cls, seconds: float = 2) -> "BrowserAction":
        return cls(action_type=BrowserActionType.WAIT, args={"seconds": seconds})
    
    @classmethod
    def go_back(cls) -> "BrowserAction":
        return cls(action_type=BrowserActionType.GO_BACK, args={})
    
    @classmethod
    def go_forward(cls) -> "BrowserAction":
        return cls(action_type=BrowserActionType.GO_FORWARD, args={})
    
    @classmethod
    def refresh(cls) -> "BrowserAction":
        return cls(action_type=BrowserActionType.REFRESH, args={})
    
    @classmethod
    def switch_tab(cls, tab_id: str) -> "BrowserAction":
        """切换到指定标签页"""
        return cls(action_type=BrowserActionType.SWITCH_TAB, args={"tab_id": tab_id})
    
    @classmethod
    def close_tab(cls, tab_id: str) -> "BrowserAction":
        """关闭指定标签页"""
        return cls(action_type=BrowserActionType.CLOSE_TAB, args={"tab_id": tab_id})
    
    @classmethod
    def stop(cls) -> "BrowserAction":
        return cls(action_type=BrowserActionType.STOP, args={})
    
    # ===== 连接管理工厂方法 =====
    
    @classmethod
    def connect(cls, headless: bool = False, initial_url: Optional[str] = None) -> "BrowserAction":
        """启动新浏览器并连接"""
        args: Dict[str, Any] = {"headless": headless}
        if initial_url:
            args["initial_url"] = initial_url
        return cls(action_type=BrowserActionType.CONNECT, args=args)
    
    @classmethod
    def attach(cls, cdp_url: str) -> "BrowserAction":
        """接管用户已打开的浏览器（通过 CDP）"""
        return cls(action_type=BrowserActionType.ATTACH, args={"cdp_url": cdp_url})
    
    @classmethod
    def extract_content(cls, selector: Optional[str] = None) -> "BrowserAction":
        """提取页面文本内容"""
        args: Dict[str, Any] = {}
        if selector:
            args["selector"] = selector
        return cls(action_type=BrowserActionType.EXTRACT_CONTENT, args=args)
    
    @classmethod
    def disconnect(cls) -> "BrowserAction":
        """断开浏览器连接"""
        return cls(action_type=BrowserActionType.DISCONNECT, args={})


# ==================== Planner 输出 ====================

@dataclass
class BrowserPlannerOutput:
    """
    Planner 输出
    
    Planner 观察页面状态（截图 + 元素列表），决定下一步动作。
    """
    observation: str           # 对当前页面的观察
    reasoning: str             # 推理过程
    next_action: str           # 下一步动作的自然语言描述
    target_element: Optional[int] = None  # 目标元素索引（如果需要）
    is_milestone_completed: bool = False
    completion_summary: Optional[str] = None
    output_filename: Optional[str] = None   # 输出文件名 (如 "bilibili_top100.md")
    result_markdown: Optional[str] = None   # AI 主动生成的 markdown 文件内容
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "Observation": self.observation,
            "Reasoning": self.reasoning,
            "Action": self.next_action,
            "TargetElement": self.target_element,
            "MilestoneCompleted": self.is_milestone_completed,
            "node_completion_summary": self.completion_summary,
            "output_filename": self.output_filename,
            "result_markdown": self.result_markdown,
        }


# ==================== Agent 步骤结果 ====================

@dataclass
class BrowserAgentStep:
    """Agent 单步执行结果"""
    planner_output: BrowserPlannerOutput
    browser_action: Optional[BrowserAction] = None
    reasoning_text: str = ""
    token_usage: Dict[str, int] = field(default_factory=dict)
    error: Optional[str] = None
    
    @property
    def is_completed(self) -> bool:
        return self.planner_output.is_milestone_completed
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "planner": self.planner_output.to_dict(),
            "action": self.browser_action.to_dict() if self.browser_action else None,
            "reasoning": self.reasoning_text,
            "token_usage": self.token_usage,
            "is_completed": self.is_completed,
            "error": self.error,
        }


# ==================== 上下文模型 ====================

@dataclass
class BrowserContext:
    """
    Browser Agent 上下文
    
    包含任务信息和当前页面状态。
    """
    node_id: str
    task_description: str          # 整体任务描述
    milestone_objective: str       # 当前里程碑目标
    page_state: Optional[PageState] = None  # 当前页面状态（前端返回）
    guidance_steps: List[str] = field(default_factory=list)
    history_md: str = ""
    loop_context: Optional[Dict[str, Any]] = None
    extracted_content: Optional[str] = None  # extract_content 返回的页面文本
    collected_data: Optional[str] = None  # 中途通过 node_completion_summary 收集的数据
