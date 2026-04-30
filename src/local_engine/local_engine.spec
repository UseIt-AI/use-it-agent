# -*- mode: python ; coding: utf-8 -*-
import os

from PyInstaller.utils.hooks import collect_submodules

_SPEC_DIR = os.path.dirname(os.path.abspath(SPEC))

hiddenimports = ['uvicorn', 'uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.auto', 'uvicorn.protocols', 'uvicorn.protocols.http', 'uvicorn.protocols.http.auto', 'uvicorn.lifespan', 'uvicorn.lifespan.on', 'uvicorn.lifespan.off', 'fastapi', 'starlette', 'pydantic', 'pydantic_core', 'pynput', 'pynput.keyboard', 'pynput.mouse', 'pynput.keyboard._win32', 'pynput.mouse._win32', 'PIL', 'PIL.Image', 'PIL.ImageGrab', 'mss', 'mss.windows', 'pyautogui', 'pyscreeze', 'httpx', 'httpcore', 'anyio', 'sniffio', 'h11', 'win32com', 'win32com.client', 'win32api', 'win32gui', 'win32con', 'pythoncom', 'pywintypes', 'controllers', 'controllers.excel', 'controllers.computer_use', 'controllers.computer_use.win_executor', 'controllers.computer_use.win_executor.handlers', 'local_engine_core', 'controller_api', 'api_routes', 'routes', 'cua_request_router', 'useit_shared']
hiddenimports += collect_submodules('uvicorn')
hiddenimports += collect_submodules('fastapi')
hiddenimports += collect_submodules('starlette')
hiddenimports += collect_submodules('pydantic')
hiddenimports += collect_submodules('pynput')
hiddenimports += collect_submodules('mss')
hiddenimports += collect_submodules('pyscreeze')
hiddenimports += collect_submodules('win32com')
hiddenimports += collect_submodules('controllers')
hiddenimports += collect_submodules('local_engine_core')
hiddenimports += collect_submodules('api_routes')


a = Analysis(
    [os.path.join(_SPEC_DIR, 'main.py')],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'scipy', 'pandas', 'IPython', 'pytest'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='local_engine',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
