"""
进程枚举（基于 psutil）

用途：让 AI 知道"后台跑着什么"。对于有窗口的应用，window_handler 能给出更细的文档级信息；
process_handler 主要覆盖无窗口 / 托盘 / 后台服务类进程。
"""
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    psutil = None  # type: ignore[assignment]
    logger.warning("psutil not available, ProcessHandler disabled")


# 默认过滤掉的系统/僵尸进程名（无实际用户意义）
_SYSTEM_NOISE = {
    "System Idle Process",
    "System",
    "Registry",
    "Secure System",
    "Memory Compression",
    "smss.exe",
    "csrss.exe",
    "wininit.exe",
    "services.exe",
    "lsass.exe",
    "winlogon.exe",
    "fontdrvhost.exe",
    "dwm.exe",
    "svchost.exe",
}


class ProcessHandler:
    """进程枚举"""

    @staticmethod
    def list_processes(
        name_contains: Optional[str] = None,
        include_system: bool = False,
        include_metrics: bool = False,
    ) -> Dict[str, Any]:
        """
        列出运行中的进程。

        Args:
            name_contains: 按名字（exe 名）模糊匹配，大小写不敏感
            include_system: 是否包含系统噪音进程（svchost / smss 等），默认 False
            include_metrics: 是否采集 CPU/内存（有额外开销），默认 False

        Returns:
            {"success": True, "processes": [...], "count": N}
        """
        if not PSUTIL_AVAILABLE:
            return {"success": False, "error": "psutil not available", "processes": [], "count": 0}

        needle = name_contains.lower() if name_contains else None
        processes: List[Dict[str, Any]] = []

        # 这些属性 psutil 会一次性采集，比每个属性单独调开销低
        attrs = ["pid", "name", "exe", "username", "create_time"]
        if include_metrics:
            attrs += ["cpu_percent", "memory_info"]

        for proc in psutil.process_iter(attrs=attrs, ad_value=None):
            try:
                info = proc.info
                name = info.get("name") or ""

                if not include_system and name in _SYSTEM_NOISE:
                    continue
                if needle and needle not in name.lower():
                    continue

                item: Dict[str, Any] = {
                    "pid": info.get("pid"),
                    "name": name,
                    "exe": info.get("exe") or "",
                    "username": info.get("username") or "",
                    "create_time": info.get("create_time"),
                }

                if include_metrics:
                    mem = info.get("memory_info")
                    item["cpu_percent"] = info.get("cpu_percent") or 0.0
                    item["memory_mb"] = round(mem.rss / 1024 / 1024, 1) if mem else 0.0

                processes.append(item)
            except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
                continue

        processes.sort(key=lambda p: p["name"].lower())
        return {"success": True, "processes": processes, "count": len(processes)}

    @staticmethod
    def find_by_name(name: str, exact: bool = False) -> Dict[str, Any]:
        """
        按名字查找进程。

        Args:
            name: 进程 exe 名，如 "POWERPNT.EXE"
            exact: True=精确匹配（忽略大小写），False=包含匹配

        Returns:
            {"success": True, "processes": [...], "count": N}
        """
        if not PSUTIL_AVAILABLE:
            return {"success": False, "error": "psutil not available", "processes": [], "count": 0}

        if not name:
            return {"success": False, "error": "name required", "processes": [], "count": 0}

        needle = name.lower()
        matched: List[Dict[str, Any]] = []

        for proc in psutil.process_iter(attrs=["pid", "name", "exe", "create_time"], ad_value=None):
            try:
                info = proc.info
                pname = (info.get("name") or "").lower()
                hit = (pname == needle) if exact else (needle in pname)
                if hit:
                    matched.append({
                        "pid": info.get("pid"),
                        "name": info.get("name"),
                        "exe": info.get("exe") or "",
                        "create_time": info.get("create_time"),
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
                continue

        return {"success": True, "processes": matched, "count": len(matched)}

    @staticmethod
    def get_process_info(pid: int) -> Dict[str, Any]:
        """按 PID 取单个进程详情"""
        if not PSUTIL_AVAILABLE:
            return {"success": False, "error": "psutil not available"}

        try:
            proc = psutil.Process(pid)
            with proc.oneshot():
                mem = proc.memory_info()
                return {
                    "success": True,
                    "process": {
                        "pid": proc.pid,
                        "name": proc.name(),
                        "exe": proc.exe() if proc.exe() else "",
                        "cmdline": proc.cmdline(),
                        "username": proc.username(),
                        "create_time": proc.create_time(),
                        "cpu_percent": proc.cpu_percent(interval=None),
                        "memory_mb": round(mem.rss / 1024 / 1024, 1),
                        "status": proc.status(),
                        "num_threads": proc.num_threads(),
                    },
                }
        except psutil.NoSuchProcess:
            return {"success": False, "error": f"process {pid} not found"}
        except psutil.AccessDenied:
            return {"success": False, "error": f"access denied to process {pid}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
