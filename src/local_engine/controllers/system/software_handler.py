r"""
已安装软件枚举（增强版）

数据来源：
1. HKLM\...\Uninstall         - 系统级安装（所有用户）
2. HKLM WOW6432Node\...       - 32 位程序在 64 位系统
3. HKCU\...\Uninstall         - 当前用户安装（如 VS Code user installer）
4. HKLM\...\App Paths         - 应用可执行路径索引（Win+R 能启动的那些）

合并去重后，尽量补全每条记录的 exe 路径，方便后续 launch。
"""
import logging
import os
import platform
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# 常见软件的别名 → App Paths 下的 exe basename（lower-case）
# 现代 Office (Click-to-Run / M365) 在 Uninstall 里只有套件级条目（如
# "Microsoft 365 企业应用版"），单独搜 "PowerPoint" / "Word" 会命中 0 个。
# 但 Win+R 是靠 HKLM\...\App Paths\POWERPNT.EXE 这种键启动的，所以我们
# 把常见软件名映射到对应的 App Paths basename 作为兜底。
_APP_ALIASES: Dict[str, List[str]] = {
    # Microsoft Office
    "powerpoint": ["powerpnt.exe"],
    "ppt":        ["powerpnt.exe"],
    "word":       ["winword.exe"],
    "excel":      ["excel.exe"],
    "outlook":    ["outlook.exe"],
    "onenote":    ["onenote.exe"],
    "access":     ["msaccess.exe"],
    "publisher":  ["mspub.exe"],
    "visio":      ["visio.exe"],
    "project":    ["winproj.exe"],
    # Browsers
    "edge":       ["msedge.exe"],
    "chrome":     ["chrome.exe"],
    "firefox":    ["firefox.exe"],
    # Dev / Productivity
    "vscode":     ["code.exe"],
    "vs code":    ["code.exe"],
    "code":       ["code.exe"],
    "cursor":     ["cursor.exe"],
    "teams":      ["ms-teams.exe", "teams.exe"],
    "onedrive":   ["onedrive.exe"],
    # Windows 内置
    "notepad":    ["notepad.exe"],
    "calc":       ["calc.exe"],
    "calculator": ["calc.exe"],
    "paint":      ["mspaint.exe"],
    "wordpad":    ["wordpad.exe"],
    "explorer":   ["explorer.exe"],
}


def _open_hkey(winreg_mod, root_name: str):
    """返回 winreg 的 HKEY 常量"""
    return getattr(winreg_mod, root_name)


def _read_value(winreg_mod, key, name: str) -> str:
    try:
        val = winreg_mod.QueryValueEx(key, name)[0]
        return val if isinstance(val, str) else str(val or "")
    except OSError:
        return ""


def _enum_uninstall_key(
    winreg_mod,
    root: str,
    subpath: str,
    flags: int,
    apps: List[Dict[str, str]],
    seen_keys: set,
) -> None:
    """枚举一个 Uninstall 注册表节点下的所有软件"""
    try:
        hkey = _open_hkey(winreg_mod, root)
        key = winreg_mod.OpenKey(hkey, subpath, 0, winreg_mod.KEY_READ | flags)
    except OSError:
        return

    try:
        subkey_count = winreg_mod.QueryInfoKey(key)[0]
        for i in range(subkey_count):
            try:
                subkey_name = winreg_mod.EnumKey(key, i)
                subkey = winreg_mod.OpenKey(key, subkey_name, 0, winreg_mod.KEY_READ | flags)
            except OSError:
                continue

            try:
                display_name = _read_value(winreg_mod, subkey, "DisplayName")
                if not display_name:
                    continue

                # 跳过系统更新、热修复
                if _read_value(winreg_mod, subkey, "SystemComponent") == "1":
                    continue
                if _read_value(winreg_mod, subkey, "ReleaseType") in ("Update", "Hotfix", "Security Update"):
                    continue

                dedup_key = display_name.lower()
                if dedup_key in seen_keys:
                    continue
                seen_keys.add(dedup_key)

                install_loc = _read_value(winreg_mod, subkey, "InstallLocation")
                display_icon = _read_value(winreg_mod, subkey, "DisplayIcon")

                # DisplayIcon 通常指向 exe（可能带 ",0" 后缀表示图标索引）
                exe_path = ""
                if display_icon:
                    candidate = display_icon.split(",")[0].strip().strip('"')
                    if candidate.lower().endswith(".exe") and os.path.exists(candidate):
                        exe_path = candidate

                apps.append({
                    "name": display_name,
                    "version": _read_value(winreg_mod, subkey, "DisplayVersion"),
                    "publisher": _read_value(winreg_mod, subkey, "Publisher"),
                    "install_location": install_loc,
                    "uninstall_string": _read_value(winreg_mod, subkey, "UninstallString"),
                    "exe_path": exe_path,
                    "source": f"{root}:{subpath.split(chr(92))[-1]}",
                })
            finally:
                winreg_mod.CloseKey(subkey)
    finally:
        winreg_mod.CloseKey(key)


def _enum_app_paths(winreg_mod) -> Dict[str, str]:
    """
    枚举 App Paths（Win+R 能识别的那些），返回 {exe_basename_lower: exe_full_path}
    """
    result: Dict[str, str] = {}
    paths = [
        ("HKEY_LOCAL_MACHINE", r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
        ("HKEY_LOCAL_MACHINE", r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths"),
        ("HKEY_CURRENT_USER", r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
    ]
    for root, sub in paths:
        try:
            hkey = _open_hkey(winreg_mod, root)
            key = winreg_mod.OpenKey(hkey, sub)
        except OSError:
            continue
        try:
            n = winreg_mod.QueryInfoKey(key)[0]
            for i in range(n):
                try:
                    exe_name = winreg_mod.EnumKey(key, i)
                    sub_k = winreg_mod.OpenKey(key, exe_name)
                    try:
                        # (Default) 值就是 exe 完整路径
                        default_val = _read_value(winreg_mod, sub_k, "")
                        if default_val:
                            exe_full = default_val.strip().strip('"')
                            result[exe_name.lower()] = exe_full
                    finally:
                        winreg_mod.CloseKey(sub_k)
                except OSError:
                    continue
        finally:
            winreg_mod.CloseKey(key)
    return result


class SoftwareHandler:
    """已安装软件枚举"""

    @staticmethod
    def list_installed(
        name_contains: Optional[str] = None,
        include_system_components: bool = False,
    ) -> Dict[str, Any]:
        """
        列出本机已安装软件（合并 HKLM + HKCU + App Paths）。

        Args:
            name_contains: 按软件名模糊匹配
            include_system_components: 是否包含系统组件（默认过滤）

        Returns:
            {"success": True, "software": [...], "count": N}
        """
        if platform.system() != "Windows":
            return {"success": False, "error": "Windows only", "software": [], "count": 0}

        try:
            import winreg
        except ImportError as e:
            return {"success": False, "error": f"winreg import failed: {e}", "software": [], "count": 0}

        apps: List[Dict[str, str]] = []
        seen_keys: set = set()

        # 1) HKLM 64-bit + 32-bit (WOW6432Node)
        _enum_uninstall_key(
            winreg, "HKEY_LOCAL_MACHINE",
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
            0, apps, seen_keys,
        )
        _enum_uninstall_key(
            winreg, "HKEY_LOCAL_MACHINE",
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
            0, apps, seen_keys,
        )
        # 2) HKCU (per-user install, 如 VS Code user installer)
        _enum_uninstall_key(
            winreg, "HKEY_CURRENT_USER",
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
            0, apps, seen_keys,
        )

        # 3) App Paths 补充 exe 路径
        app_paths = _enum_app_paths(winreg)

        # 4) 二次补全 exe：对于没有 exe_path 的记录，尝试从 App Paths 或 install_location 猜
        for item in apps:
            if item.get("exe_path"):
                continue
            # 猜 1：按软件名首词找 App Paths
            first_word = item["name"].split()[0].lower() if item["name"] else ""
            for basename, full in app_paths.items():
                if first_word and first_word in basename:
                    if os.path.exists(full):
                        item["exe_path"] = full
                        break
            # 猜 2：install_location 下找唯一的 .exe
            if not item.get("exe_path") and item.get("install_location"):
                loc = item["install_location"]
                if os.path.isdir(loc):
                    try:
                        exes = [f for f in os.listdir(loc) if f.lower().endswith(".exe")]
                        if len(exes) == 1:
                            item["exe_path"] = os.path.join(loc, exes[0])
                    except OSError:
                        pass

        # 过滤
        if name_contains:
            needle = name_contains.lower()
            apps = [a for a in apps if needle in a["name"].lower()]

        apps.sort(key=lambda x: x["name"].lower())

        return {
            "success": True,
            "software": apps,
            "count": len(apps),
            "app_paths_count": len(app_paths),
        }

    @staticmethod
    def find_exe(name_contains: str) -> Dict[str, Any]:
        """
        按软件名模糊匹配，返回所有候选 exe 路径（可启动的）。
        AI 用这个来决定 launch 哪个 exe。

        候选来源：
          A) App Paths（Win+R 能识别的 exe），按别名表 + basename 模糊匹配。
             这是最可靠的"这个名字能真正启动"的来源。
          B) Uninstall 注册表里的已安装软件（有 exe_path 的）。注意这里的
             exe_path 常常是 DisplayIcon 指向的 setup/其它 exe，**不一定**
             是用户想要的那个应用主 exe。

        排序：App Paths 来源优先（放在前面），Uninstall 来源在后。
        """
        result = SoftwareHandler.list_installed(name_contains=name_contains)
        if not result.get("success"):
            return result

        # A) App Paths 候选（优先，真正能用的 exe）
        app_path_hits = SoftwareHandler._find_in_app_paths(name_contains)
        seen_exes = {c["exe_path"].lower() for c in app_path_hits if c.get("exe_path")}

        # B) Uninstall 候选（补充）
        uninstall_hits: List[Dict[str, str]] = []
        for s in result["software"]:
            exe = s.get("exe_path") or ""
            if not exe:
                continue
            key = exe.lower()
            if key in seen_exes:
                continue
            seen_exes.add(key)
            uninstall_hits.append({
                "name": s["name"],
                "exe_path": exe,
                "version": s.get("version", ""),
                "source": "uninstall",
            })

        candidates = app_path_hits + uninstall_hits
        return {"success": True, "candidates": candidates, "count": len(candidates)}

    @staticmethod
    def _find_in_app_paths(name_contains: str) -> List[Dict[str, str]]:
        """
        在 HKLM/HKCU App Paths 下按别名表 + basename 模糊匹配查找可启动 exe。
        仅在 Windows 上有效。
        """
        if platform.system() != "Windows":
            return []
        try:
            import winreg
        except ImportError:
            return []

        app_paths = _enum_app_paths(winreg)
        if not app_paths:
            return []

        query = (name_contains or "").strip().lower()
        if not query:
            return []

        hits: List[Dict[str, str]] = []
        seen_exes: set = set()

        def _push(basename: str, full: str) -> None:
            key = full.lower()
            if key in seen_exes:
                return
            if not os.path.exists(full):
                return
            seen_exes.add(key)
            hits.append({
                "name": os.path.splitext(basename)[0],
                "exe_path": full,
                "version": "",
                "source": "app_paths",
            })

        # 1) 预定义别名
        for basename in _APP_ALIASES.get(query, []):
            full = app_paths.get(basename.lower())
            if full:
                _push(basename, full)

        # 2) basename 子串模糊匹配（去掉空格与 .exe 后对比）
        query_norm = query.replace(".exe", "").replace(" ", "")
        if query_norm:
            for basename, full in app_paths.items():
                base_norm = basename.lower().replace(".exe", "")
                if query_norm in base_norm:
                    _push(basename, full)

        return hits
