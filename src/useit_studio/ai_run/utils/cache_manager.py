"""
本地缓存清理管理器

管理 .cache 目录的磁盘空间，防止无限增长。
支持基于 LRU（最近最少使用）和 TTL（最大存活时间）的自动清理。

所有缓存文件均可从 S3 重新下载，清理是安全的。

清理策略（按优先级）:
    1. TTL 过期: 超过 max_age_hours 未访问的文件直接删除
    2. 容量上限: 总大小超过 max_size_gb 时，按 LRU 淘汰最旧文件

配置（环境变量）:
    CACHE_MAX_SIZE_GB        总缓存上限（GB），默认 5
    CACHE_MAX_AGE_HOURS      文件最大存活时间（小时），默认 168（7天）
    CACHE_CLEANUP_INTERVAL   清理间隔（秒），默认 3600（1小时）
    CACHE_ROOT_DIR           缓存根目录，默认 ".cache"
"""

import os
import time
import shutil
import threading
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)


@dataclass
class CacheConfig:
    root_dir: str = ".cache"
    max_size_gb: float = 5.0
    max_age_hours: float = 168.0  # 7 days
    cleanup_interval_seconds: int = 3600  # 1 hour
    subdirs: List[str] = field(default_factory=lambda: ["s3_files", "s3_skills"])

    @classmethod
    def from_env(cls) -> "CacheConfig":
        return cls(
            root_dir=os.getenv("CACHE_ROOT_DIR", ".cache"),
            max_size_gb=float(os.getenv("CACHE_MAX_SIZE_GB", "5")),
            max_age_hours=float(os.getenv("CACHE_MAX_AGE_HOURS", "168")),
            cleanup_interval_seconds=int(os.getenv("CACHE_CLEANUP_INTERVAL", "3600")),
        )


@dataclass
class _FileEntry:
    path: str
    size: int
    last_access: float


class CacheManager:
    """
    本地磁盘缓存管理器。

    在后台线程中定期扫描缓存目录，按 TTL 和 LRU 策略清理文件。
    """

    def __init__(self, config: Optional[CacheConfig] = None):
        self.config = config or CacheConfig.from_env()
        self._lock = threading.Lock()
        self._cleanup_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self._max_size_bytes = int(self.config.max_size_gb * 1024 * 1024 * 1024)
        self._max_age_seconds = self.config.max_age_hours * 3600

        logger.info(
            "[CacheManager] Initialized: root=%s, max_size=%.1fGB, "
            "max_age=%.0fh, interval=%ds",
            self.config.root_dir,
            self.config.max_size_gb,
            self.config.max_age_hours,
            self.config.cleanup_interval_seconds,
        )

    # ------------------------------------------------------------------ #
    # Lifecycle                                                            #
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        """启动后台清理线程"""
        if self._cleanup_thread is not None and self._cleanup_thread.is_alive():
            return

        self._stop_event.clear()

        def _loop():
            self._run_cleanup()
            while not self._stop_event.wait(self.config.cleanup_interval_seconds):
                self._run_cleanup()

        self._cleanup_thread = threading.Thread(
            target=_loop, daemon=True, name="cache-cleaner"
        )
        self._cleanup_thread.start()
        logger.info("[CacheManager] Background cleanup thread started")

    def stop(self) -> None:
        """停止后台清理线程"""
        self._stop_event.set()
        if self._cleanup_thread is not None:
            self._cleanup_thread.join(timeout=5)
            self._cleanup_thread = None
        logger.info("[CacheManager] Background cleanup thread stopped")

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def touch(self, path: str) -> None:
        """标记文件/目录为最近使用（更新 atime/mtime）"""
        try:
            p = Path(path)
            if p.exists():
                now = time.time()
                os.utime(str(p), (now, now))
        except OSError:
            pass

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        entries = self._scan_entries()
        total_size = sum(e.size for e in entries)
        return {
            "root_dir": os.path.abspath(self.config.root_dir),
            "total_files": len(entries),
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "max_size_mb": round(self._max_size_bytes / (1024 * 1024), 2),
            "max_age_hours": self.config.max_age_hours,
            "cleanup_interval_seconds": self.config.cleanup_interval_seconds,
        }

    def run_cleanup_now(self) -> Dict[str, Any]:
        """手动触发一次清理，返回清理结果"""
        return self._run_cleanup()

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _scan_entries(self) -> List[_FileEntry]:
        """扫描所有缓存文件"""
        entries: List[_FileEntry] = []
        root = Path(self.config.root_dir)

        for subdir_name in self.config.subdirs:
            subdir = root / subdir_name
            if not subdir.is_dir():
                continue
            for file_path in subdir.rglob("*"):
                if not file_path.is_file():
                    continue
                try:
                    stat = file_path.stat()
                    last_access = max(stat.st_atime, stat.st_mtime)
                    entries.append(
                        _FileEntry(
                            path=str(file_path),
                            size=stat.st_size,
                            last_access=last_access,
                        )
                    )
                except OSError:
                    continue

        return entries

    def _run_cleanup(self) -> Dict[str, Any]:
        """执行一轮清理"""
        with self._lock:
            result = {"expired_removed": 0, "lru_removed": 0, "bytes_freed": 0}
            now = time.time()

            entries = self._scan_entries()
            if not entries:
                return result

            total_size = sum(e.size for e in entries)
            logger.info(
                "[CacheManager] Scan complete: %d files, %.1f MB",
                len(entries),
                total_size / (1024 * 1024),
            )

            # Phase 1: TTL – 删除过期文件
            alive: List[_FileEntry] = []
            for entry in entries:
                age = now - entry.last_access
                if age > self._max_age_seconds:
                    if self._remove_file(entry.path):
                        result["expired_removed"] += 1
                        result["bytes_freed"] += entry.size
                        total_size -= entry.size
                else:
                    alive.append(entry)

            # Phase 2: LRU – 如果仍超容量，按最近访问时间升序淘汰
            if total_size > self._max_size_bytes:
                alive.sort(key=lambda e: e.last_access)
                for entry in alive:
                    if total_size <= self._max_size_bytes:
                        break
                    if self._remove_file(entry.path):
                        result["lru_removed"] += 1
                        result["bytes_freed"] += entry.size
                        total_size -= entry.size

            # 清理空目录
            self._remove_empty_dirs()

            freed_mb = result["bytes_freed"] / (1024 * 1024)
            total_removed = result["expired_removed"] + result["lru_removed"]
            if total_removed > 0:
                logger.info(
                    "[CacheManager] Cleanup done: removed %d files "
                    "(expired=%d, lru=%d), freed %.1f MB",
                    total_removed,
                    result["expired_removed"],
                    result["lru_removed"],
                    freed_mb,
                )
            else:
                logger.debug("[CacheManager] Cleanup done: nothing to remove")

            return result

    def _remove_file(self, path: str) -> bool:
        try:
            os.remove(path)
            logger.debug("[CacheManager] Removed: %s", path)
            return True
        except OSError as e:
            logger.warning("[CacheManager] Failed to remove %s: %s", path, e)
            return False

    def _remove_empty_dirs(self) -> None:
        """自底向上清理空目录"""
        root = Path(self.config.root_dir)
        for subdir_name in self.config.subdirs:
            subdir = root / subdir_name
            if not subdir.is_dir():
                continue
            # 反向遍历使得先处理深层目录
            for dirpath in sorted(subdir.rglob("*"), reverse=True):
                if dirpath.is_dir():
                    try:
                        dirpath.rmdir()  # 只有空目录才会成功
                    except OSError:
                        pass


# ------------------------------------------------------------------ #
# Module-level singleton                                               #
# ------------------------------------------------------------------ #

_instance: Optional[CacheManager] = None
_instance_lock = threading.Lock()


def get_cache_manager(config: Optional[CacheConfig] = None) -> CacheManager:
    """获取全局 CacheManager 单例"""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = CacheManager(config)
    return _instance


def start_cache_cleanup() -> CacheManager:
    """便捷函数：获取单例并启动后台清理线程"""
    manager = get_cache_manager()
    manager.start()
    return manager
