"""
Browser-Use Monkey Patches
对 browser-use 库的运行时补丁

这些补丁修复/优化了 browser-use 库的一些问题：
1. 禁用 about:blank DVD screensaver 动画（减少视觉干扰）
2. Profile 复制优化（跳过锁定文件、缓存、历史、会话等，加快启动）
3. 禁用自动打开页面（禁用账户页面、首次运行提示等，加快启动）
"""

import shutil
import tempfile
from pathlib import Path

# 标记是否已应用补丁
_patches_applied = False


def apply_patches(use_proxy: bool = True, patch_profile_copy: bool = False):
    """
    应用所有 monkey patches（只执行一次）
    
    Args:
        use_proxy: 是否使用系统代理。设为 False 可避免代理超时问题。
        patch_profile_copy: 是否启用 profile 复制优化（可能导致 CDP 连接问题）
    """
    global _patches_applied
    if _patches_applied:
        return
    _patches_applied = True
    
    # 首先修复 Windows 参数解析 Bug（必须在其他补丁之前）
    _patch_fix_windows_args_bug()
    
    # 修复 Windows 上 subprocess 路径处理问题（核心修复）
    _patch_fix_windows_subprocess_path()
    
    _patch_disable_dvd_screensaver()
    
    # 暂时禁用 profile 复制补丁，可能导致 CDP 连接问题
    if patch_profile_copy:
        _patch_profile_copy_ignore_locked()
    
    _patch_disable_auto_open_pages(use_proxy=use_proxy)


def _patch_fix_windows_args_bug():
    """
    Monkey Patch 0: 修复 Windows 上的参数解析 Bug
    
    browser-use 库的 CHROME_DEFAULT_ARGS 包含这个参数：
    '--simulate-outdated-no-au="Tue, 31 Dec 2099 23:59:59 GMT"'
    
    在 Windows 上，这个带引号的参数会被错误解析，导致：
    - "31" 被解释为 URL http://0.0.0.31/
    - "Dec" 被解释为 URL http://dec/
    - "23:59:59" 被解释为某种 IP
    - "GMT" 被解释为 URL http://gmt/
    
    这个补丁直接从 CHROME_DEFAULT_ARGS 列表中移除有问题的参数。
    """
    import platform
    if platform.system() != 'Windows':
        print("[MonkeyPatches] Patch 0: skipped (not Windows)")
        return
    
    try:
        from browser_use.browser import profile as browser_profile
        
        # 直接修改全局列表
        original_len = len(browser_profile.CHROME_DEFAULT_ARGS)
        
        # 找到并移除有问题的参数
        args_to_remove = []
        for arg in browser_profile.CHROME_DEFAULT_ARGS:
            if 'simulate-outdated-no-au' in arg:
                args_to_remove.append(arg)
                print(f"[MonkeyPatches] Found problematic arg: {arg[:60]}...")
        
        for arg in args_to_remove:
            browser_profile.CHROME_DEFAULT_ARGS.remove(arg)
        
        removed_count = original_len - len(browser_profile.CHROME_DEFAULT_ARGS)
        print(f"[MonkeyPatches] Patch 0: removed {removed_count} problematic args from CHROME_DEFAULT_ARGS")
    except Exception as e:
        print(f"[MonkeyPatches] Warning: failed to apply patch 0: {e}")


def _patch_fix_windows_subprocess_path():
    """
    Monkey Patch 0.5: 修复 Windows 上 subprocess 路径处理问题
    
    browser-use 使用 asyncio.create_subprocess_exec 启动浏览器：
        subprocess = await asyncio.create_subprocess_exec(browser_path, *launch_args, ...)
    
    问题：在 Windows 上，带空格的路径（如 'User Data'）无法被正确解析，
    导致 '--user-data-dir=C:\\...\\User Data' 被截断为 '--user-data-dir=C:\\...\\User'
    
    解决方案：Monkey patch LocalBrowserWatchdog._launch_browser 方法，
    在 Windows 上使用 shell=True 启动浏览器（能正确处理带空格的路径）
    
    这是一个优雅的修复，因为：
    1. 保留了 browser-use 的所有原生功能（随机端口、重试逻辑、进程管理等）
    2. 只修改了启动方式，其他逻辑不变
    3. 仅在 Windows 上应用
    """
    import platform
    if platform.system() != 'Windows':
        print("[MonkeyPatches] Patch 0.5: skipped (not Windows)")
        return
    
    try:
        from browser_use.browser.watchdogs.local_browser_watchdog import LocalBrowserWatchdog
        import asyncio
        import subprocess
        import psutil
        
        # 保存原始的 _launch_browser 方法
        _original_launch_browser = LocalBrowserWatchdog._launch_browser
        
        async def _patched_launch_browser(self, max_retries: int = 3):
            """
            修复版的 _launch_browser 方法
            
            在 Windows 上使用 subprocess.Popen(shell=True) 启动浏览器，
            然后转换为与原方法相同的返回值格式。
            """
            import shutil
            
            profile = self.browser_session.browser_profile
            self._original_user_data_dir = str(profile.user_data_dir) if profile.user_data_dir else None
            self._temp_dirs_to_cleanup = []
            
            for attempt in range(max_retries):
                try:
                    # 获取浏览器路径
                    if profile.executable_path:
                        browser_path = profile.executable_path
                    else:
                        browser_path = self._find_installed_browser_path()
                        if not browser_path:
                            browser_path = await self._install_browser_with_playwright()
                    
                    if not browser_path:
                        raise RuntimeError('No local Chrome/Chromium install found')
                    
                    # 获取调试端口
                    debug_port = self._find_free_port()
                    
                    print(f'[LocalBrowserWatchdog-Patched] Launching with shell=True on Windows')
                    print(f'[LocalBrowserWatchdog-Patched] CDP port: {debug_port}')
                    print(f'[LocalBrowserWatchdog-Patched] Browser path: {browser_path}')
                    
                    # 检查是否有现有的 Edge 进程
                    try:
                        import psutil as ps
                        edge_procs = [p for p in ps.process_iter(['name']) if p.info['name'] and 'msedge' in p.info['name'].lower()]
                        if edge_procs:
                            print(f'[LocalBrowserWatchdog-Patched] WARNING: Found {len(edge_procs)} existing Edge processes!')
                            print(f'[LocalBrowserWatchdog-Patched] Killing existing Edge processes...')
                            for p in edge_procs:
                                try:
                                    p.kill()
                                except Exception:
                                    pass
                            await asyncio.sleep(3)  # 增加等待时间，确保进程完全退出
                            print(f'[LocalBrowserWatchdog-Patched] Killed existing Edge processes')
                    except Exception as e:
                        print(f'[LocalBrowserWatchdog-Patched] Warning: Failed to check/kill Edge processes: {e}')
                    
                    # 构建精简的命令参数（关键修复！）
                    # 不使用 profile.get_args()，而是手动构建必要参数
                    # 这样可以确保 --remote-debugging-port 参数正确传递
                    user_data_dir = str(profile.user_data_dir) if profile.user_data_dir else ''
                    profile_dir = profile.profile_directory or 'Default'
                    
                    cmd = (
                        f'"{browser_path}" '
                        f'--remote-debugging-port={debug_port} '  # CDP 端口放在前面！
                        f'--user-data-dir="{user_data_dir}" '
                        f'--profile-directory="{profile_dir}" '
                        f'--no-first-run '
                        f'--no-default-browser-check '
                        f'--disable-sync '
                        f'--disable-background-networking '
                        f'--disable-client-side-phishing-detection '
                        f'--disable-default-apps '
                        f'--disable-extensions '
                        f'--disable-hang-monitor '
                        f'--disable-popup-blocking '
                        f'--disable-prompt-on-repost '
                        f'--disable-translate '
                        f'--metrics-recording-only '
                        f'--safebrowsing-disable-auto-update '
                        f'--password-store=basic '
                        # 关键：禁止恢复之前的会话！
                        f'--disable-session-crashed-bubble '
                        f'--disable-infobars '
                        f'--no-restore-session-state '
                        f'--hide-crash-restore-bubble '
                    )
                    
                    if profile.headless:
                        cmd += '--headless=new '
                    
                    print(f'[LocalBrowserWatchdog-Patched] Command: {cmd}')
                    
                    # 使用 shell=True 启动（Windows 上能正确处理带空格的路径）
                    proc = subprocess.Popen(
                        cmd,
                        shell=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                    )
                    
                    print(f'[LocalBrowserWatchdog-Patched] Shell PID: {proc.pid}')
                    
                    # 等待浏览器启动
                    await asyncio.sleep(3)
                    
                    # 转换为 psutil.Process
                    process = psutil.Process(proc.pid)
                    
                    # 等待 CDP 就绪（复用 browser-use 的逻辑）
                    cdp_url = await self._wait_for_cdp_url(debug_port)
                    
                    self.logger.debug(f'[LocalBrowserWatchdog-Patched] CDP ready at {cdp_url}')
                    
                    # 清理未使用的临时目录
                    currently_used_dir = str(profile.user_data_dir)
                    unused_temp_dirs = [d for d in self._temp_dirs_to_cleanup if str(d) != currently_used_dir]
                    for tmp_dir in unused_temp_dirs:
                        try:
                            shutil.rmtree(tmp_dir, ignore_errors=True)
                        except Exception:
                            pass
                    
                    self._temp_dirs_to_cleanup = [d for d in self._temp_dirs_to_cleanup if str(d) == currently_used_dir]
                    
                    return process, cdp_url
                    
                except Exception as e:
                    self.logger.warning(f'[LocalBrowserWatchdog-Patched] Attempt {attempt + 1} failed: {e}')
                    if attempt == max_retries - 1:
                        raise
                    # 复用 browser-use 的重试逻辑（切换到临时目录）
                    await self._switch_to_temp_profile()
            
            raise RuntimeError('Failed to launch browser after all retries')
        
        # 替换方法
        LocalBrowserWatchdog._launch_browser = _patched_launch_browser
        
        print("[MonkeyPatches] Patch 0.5: fixed Windows subprocess path handling in LocalBrowserWatchdog._launch_browser")
    except Exception as e:
        print(f"[MonkeyPatches] Warning: failed to apply patch 0.5: {e}")


def _patch_disable_dvd_screensaver():
    """
    Monkey Patch 1: 禁用 about:blank DVD screensaver 动画
    
    browser-use 库会在空白页面显示一个 DVD logo 动画，
    这在自动化场景中是不必要的视觉干扰。
    """
    try:
        from browser_use.browser.watchdogs.aboutblank_watchdog import AboutBlankWatchdog
        
        async def _noop_show_dvd_screensaver(*args, **kwargs):
            pass
        
        AboutBlankWatchdog._show_dvd_screensaver_on_about_blank_tabs = _noop_show_dvd_screensaver
        AboutBlankWatchdog._show_dvd_screensaver_loading_animation_cdp = _noop_show_dvd_screensaver
        
        print("[MonkeyPatches] Patch 1: disabled DVD screensaver animation")
    except Exception as e:
        print(f"[MonkeyPatches] Warning: failed to apply patch 1: {e}")


def _patch_profile_copy_ignore_locked():
    """
    Monkey Patch 2: Profile 复制时跳过锁定文件
    
    当 Chrome 正在运行时，某些文件（如 Cookies）会被锁定，
    导致 profile 复制失败。这个补丁会跳过这些锁定的文件。
    """
    try:
        from browser_use.browser.profile import BrowserProfile as BrowserUseProfile
        
        def _copy_profile_ignore_locked(self) -> None:
            """Copy profile to temp directory, skipping locked files."""
            if self.user_data_dir is None:
                return
            
            user_data_str = str(self.user_data_dir)
            if 'browser-use-user-data-dir-' in user_data_str.lower():
                # Already using a temp directory
                return
            
            is_chrome = (
                'chrome' in user_data_str.lower()
                or 'chromium' in user_data_str.lower()
                or 'edge' in user_data_str.lower()
            )
            
            if not is_chrome:
                return
            
            temp_dir = tempfile.mkdtemp(prefix='browser-use-user-data-dir-')
            path_original_user_data = Path(self.user_data_dir)
            path_original_profile = path_original_user_data / self.profile_directory
            path_temp_profile = Path(temp_dir) / self.profile_directory
            
            if path_original_profile.exists():
                def ignore_locked_files(src, names):
                    """忽略可能被锁定的文件和不必要的大文件/目录"""
                    ignored = []
                    for name in names:
                        name_lower = name.lower()
                        # 跳过锁定文件
                        if name_lower in [
                            'cookies', 'cookies-journal',
                            'safe browsing cookies', 'safe browsing cookies-journal',
                            'lockfile', 'lock',
                        ]:
                            ignored.append(name)
                        # 跳过大型缓存目录（加快复制速度）
                        elif name_lower in [
                            'cache', 'code cache', 'gpucache', 'service worker',
                            'media cache', 'application cache',
                        ]:
                            ignored.append(name)
                        # 跳过历史记录（减少数据量）
                        elif name_lower in [
                            'history', 'history-journal',
                            'top sites', 'top sites-journal',
                            'visited links',
                        ]:
                            ignored.append(name)
                        # 跳过会话恢复（避免自动打开大量标签页）
                        elif name_lower in [
                            'sessions', 'session storage',
                            'current session', 'current tabs', 'last session', 'last tabs',
                        ]:
                            ignored.append(name)
                    return ignored
                
                try:
                    shutil.copytree(
                        path_original_profile, 
                        path_temp_profile,
                        ignore=ignore_locked_files,
                        ignore_dangling_symlinks=True,
                    )
                except shutil.Error as e:
                    print(f"[MonkeyPatches] Profile copy partial errors: {len(e.args[0])} files skipped")
                except Exception as e:
                    print(f"[MonkeyPatches] Profile copy error: {e}")
                    path_temp_profile.mkdir(parents=True, exist_ok=True)
                
                # 复制 Local State
                local_state_src = path_original_user_data / 'Local State'
                local_state_dst = Path(temp_dir) / 'Local State'
                if local_state_src.exists():
                    try:
                        shutil.copy(local_state_src, local_state_dst)
                    except Exception:
                        pass
                
                print(f"[MonkeyPatches] Copied profile to: {temp_dir}")
            else:
                Path(temp_dir).mkdir(parents=True, exist_ok=True)
                path_temp_profile.mkdir(parents=True, exist_ok=True)
                print(f"[MonkeyPatches] Created new profile in: {temp_dir}")
            
            self.user_data_dir = temp_dir
        
        BrowserUseProfile._copy_profile = _copy_profile_ignore_locked
        
        print("[MonkeyPatches] Patch 2: profile copy ignores locked files")
    except Exception as e:
        print(f"[MonkeyPatches] Warning: failed to apply patch 2: {e}")


def _patch_disable_auto_open_pages(use_proxy: bool = True):
    """
    Monkey Patch 3: 禁用 Chrome 自动打开页面 + 修复 Windows 参数解析 Bug
    
    Chrome 启动时会自动：
    1. 打开 accounts.google.com（账户管理页面）
    2. 恢复上次的标签页（Sessions）
    
    另外，browser-use 库的 --simulate-outdated-no-au 参数在 Windows 上有 bug：
    参数 '--simulate-outdated-no-au="Tue, 31 Dec 2099 23:59:59 GMT"' 
    会被 Windows 错误解析，导致 31, Dec, 23:59:59, GMT 被当作 URL 打开。
    
    这个补丁：
    1. 添加启动参数来禁用自动打开页面
    2. 过滤掉有问题的 simulate-outdated-no-au 参数
    
    Args:
        use_proxy: 是否使用系统代理
    """
    try:
        from browser_use.browser.profile import BrowserProfile as BrowserUseProfile
        import platform
        
        # 保存原始的 to_browser_config 方法
        _original_to_browser_config = BrowserUseProfile.to_browser_config
        
        def _to_browser_config_with_extra_args(self):
            """添加额外的启动参数，过滤有问题的参数"""
            config = _original_to_browser_config(self)
            
            # 获取现有的 args
            args = config.get('args', [])
            
            # 在 Windows 上过滤掉有问题的 simulate-outdated-no-au 参数
            # 这个参数的引号在 Windows 上解析有问题，会导致日期被当作 URL 打开
            if platform.system() == 'Windows':
                filtered_args = []
                for arg in args:
                    if 'simulate-outdated-no-au' in arg:
                        print(f"[MonkeyPatches] Filtering problematic arg: {arg[:50]}...")
                        continue
                    filtered_args.append(arg)
                args = filtered_args
            
            # 添加禁用自动打开页面的参数
            extra_args = [
                '--no-first-run',                    # 禁用首次运行体验
                '--no-default-browser-check',        # 禁用默认浏览器检查
                '--disable-features=Translate',      # 禁用翻译提示
                '--disable-sync',                    # 禁用同步（避免打开账户页面）
                '--disable-background-networking',   # 禁用后台网络请求
                '--disable-session-crashed-bubble',  # 禁用"Chrome未正确关闭"提示
                '--restore-last-session=false',      # 不恢复上次会话
                '--disable-restore-session-state',   # 禁用恢复会话状态
            ]
            
            # 如果不使用代理，添加禁用代理参数
            if not use_proxy:
                extra_args.append('--no-proxy-server')
            
            # 合并参数（去重）
            existing_args_set = set(args)
            for arg in extra_args:
                if arg not in existing_args_set:
                    args.append(arg)
            
            config['args'] = args
            return config
        
        # 替换方法
        BrowserUseProfile.to_browser_config = _to_browser_config_with_extra_args
        
        proxy_status = "enabled" if use_proxy else "disabled"
        print(f"[MonkeyPatches] Patch 3: disabled auto-open pages, filtered Windows-problematic args (proxy: {proxy_status})")
    except Exception as e:
        print(f"[MonkeyPatches] Warning: failed to apply patch 3: {e}")
