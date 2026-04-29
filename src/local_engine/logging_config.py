"""
UseIt Local Engine - 日志配置模块

提供统一的日志配置，支持:
- 控制台输出
- 文件输出 (滚动日志)
- 结构化日志格式
- 不同级别的日志

使用方法:
    from logging_config import setup_logging, get_logger
    
    # 在应用启动时调用
    setup_logging()
    
    # 获取日志器
    logger = get_logger(__name__)
    logger.info("Hello World")

环境变量:
    LOG_LEVEL: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    LOG_DIR: 日志目录路径
    LOG_MAX_SIZE: 单个日志文件最大大小 (MB)
    LOG_BACKUP_COUNT: 保留的日志文件数量
"""

import os
import sys
import tempfile
import logging
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from pathlib import Path
from datetime import datetime
from typing import Optional

# ============================================================
# 配置常量
# ============================================================

DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_MAX_SIZE_MB = 10  # 单个日志文件最大 10MB
DEFAULT_BACKUP_COUNT = 5  # 保留 5 个备份
APP_LOG_SUBDIR = "useit_studio/logs"  # 放在用户目录下的子路径


def _is_packaged() -> bool:
    """判断当前是否运行在打包后的可执行文件里（PyInstaller / Nuitka / cx_Freeze / py2exe）

    Nuitka 1.x 不会设置 `sys.frozen`，仅依赖它会漏判，所以同时检查多个标志。
    """
    if getattr(sys, "frozen", False):
        return True
    if hasattr(sys, "_MEIPASS"):
        return True
    try:
        import __main__  # type: ignore
        if hasattr(__main__, "__compiled__"):
            return True
    except Exception:
        pass
    return False


def _default_log_dir() -> Path:
    """返回一个"当前用户一定能写"的默认日志目录。

    优先级：
      1. Windows: %LOCALAPPDATA%\\useit_studio\\logs
      2. Windows: %APPDATA%\\useit_studio\\logs
      3. POSIX:   ~/.local/share/useit_studio/logs
      4. 兜底:    <tempdir>/useit_studio/logs

    注意：不再使用 "./.logs" 作为默认值 —— 打包后 CWD 可能落在
    Program Files 之类只读目录，普通用户会 PermissionError。
    """
    # Windows
    if sys.platform == "win32":
        localappdata = os.environ.get("LOCALAPPDATA")
        if localappdata:
            return Path(localappdata) / APP_LOG_SUBDIR
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / APP_LOG_SUBDIR
    else:
        # Linux / macOS：XDG_DATA_HOME 或 ~/.local/share
        xdg = os.environ.get("XDG_DATA_HOME")
        if xdg:
            return Path(xdg) / APP_LOG_SUBDIR
        home = os.environ.get("HOME")
        if home:
            return Path(home) / ".local" / "share" / APP_LOG_SUBDIR

    # 所有常规路径都不可用时兜底到临时目录
    return Path(tempfile.gettempdir()) / APP_LOG_SUBDIR


def get_screenshot_debug_dir() -> Path:
    """
    调试用全屏截图落盘目录。

    开发：local engine 包根下 ``debug_screenshots``（与 .gitignore 一致）。
    打包：不能写在 Program Files 或解压只读目录，使用用户可写路径。

    优先级与日志目录对齐：
      1. 若设置了 ``LOG_DIR``，使用 ``Path(LOG_DIR).parent / "debug_screenshots"``（与 logs 同级，便于 userData 管理）
      2. 否则：打包时 ``%LOCALAPPDATA%/useit_studio/debug_screenshots``；非打包时仍为本包根下 ``debug_screenshots``。
    """
    log_dir_env = (os.environ.get("LOG_DIR") or "").strip()
    if log_dir_env:
        base = Path(log_dir_env).expanduser().resolve().parent
    elif _is_packaged():
        base = _default_log_dir().parent
    else:
        base = Path(__file__).resolve().parent

    d = base / "debug_screenshots"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        d = Path(tempfile.gettempdir()) / "useit_studio" / "debug_screenshots"
        d.mkdir(parents=True, exist_ok=True)
    return d


# 保持向后兼容：旧代码里若有人 import DEFAULT_LOG_DIR 仍能拿到一个字符串
DEFAULT_LOG_DIR = str(_default_log_dir())

# 日志格式
CONSOLE_FORMAT = "[%(asctime)s] %(levelname)-8s %(name)s - %(message)s"
FILE_FORMAT = "[%(asctime)s] %(levelname)-8s [%(name)s:%(lineno)d] - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# ============================================================
# 全局变量
# ============================================================

_logging_initialized = False
_log_dir: Optional[Path] = None

# ============================================================
# 颜色支持 (控制台)
# ============================================================

class ColoredFormatter(logging.Formatter):
    """支持颜色的日志格式化器 (仅控制台)"""
    
    # ANSI 颜色代码
    COLORS = {
        'DEBUG': '\033[36m',     # 青色
        'INFO': '\033[32m',      # 绿色
        'WARNING': '\033[33m',   # 黄色
        'ERROR': '\033[31m',     # 红色
        'CRITICAL': '\033[35m',  # 紫色
    }
    RESET = '\033[0m'
    
    def __init__(self, fmt: str, datefmt: str = None, use_colors: bool = True):
        super().__init__(fmt, datefmt)
        self.use_colors = use_colors and self._supports_color()
    
    def _supports_color(self) -> bool:
        """检查终端是否支持颜色"""
        # Windows 10+ 支持 ANSI
        if sys.platform == 'win32':
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                # 启用 ANSI 支持
                kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
                return True
            except Exception:
                return False
        # Unix 系统通常支持
        return hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()
    
    def format(self, record: logging.LogRecord) -> str:
        if self.use_colors and record.levelname in self.COLORS:
            record.levelname = f"{self.COLORS[record.levelname]}{record.levelname}{self.RESET}"
        return super().format(record)

# ============================================================
# 主要函数
# ============================================================

def setup_logging(
    log_level: Optional[str] = None,
    log_dir: Optional[str] = None,
    app_name: str = "local_engine",
    max_size_mb: Optional[int] = None,
    backup_count: Optional[int] = None,
    enable_console: bool = True,
    enable_file: bool = True,
) -> None:
    """
    配置日志系统
    
    Args:
        log_level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_dir: 日志目录路径
        app_name: 应用名称 (用于日志文件名)
        max_size_mb: 单个日志文件最大大小 (MB)
        backup_count: 保留的备份文件数量
        enable_console: 是否启用控制台输出
        enable_file: 是否启用文件输出；打包 exe 下若写入失败会自动回退到 %TEMP% 或关闭文件日志
    """
    global _logging_initialized, _log_dir
    
    if _logging_initialized:
        return
    
    # 从环境变量读取配置
    level_str = log_level or os.environ.get('LOG_LEVEL', DEFAULT_LOG_LEVEL)
    max_bytes = (max_size_mb or int(os.environ.get('LOG_MAX_SIZE', DEFAULT_MAX_SIZE_MB))) * 1024 * 1024
    backup = backup_count or int(os.environ.get('LOG_BACKUP_COUNT', DEFAULT_BACKUP_COUNT))

    # 日志目录解析优先级：
    #   1. 函数参数 log_dir
    #   2. 环境变量 LOG_DIR（Electron 等宿主注入）
    #   3. _default_log_dir() 返回的用户可写目录（%LOCALAPPDATA%/useit_studio/logs 之类）
    # 注意：**不再**使用 "./.logs"，避免打包后 CWD 落在 Program Files 等只读位置时
    # 普通权限直接 PermissionError 闪退。
    log_dir_from_env = (os.environ.get("LOG_DIR") or "").strip()
    if log_dir:
        log_dir_path = Path(log_dir)
    elif log_dir_from_env:
        log_dir_path = Path(log_dir_from_env)
    else:
        log_dir_path = _default_log_dir()

    # Nuitka / PyInstaller 等打包 exe 下的默认策略：
    # - 有 LOG_DIR（如 Electron 传入 app.getPath('userData')/logs）：写文件，关控制台，
    #   避免宿主用 pipe 接 stdio 时启动阶段日志塞满管道导致 HTTP 永不监听（前端 failed to fetch）。
    # - 没有 LOG_DIR：仍写文件到 _default_log_dir()，保留控制台（方便双击运行时排障）。
    if _is_packaged():
        if log_dir_from_env:
            enable_file = True
            enable_console = False
        else:
            enable_file = True
            enable_console = True
    
    # 解析日志级别
    level = getattr(logging, level_str.upper(), logging.INFO)
    
    # 创建日志目录；失败（比如只读分区、权限不足）时降级为仅 stdout，绝不让日志初始化把进程拖崩
    if enable_file:
        try:
            log_dir_path.mkdir(parents=True, exist_ok=True)
            # 额外尝试写一个 .write_test 文件验证真的可写（有些只读挂载 mkdir 成功但写失败）
            probe = log_dir_path / ".write_test"
            try:
                probe.write_text("ok", encoding="utf-8")
            finally:
                try:
                    probe.unlink()
                except Exception:
                    pass
            _log_dir = log_dir_path
        except Exception as e:
            # 回退到临时目录；再失败就彻底关掉文件日志
            fallback = Path(tempfile.gettempdir()) / APP_LOG_SUBDIR
            try:
                fallback.mkdir(parents=True, exist_ok=True)
                log_dir_path = fallback
                _log_dir = log_dir_path
                print(
                    f"[logging] WARNING: cannot write to {log_dir} or resolved log dir ({e}); "
                    f"falling back to {fallback}",
                    file=sys.stderr,
                )
            except Exception as e2:
                enable_file = False
                _log_dir = None
                print(
                    f"[logging] WARNING: no writable log dir available ({e2}); file logging disabled",
                    file=sys.stderr,
                )
    else:
        _log_dir = None
    
    # 获取根日志器
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # 清除已有的处理器
    root_logger.handlers.clear()
    
    # 控制台处理器
    if enable_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(ColoredFormatter(CONSOLE_FORMAT, DATE_FORMAT))
        root_logger.addHandler(console_handler)
    
    # 文件处理器
    if enable_file:
        # 主日志文件 (滚动)
        log_file = log_dir_path / f"{app_name}.log"
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup,
            encoding='utf-8'
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(logging.Formatter(FILE_FORMAT, DATE_FORMAT))
        root_logger.addHandler(file_handler)
        
        # 错误日志文件 (单独记录 ERROR 及以上)
        error_log_file = log_dir_path / f"{app_name}_error.log"
        error_handler = RotatingFileHandler(
            error_log_file,
            maxBytes=max_bytes,
            backupCount=backup,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(logging.Formatter(FILE_FORMAT, DATE_FORMAT))
        root_logger.addHandler(error_handler)
    
    # 降低第三方库的日志级别
    noisy_loggers = [
        'uvicorn.access',
        'uvicorn.error',
        'httpx',
        'httpcore',
        'asyncio',
        'websockets',
        'PIL',
    ]
    for logger_name in noisy_loggers:
        logging.getLogger(logger_name).setLevel(logging.WARNING)
    
    _logging_initialized = True
    
    # 记录初始化信息
    logger = logging.getLogger(__name__)
    logger.info("=" * 50)
    logger.info(f"  Logging initialized")
    logger.info(f"  Level: {level_str}")
    if enable_file:
        logger.info(f"  Log dir: {log_dir_path.absolute()}")
    else:
        logger.info("  File logging: disabled (no writable log directory)")
    if _is_packaged():
        logger.info(f"  Packaged: True (set LOG_DIR env to override default location)")
    logger.info("=" * 50)

def get_logger(name: str) -> logging.Logger:
    """
    获取日志器
    
    Args:
        name: 日志器名称 (通常使用 __name__)
    
    Returns:
        logging.Logger 实例
    """
    return logging.getLogger(name)

def get_log_dir() -> Optional[Path]:
    """获取日志目录路径"""
    return _log_dir

# ============================================================
# 便捷函数
# ============================================================

def log_exception(logger: logging.Logger, message: str, exc: Exception) -> None:
    """
    记录异常信息
    
    Args:
        logger: 日志器
        message: 错误消息
        exc: 异常对象
    """
    logger.error(f"{message}: {exc}", exc_info=True)

def log_request(logger: logging.Logger, method: str, path: str, status: int, duration_ms: float) -> None:
    """
    记录 HTTP 请求
    
    Args:
        logger: 日志器
        method: HTTP 方法
        path: 请求路径
        status: 响应状态码
        duration_ms: 请求耗时 (毫秒)
    """
    level = logging.INFO if status < 400 else logging.WARNING if status < 500 else logging.ERROR
    logger.log(level, f"{method} {path} - {status} ({duration_ms:.1f}ms)")

# ============================================================
# 测试
# ============================================================

if __name__ == '__main__':
    # 测试日志配置
    setup_logging(log_level='DEBUG', app_name='test')
    
    logger = get_logger(__name__)
    
    logger.debug("This is a debug message")
    logger.info("This is an info message")
    logger.warning("This is a warning message")
    logger.error("This is an error message")
    logger.critical("This is a critical message")
    
    try:
        raise ValueError("Test exception")
    except Exception as e:
        log_exception(logger, "Caught an exception", e)
    
    print(f"\nLog directory: {get_log_dir()}")


