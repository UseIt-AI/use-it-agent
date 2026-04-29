"""
Browser Configuration
浏览器配置模块，用于连接真实浏览器（保留登录态）

基于 browser-use 官方文档:
https://docs.browser-use.com/customize/browser/real-browser

使用方法:
    from browser_use import Browser
    
    browser = Browser(
        executable_path='C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
        user_data_dir='%LOCALAPPDATA%\\Google\\Chrome\\User Data',
        profile_directory='Default',
    )
"""

import json
import os
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any


class BrowserType(Enum):
    """浏览器类型"""
    CHROME = "chrome"
    EDGE = "edge"
    AUTO = "auto"


@dataclass
class BrowserProfile:
    """浏览器 Profile 信息"""
    directory: str  # Profile 目录名，如 "Default", "Profile 5"
    name: str  # 显示名称
    email: str = ""  # 关联的邮箱
    is_using_default_name: bool = True


@dataclass
class BrowserConfig:
    """
    浏览器配置
    
    用于连接真实浏览器，保留登录态、Cookie、书签等
    
    Attributes:
        browser_type: 浏览器类型 (chrome, edge, auto)
        executable_path: 浏览器可执行文件路径
        user_data_dir: 用户数据目录
        profile_directory: Profile 目录名
        headless: 是否无头模式
        enable_default_extensions: 是否启用默认扩展（广告拦截等）
        highlight_elements: 是否高亮显示交互元素
        extra_args: 额外的启动参数
    """
    browser_type: BrowserType = BrowserType.AUTO
    executable_path: Optional[str] = None
    user_data_dir: Optional[str] = None
    profile_directory: str = "Default"
    headless: bool = False
    enable_default_extensions: bool = False  # 默认禁用，加快启动速度
    highlight_elements: bool = True  # 默认启用，方便调试
    initial_url: Optional[str] = None  # 连接后自动导航到的 URL（避免 about:blank 动画）
    extra_args: List[str] = field(default_factory=list)
    
    # Windows 默认路径
    CHROME_PATHS = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    
    EDGE_PATHS = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    
    CHROME_USER_DATA = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data")
    EDGE_USER_DATA = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\User Data")
    
    def __post_init__(self):
        """初始化后自动填充路径"""
        if self.executable_path is None:
            self.executable_path = self._find_executable()
        
        if self.user_data_dir is None:
            self.user_data_dir = self._get_user_data_dir()
    
    def _find_executable(self) -> Optional[str]:
        """查找浏览器可执行文件"""
        if self.browser_type == BrowserType.CHROME:
            paths = self.CHROME_PATHS
        elif self.browser_type == BrowserType.EDGE:
            paths = self.EDGE_PATHS
        else:  # AUTO
            paths = self.CHROME_PATHS + self.EDGE_PATHS
        
        for path in paths:
            expanded = os.path.expandvars(path)
            if os.path.exists(expanded):
                # 自动设置 browser_type
                if self.browser_type == BrowserType.AUTO:
                    if "chrome" in path.lower():
                        self.browser_type = BrowserType.CHROME
                    else:
                        self.browser_type = BrowserType.EDGE
                return expanded
        
        return None
    
    def _get_user_data_dir(self) -> Optional[str]:
        """获取用户数据目录"""
        if self.browser_type == BrowserType.CHROME:
            return self.CHROME_USER_DATA
        elif self.browser_type == BrowserType.EDGE:
            return self.EDGE_USER_DATA
        else:
            # AUTO: 根据找到的浏览器决定
            if self.executable_path and "chrome" in self.executable_path.lower():
                return self.CHROME_USER_DATA
            elif self.executable_path and "edge" in self.executable_path.lower():
                return self.EDGE_USER_DATA
        return None
    
    def get_profiles(self) -> List[BrowserProfile]:
        """
        获取所有可用的 Profile 列表
        
        Returns:
            Profile 列表
        """
        profiles = []
        
        if not self.user_data_dir or not os.path.exists(self.user_data_dir):
            return profiles
        
        for item in os.listdir(self.user_data_dir):
            item_path = os.path.join(self.user_data_dir, item)
            if not os.path.isdir(item_path):
                continue
            
            # 只检查 Default 和 Profile X 目录
            if item != "Default" and not item.startswith("Profile "):
                continue
            
            prefs_path = os.path.join(item_path, "Preferences")
            if not os.path.exists(prefs_path):
                continue
            
            try:
                with open(prefs_path, 'r', encoding='utf-8') as f:
                    prefs = json.load(f)
                
                profile_info = prefs.get("profile", {})
                account_info = prefs.get("account_info", [])
                
                name = profile_info.get("name", item)
                email = ""
                if account_info and len(account_info) > 0:
                    email = account_info[0].get("email", "")
                
                profiles.append(BrowserProfile(
                    directory=item,
                    name=name,
                    email=email,
                    is_using_default_name=profile_info.get("using_default_name", True),
                ))
            except Exception:
                profiles.append(BrowserProfile(
                    directory=item,
                    name=item,
                ))
        
        return profiles
    
    def to_browser_use_config(self) -> Dict[str, Any]:
        """
        转换为 browser-use 库的配置格式
        
        Returns:
            browser-use BrowserSession 构造参数
        """
        config = {}
        
        if self.executable_path:
            config["executable_path"] = self.executable_path
        
        if self.user_data_dir:
            config["user_data_dir"] = self.user_data_dir
        
        if self.profile_directory:
            config["profile_directory"] = self.profile_directory
        
        config["headless"] = self.headless
        config["enable_default_extensions"] = self.enable_default_extensions
        config["highlight_elements"] = self.highlight_elements
        
        if self.extra_args:
            config["args"] = self.extra_args
        
        return config
    
    def validate(self) -> tuple[bool, str]:
        """
        验证配置是否有效
        
        Returns:
            (是否有效, 错误信息)
        """
        if not self.executable_path:
            return False, "Browser executable not found"
        
        if not os.path.exists(self.executable_path):
            return False, f"Browser executable not found: {self.executable_path}"
        
        if not self.user_data_dir:
            return False, "User data directory not specified"
        
        if not os.path.exists(self.user_data_dir):
            return False, f"User data directory not found: {self.user_data_dir}"
        
        # 检查 Profile 是否存在
        profile_path = os.path.join(self.user_data_dir, self.profile_directory)
        if not os.path.exists(profile_path):
            return False, f"Profile not found: {self.profile_directory}"
        
        return True, "OK"
    
    @classmethod
    def get_installed_browsers(cls) -> List[Dict[str, Any]]:
        """
        获取已安装的浏览器列表
        
        Returns:
            [{"type": "chrome", "path": "...", "user_data_dir": "..."}]
        """
        browsers = []
        
        for path in cls.CHROME_PATHS:
            expanded = os.path.expandvars(path)
            if os.path.exists(expanded):
                browsers.append({
                    "type": "chrome",
                    "path": expanded,
                    "user_data_dir": cls.CHROME_USER_DATA,
                })
                break
        
        for path in cls.EDGE_PATHS:
            expanded = os.path.expandvars(path)
            if os.path.exists(expanded):
                browsers.append({
                    "type": "edge",
                    "path": expanded,
                    "user_data_dir": cls.EDGE_USER_DATA,
                })
                break
        
        return browsers


def get_default_config(
    browser_type: str = "auto",
    profile_directory: str = "Default",
    headless: bool = False,
    enable_default_extensions: bool = False,
    highlight_elements: bool = True,
) -> BrowserConfig:
    """
    获取默认浏览器配置
    
    Args:
        browser_type: 浏览器类型 ("chrome", "edge", "auto")
        profile_directory: Profile 目录名
        headless: 是否无头模式
        enable_default_extensions: 是否启用默认扩展
        highlight_elements: 是否高亮显示交互元素
    
    Returns:
        BrowserConfig 实例
    """
    bt = BrowserType(browser_type.lower()) if browser_type.lower() in ["chrome", "edge", "auto"] else BrowserType.AUTO
    
    return BrowserConfig(
        browser_type=bt,
        profile_directory=profile_directory,
        headless=headless,
        enable_default_extensions=enable_default_extensions,
        highlight_elements=highlight_elements,
    )
