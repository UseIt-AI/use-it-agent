"""
Browser Controller
浏览器控制器，基于 browser-use 库 (新版 API)

基于 browser-use 官方文档:
https://docs.browser-use.com/

主要功能:
1. 连接真实浏览器（保留登录态）
2. 执行浏览器操作（点击、输入、滚动等）
3. 获取页面状态（截图、元素列表等）
"""

import asyncio
import base64
import os
import platform
import re
from typing import Any, Dict, List, Optional

from agent_ndjson_debug import write_agent_ndjson_line as _agent_log


def _get_active_window_title() -> Optional[str]:
    """
    获取当前激活窗口的标题（Windows 专用）
    
    用于检测用户当前正在看的浏览器标签页。
    
    Returns:
        窗口标题，如 "Google - Microsoft Edge"
        如果获取失败或非 Windows 系统，返回 None
    """
    if platform.system() != 'Windows':
        return None
    
    try:
        import ctypes
        from ctypes import wintypes
        
        user32 = ctypes.windll.user32
        
        # 获取前台窗口句柄
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        
        # 获取窗口标题长度
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return None
        
        # 获取窗口标题
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        
        return buffer.value
    except Exception as e:
        print(f"[BrowserController] Warning: Failed to get active window title: {e}")
        return None


def _get_all_visible_window_titles() -> List[str]:
    """
    获取所有可见窗口的标题（Windows 专用）
    
    用于在前台窗口不是浏览器时（如用户在使用 AI Agent 工具），
    枚举所有窗口寻找浏览器窗口。
    
    Returns:
        所有可见窗口标题的列表
    """
    if platform.system() != 'Windows':
        return []
    
    try:
        import ctypes
        from ctypes import wintypes
        
        user32 = ctypes.windll.user32
        window_titles = []
        
        def get_window_title(hwnd) -> str:
            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return ""
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            return buffer.value
        
        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        
        def enum_windows_callback(hwnd, lParam):
            if not user32.IsWindowVisible(hwnd):
                return True
            title = get_window_title(hwnd)
            if title:
                window_titles.append(title)
            return True
        
        # 保持 callback 引用，防止被垃圾回收
        callback = WNDENUMPROC(enum_windows_callback)
        user32.EnumWindows(callback, 0)
        
        return window_titles
        
    except Exception as e:
        print(f"[BrowserController] Warning: Failed to enumerate windows: {e}")
        return []


async def _smart_detect_active_tab_via_cdp(cdp_url: str) -> Optional[str]:
    """
    智能检测用户当前激活的标签页（无硬编码版本）
    
    核心思路：
    1. 获取 CDP 所有标签页
    2. 获取所有可见窗口标题（因为用户可能在使用 AI Agent 工具，前台窗口不是浏览器）
    3. 对每个窗口标题，检查是否有 tab 的 title 被包含
    4. 选择最长匹配的 tab（更精确）
    
    这样就不需要硬编码浏览器关键词或正则表达式了！
    
    Args:
        cdp_url: CDP URL，如 "http://localhost:9222"
        
    Returns:
        目标标签页的 target_id，如果失败返回 None
    """
    import aiohttp
    import json as json_module
    import re
    from urllib.parse import urlparse
    
    # 标准化：移除零宽字符
    def normalize(s: str) -> str:
        return re.sub(r'[\u200b\u200c\u200d\ufeff]', '', s).strip()
    
    try:
        # 1. 获取 CDP 所有标签页
        parsed = urlparse(cdp_url)
        if parsed.scheme in ("ws", "wss"):
            http_scheme = "https" if parsed.scheme == "wss" else "http"
        else:
            http_scheme = parsed.scheme or "http"
        http_base_url = f"{http_scheme}://{parsed.netloc or 'localhost:9222'}"
        
        timeout = aiohttp.ClientTimeout(total=3)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"{http_base_url}/json") as resp:
                if resp.status != 200:
                    print(f"[SmartDetect] Failed to get tabs: HTTP {resp.status}")
                    return None
                targets = await resp.json()
        
        # 过滤出有效的页面
        page_targets = [
            t for t in targets
            if t.get("type") == "page"
            and not t.get("url", "").startswith("devtools://")
        ]
        
        if not page_targets:
            print("[SmartDetect] No valid page targets found")
            return None
        
        # 打印所有 tabs
        print(f"[SmartDetect] Found {len(page_targets)} tabs:")
        for i, t in enumerate(page_targets):
            print(f"[SmartDetect]   tab{i}: {normalize(t.get('title', 'N/A'))[:40]}...")
        
        # 2. 获取所有可见窗口标题（因为前台窗口可能是 AI Agent 工具而不是浏览器）
        all_window_titles = _get_all_visible_window_titles()
        if not all_window_titles:
            print("[SmartDetect] No visible windows found")
            return None
        
        # 定义常见的浏览器窗口后缀（安全锁：过滤掉记事本、文件夹等干扰）
        # 这是系统级的应用名称，极其稳定，几年都不会变
        BROWSER_SUFFIXES = [
            "- Google Chrome",
            "- Microsoft Edge", 
            "- Microsoft​ Edge",  # 带零宽空格的版本
            "- Chromium",
            "- Brave",
            "- Firefox",
            "- Opera",
            "- Chrome",
            "- Edge",
        ]
        
        # 过滤出浏览器窗口
        browser_windows = []
        for title in all_window_titles:
            title_normalized = normalize(title)
            # 检查是否以浏览器后缀结尾（不区分大小写）
            for suffix in BROWSER_SUFFIXES:
                if title_normalized.lower().endswith(suffix.lower()):
                    browser_windows.append(title)
                    break
        
        if not browser_windows:
            print(f"[SmartDetect] No browser windows found among {len(all_window_titles)} windows")
            return None
        
        print(f"[SmartDetect] Found {len(browser_windows)} browser windows (filtered from {len(all_window_titles)} total)")
        
        # 3. 对每个浏览器窗口标题，检查是否有 tab 的 title 被包含
        best_match = None
        best_match_len = 0
        matched_window = None
        
        for window_title in browser_windows:
            window_title_normalized = normalize(window_title)
            
            for target in page_targets:
                tab_title = normalize(target.get("title", ""))
                tab_url = target.get("url", "")
                
                # 跳过空标签页（通过 URL 判断，不依赖语言相关的标题）
                if not tab_title or tab_url in ["about:blank", ""] or "://newtab" in tab_url:
                    continue
                
                # 核心匹配逻辑：tab 的 title 是否被窗口标题包含
                if tab_title in window_title_normalized:
                    # 选择最长匹配（更精确）
                    if len(tab_title) > best_match_len:
                        best_match = target
                        best_match_len = len(tab_title)
                        matched_window = window_title_normalized
        
        if not best_match:
            print("[SmartDetect] No matching tab found in any window")
            return None
        
        print(f"[SmartDetect] ✓ Match found: '{normalize(best_match.get('title', ''))[:40]}...'")
        print(f"[SmartDetect]   in window: '{matched_window[:50]}...'")
        print(f"[SmartDetect]   match length: {best_match_len}")
        
        # 4. 激活匹配的标签页
        target_id = best_match.get("id")
        if not target_id:
            print("[SmartDetect] Target page has no id")
            return None
        
        # 获取浏览器级别的 WebSocket URL
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"{http_base_url}/json/version") as resp:
                version_info = await resp.json()
        
        browser_ws_url = version_info.get("webSocketDebuggerUrl")
        if not browser_ws_url:
            print("[SmartDetect] Could not get browser WebSocket URL")
            return None
        
        # 发送 Target.activateTarget 命令
        try:
            import websockets
            import asyncio
            
            async with websockets.connect(browser_ws_url) as ws:
                activate_cmd = {
                    "id": 1,
                    "method": "Target.activateTarget",
                    "params": {"targetId": target_id}
                }
                await ws.send(json_module.dumps(activate_cmd))
                
                try:
                    response = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    result = json_module.loads(response)
                    if "error" in result:
                        print(f"[SmartDetect] ✗ Failed to activate: {result['error']}")
                        return None
                    else:
                        print(f"[SmartDetect] ✓ Activated: {best_match.get('title', 'N/A')[:40]}")
                        return target_id
                except asyncio.TimeoutError:
                    print(f"[SmartDetect] Activate timed out (may have succeeded)")
                    return target_id
                    
        except ImportError:
            print("[SmartDetect] websockets library not installed")
            return None
            
    except Exception as e:
        print(f"[SmartDetect] Error: {type(e).__name__}: {e}")
        return None


async def _activate_target_tab_via_cdp(
    cdp_url: str,
    target_url: Optional[str] = None,
    target_title: Optional[str] = None,
) -> Optional[str]:
    """
    在 browser-use 启动前，通过 CDP 激活正确的标签页
    
    这是解决"多标签页时操作错误页面"问题的关键。
    必须在 BrowserSession.start() 之前调用，这样 browser-use 会默认 focus 到
    我们已经激活的标签页。
    
    策略优先级：
    1. 如果提供了 target_url，精确匹配该 URL
    2. 如果提供了 target_title（从 Windows API 获取），匹配标题
    3. 返回 None，让 browser-use 使用默认行为
    
    Args:
        cdp_url: CDP URL，如 "http://localhost:9222"
        target_url: 目标页面 URL（精确匹配）
        target_title: 目标页面标题（从 Windows 窗口标题提取）
        
    Returns:
        目标标签页的 target_id，如果失败返回 None
    """
    import aiohttp
    import json as json_module
    from urllib.parse import urlparse, unquote
    
    try:
        # 解析 CDP URL
        parsed = urlparse(cdp_url)
        if parsed.scheme in ("ws", "wss"):
            http_scheme = "https" if parsed.scheme == "wss" else "http"
        else:
            http_scheme = parsed.scheme or "http"
        http_base_url = f"{http_scheme}://{parsed.netloc or 'localhost:9222'}"
        
        # 1. 获取所有标签页
        timeout = aiohttp.ClientTimeout(total=3)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"{http_base_url}/json") as resp:
                if resp.status != 200:
                    print(f"[CDP] Failed to get tabs: HTTP {resp.status}")
                    return None
                targets = await resp.json()
        
        # 2. 过滤出有效的页面
        page_targets = [
            t for t in targets
            if t.get("type") == "page"
            and not t.get("url", "").startswith("devtools://")
        ]
        
        if not page_targets:
            print("[CDP] No valid page targets found")
            return None
        
        print(f"[CDP] Found {len(page_targets)} tabs:")
        for i, t in enumerate(page_targets[:5]):
            print(f"[CDP]   tab{i}: {t.get('title', 'N/A')[:40]}")
        
        target_page = None
        
        # 3. 策略 1：使用 target_url 精确匹配
        if target_url:
            target_url_decoded = unquote(target_url)
            print(f"[CDP] Looking for tab matching URL: {target_url[:60]}...")
            
            for target in page_targets:
                tab_url = target.get("url", "")
                tab_url_decoded = unquote(tab_url)
                
                # 精确匹配或去掉尾部斜杠后匹配
                if (tab_url == target_url or 
                    tab_url_decoded == target_url_decoded or
                    tab_url.rstrip("/") == target_url.rstrip("/") or
                    tab_url_decoded.rstrip("/") == target_url_decoded.rstrip("/")):
                    target_page = target
                    print(f"[CDP] ✓ Found exact URL match: {target.get('title', 'N/A')[:40]}")
                    break
                
                # 部分匹配（用于 URL 参数变化的情况）
                if target_url_decoded in tab_url_decoded or tab_url_decoded in target_url_decoded:
                    target_page = target
                    print(f"[CDP] ✓ Found partial URL match: {target.get('title', 'N/A')[:40]}")
                    break
        
        # 4. 策略 2：使用 target_title 匹配（从 Windows API 获取）
        if not target_page and target_title:
            print(f"[CDP] Looking for tab matching title: {target_title[:40]}...")
            
            for target in page_targets:
                tab_title = target.get("title", "")
                
                # 精确匹配
                if tab_title == target_title:
                    target_page = target
                    print(f"[CDP] ✓ Found exact title match")
                    break
                
                # 部分匹配（标题可能被截断）
                if target_title in tab_title or tab_title in target_title:
                    target_page = target
                    print(f"[CDP] ✓ Found partial title match: {tab_title[:40]}")
                    break
        
        if not target_page:
            print("[CDP] No matching tab found, will use browser-use default")
            return None
        
        # 5. 通过 CDP WebSocket 激活目标标签页
        target_id = target_page.get("id")
        if not target_id:
            print("[CDP] Target page has no id")
            return None
        
        # 获取浏览器级别的 WebSocket URL
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"{http_base_url}/json/version") as resp:
                version_info = await resp.json()
        
        browser_ws_url = version_info.get("webSocketDebuggerUrl")
        if not browser_ws_url:
            print("[CDP] Could not get browser WebSocket URL")
            return None
        
        # 6. 发送 Target.activateTarget 命令
        try:
            import websockets
            
            async with websockets.connect(browser_ws_url) as ws:
                activate_cmd = {
                    "id": 1,
                    "method": "Target.activateTarget",
                    "params": {"targetId": target_id}
                }
                await ws.send(json_module.dumps(activate_cmd))
                
                try:
                    response = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    result = json_module.loads(response)
                    if "error" in result:
                        print(f"[CDP] ✗ Failed to activate tab: {result['error']}")
                        return None
                    else:
                        print(f"[CDP] ✓ Activated tab: {target_page.get('title', 'N/A')[:40]}")
                        return target_id
                except asyncio.TimeoutError:
                    print(f"[CDP] Activate command timed out (may have succeeded)")
                    return target_id
                    
        except ImportError:
            print("[CDP] websockets library not installed, skipping tab activation")
            return None
            
    except Exception as e:
        print(f"[CDP] Failed to activate target tab: {type(e).__name__}: {e}")
        return None


# 禁用代理环境变量（避免 httpx 通过代理连接 localhost CDP）
# 必须在导入 browser-use 之前设置
os.environ.pop('HTTP_PROXY', None)
os.environ.pop('HTTPS_PROXY', None)
os.environ.pop('http_proxy', None)
os.environ.pop('https_proxy', None)
os.environ['NO_PROXY'] = 'localhost,127.0.0.1'
os.environ['no_proxy'] = 'localhost,127.0.0.1'

from .config import BrowserConfig, BrowserType, get_default_config

# 导入 browser-use 库（新版 API）
try:
    from browser_use import BrowserSession
    from browser_use.browser.events import (
        ClickElementEvent,
        TypeTextEvent,
        ScrollEvent,
        SendKeysEvent,
    )
    BROWSER_USE_AVAILABLE = True
    
    # 应用 monkey patches
    # - use_proxy=False: 禁用代理，避免超时问题
    # - patch_profile_copy=False: 不修改 profile 复制逻辑，避免 CDP 连接问题
    from .utils.monkey_patches import apply_patches
    apply_patches(use_proxy=False, patch_profile_copy=False)
    
except ImportError:
    BROWSER_USE_AVAILABLE = False
    BrowserSession = None


class BrowserController:
    """
    浏览器控制器
    
    使用 browser-use 官方库连接真实浏览器，保留登录态。
    
    使用方法:
        controller = BrowserController(config)
        await controller.connect()
        state = await controller.get_page_state()
        await controller.execute_action({"action": "go_to_url", "url": "https://example.com"})
        await controller.disconnect()
    """
    
    # 事件超时时间（秒）
    EVENT_TIMEOUT = 10.0
    
    def __init__(self, config: Optional[BrowserConfig] = None):
        """
        初始化控制器
        
        Args:
            config: 浏览器配置
        """
        self.config = config or get_default_config()
        
        # browser-use 对象（新版 API）
        self._session: Optional[BrowserSession] = None
        self._connected = False
        
        # 缓存的 DOM 状态
        self._cached_state = None
        self._cached_selector_map = None
    
    @property
    def is_connected(self) -> bool:
        """是否已连接"""
        return self._connected
    
    # ========== 连接管理 ==========
    
    async def connect(self) -> Dict[str, Any]:
        """
        连接到浏览器（优先 attach，不行就 connect）
        
        连接策略：
        1. 优先检测是否有带 CDP 端口的浏览器在运行（默认 9222）
           - 如果有 → 直接 attach（接管用户已有浏览器）
        2. 如果没有 → 启动新浏览器
           - 通过 monkey patch 修复的 native 模式
           - 或 Windows fallback 模式
        
        Returns:
            连接结果
        """
        if self._connected:
            return {"success": True, "message": "Already connected"}
        
        if not BROWSER_USE_AVAILABLE:
            return {"success": False, "error": "browser-use library not installed. Run: pip install browser-use"}
        
        # 验证配置
        valid, error = self.config.validate()
        if not valid:
            return {"success": False, "error": error}
        
        print(f"[BrowserController] Connecting to browser...")
        print(f"[BrowserController]   executable: {self.config.executable_path}")
        print(f"[BrowserController]   user_data_dir: {self.config.user_data_dir}")
        print(f"[BrowserController]   profile: {self.config.profile_directory}")
        
        # ========== 第一步：优先尝试 attach（检测现有 CDP 浏览器）==========
        attach_result = await self._try_attach_existing_browser()
        if attach_result.get("success"):
            return attach_result
        
        # ========== 第二步：没有现有浏览器，启动新浏览器 ==========
        print(f"[BrowserController] No existing CDP browser found, starting new browser...")
        
        # 先尝试原生 browser-use 连接（所有平台，已通过 monkey patch 修复）
        result = await self._connect_native()
        
        if result.get("success"):
            return result
        
        # 如果原生连接失败，Windows 上尝试 fallback 模式
        import platform
        if platform.system() == 'Windows':
            print(f"[BrowserController] Native connect failed: {result.get('error')}")
            print("[BrowserController] Trying Windows fallback mode (manual launch + attach)...")
            return await self._connect_windows_fallback()
        
        return result
    
    async def _try_attach_existing_browser(
        self,
        cdp_port: int = 9222,
        target_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        尝试 attach 到已有的带 CDP 端口的浏览器
        
        这是"优先 attach"策略的核心：
        - 如果用户已经用 --remote-debugging-port 启动了浏览器，直接接管
        - 如果没有，返回失败，让调用方启动新浏览器
        
        Args:
            cdp_port: CDP 端口号，默认 9222
            target_url: 目标页面 URL（用于精确匹配要操作的标签页）
            
        Returns:
            attach 结果，成功或失败
        """
        import aiohttp
        
        cdp_url = f"http://localhost:{cdp_port}"
        
        print(f"[BrowserController] Checking for existing CDP browser on port {cdp_port}...")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{cdp_url}/json/version",
                    timeout=aiohttp.ClientTimeout(total=2)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        browser_info = data.get('Browser', 'unknown')
                        print(f"[BrowserController] ✓ Found existing browser: {browser_info}")
                        print(f"[BrowserController] Using ATTACH mode (connecting to existing browser)")
                        
                        # 直接 attach（传递 target_url）
                        result = await self.attach(
                            cdp_url=cdp_url,
                            highlight_elements=self.config.highlight_elements,
                            target_url=target_url,
                        )
                        
                        if result.get("success"):
                            result["mode"] = "attach"
                            result["message"] = f"Attached to existing browser ({browser_info})"
                        
                        return result
        except aiohttp.ClientConnectorError:
            print(f"[BrowserController] ✗ No CDP browser on port {cdp_port} (connection refused)")
        except asyncio.TimeoutError:
            print(f"[BrowserController] ✗ No CDP browser on port {cdp_port} (timeout)")
        except Exception as e:
            print(f"[BrowserController] ✗ No CDP browser on port {cdp_port} ({type(e).__name__}: {e})")
        
        return {"success": False, "error": "No existing CDP browser found"}
    
    async def _connect_native(self) -> Dict[str, Any]:
        """原生 browser-use 连接（非 Windows 平台）"""
        try:
            self._session = BrowserSession(
                executable_path=self.config.executable_path,
                user_data_dir=self.config.user_data_dir,
                profile_directory=self.config.profile_directory,
                headless=self.config.headless,
                enable_default_extensions=self.config.enable_default_extensions,
                highlight_elements=self.config.highlight_elements,
            )
            
            await self._session.start()
            self._connected = True
            
            if self.config.initial_url:
                print(f"[BrowserController] Navigating to initial URL: {self.config.initial_url}")
                await self._session._cdp_navigate(self.config.initial_url)
                await asyncio.sleep(1)
            
            print(f"[BrowserController] Connected successfully!")
            
            return {
                "success": True,
                "message": "Connected via browser-use",
                "browser_type": self.config.browser_type.value,
                "profile": self.config.profile_directory,
            }
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}
    
    async def _connect_windows_fallback(self) -> Dict[str, Any]:
        """
        Windows 专用 fallback 模式
        
        browser-use 使用 asyncio.create_subprocess_exec 启动浏览器，
        在 Windows 上无法正确处理带空格的路径（如 'User Data'），
        导致 CDP 端口无法绑定。
        
        这个方法使用 subprocess.Popen(shell=True) 启动浏览器，
        然后用 attach 模式连接 CDP。
        
        注意：CDP 检测已在 connect() 方法开头完成，这里直接启动新浏览器。
        """
        import subprocess
        import aiohttp
        import psutil
        
        cdp_port = 9222
        cdp_url = f"http://localhost:{cdp_port}"
        
        # 杀掉所有现有的 Edge 进程（关键步骤！）
        print(f"[BrowserController] Checking for existing Edge processes...")
        try:
            edge_procs = [p for p in psutil.process_iter(['name', 'pid']) 
                        if p.info['name'] and 'msedge' in p.info['name'].lower()]
            if edge_procs:
                print(f"[BrowserController] Found {len(edge_procs)} existing Edge processes, killing them...")
                for p in edge_procs:
                    try:
                        p.kill()
                        print(f"[BrowserController]   Killed PID {p.info['pid']}")
                    except Exception as e:
                        print(f"[BrowserController]   Failed to kill PID {p.info['pid']}: {e}")
                # 等待进程完全退出
                await asyncio.sleep(3)
                print(f"[BrowserController] All Edge processes killed")
            else:
                print(f"[BrowserController] No existing Edge processes found")
        except Exception as e:
            print(f"[BrowserController] Warning: Failed to check/kill Edge processes: {e}")
        
        # 构建命令（使用引号包裹带空格的路径）
        cmd = (
            f'"{self.config.executable_path}" '
            f'--remote-debugging-port={cdp_port} '  # CDP 端口放在前面
            f'--user-data-dir="{self.config.user_data_dir}" '
            f'--profile-directory="{self.config.profile_directory}" '
            f'--no-first-run '
            f'--no-default-browser-check '
            f'--disable-sync '
            f'--disable-background-networking '
            f'--disable-client-side-phishing-detection '
            # 关键：禁止恢复之前的会话！
            f'--disable-session-crashed-bubble '
            f'--disable-infobars '
            f'--no-restore-session-state '
            f'--hide-crash-restore-bubble '
        )
        
        if self.config.headless:
            cmd += ' --headless=new'
        
        print(f"[BrowserController] Launching browser with shell command...")
        print(f"[BrowserController]   Command: {cmd[:150]}...")
        print(f"[BrowserController]   CDP port: {cdp_port}")
        
        # 使用 shell=True 启动（这在 Windows 上能正确处理带空格的路径）
        proc = subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        print(f"[BrowserController] Shell process started, PID: {proc.pid}")
        
        # 等待浏览器启动
        await asyncio.sleep(3)
        
        # 等待 CDP 端口就绪
        print(f"[BrowserController] Waiting for CDP to be ready on port {cdp_port}...")
        for i in range(30):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{cdp_url}/json/version", timeout=aiohttp.ClientTimeout(total=1)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            print(f"[BrowserController] CDP ready! Browser: {data.get('Browser', 'unknown')}")
                            break
            except aiohttp.ClientConnectorError as e:
                if i % 5 == 0:
                    print(f"[BrowserController]   Still waiting... ({i}s) - {type(e).__name__}")
            except Exception as e:
                if i % 5 == 0:
                    print(f"[BrowserController]   Still waiting... ({i}s) - {type(e).__name__}: {e}")
            await asyncio.sleep(1)
        else:
            # 检查 Edge 进程是否在运行
            try:
                edge_procs = [p for p in psutil.process_iter(['name', 'cmdline']) 
                            if p.info['name'] and 'msedge' in p.info['name'].lower()]
                if edge_procs:
                    print(f"[BrowserController] Edge is running but CDP not ready. Checking command line...")
                    for p in edge_procs[:3]:
                        try:
                            cmdline = ' '.join(p.info.get('cmdline', [])[:5])
                            print(f"[BrowserController]   PID {p.pid}: {cmdline[:100]}...")
                        except Exception:
                            pass
                else:
                    print(f"[BrowserController] No Edge process found after launch!")
            except Exception as e:
                print(f"[BrowserController] Failed to check Edge processes: {e}")
            
            return {"success": False, "error": f"CDP port {cdp_port} not ready after 30 seconds"}
        
        # 使用 attach 连接
        result = await self.attach(cdp_url=cdp_url, highlight_elements=self.config.highlight_elements)
        
        if result.get("success"):
            result["message"] = "Connected via Windows fallback mode"
            result["mode"] = "windows_fallback"
            result["cdp_port"] = cdp_port
        
        return result
    
    async def disconnect(self) -> Dict[str, Any]:
        """断开连接并关闭浏览器"""
        try:
            if self._session:
                await self._session.stop()
        except Exception as e:
            print(f"[BrowserController] Error during disconnect: {e}")
        
        self._session = None
        self._connected = False
        self._cached_state = None
        self._cached_selector_map = None
        
        return {"success": True, "message": "Disconnected"}
    
    async def attach(
        self,
        cdp_url: str = "http://localhost:9222",
        highlight_elements: bool = True,
        target_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        接管用户正在使用的浏览器（通过 CDP 连接）
        
        用户需要先用 --remote-debugging-port=9222 启动浏览器：
        
        Windows:
            chrome.exe --remote-debugging-port=9222
        
        Mac:
            /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome --remote-debugging-port=9222
        
        Args:
            cdp_url: CDP URL，如 http://localhost:9222
            highlight_elements: 是否高亮显示交互元素
            target_url: 目标页面 URL（保留参数但暂不使用，避免标签页切换问题）
        
        Returns:
            连接结果
        """
        if self._connected:
            return {"success": True, "message": "Already connected"}
        
        if not BROWSER_USE_AVAILABLE:
            return {"success": False, "error": "browser-use library not installed"}
        
        try:
            print(f"[BrowserController] Attaching to existing browser via CDP...")
            print(f"[BrowserController]   cdp_url: {cdp_url}")
            
            # ========== 智能标签页检测（在 BrowserSession.start() 之前）==========
            # 这一步很关键：通过 CDP 预激活正确的标签页，
            # 这样 browser-use 启动后就会自动 focus 到我们已经激活的标签页
            activated_tab_id = None
            try:
                # 1. 先尝试使用传入的 target_url（精确匹配）
                if target_url:
                    print(f"[BrowserController] Looking for tab with URL: {target_url[:60]}...")
                    activated_tab_id = await _activate_target_tab_via_cdp(
                        cdp_url=cdp_url,
                        target_url=target_url,
                    )
                
                # 2. 如果没有 target_url 或匹配失败，使用智能检测（无硬编码）
                #    核心逻辑：获取前台窗口标题，在 CDP tabs 中搜索哪个 tab 的 title 被包含
                if not activated_tab_id:
                    print(f"[BrowserController] Trying smart tab detection (no hardcoding)...")
                    activated_tab_id = await _smart_detect_active_tab_via_cdp(cdp_url=cdp_url)
                
                if activated_tab_id:
                    print(f"[BrowserController] ✓ Pre-activated target tab: {activated_tab_id[:12]}...")
                else:
                    print(f"[BrowserController] No specific tab detected, will use browser-use default")
            except Exception as e:
                print(f"[BrowserController] Tab detection failed (will use default): {e}")
            
            # 创建 BrowserSession 并通过 CDP 连接（不启动新浏览器）
            self._session = BrowserSession(
                cdp_url=cdp_url,
                is_local=False,  # 表示连接到远程/已有浏览器
                highlight_elements=highlight_elements,
            )
            
            # 启动会话
            await self._session.start()
            
            self._connected = True
            
            # ========== 关键：在 BrowserSession.start() 之后切换到预激活的标签页 ==========
            # BrowserSession.start() 可能不会使用我们通过 CDP 预激活的标签页，
            # 所以这里需要显式切换到目标标签页
            if activated_tab_id:
                try:
                    from browser_use.browser.events import SwitchTabEvent
                    await self._session.event_bus.dispatch(SwitchTabEvent(target_id=activated_tab_id))
                    await asyncio.sleep(0.3)  # 等待切换完成
                    print(f"[BrowserController] ✓ Switched to target tab: {activated_tab_id[:12]}...")
                except Exception as e:
                    print(f"[BrowserController] ⚠ Failed to switch to target tab: {e}")
            
            print(f"[BrowserController] Attached to browser successfully!")
            
            # 获取当前页面信息
            current_url = ""
            current_title = ""
            try:
                state = await self._session.get_browser_state_summary(include_screenshot=False)
                current_url = state.url or ""
                current_title = state.title or ""
            except Exception:
                pass
            
            result = {
                "success": True,
                "message": "Attached to existing browser via CDP",
                "cdp_url": cdp_url,
                "current_url": current_url,
                "current_title": current_title,
            }
            
            if activated_tab_id:
                result["activated_tab_id"] = activated_tab_id
            
            return result
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}
    
    # ========== 页面状态 ==========
    
    async def get_page_state(
        self,
        include_screenshot: bool = True,
        max_elements: int = 100,
    ) -> Dict[str, Any]:
        """
        获取页面状态
        
        Args:
            include_screenshot: 是否包含截图
            max_elements: 最大元素数量
        
        Returns:
            页面状态字典
        """
        if not self._connected or not self._session:
            raise Exception("Not connected")
        
        # 使用 browser-use 的 get_browser_state_summary 方法
        state = await self._session.get_browser_state_summary(include_screenshot=include_screenshot)

        # region agent log
        _agent_log(
            hypothesisId="A",
            location="controllers/browser_use/controller.py:get_page_state",
            message="Fetched browser state summary",
            data={
                "include_screenshot": bool(include_screenshot),
                "max_elements": int(max_elements),
                "url": (state.url or "")[:200],
                "title": (state.title or "")[:200],
                "has_dom_state": bool(getattr(state, "dom_state", None)),
                "selector_map_len": int(len(getattr(getattr(state, "dom_state", None), "selector_map", {}) or {})),
                "selector_map_first_keys": list(
                    list(getattr(getattr(state, "dom_state", None), "selector_map", {}) or {})[:5]
                ),
            },
        )
        # endregion
        
        # 缓存状态用于后续操作
        self._cached_state = state
        # NOTE: selector_map 有时会短暂为空（例如页面忙/状态采集失败），
        # 不要用空 selector_map 覆盖掉已有缓存，否则后续 click/input 会出现
        # "Element index X not found" 的随机失败。
        if state.dom_state and getattr(state.dom_state, "selector_map", None):
            self._cached_selector_map = state.dom_state.selector_map
        
        # 保存原始 state 到文件（调试用）
        try:
            import json
            import tempfile
            from pathlib import Path
            
            # 使用临时目录而不是模块目录
            debug_dir = Path(tempfile.gettempdir()) / "browser_use_debug"
            debug_dir.mkdir(exist_ok=True)
            
            # 保存 DOM state 的 LLM 表示
            if state.dom_state:
                dom_repr = state.dom_state.llm_representation()
                with open(debug_dir / "dom_state.txt", "w", encoding="utf-8") as f:
                    f.write(dom_repr)
                
                # 保存 selector_map 的详细信息
                selector_info = []
                for key, node in state.dom_state.selector_map.items():
                    node_info = {
                        "index": key,
                        "tag_name": getattr(node, 'tag_name', ''),
                        "attributes": dict(getattr(node, 'attributes', {}) or {}),
                    }
                    # 尝试获取文本
                    if hasattr(node, 'get_all_children_text'):
                        node_info["text"] = node.get_all_children_text()[:200]
                    if hasattr(node, 'llm_representation'):
                        node_info["llm_repr"] = node.llm_representation()[:200]
                    selector_info.append(node_info)
                
                with open(debug_dir / "selector_map.json", "w", encoding="utf-8") as f:
                    json.dump(selector_info, f, indent=2, ensure_ascii=False)
            
            print(f"[BrowserController] Debug output saved to {debug_dir}")
        except Exception as e:
            print(f"[BrowserController] Failed to save debug output: {e}")
        
        result = {
            "url": state.url or "",
            "title": state.title or "",
            "elements": [],
            "element_count": 0,
        }
        
        # ========== 获取所有 Tabs 信息 ==========
        # 让 AI 知道当前浏览器有哪些标签页，以及自己在哪个标签页
        try:
            tabs = await self._session.get_tabs()
            current_target_id = self._session.agent_focus_target_id
            
            tabs_info = []
            active_tab_index = 0
            for i, tab in enumerate(tabs):
                is_active = tab.target_id == current_target_id
                if is_active:
                    active_tab_index = i
                tabs_info.append({
                    "tab_index": i,
                    "tab_id": tab.target_id,
                    "url": tab.url or "",
                    "title": tab.title or "",
                    "is_active": is_active,
                })
            
            result["tabs"] = tabs_info
            result["tab_count"] = len(tabs_info)
            result["active_tab_index"] = active_tab_index
            
            # ========== 生成 snapshot（AI_Run 会自动添加到 prompt）==========
            # 格式化 tabs 信息，让 AI 知道浏览器中有哪些标签页
            result["snapshot"] = self._format_tabs_snapshot(tabs_info, active_tab_index)
            
            # 打印 tabs 信息（简洁格式）
            print(f"[BrowserController] Tabs ({len(tabs_info)} total, active: tab{active_tab_index}):")
            for t in tabs_info:
                marker = "→" if t["is_active"] else " "
                print(f"[BrowserController]   {marker} tab{t['tab_index']}: {t['title'][:40]}...")
        except Exception as e:
            print(f"[BrowserController] Failed to get tabs info: {e}")
            result["tabs"] = []
            result["tab_count"] = 0
            result["active_tab_index"] = 0
            result["snapshot"] = ""
        
        # 截图
        if include_screenshot and state.screenshot:
            result["screenshot_base64"] = state.screenshot
        
        # 元素列表 — 视口优先排序
        # ================================================================
        # 问题: 简单按 DOM 顺序截断到 max_elements，滚动后页面顶部的
        #       不可见元素(y<0)占满名额，视口内新出现的元素被截断。
        # 解决: 优先返回当前视口内的元素，再补充视口附近的元素。
        # ================================================================
        if state.dom_state and state.dom_state.selector_map:
            # --- Step 1: 获取视口高度（用于判断元素是否可见）---
            viewport_height = 900  # fallback for typical 1080p browser
            try:
                cdp_for_vh = await self._session.get_or_create_cdp_session(focus=True)
                vh_result = await cdp_for_vh.cdp_client.send.Runtime.evaluate(
                    params={'expression': 'window.innerHeight'},
                    session_id=cdp_for_vh.session_id,
                )
                vh = vh_result.get('result', {}).get('value')
                if isinstance(vh, (int, float)) and vh > 0:
                    viewport_height = int(vh)
            except Exception:
                pass  # 获取失败就用默认值
            
            # --- Step 2: 快速收集所有元素的位置 ---
            all_items = []  # list of (key, node, y_position_or_None)
            for key, node in state.dom_state.selector_map.items():
                y = None
                if hasattr(node, 'absolute_position') and node.absolute_position:
                    y = node.absolute_position.y
                all_items.append((key, node, y))
            
            # --- Step 3: 按视口可见性分组 ---
            in_viewport = []     # 0 <= y < viewport_height（当前可见）
            below_vp = []        # y >= viewport_height（视口下方，滚动可达）
            above_vp = []        # y < 0（已滚出视口上方）
            no_pos = []          # 没有位置数据
            
            for item in all_items:
                _, _, y = item
                if y is None:
                    no_pos.append(item)
                elif 0 <= y < viewport_height:
                    in_viewport.append(item)
                elif y < 0:
                    above_vp.append(item)
                else:
                    below_vp.append(item)
            
            # --- Step 4: 组内排序 ---
            in_viewport.sort(key=lambda e: e[2])          # 视口内: 从上到下
            below_vp.sort(key=lambda e: e[2])              # 视口下方: 距视口近的优先
            above_vp.sort(key=lambda e: -e[2])             # 视口上方: 距视口近的优先 (y 接近 0)
            
            # --- Step 5: 合并优先级 ---
            # 视口内 > 视口下方(即将滚到) > 无位置 > 视口上方(已经过去)
            prioritized = in_viewport + below_vp + no_pos + above_vp
            selected = prioritized[:max_elements]
            
            print(
                f"[BrowserController] Viewport priority: "
                f"in_viewport={len(in_viewport)}, below={len(below_vp)}, "
                f"above={len(above_vp)}, no_pos={len(no_pos)}, "
                f"viewport_h={viewport_height}, selected={len(selected)}/{len(all_items)}"
            )
            
            # --- Step 6: 构建元素列表（逻辑与原来相同）---
            elements = []
            enriched_count = 0  # 被父元素上下文补充的元素计数
            for key, node, _ in selected:
                # 获取元素位置
                position = None
                if hasattr(node, 'absolute_position') and node.absolute_position:
                    pos = node.absolute_position
                    position = {
                        "x": pos.x,
                        "y": pos.y,
                        "width": pos.width,
                        "height": pos.height,
                    }
                
                tag_name = (getattr(node, 'tag_name', '') or '').lower()
                
                # 获取元素文本 - 使用 browser-use 的方法
                text = ""
                if hasattr(node, 'get_all_children_text'):
                    text = node.get_all_children_text()[:100]
                elif hasattr(node, 'llm_representation'):
                    text = node.llm_representation()[:100]
                # 如果还是空，尝试从 attributes 获取
                if not text:
                    attrs = getattr(node, 'attributes', {}) or {}
                    for attr_name in ['aria-label', 'title', 'placeholder', 'alt', 'value']:
                        if attrs.get(attr_name):
                            text = attrs[attr_name][:100]
                            break
                
                # ========== 信息贫乏元素的父元素上下文补充 ==========
                # 对于 img/video/canvas/svg 等没有自身文本的元素，
                # 向上遍历 parent_node 获取最近的有意义文本，
                # 让 AI 知道这个元素属于哪个区域、代表什么内容。
                parent_context = None
                INFO_POOR_TAGS = {'img', 'video', 'canvas', 'svg', 'input'}
                if not text and tag_name in INFO_POOR_TAGS:
                    parent_context = _extract_parent_context(node)
                    if parent_context:
                        text = f"[in: {parent_context}]"
                        enriched_count += 1
                
                elem = {
                    "index": key,
                    "tag": getattr(node, 'tag_name', ''),
                    "text": text,
                    "attributes": getattr(node, 'attributes', {}),
                    "position": position,
                }
                if parent_context:
                    elem["parent_context"] = parent_context
                elements.append(elem)

            result["elements"] = elements
            result["element_count"] = len(state.dom_state.selector_map)

            # region agent log
            _agent_log(
                hypothesisId="A",
                location="controllers/browser_use/controller.py:get_page_state",
                message="Built API elements list (viewport-prioritized)",
                data={
                    "returned_elements_len": int(len(elements)),
                    "returned_first_indices": [e.get("index") for e in elements[:5]],
                    "enriched_by_parent_context": enriched_count,
                    "viewport_height": viewport_height,
                    "distribution": {
                        "in_viewport": len(in_viewport),
                        "below_viewport": len(below_vp),
                        "above_viewport": len(above_vp),
                        "no_position": len(no_pos),
                    },
                },
            )
            # endregion
        
        return result
    
    # ========== 辅助方法 ==========
    
    def _format_tabs_snapshot(self, tabs_info: List[Dict], active_tab_index: int) -> str:
        """
        格式化 tabs 信息为 snapshot 文本
        
        这个文本会被 AI_Run 自动添加到 user prompt 中，
        让 AI 知道浏览器中有哪些标签页。
        
        Args:
            tabs_info: 标签页信息列表
            active_tab_index: 当前活动标签页的索引
            
        Returns:
            格式化的 snapshot 文本
        """
        if not tabs_info:
            return ""
        
        lines = [
            "## Browser Tabs",
            f"Total: {len(tabs_info)} tabs | Active: tab{active_tab_index}",
            "",
        ]
        
        for tab in tabs_info:
            idx = tab["tab_index"]
            title = tab["title"] or "(untitled)"
            url = tab["url"] or ""
            is_active = tab["is_active"]
            
            # 标记活动标签页
            marker = "[ACTIVE] " if is_active else ""
            
            # 截断过长的 URL
            url_display = url[:80] + "..." if len(url) > 80 else url
            
            lines.append(f"- tab{idx}: {marker}{title}")
            lines.append(f"  URL: {url_display}")
        
        return "\n".join(lines)
    
    def _get_element_by_index(self, index: int):
        """根据 index 获取元素节点"""
        if not self._cached_selector_map:
            return None
        node = self._cached_selector_map.get(index)

        # region agent log
        _agent_log(
            hypothesisId="A",
            location="controllers/browser_use/controller.py:_get_element_by_index",
            message="Selector map lookup",
            data={
                "requested_index": int(index),
                "direct_hit": bool(node is not None),
                "cached_selector_map_len": int(len(self._cached_selector_map or {})),
                "cached_first_keys": list(list(self._cached_selector_map or {})[:5]),
            },
        )
        # endregion

        if node is not None:
            return node

        # Compatibility: some callers pass the *position* in the returned elements list
        # (0..N-1) instead of the underlying selector_map key (often 10+ / 100+).
        # If direct lookup failed, interpret small integers as ordinal index.
        try:
            ordinal = int(index)
        except Exception:
            return None

        if ordinal < 0 or ordinal >= len(self._cached_selector_map):
            return None

        keys = list(self._cached_selector_map.keys())
        resolved_key = keys[ordinal]
        resolved_node = self._cached_selector_map.get(resolved_key)

        # region agent log
        _agent_log(
            hypothesisId="D",
            location="controllers/browser_use/controller.py:_get_element_by_index",
            message="Resolved ordinal index to selector_map key",
            data={
                "requested_index": int(index),
                "resolved_key": int(resolved_key) if isinstance(resolved_key, int) else str(resolved_key),
                "resolved_hit": bool(resolved_node is not None),
            },
        )
        # endregion

        return resolved_node
    
    async def _dispatch_event_with_timeout(self, event, timeout: float = None):
        """分发事件并等待完成，带超时"""
        timeout = timeout or self.EVENT_TIMEOUT
        dispatched = self._session.event_bus.dispatch(event)
        try:
            await asyncio.wait_for(dispatched, timeout=timeout)
            return True
        except asyncio.TimeoutError:
            # 超时但事件可能已发送
            return True
    
    async def _send_key_via_cdp(self, key: str):
        """通过 CDP 直接发送按键"""
        cdp_session = await self._session.get_or_create_cdp_session(focus=True)
        
        # 按键映射
        key_codes = {
            "Enter": 13,
            "Tab": 9,
            "Escape": 27,
            "Backspace": 8,
            "Delete": 46,
            "ArrowUp": 38,
            "ArrowDown": 40,
            "ArrowLeft": 37,
            "ArrowRight": 39,
        }
        
        key_code = key_codes.get(key, 0)
        
        # keyDown
        await cdp_session.cdp_client.send.Input.dispatchKeyEvent(
            params={
                'type': 'keyDown',
                'key': key,
                'code': key,
                'windowsVirtualKeyCode': key_code,
                'nativeVirtualKeyCode': key_code,
            },
            session_id=cdp_session.session_id
        )
        
        # keyUp
        await cdp_session.cdp_client.send.Input.dispatchKeyEvent(
            params={
                'type': 'keyUp',
                'key': key,
                'code': key,
                'windowsVirtualKeyCode': key_code,
                'nativeVirtualKeyCode': key_code,
            },
            session_id=cdp_session.session_id
        )
    
    # ========== 执行操作 ==========
    
    async def execute_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行浏览器操作
        
        支持的 Action 类型:
        - go_to_url: 导航到 URL
        - click_element: 点击元素
        - input_text: 输入文本
        - scroll_down / scroll_up: 滚动
        - press_key: 按键
        - go_back / go_forward: 导航
        - refresh: 刷新
        - wait: 等待
        - screenshot: 截图
        - extract_content: 提取内容
        
        Args:
            action: Action 字典
        
        Returns:
            执行结果
        """
        if not self._connected or not self._session:
            raise Exception("Not connected")
        
        action_type = action.get("action", "").lower()
        
        try:
            # ========== 导航 ==========
            if action_type == "go_to_url":
                url = action.get("url", "")
                await self._session._cdp_navigate(url)
                await asyncio.sleep(1)  # 等待页面加载
                return {"success": True, "action": action_type, "url": url}
            
            elif action_type == "go_back":
                # 通过 CDP 执行后退
                cdp_session = await self._session.get_or_create_cdp_session(focus=True)
                await cdp_session.cdp_client.send.Page.goBack(session_id=cdp_session.session_id)
                await asyncio.sleep(0.5)
                return {"success": True, "action": action_type}
            
            elif action_type == "go_forward":
                cdp_session = await self._session.get_or_create_cdp_session(focus=True)
                await cdp_session.cdp_client.send.Page.goForward(session_id=cdp_session.session_id)
                await asyncio.sleep(0.5)
                return {"success": True, "action": action_type}
            
            elif action_type == "refresh":
                cdp_session = await self._session.get_or_create_cdp_session(focus=True)
                await cdp_session.cdp_client.send.Page.reload(session_id=cdp_session.session_id)
                await asyncio.sleep(1)
                return {"success": True, "action": action_type}
            
            # ========== 元素交互 ==========
            elif action_type == "click_element":
                index = action.get("index", 0)
                
                # 先刷新状态获取最新的 selector_map
                await self.get_page_state(include_screenshot=False)

                # region agent log
                _agent_log(
                    hypothesisId="B",
                    location="controllers/browser_use/controller.py:execute_action(click_element)",
                    message="Click element requested",
                    data={
                        "index": int(index),
                        "cached_selector_map_len": int(len(self._cached_selector_map or {})),
                        "cached_first_keys": list(list(self._cached_selector_map or {})[:5]),
                    },
                )
                # endregion
                
                node = self._get_element_by_index(index)
                if not node:
                    return {"success": False, "error": f"Element index {index} not found"}
                
                # 记录点击前的标签页数量
                tabs_before = []
                try:
                    tabs_before = await self._session.get_tabs()
                except Exception:
                    pass
                tabs_count_before = len(tabs_before)
                
                # 高亮元素（如果启用）
                if self.config.highlight_elements:
                    try:
                        await self._session.highlight_interaction_element(node)
                        await asyncio.sleep(0.3)
                    except Exception:
                        pass
                
                # ========== 智能点击策略 ==========
                # 
                # 问题背景：
                # 对于通过 has_js_click_listener 检测到的非标准交互元素（如 Vue @click 
                # 绑定的 <img>、<div> 等），CDP 的 Input.dispatchMouseEvent 在元素中心
                # 坐标做 hit-test 时，可能命中被其他元素遮挡的位置（如文字覆盖层），
                # 导致目标元素的事件处理器永远不会被触发。
                #
                # 而 JS element.click() 虽然绕过 hit-test，但产生 isTrusted=false 的事件，
                # 如果 click handler 调用 window.open()，会被浏览器 popup blocker 拦截
                # （尤其是 ATTACH 模式下，浏览器没有 --disable-popup-blocking 参数）。
                #
                # 解决方案（z-index boost）：
                # 1. 临时提升目标元素的 z-index，确保它在视觉最上层
                # 2. 使用 CDP 坐标点击（Input.dispatchMouseEvent），产生 isTrusted=true 事件
                # 3. 坐标 hit-test 命中正确元素 → Vue handler 正常触发 → window.open() 被允许
                # 4. 点击后恢复元素原始样式
                #
                STANDARD_INTERACTIVE_TAGS = {'a', 'button', 'input', 'select', 'textarea', 'summary', 'details', 'option'}
                tag_name = getattr(node, 'tag_name', '').lower()
                needs_click_fix = getattr(node, 'has_js_click_listener', False) and tag_name not in STANDARD_INTERACTIVE_TAGS
                
                if needs_click_fix:
                    print(f"[BrowserController] Non-standard clickable <{tag_name}> detected, using z-index boost + CDP click")
                    boosted = False
                    cdp_session = None
                    object_id = None
                    try:
                        cdp_session = await self._session.get_or_create_cdp_session(focus=True)
                        resolve_result = await cdp_session.cdp_client.send.DOM.resolveNode(
                            params={'backendNodeId': node.backend_node_id},
                            session_id=cdp_session.session_id,
                        )
                        object_id = resolve_result.get('object', {}).get('objectId')
                        
                        if object_id:
                            # Step 1: 临时提升 z-index，确保元素在最上层
                            await cdp_session.cdp_client.send.Runtime.callFunctionOn(
                                params={
                                    'functionDeclaration': '''function() {
                                        this._bu_orig = {
                                            zIndex: this.style.zIndex,
                                            position: this.style.position
                                        };
                                        this.style.zIndex = '999999';
                                        if (getComputedStyle(this).position === 'static') {
                                            this.style.position = 'relative';
                                        }
                                    }''',
                                    'objectId': object_id,
                                },
                                session_id=cdp_session.session_id,
                            )
                            boosted = True
                            await asyncio.sleep(0.05)
                            print(f"[BrowserController] ✓ z-index boosted for <{tag_name}>")
                    except Exception as e:
                        print(f"[BrowserController] Warning: z-index boost failed ({e}), will try normal click")
                    
                    # Step 2: 使用 CDP 坐标点击（trusted event）
                    try:
                        await self._dispatch_event_with_timeout(ClickElementEvent(node=node))
                        print(f"[BrowserController] ✓ CDP coordinate click dispatched on <{tag_name}>")
                    except Exception as e:
                        print(f"[BrowserController] Warning: CDP click failed ({e})")
                    
                    # Step 3: 恢复原始 z-index
                    if boosted and cdp_session and object_id:
                        try:
                            await cdp_session.cdp_client.send.Runtime.callFunctionOn(
                                params={
                                    'functionDeclaration': '''function() {
                                        if (this._bu_orig) {
                                            this.style.zIndex = this._bu_orig.zIndex;
                                            this.style.position = this._bu_orig.position;
                                            delete this._bu_orig;
                                        }
                                    }''',
                                    'objectId': object_id,
                                },
                                session_id=cdp_session.session_id,
                            )
                        except Exception:
                            pass  # 页面可能已跳转，恢复失败没关系
                else:
                    # 标准路径：使用 CDP Input.dispatchMouseEvent（坐标点击）
                    await self._dispatch_event_with_timeout(
                        ClickElementEvent(node=node)
                    )
                
                # ========== 检测并跟随新标签页 ==========
                # 等待可能的新标签页打开
                await asyncio.sleep(0.5)
                
                try:
                    tabs_after = await self._session.get_tabs()
                    tabs_count_after = len(tabs_after)
                    
                    # 如果打开了新标签页，自动切换到新标签页
                    if tabs_count_after > tabs_count_before:
                        print(f"[BrowserController] New tab detected: {tabs_count_before} -> {tabs_count_after}")
                        
                        # 找到新标签页（通常是最后一个）
                        new_tab = tabs_after[-1]
                        new_tab_id = getattr(new_tab, 'target_id', None) or getattr(new_tab, 'id', None)
                        new_tab_url = getattr(new_tab, 'url', 'unknown')
                        
                        if new_tab_id:
                            print(f"[BrowserController] Switching to new tab: {new_tab_url[:60]}...")
                            from browser_use.browser.events import SwitchTabEvent
                            await self._session.event_bus.dispatch(SwitchTabEvent(target_id=new_tab_id))
                            await asyncio.sleep(0.5)
                            print(f"[BrowserController] ✓ Switched to new tab")
                except Exception as e:
                    print(f"[BrowserController] Warning: Failed to check for new tabs: {e}")
                
                return {"success": True, "action": action_type, "index": index}
            
            elif action_type == "input_text":
                index = action.get("index", 0)
                text = action.get("text", "")
                
                # 先刷新状态
                await self.get_page_state(include_screenshot=False)

                # region agent log
                _agent_log(
                    hypothesisId="B",
                    location="controllers/browser_use/controller.py:execute_action(input_text)",
                    message="Input text requested",
                    data={
                        "index": int(index),
                        "text_len": int(len(text or "")),
                        "cached_selector_map_len": int(len(self._cached_selector_map or {})),
                        "cached_first_keys": list(list(self._cached_selector_map or {})[:5]),
                    },
                )
                # endregion
                
                node = self._get_element_by_index(index)
                if not node:
                    return {"success": False, "error": f"Element index {index} not found"}
                
                # 使用事件系统输入
                await self._dispatch_event_with_timeout(
                    TypeTextEvent(node=node, text=text)
                )
                
                return {"success": True, "action": action_type, "index": index, "text": text}
            
            # ========== 滚动 ==========
            elif action_type == "scroll_down":
                # 默认滚动 750 像素（约一屏高度），可通过 amount 参数自定义
                amount = action.get("amount", 750)
                await self._dispatch_event_with_timeout(
                    ScrollEvent(direction='down', amount=amount)
                )
                return {"success": True, "action": action_type, "amount": amount}
            
            elif action_type == "scroll_up":
                # 默认滚动 750 像素（约一屏高度），可通过 amount 参数自定义
                amount = action.get("amount", 750)
                await self._dispatch_event_with_timeout(
                    ScrollEvent(direction='up', amount=amount)
                )
                return {"success": True, "action": action_type, "amount": amount}
            
            # ========== 键盘 ==========
            elif action_type == "press_key":
                key = action.get("key", "")
                # 使用 CDP 直接发送按键（避免事件系统卡住）
                await self._send_key_via_cdp(key)
                return {"success": True, "action": action_type, "key": key}
            
            # ========== 其他 ==========
            elif action_type == "wait":
                seconds = action.get("seconds", 1)
                await asyncio.sleep(seconds)
                return {"success": True, "action": action_type, "seconds": seconds}
            
            elif action_type == "screenshot":
                state = await self._session.get_browser_state_summary(include_screenshot=True)
                return {
                    "success": True,
                    "action": action_type,
                    "image_base64": state.screenshot or "",
                }
            
            elif action_type == "extract_content":
                selector = action.get("selector", "body")
                cdp_session = await self._session.get_or_create_cdp_session(focus=True)
                
                # 通过 CDP 执行 JavaScript
                # 使用 innerText 而非 textContent，因为 innerText 会：
                # 1. 在块级元素（div, p, br 等）之间插入换行符
                # 2. 按照视觉渲染结果返回文本，保留结构化排版
                # 3. 隐藏 display:none 的元素（textContent 则会包含）
                result = await cdp_session.cdp_client.send.Runtime.evaluate(
                    params={
                        'expression': f"document.querySelector('{selector}')?.innerText || ''",
                        'returnByValue': True,
                    },
                    session_id=cdp_session.session_id
                )
                
                content = result.get('result', {}).get('value', '')
                return {"success": True, "action": action_type, "content": content.strip()}
            
            # ========== 窗口控制 ==========
            elif action_type == "maximize_window":
                cdp_session = await self._session.get_or_create_cdp_session(focus=True)
                
                try:
                    # 获取窗口 ID（需要传 targetId）
                    windows_result = await cdp_session.cdp_client.send.Browser.getWindowForTarget(
                        params={'targetId': cdp_session.target_id},
                        session_id=cdp_session.session_id
                    )
                    window_id = windows_result.get('windowId')
                    
                    if window_id:
                        # 设置窗口为最大化状态
                        await cdp_session.cdp_client.send.Browser.setWindowBounds(
                            params={
                                'windowId': window_id,
                                'bounds': {'windowState': 'maximized'}
                            },
                            session_id=cdp_session.session_id
                        )
                        return {"success": True, "action": action_type, "window_id": window_id}
                    else:
                        return {"success": False, "error": "Failed to get window ID"}
                except Exception as e:
                    # 如果 CDP 方法失败，尝试使用 JavaScript
                    print(f"[BrowserController] CDP maximize failed: {e}, trying JavaScript...")
                    try:
                        await cdp_session.cdp_client.send.Runtime.evaluate(
                            params={
                                'expression': '''
                                    // 尝试进入全屏或最大化
                                    if (document.documentElement.requestFullscreen) {
                                        // 不使用全屏，因为会隐藏地址栏
                                    }
                                    // 通过 window.moveTo 和 resizeTo 模拟最大化
                                    window.moveTo(0, 0);
                                    window.resizeTo(screen.availWidth, screen.availHeight);
                                    true;
                                ''',
                                'returnByValue': True,
                            },
                            session_id=cdp_session.session_id
                        )
                        return {"success": True, "action": action_type, "method": "javascript"}
                    except Exception as js_error:
                        return {"success": False, "error": f"CDP: {e}, JS: {js_error}"}
            
            elif action_type == "minimize_window":
                cdp_session = await self._session.get_or_create_cdp_session(focus=True)
                try:
                    windows_result = await cdp_session.cdp_client.send.Browser.getWindowForTarget(
                        params={'targetId': cdp_session.target_id},
                        session_id=cdp_session.session_id
                    )
                    window_id = windows_result.get('windowId')
                    
                    if window_id:
                        await cdp_session.cdp_client.send.Browser.setWindowBounds(
                            params={
                                'windowId': window_id,
                                'bounds': {'windowState': 'minimized'}
                            },
                            session_id=cdp_session.session_id
                        )
                        return {"success": True, "action": action_type}
                    else:
                        return {"success": False, "error": "Failed to get window ID"}
                except Exception as e:
                    return {"success": False, "error": str(e)}
            
            elif action_type == "set_window_size":
                width = action.get("width", 1280)
                height = action.get("height", 720)
                cdp_session = await self._session.get_or_create_cdp_session(focus=True)
                try:
                    windows_result = await cdp_session.cdp_client.send.Browser.getWindowForTarget(
                        params={'targetId': cdp_session.target_id},
                        session_id=cdp_session.session_id
                    )
                    window_id = windows_result.get('windowId')
                    
                    if window_id:
                        await cdp_session.cdp_client.send.Browser.setWindowBounds(
                            params={
                                'windowId': window_id,
                                'bounds': {
                                    'windowState': 'normal',
                                    'width': width,
                                    'height': height
                                }
                            },
                            session_id=cdp_session.session_id
                        )
                        return {"success": True, "action": action_type, "width": width, "height": height}
                    else:
                        return {"success": False, "error": "Failed to get window ID"}
                except Exception as e:
                    return {"success": False, "error": str(e)}
            
            # ========== Tab 管理 ==========
            elif action_type == "switch_tab":
                tab_id = action.get("tab_id", "")
                # tab_id 格式为 "tab0", "tab1" 等，需要解析出 index 然后映射到实际 target_id
                tab_match = re.match(r'tab(\d+)', tab_id)
                if not tab_match:
                    return {"success": False, "error": f"Invalid tab_id format: {tab_id}, expected 'tab0', 'tab1', etc."}
                
                tab_index = int(tab_match.group(1))
                tabs = await self._session.get_tabs()
                
                if tab_index < 0 or tab_index >= len(tabs):
                    return {"success": False, "error": f"Tab index {tab_index} out of range (0-{len(tabs)-1})"}
                
                target_tab = tabs[tab_index]
                target_id = target_tab.target_id
                
                from browser_use.browser.events import SwitchTabEvent
                await self._session.event_bus.dispatch(SwitchTabEvent(target_id=target_id))
                await asyncio.sleep(0.5)
                
                print(f"[BrowserController] ✓ Switched to tab{tab_index}: {target_tab.title[:40]}...")
                return {
                    "success": True,
                    "action": action_type,
                    "tab_id": tab_id,
                    "title": target_tab.title or "",
                    "url": target_tab.url or "",
                }
            
            elif action_type == "close_tab":
                tab_id = action.get("tab_id", "")
                tabs = await self._session.get_tabs()
                current_target_id = self._session.agent_focus_target_id
                
                # 支持 "current" 作为 tab_id，解析为当前活跃标签页
                if tab_id == "current":
                    # 找到当前活跃标签页的索引
                    tab_index = None
                    for i, tab in enumerate(tabs):
                        if tab.target_id == current_target_id:
                            tab_index = i
                            break
                    if tab_index is None:
                        return {"success": False, "error": "Cannot determine current active tab"}
                else:
                    tab_match = re.match(r'tab(\d+)', tab_id)
                    if not tab_match:
                        return {"success": False, "error": f"Invalid tab_id format: {tab_id}, expected 'tab0', 'tab1', 'current', etc."}
                    tab_index = int(tab_match.group(1))
                
                if tab_index < 0 or tab_index >= len(tabs):
                    return {"success": False, "error": f"Tab index {tab_index} out of range (0-{len(tabs)-1})"}
                
                if len(tabs) <= 1:
                    return {"success": False, "error": "Cannot close the only remaining tab"}
                
                target_tab = tabs[tab_index]
                target_id = target_tab.target_id
                
                # 如果要关闭的是当前活跃标签页，先切换到其他标签页
                is_active = (target_id == current_target_id)
                if is_active:
                    # 优先切换到前一个标签页，否则切换到后一个
                    switch_to_index = tab_index - 1 if tab_index > 0 else tab_index + 1
                    switch_to_tab_obj = tabs[switch_to_index]
                    from browser_use.browser.events import SwitchTabEvent
                    await self._session.event_bus.dispatch(SwitchTabEvent(target_id=switch_to_tab_obj.target_id))
                    await asyncio.sleep(0.5)
                    print(f"[BrowserController] Auto-switched to tab{switch_to_index} before closing tab{tab_index}")
                
                # 通过 browser_use 事件总线关闭标签页（与 session_manager.close_tab 一致）
                from browser_use.browser.events import CloseTabEvent
                await self._session.event_bus.dispatch(CloseTabEvent(target_id=target_id))
                await asyncio.sleep(0.5)
                
                print(f"[BrowserController] ✓ Closed tab{tab_index}: {target_tab.title[:40]}...")
                return {
                    "success": True,
                    "action": action_type,
                    "tab_id": tab_id,
                    "title": target_tab.title or "",
                }
            
            else:
                return {"success": False, "error": f"Unknown action: {action_type}"}
        
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"success": False, "action": action_type, "error": str(e)}
    
    async def execute_actions(self, actions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """执行多个操作"""
        results = []
        for action in actions:
            result = await self.execute_action(action)
            results.append(result)
            if not result.get("success"):
                break
        
        return {
            "success": all(r.get("success") for r in results),
            "results": results,
        }
    
    # ========== 状态查询 ==========
    
    async def get_status(self) -> Dict[str, Any]:
        """获取控制器状态"""
        status = {
            "connected": self._connected,
            "browser_type": self.config.browser_type.value,
            "profile": self.config.profile_directory,
            "executable_path": self.config.executable_path,
            "user_data_dir": self.config.user_data_dir,
        }
        
        if self._connected and self._session:
            try:
                state = await self._session.get_browser_state_summary(include_screenshot=False)
                status["current_url"] = state.url or ""
                status["current_title"] = state.title or ""
            except Exception:
                pass
        
        return status


# ==================== 辅助函数 ====================


def _extract_parent_context(node, max_depth: int = 5, max_text_len: int = 80) -> Optional[str]:
    """
    为信息贫乏的元素（img/video/canvas/svg）提取父元素上下文。
    
    向上遍历 parent_node 链，找到最近的含有有意义文本的祖先元素，
    返回该祖先的简要描述，让 AI 知道这个元素属于什么区域。
    
    例如:
      <div class="video-card">零跑CEO：65%零部件我自己造！</div>
        └ <img class="cover">  ← 信息贫乏，text 为空
      
      返回: "零跑CEO：65%零部件我自己造！"
    
    Args:
        node: browser-use 的 EnhancedDOMTreeNode
        max_depth: 最多向上遍历几层
        max_text_len: 返回文本的最大长度
    
    Returns:
        父元素上下文文本，如果找不到则返回 None
    """
    parent = getattr(node, 'parent_node', None)
    depth = 0
    
    while parent and depth < max_depth:
        depth += 1
        
        # 跳过无意义的顶层节点
        parent_tag = (getattr(parent, 'tag_name', '') or '').lower()
        if parent_tag in ('html', 'body', 'head', ''):
            parent = getattr(parent, 'parent_node', None)
            continue
        
        # 尝试获取父元素的文本内容
        parent_text = ""
        if hasattr(parent, 'get_all_children_text'):
            parent_text = (parent.get_all_children_text() or "").strip()
        
        if parent_text and len(parent_text) > 3:
            # 截断过长的文本
            if len(parent_text) > max_text_len:
                parent_text = parent_text[:max_text_len] + "..."
            return parent_text
        
        # 如果文本为空，检查父元素的 aria-label / title
        parent_attrs = getattr(parent, 'attributes', {}) or {}
        for attr_name in ['aria-label', 'title', 'data-name', 'alt']:
            attr_val = (parent_attrs.get(attr_name) or "").strip()
            if attr_val and len(attr_val) > 2:
                if len(attr_val) > max_text_len:
                    attr_val = attr_val[:max_text_len] + "..."
                return attr_val
        
        # 继续向上
        parent = getattr(parent, 'parent_node', None)
    
    return None


# 全局控制器实例
_controller: Optional[BrowserController] = None


def get_controller() -> BrowserController:
    """获取全局控制器实例"""
    global _controller
    if _controller is None:
        _controller = BrowserController()
    return _controller


async def reset_controller(config: Optional[BrowserConfig] = None) -> BrowserController:
    """重置全局控制器"""
    global _controller
    if _controller and _controller.is_connected:
        await _controller.disconnect()
    
    _controller = BrowserController(config=config)
    return _controller
