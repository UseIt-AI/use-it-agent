"""
Chrome 快捷方式工具
用于安全地创建/修改浏览器快捷方式，以启用 --remote-debugging-port。

支持修改的快捷方式位置：
- 桌面
- 开始菜单
- 任务栏
"""

import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import subprocess
import re


def get_chrome_shortcut_paths() -> Dict[str, List[Path]]:
    """
    获取所有 Chrome 快捷方式路径
    
    Returns:
        {
            "desktop": [Path, ...],
            "start_menu": [Path, ...],
            "taskbar": [Path, ...],
        }
    """
    shortcuts = {
        "desktop": [],
        "start_menu": [],
        "taskbar": [],
    }
    
    if sys.platform != "win32":
        return shortcuts
    
    # 用户目录
    user_home = Path(os.path.expanduser("~"))
    
    # 桌面
    desktop_paths = [
        user_home / "Desktop",
        user_home / "桌面",  # 中文系统
        Path(os.path.expandvars(r"%PUBLIC%\Desktop")),  # 公共桌面
    ]
    
    # 开始菜单
    start_menu_paths = [
        user_home / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        Path(os.path.expandvars(r"%ProgramData%\Microsoft\Windows\Start Menu\Programs")),
    ]
    
    # 任务栏
    taskbar_paths = [
        user_home / "AppData" / "Roaming" / "Microsoft" / "Internet Explorer" / "Quick Launch" / "User Pinned" / "TaskBar",
    ]
    
    # 搜索 Chrome 快捷方式
    chrome_names = [
        "Google Chrome.lnk",
        "Chrome.lnk",
        "谷歌浏览器.lnk",
        "Microsoft Edge.lnk",
        "Edge.lnk",
        "微软 Edge.lnk",
        "微软浏览器.lnk",
    ]
    
    for path in desktop_paths:
        if path.exists():
            for name in chrome_names:
                lnk = path / name
                if lnk.exists():
                    shortcuts["desktop"].append(lnk)
    
    for path in start_menu_paths:
        if path.exists():
            # 直接在目录下
            for name in chrome_names:
                lnk = path / name
                if lnk.exists():
                    shortcuts["start_menu"].append(lnk)
            # 在 Google Chrome 子目录下
            chrome_dir = path / "Google Chrome"
            if chrome_dir.exists():
                for name in chrome_names:
                    lnk = chrome_dir / name
                    if lnk.exists():
                        shortcuts["start_menu"].append(lnk)
    
    for path in taskbar_paths:
        if path.exists():
            for name in chrome_names:
                lnk = path / name
                if lnk.exists():
                    shortcuts["taskbar"].append(lnk)
    
    return shortcuts


def read_shortcut(lnk_path: Path) -> Optional[Dict[str, str]]:
    """
    读取快捷方式信息
    
    Returns:
        {
            "target": "C:\\...\\chrome.exe",
            "arguments": "--some-arg",
            "working_dir": "C:\\...",
            "icon_location": "C:\\...\\chrome.exe,0",
            "description": "...",
        }
    """
    if sys.platform != "win32":
        return None
    
    try:
        # 使用 PowerShell 读取快捷方式
        ps_script = f'''
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut("{lnk_path}")
Write-Output "TARGET:$($shortcut.TargetPath)"
Write-Output "ARGS:$($shortcut.Arguments)"
Write-Output "WORKDIR:$($shortcut.WorkingDirectory)"
Write-Output "ICON:$($shortcut.IconLocation)"
Write-Output "DESC:$($shortcut.Description)"
'''
        result = subprocess.run(
            ["powershell", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        if result.returncode != 0:
            return None
        
        info = {}
        for line in result.stdout.strip().split("\n"):
            if line.startswith("TARGET:"):
                info["target"] = line[7:].strip()
            elif line.startswith("ARGS:"):
                info["arguments"] = line[5:].strip()
            elif line.startswith("WORKDIR:"):
                info["working_dir"] = line[8:].strip()
            elif line.startswith("ICON:"):
                info["icon_location"] = line[5:].strip()
            elif line.startswith("DESC:"):
                info["description"] = line[5:].strip()
        
        return info
    except Exception as e:
        print(f"Error reading shortcut {lnk_path}: {e}")
        return None


def _ps_escape(s: str) -> str:
    # Escape for a double-quoted PowerShell string literal
    # https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_quoting_rules
    return s.replace('"', '`"')


def write_shortcut(
    lnk_path: Path,
    target: str,
    arguments: str,
    working_dir: str = "",
    icon_location: str = "",
    description: str = "",
) -> Tuple[bool, str]:
    """
    创建/覆盖写入 .lnk 快捷方式（Windows）。
    """
    if sys.platform != "win32":
        return False, "Only supported on Windows"

    try:
        ps_script = f'''
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut("{lnk_path}")
$shortcut.TargetPath = "{_ps_escape(target)}"
$shortcut.Arguments = "{_ps_escape(arguments)}"
$shortcut.WorkingDirectory = "{_ps_escape(working_dir)}"
if ("{_ps_escape(icon_location)}" -ne "") {{ $shortcut.IconLocation = "{_ps_escape(icon_location)}" }}
if ("{_ps_escape(description)}" -ne "") {{ $shortcut.Description = "{_ps_escape(description)}" }}
$shortcut.Save()
'''
        result = subprocess.run(
            ["powershell", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return False, f"PowerShell error: {result.stderr}"
        return True, f"Written: {lnk_path}"
    except Exception as e:
        return False, f"Error: {e}"


def _remove_flag(args: str, flag: str) -> str:
    # Remove: --flag=value  OR  --flag value  OR  --flag (bare)
    pattern = rf'(?:^|\s){re.escape(flag)}(?:=(?:"[^"]*"|\'[^\']*\'|\S+)|\s+(?:"[^"]*"|\'[^\']*\'|\S+))?'
    return re.sub(pattern, ' ', args).strip()


def _get_flag_value(args: str, flag: str) -> Optional[str]:
    # Match: --flag=value OR --flag "value" OR --flag 'value' OR --flag value
    pattern = rf'(?:^|\s){re.escape(flag)}(?:=|\s+)(?:"([^"]*)"|\'([^\']*)\'|(\S+))'
    m = re.search(pattern, args)
    if not m:
        return None
    return next((g for g in m.groups() if g is not None), None)


def _build_debug_args(existing_args: str, port: int, address: str = "127.0.0.1") -> str:
    args = existing_args or ""
    args = _remove_flag(args, "--remote-debugging-port")
    args = _remove_flag(args, "--remote-debugging-address")
    # Prepend for readability and to minimize surprises.
    prefix = f'--remote-debugging-address={address} --remote-debugging-port={port}'.strip()
    return f"{prefix} {args}".strip()


def _is_legacy_debug_data_dir(user_data_dir: Optional[str]) -> bool:
    if not user_data_dir:
        return False
    normalized = user_data_dir.strip().strip('"').strip("'")
    # Only treat exact legacy dirs as "ours" (safe to auto-repair)
    legacy_chrome = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Debug Data")
    legacy_edge = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Debug Data")
    return os.path.normcase(normalized) in {os.path.normcase(legacy_chrome), os.path.normcase(legacy_edge)}


def modify_shortcut(lnk_path: Path, add_args: str, remove_args: Optional[List[str]] = None) -> Tuple[bool, str]:
    """
    修改快捷方式参数
    
    Args:
        lnk_path: 快捷方式路径
        add_args: 要添加的参数
        remove_args: 要移除的参数列表
    
    Returns:
        (success, message)
    """
    if sys.platform != "win32":
        return False, "Only supported on Windows"
    
    try:
        # 先读取当前参数
        info = read_shortcut(lnk_path)
        if not info:
            return False, f"Cannot read shortcut: {lnk_path}"
        
        current_args = info.get("arguments", "")
        
        # 移除指定参数（按 flag 名称移除）
        if remove_args:
            for arg in remove_args:
                current_args = _remove_flag(current_args, arg)
        
        # 检查是否已经有这个参数
        if add_args in current_args:
            return True, f"Already has {add_args}"
        
        # 添加新参数
        new_args = f"{current_args} {add_args}".strip()
        
        # 使用 PowerShell 修改快捷方式
        ps_script = f'''
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut("{lnk_path}")
$shortcut.Arguments = "{_ps_escape(new_args)}"
$shortcut.Save()
'''
        result = subprocess.run(
            ["powershell", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        if result.returncode != 0:
            return False, f"PowerShell error: {result.stderr}"
        
        return True, f"Modified: {lnk_path}"
    except Exception as e:
        return False, f"Error: {e}"


USEIT_DEBUG_SHORTCUT_SUFFIX = " (UseIt Debug)"
USEIT_DEBUG_SHORTCUT_DESC = "UseIt Debug Shortcut"


def enable_remote_debugging(
    port: int = 9222,
    mode: str = "copy",
    use_separate_profile: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    启用远程调试。

    ✅ 默认模式为 **copy**：不修改用户原快捷方式，只创建一个 UseIt 专用调试快捷方式（继承用户原 Profile）。
    ⚠️ in_place 模式会就地修改用户原快捷方式（仍然不更改 Profile，只增量加 remote debugging 参数）。

    Args:
        port: 调试端口，默认 9222
        mode: "copy" | "in_place"
        use_separate_profile: 兼容旧参数（已废弃）。传入不会再创建 Debug Data Profile。
    
    Returns:
        {
            "success": bool,
            "created": [...],          # copy 模式创建的新快捷方式
            "modified": [...],         # in_place 模式修改的快捷方式
            "failed": [...],
            "already_enabled": [...],  # 目标快捷方式已包含 remote debugging 参数
            "repaired_legacy": [...],  # 自动修复旧版写入的 Debug Data
            "warnings": [...],
        }
    """
    result = {
        "success": True,
        "created": [],
        "modified": [],
        "failed": [],
        "already_enabled": [],
        "repaired_legacy": [],
        "warnings": [],
        "not_found": [],
    }
    
    mode = (mode or "copy").strip().lower()
    if mode not in {"copy", "in_place"}:
        result["success"] = False
        result["failed"].append({"message": f"Invalid mode: {mode}"})
        return result

    if use_separate_profile is not None:
        result["warnings"].append(
            "Deprecated parameter 'use_separate_profile' was provided and is ignored. "
            "UseIt will no longer create a separate Debug Data profile."
        )

    shortcuts = get_chrome_shortcut_paths()
    
    # 检查是否找到任何快捷方式
    total = sum(len(v) for v in shortcuts.values())
    if total == 0:
        result["success"] = False
        result["not_found"] = ["No Chrome shortcuts found"]
        return result
    
    for location, paths in shortcuts.items():
        for lnk_path in paths:
            # 先读取当前快捷方式
            info = read_shortcut(lnk_path)
            if not info:
                result["failed"].append({
                    "location": location,
                    "path": str(lnk_path),
                    "message": "Cannot read shortcut",
                })
                continue
            
            target = info.get("target", "").lower()
            current_args = info.get("arguments", "")
            
            # 只处理 Chrome / Edge
            if not ("chrome" in target or "edge" in target or "msedge" in target):
                result["failed"].append({
                    "location": location,
                    "path": str(lnk_path),
                    "message": f"Unknown browser target: {target}",
                })
                continue

            # 旧版遗留修复：如果发现 user-data-dir 指向我们曾经写入的 Debug Data，则自动回滚该部分
            user_data_dir = _get_flag_value(current_args, "--user-data-dir")
            if _is_legacy_debug_data_dir(user_data_dir):
                repaired_args = current_args
                repaired_args = _remove_flag(repaired_args, "--user-data-dir")
                repaired_args = _remove_flag(repaired_args, "--remote-debugging-port")
                repaired_args = _remove_flag(repaired_args, "--remote-debugging-address")
                if repaired_args != current_args:
                    ok, msg = write_shortcut(
                        lnk_path=lnk_path,
                        target=info.get("target", ""),
                        arguments=repaired_args,
                        working_dir=info.get("working_dir", ""),
                        icon_location=info.get("icon_location", ""),
                        description=info.get("description", ""),
                    )
                    if ok:
                        result["repaired_legacy"].append({
                            "location": location,
                            "path": str(lnk_path),
                            "message": "Repaired legacy Debug Data user-data-dir injection",
                        })
                        current_args = repaired_args
                    else:
                        result["warnings"].append(f"Failed to repair legacy shortcut {lnk_path}: {msg}")

            if mode == "copy":
                # 创建专用调试快捷方式，不修改用户原快捷方式参数
                src_stem = lnk_path.stem
                if src_stem.endswith(USEIT_DEBUG_SHORTCUT_SUFFIX):
                    # 避免递归创建
                    continue
                debug_lnk = lnk_path.with_name(f"{src_stem}{USEIT_DEBUG_SHORTCUT_SUFFIX}.lnk")

                new_args = _build_debug_args(current_args, port=port)
                existing_debug_info = read_shortcut(debug_lnk) if debug_lnk.exists() else None
                has_debug = "--remote-debugging-port" in (existing_debug_info.get("arguments", "") if existing_debug_info else "")
                if debug_lnk.exists() and has_debug:
                    result["already_enabled"].append({
                        "location": location,
                        "path": str(debug_lnk),
                        "message": "UseIt debug shortcut already exists",
                    })
                    continue

                ok, msg = write_shortcut(
                    lnk_path=debug_lnk,
                    target=info.get("target", ""),
                    arguments=new_args,
                    working_dir=info.get("working_dir", ""),
                    icon_location=info.get("icon_location", ""),
                    description=USEIT_DEBUG_SHORTCUT_DESC,
                )
                if ok:
                    result["created"].append({
                        "location": location,
                        "path": str(debug_lnk),
                        "message": f"Created UseIt debug shortcut with --remote-debugging-port={port}",
                        "new_args": new_args,
                    })
                else:
                    result["failed"].append({
                        "location": location,
                        "path": str(debug_lnk),
                        "message": msg,
                    })
                    result["success"] = False
            else:
                # in_place：就地修改，只增量添加 remote debugging 参数，不修改 profile / user-data-dir
                if f"--remote-debugging-port={port}" in current_args or re.search(r'--remote-debugging-port[=\s]'+re.escape(str(port)), current_args):
                    result["already_enabled"].append({
                        "location": location,
                        "path": str(lnk_path),
                        "message": f"Already has --remote-debugging-port={port}",
                    })
                    continue

                new_args = _build_debug_args(current_args, port=port)
                ok, msg = write_shortcut(
                    lnk_path=lnk_path,
                    target=info.get("target", ""),
                    arguments=new_args,
                    working_dir=info.get("working_dir", ""),
                    icon_location=info.get("icon_location", ""),
                    description=info.get("description", ""),
                )
                if ok:
                    result["modified"].append({
                        "location": location,
                        "path": str(lnk_path),
                        "message": f"Added --remote-debugging-port={port} (in_place)",
                        "new_args": new_args,
                    })
                else:
                    result["failed"].append({
                        "location": location,
                        "path": str(lnk_path),
                        "message": msg,
                    })
                    result["success"] = False
    
    return result


def disable_remote_debugging(mode: str = "copy") -> Dict[str, Any]:
    """
    禁用远程调试。

    - copy（默认）：删除 UseIt 创建的调试快捷方式，不触碰用户原快捷方式
    - in_place：从用户原快捷方式移除 remote debugging 参数（不会修改 profile / user-data-dir）
    """
    result = {
        "success": True,
        "deleted": [],
        "modified": [],
        "failed": [],
        "not_found": [],
    }
    
    mode = (mode or "copy").strip().lower()
    if mode not in {"copy", "in_place"}:
        result["success"] = False
        result["failed"].append({"message": f"Invalid mode: {mode}"})
        return result

    shortcuts = get_chrome_shortcut_paths()
    
    total = sum(len(v) for v in shortcuts.values())
    if total == 0:
        result["success"] = False
        result["not_found"] = ["No Chrome shortcuts found"]
        return result
    
    for location, paths in shortcuts.items():
        for lnk_path in paths:
            if mode == "copy":
                # 删除我们创建的 UseIt Debug 快捷方式（同目录同名后缀）
                debug_lnk = lnk_path.with_name(f"{lnk_path.stem}{USEIT_DEBUG_SHORTCUT_SUFFIX}.lnk")
                if debug_lnk.exists():
                    try:
                        info = read_shortcut(debug_lnk)
                        # 双保险：需要 Description 标记 或 名字匹配
                        if info and info.get("description") == USEIT_DEBUG_SHORTCUT_DESC:
                            debug_lnk.unlink()
                            result["deleted"].append({
                                "location": location,
                                "path": str(debug_lnk),
                                "message": "Deleted UseIt debug shortcut",
                            })
                    except Exception as e:
                        result["failed"].append({
                            "location": location,
                            "path": str(debug_lnk),
                            "message": str(e),
                        })
                        result["success"] = False
                continue

            # 读取当前参数
            info = read_shortcut(lnk_path)
            if not info:
                result["failed"].append({
                    "location": location,
                    "path": str(lnk_path),
                    "message": "Cannot read shortcut",
                })
                continue
            
            current_args = info.get("arguments", "")
            
            # 检查是否有需要移除的参数
            if "--remote-debugging-port" not in current_args and "--remote-debugging-address" not in current_args:
                continue  # 不需要修改
            
            # 移除参数
            new_args = current_args
            new_args = _remove_flag(new_args, "--remote-debugging-port")
            new_args = _remove_flag(new_args, "--remote-debugging-address")

            ok, msg = write_shortcut(
                lnk_path=lnk_path,
                target=info.get("target", ""),
                arguments=new_args,
                working_dir=info.get("working_dir", ""),
                icon_location=info.get("icon_location", ""),
                description=info.get("description", ""),
            )

            if ok:
                result["modified"].append({
                    "location": location,
                    "path": str(lnk_path),
                    "message": "Removed remote debugging flags (in_place)",
                })
            else:
                result["failed"].append({
                    "location": location,
                    "path": str(lnk_path),
                    "message": msg,
                })
                result["success"] = False
    
    return result


def get_shortcuts_status() -> Dict[str, Any]:
    """
    获取所有 Chrome 快捷方式的状态
    
    Returns:
        {
            "shortcuts": [
                {
                    "location": "desktop",
                    "path": "...",
                    "target": "...",
                    "arguments": "...",
                    "has_remote_debugging": bool,
                    "port": int or None,
                    "is_useit_debug": bool,
                },
                ...
            ]
        }
    """
    result = {
        "shortcuts": [],
    }
    
    shortcuts = get_chrome_shortcut_paths()
    
    for location, paths in shortcuts.items():
        for lnk_path in paths:
            info = read_shortcut(lnk_path)
            
            item = {
                "location": location,
                "path": str(lnk_path),
                "target": info.get("target", "") if info else "",
                "arguments": info.get("arguments", "") if info else "",
                "has_remote_debugging": False,
                "port": None,
                "is_useit_debug": False,
            }
            
            if info and info.get("arguments"):
                args = info["arguments"]
                if "--remote-debugging-port" in args:
                    item["has_remote_debugging"] = True
                    # 提取端口号
                    match = re.search(r'--remote-debugging-port[=\s](\d+)', args)
                    if match:
                        item["port"] = int(match.group(1))
                if info.get("description") == USEIT_DEBUG_SHORTCUT_DESC or lnk_path.stem.endswith(USEIT_DEBUG_SHORTCUT_SUFFIX):
                    item["is_useit_debug"] = True
            
            result["shortcuts"].append(item)
    
    return result
