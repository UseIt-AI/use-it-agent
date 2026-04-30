"""
UseIt Local Engine - 主入口

本地服务引擎，提供:
- Excel 控制器
- AutoCAD 控制器
- Computer Use 控制器
- CUA 请求路由

端口: 8324 (默认)

注意：不要设置 DPI 感知！
保持 Windows 默认的 DPI 虚拟化，这样：
- pynput 使用逻辑坐标
- 屏幕 API 返回逻辑分辨率
- 截图自动缩放到逻辑分辨率
三者天然对齐，无需坐标转换。
"""
import os
import sys

# 打包环境下的全局异常处理（防止窗口立即关闭）
def _setup_exception_hook():
    """设置全局异常钩子，打包后出错时暂停窗口"""
    if not getattr(sys, 'frozen', False):
        return  # 开发环境不需要
    
    original_excepthook = sys.excepthook
    
    def custom_excepthook(exc_type, exc_value, exc_tb):
        original_excepthook(exc_type, exc_value, exc_tb)
        print("\n" + "=" * 60)
        print("  FATAL ERROR: Local Engine crashed!")
        print(f"  {exc_type.__name__}: {exc_value}")
        print("  Press Enter to exit...")
        print("=" * 60)
        try:
            input()
        except:
            pass
    
    sys.excepthook = custom_excepthook

_setup_exception_hook()

# 标准库导入
import json
from pathlib import Path

# 第三方库导入
try:
    from fastapi import FastAPI, HTTPException
    import uvicorn
    from fastapi.middleware.cors import CORSMiddleware
except ImportError as e:
    import traceback
    print("=" * 60)
    print("ERROR: Failed to import required packages")
    print("=" * 60)
    print(f"ImportError message: {e}")
    print(f"ImportError type: {type(e).__name__}")
    if hasattr(e, 'name'):
        print(f"Missing module: {e.name}")
    if hasattr(e, 'path'):
        print(f"Module path: {e.path}")
    print("\nFull traceback:")
    traceback.print_exc()
    print("=" * 60)
    if getattr(sys, 'frozen', False):
        input("Press Enter to exit...")
    sys.exit(1)
except Exception as e:
    import traceback
    print("=" * 60)
    print("ERROR: Unexpected error during import")
    print("=" * 60)
    print(f"Error: {e}")
    print("\nFull traceback:")
    traceback.print_exc()
    print("=" * 60)
    if getattr(sys, 'frozen', False):
        input("Press Enter to exit...")
    sys.exit(1)

# Ensure the current directory is in the python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# ============================================================
# 配置加载
# ============================================================

def load_api_keys():
    """从配置文件加载 API Keys"""
    config_paths = [
        Path(__file__).parent / "config" / "api_keys.json",
        Path("config/api_keys.json"),
        Path("api_keys.json"),
    ]
    
    for config_path in config_paths:
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    
                # 设置环境变量
                if config.get("openai_api_key"):
                    os.environ.setdefault('OPENAI_API_KEY', config["openai_api_key"])
                if config.get("anthropic_api_key"):
                    os.environ.setdefault('ANTHROPIC_API_KEY', config["anthropic_api_key"])
                    
                return True
            except Exception as e:
                print(f"Warning: Failed to load config from {config_path}: {e}")
    
    return False

# 加载配置
load_api_keys()

# ============================================================
# 日志配置
# ============================================================

from logging_config import setup_logging, get_logger

# 初始化日志系统
setup_logging(
    app_name="local_engine",
    log_level=os.environ.get("LOG_LEVEL", "INFO"),
)

logger = get_logger(__name__)

# ============================================================
# 导入路由和组件
# ============================================================

from api.v1 import router as api_v1_router      # API v1 - 统一入口
from core import controller_registry

# ============================================================
# FastAPI 应用
# ============================================================

app = FastAPI(
    title="UseIt Local Engine",
    description="本地服务引擎 - 提供 Excel、AutoCAD、Computer Use 等控制器",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源 (本地开发)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 包含路由
app.include_router(api_v1_router)   # API v1 - 统一入口 (/api/v1/*)

# ============================================================
# 生命周期事件
# ============================================================

@app.on_event("startup")
async def startup_event():
    """应用启动时初始化"""
    logger.info("=" * 60)
    logger.info("  UseIt Local Engine Starting...")
    logger.info("=" * 60)
    logger.info(f"  PID: {os.getpid()}")
    logger.info(f"  Python: {sys.version}")
    logger.info(f"  Working Dir: {os.getcwd()}")
    logger.info("=" * 60)

    # Office 控制器（Word, Excel, PPT）使用懒加载模式
    # 它们在 api/v1/*.py 中首次调用时自动实例化，无需在此注册
    office_controllers = ["word", "excel", "ppt"]
    
    # 其他控制器通过 registry 注册（如需要）
    # controllers_to_register = [
    #     ("autocad", "controllers.autocad.controller", "AutoCADController"),
    #     ("computer", "controllers.computer_use.controller", "ComputerUseController"),
    # ]
    # for name, module_path, class_name in controllers_to_register:
    #     try:
    #         module = __import__(module_path, fromlist=[class_name])
    #         controller_class = getattr(module, class_name)
    #         controller = controller_class()
    #         controller_registry.register(name, controller)
    #         logger.info(f"  [OK] Registered controller: {name}")
    #     except Exception as e:
    #         logger.error(f"  [X] Failed to register {name} controller: {e}")
    # await controller_registry.initialize_all()

    logger.info("=" * 60)
    logger.info("  Local Engine Started")
    logger.info(f"  Available APIs: {office_controllers}")
    logger.info("=" * 60)

@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时清理"""
    logger.info("=" * 60)
    logger.info("  Local Engine Shutting Down...")
    logger.info("=" * 60)
    
    await controller_registry.cleanup_all()
    
    logger.info("  Local Engine Stopped")
    logger.info("=" * 60)

# ============================================================
# API 端点
# ============================================================

@app.get("/")
async def root():
    """根路径"""
    return {
        "service": "UseIt Local Engine",
        "version": "2.0.0",
        "docs": "/docs",
    }

@app.get("/health")
async def health():
    """健康检查端点"""
    return {
        "status": "ok",
        "service": "local_engine",
        "version": "2.0.0",
        "pid": os.getpid(),
        "controllers": controller_registry.list_controllers()
    }

@app.get("/info")
async def info():
    """服务信息"""
    return {
        "service": "UseIt Local Engine",
        "version": "2.0.0",
        "python_version": sys.version,
        "platform": sys.platform,
        "pid": os.getpid(),
        "working_dir": os.getcwd(),
        "controllers": controller_registry.list_controllers(),
        "endpoints": {
            "health": "/health",
            "docs": "/docs",
            "redoc": "/redoc",
        }
    }

# ============================================================
# 主入口
# ============================================================

def main():
    """主函数 - 用于打包后的入口"""
    # 默认绑定到 0.0.0.0 以允许外部访问（如宿主机访问 VM 中的服务）
    host = os.environ.get("LOCAL_ENGINE_HOST", "127.0.0.1")
    port = int(os.environ.get("LOCAL_ENGINE_PORT", "8324"))

    logger.info(f"Starting Local Engine on {host}:{port}...")
    
    try:
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="info",
            access_log=True,
        )
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        # 打包后的 EXE 出错时暂停，方便调试
        if getattr(sys, 'frozen', False):
            print("\n" + "=" * 60)
            print("  ERROR: Local Engine crashed!")
            print("  Press Enter to exit...")
            print("=" * 60)
            input()
        raise

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # 最外层捕获，确保窗口不会立即关闭
        import traceback
        traceback.print_exc()
        if getattr(sys, 'frozen', False):
            print("\n" + "=" * 60)
            print("  ERROR: Startup failed!")
            print("  Press Enter to exit...")
            print("=" * 60)
            input()
