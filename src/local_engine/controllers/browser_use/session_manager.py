"""
Browser Session Manager
管理多个浏览器 Session（多实例）

每个 Session 对应一个独立的浏览器连接（BrowserController）。
支持同时操作多个浏览器实例。
"""

import asyncio
import uuid
from typing import Dict, Optional, Any, List
from dataclasses import dataclass, field
from datetime import datetime
import logging

from .controller import BrowserController
from .config import BrowserConfig, BrowserType

logger = logging.getLogger(__name__)


@dataclass
class SessionInfo:
    """Session 信息"""
    session_id: str
    controller: BrowserController
    created_at: datetime = field(default_factory=datetime.now)
    config: Optional[BrowserConfig] = None
    
    # 连接方式
    connect_type: str = "connect"  # "connect" | "attach"
    cdp_url: Optional[str] = None  # attach 模式下的 CDP URL


class BrowserSessionManager:
    """
    浏览器 Session 管理器
    
    管理多个独立的浏览器连接，每个连接有唯一的 session_id。
    
    使用方法:
        manager = BrowserSessionManager()
        
        # 创建新 Session
        session_id = await manager.create_session(config)
        
        # 获取 Session
        session = manager.get_session(session_id)
        
        # 列出所有 Sessions
        sessions = manager.list_sessions()
        
        # 关闭 Session
        await manager.close_session(session_id)
    """
    
    def __init__(self):
        self._sessions: Dict[str, SessionInfo] = {}
        self._lock = asyncio.Lock()
    
    def _generate_session_id(self) -> str:
        """生成唯一的 Session ID"""
        return str(uuid.uuid4())[:8]
    
    async def create_session(
        self,
        config: Optional[BrowserConfig] = None,
        browser_type: str = "auto",
        profile_directory: str = "Default",
        headless: bool = False,
        highlight_elements: bool = True,
        initial_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        创建新的浏览器 Session
        
        Args:
            config: 浏览器配置（优先级最高）
            browser_type: 浏览器类型
            profile_directory: Profile 目录
            headless: 是否无头模式
            highlight_elements: 是否高亮元素
            initial_url: 初始 URL
        
        Returns:
            {"session_id": str, "success": bool, ...}
        """
        async with self._lock:
            session_id = self._generate_session_id()
            
            # 创建配置
            if config is None:
                bt = BrowserType(browser_type.lower()) if browser_type.lower() in ["chrome", "edge", "auto"] else BrowserType.AUTO
                config = BrowserConfig(
                    browser_type=bt,
                    profile_directory=profile_directory,
                    headless=headless,
                    highlight_elements=highlight_elements,
                    initial_url=initial_url,
                )
            
            # 创建 Controller
            controller = BrowserController(config=config)
            
            # 连接浏览器
            result = await controller.connect()
            
            if not result.get("success"):
                return {
                    "success": False,
                    "error": result.get("error", "Connection failed"),
                }
            
            # 保存 Session
            session_info = SessionInfo(
                session_id=session_id,
                controller=controller,
                config=config,
                connect_type="connect",
            )
            self._sessions[session_id] = session_info
            
            logger.info(f"[SessionManager] Created session {session_id}")
            
            return {
                "success": True,
                "session_id": session_id,
                "browser_type": config.browser_type.value,
                "profile": config.profile_directory,
                "created_at": session_info.created_at.isoformat(),
            }
    
    async def attach_session(
        self,
        cdp_url: str = "http://localhost:9222",
        highlight_elements: bool = True,
    ) -> Dict[str, Any]:
        """
        通过 CDP 接管已有浏览器创建 Session
        
        Args:
            cdp_url: CDP URL
            highlight_elements: 是否高亮元素
        
        Returns:
            {"session_id": str, "success": bool, ...}
        """
        async with self._lock:
            session_id = self._generate_session_id()
            
            # 创建 Controller
            controller = BrowserController()
            
            # 接管浏览器
            result = await controller.attach(
                cdp_url=cdp_url,
                highlight_elements=highlight_elements,
            )
            
            if not result.get("success"):
                return {
                    "success": False,
                    "error": result.get("error", "Attach failed"),
                }
            
            # 保存 Session
            session_info = SessionInfo(
                session_id=session_id,
                controller=controller,
                connect_type="attach",
                cdp_url=cdp_url,
            )
            self._sessions[session_id] = session_info
            
            logger.info(f"[SessionManager] Attached session {session_id} to {cdp_url}")
            
            return {
                "success": True,
                "session_id": session_id,
                "cdp_url": cdp_url,
                "current_url": result.get("current_url", ""),
                "current_title": result.get("current_title", ""),
                "created_at": session_info.created_at.isoformat(),
            }
    
    def get_session(self, session_id: str) -> Optional[SessionInfo]:
        """获取 Session"""
        return self._sessions.get(session_id)
    
    def get_controller(self, session_id: str) -> Optional[BrowserController]:
        """获取 Session 的 Controller"""
        session = self._sessions.get(session_id)
        return session.controller if session else None
    
    def list_sessions(self) -> List[Dict[str, Any]]:
        """列出所有 Sessions"""
        sessions = []
        for session_id, info in self._sessions.items():
            sessions.append({
                "session_id": session_id,
                "connected": info.controller.is_connected,
                "connect_type": info.connect_type,
                "cdp_url": info.cdp_url,
                "browser_type": info.config.browser_type.value if info.config else None,
                "profile": info.config.profile_directory if info.config else None,
                "created_at": info.created_at.isoformat(),
            })
        return sessions
    
    async def get_session_status(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取 Session 详细状态"""
        session = self._sessions.get(session_id)
        if not session:
            return None
        
        status = await session.controller.get_status()
        status["session_id"] = session_id
        status["connect_type"] = session.connect_type
        status["created_at"] = session.created_at.isoformat()
        
        return status
    
    async def close_session(self, session_id: str) -> Dict[str, Any]:
        """关闭并删除 Session"""
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return {"success": False, "error": f"Session {session_id} not found"}
            
            # 断开连接
            try:
                await session.controller.disconnect()
            except Exception as e:
                logger.warning(f"[SessionManager] Error disconnecting session {session_id}: {e}")
            
            # 删除 Session
            del self._sessions[session_id]
            
            logger.info(f"[SessionManager] Closed session {session_id}")
            
            return {"success": True, "session_id": session_id}
    
    async def close_all_sessions(self) -> Dict[str, Any]:
        """关闭所有 Sessions"""
        session_ids = list(self._sessions.keys())
        results = []
        
        for session_id in session_ids:
            result = await self.close_session(session_id)
            results.append(result)
        
        return {
            "success": True,
            "closed_count": len(results),
            "results": results,
        }
    
    # ==================== Tab 管理 ====================
    
    async def get_tabs(self, session_id: str) -> Optional[List[Dict[str, Any]]]:
        """
        获取 Session 的所有 Tabs
        
        Returns:
            [{"tab_id": str, "url": str, "title": str, "is_active": bool}, ...]
        """
        session = self._sessions.get(session_id)
        if not session or not session.controller.is_connected:
            return None
        
        controller = session.controller
        browser_session = controller._session
        
        if not browser_session:
            return None
        
        try:
            tabs = await browser_session.get_tabs()
            current_target_id = browser_session.agent_focus_target_id
            
            result = []
            for tab in tabs:
                result.append({
                    "tab_id": tab.target_id,
                    "url": tab.url,
                    "title": tab.title,
                    "is_active": tab.target_id == current_target_id,
                })
            
            return result
        except Exception as e:
            logger.error(f"[SessionManager] Failed to get tabs for session {session_id}: {e}")
            return None
    
    async def create_tab(
        self,
        session_id: str,
        url: str = "about:blank",
        switch_to: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """
        在 Session 中创建新 Tab
        
        Args:
            session_id: Session ID
            url: 新 Tab 的 URL
            switch_to: 是否切换到新 Tab
        
        Returns:
            {"tab_id": str, "url": str, ...}
        """
        session = self._sessions.get(session_id)
        if not session or not session.controller.is_connected:
            return None
        
        browser_session = session.controller._session
        if not browser_session:
            return None
        
        try:
            # 创建新 Tab
            target_id = await browser_session._cdp_create_new_page(url=url)
            
            # 如果需要切换到新 Tab
            if switch_to:
                from browser_use.browser.events import SwitchTabEvent
                await browser_session.event_bus.dispatch(SwitchTabEvent(target_id=target_id))
            
            return {
                "success": True,
                "tab_id": target_id,
                "url": url,
                "is_active": switch_to,
            }
        except Exception as e:
            logger.error(f"[SessionManager] Failed to create tab: {e}")
            return {"success": False, "error": str(e)}
    
    async def switch_tab(self, session_id: str, tab_id: str) -> Optional[Dict[str, Any]]:
        """
        切换到指定 Tab
        
        Args:
            session_id: Session ID
            tab_id: Tab ID (target_id)
        
        Returns:
            {"success": bool, "tab_id": str, ...}
        """
        session = self._sessions.get(session_id)
        if not session or not session.controller.is_connected:
            return None
        
        browser_session = session.controller._session
        if not browser_session:
            return None
        
        try:
            from browser_use.browser.events import SwitchTabEvent
            await browser_session.event_bus.dispatch(SwitchTabEvent(target_id=tab_id))
            
            # 等待切换完成
            await asyncio.sleep(0.3)
            
            return {
                "success": True,
                "tab_id": tab_id,
            }
        except Exception as e:
            logger.error(f"[SessionManager] Failed to switch tab: {e}")
            return {"success": False, "error": str(e)}
    
    async def close_tab(self, session_id: str, tab_id: str) -> Optional[Dict[str, Any]]:
        """
        关闭指定 Tab
        
        Args:
            session_id: Session ID
            tab_id: Tab ID (target_id)
        
        Returns:
            {"success": bool, ...}
        """
        session = self._sessions.get(session_id)
        if not session or not session.controller.is_connected:
            return None
        
        browser_session = session.controller._session
        if not browser_session:
            return None
        
        try:
            from browser_use.browser.events import CloseTabEvent
            await browser_session.event_bus.dispatch(CloseTabEvent(target_id=tab_id))
            
            return {
                "success": True,
                "tab_id": tab_id,
            }
        except Exception as e:
            logger.error(f"[SessionManager] Failed to close tab: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_tab_info(self, session_id: str, tab_id: str) -> Optional[Dict[str, Any]]:
        """获取 Tab 详细信息"""
        tabs = await self.get_tabs(session_id)
        if not tabs:
            return None
        
        for tab in tabs:
            if tab["tab_id"] == tab_id:
                return tab
        
        return None


# 全局 Session 管理器实例
_session_manager: Optional[BrowserSessionManager] = None


def get_session_manager() -> BrowserSessionManager:
    """获取全局 Session 管理器"""
    global _session_manager
    if _session_manager is None:
        _session_manager = BrowserSessionManager()
    return _session_manager
