"""
API v1 主路由 - 聚合所有子路由

端点格式: /api/v1/{controller}/{action}
"""

from fastapi import APIRouter

from .system import router as system_router
from .excel import router as excel_router
from .computer import router as computer_router
from .browser import router as browser_router
from .word import router as word_router
from .ppt import router as ppt_router
from .notification import router as notification_router
from .project import router as project_router
from .autocad import router as autocad_router
from .code import router as code_router

router = APIRouter(prefix="/api/v1", tags=["API v1"])

# System endpoints (health, info, capabilities)
router.include_router(system_router, tags=["System"])

# Controller endpoints
router.include_router(excel_router, prefix="/excel", tags=["Excel"])
router.include_router(word_router, prefix="/word", tags=["Word"])
router.include_router(ppt_router, prefix="/ppt", tags=["PowerPoint"])
router.include_router(autocad_router, prefix="/autocad", tags=["AutoCAD"])
router.include_router(computer_router, prefix="/computer", tags=["Computer"])
router.include_router(browser_router, prefix="/browser", tags=["Browser"])
router.include_router(notification_router, prefix="/notification", tags=["Notification"])
router.include_router(project_router, prefix="/project", tags=["Project"])
router.include_router(code_router, prefix="/code", tags=["Code"])