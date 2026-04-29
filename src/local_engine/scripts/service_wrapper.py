"""
UseIt Services - Windows 服务包装器

提供将 Local Engine 和 Computer Server 注册为 Windows 服务的功能。
支持 NSSM (Non-Sucking Service Manager) 和原生 Windows Service。

使用方法:
    # 安装服务 (使用 NSSM)
    python service_wrapper.py install --nssm
    
    # 安装服务 (原生 Windows Service，需要 pywin32)
    python service_wrapper.py install
    
    # 启动服务
    python service_wrapper.py start
    
    # 停止服务
    python service_wrapper.py stop
    
    # 卸载服务
    python service_wrapper.py uninstall
    
    # 查看状态
    python service_wrapper.py status

注意:
    - 安装/卸载服务需要管理员权限
    - NSSM 方式更简单，推荐使用
    - 原生方式需要 pywin32 包
"""

import os
import sys
import subprocess
import argparse
import shutil
from pathlib import Path
from typing import Optional, Tuple

# ============================================================
# 配置
# ============================================================

# 服务配置
SERVICES = {
    "local_engine": {
        "name": "UseItLocalEngine",
        "display_name": "UseIt Local Engine",
        "description": "UseIt Local Engine - Excel, AutoCAD, CUA 控制服务",
        "exe": "local_engine.exe",
        "port": 8324,
    },
    "computer_server": {
        "name": "UseItComputerServer",
        "display_name": "UseIt Computer Server",
        "description": "UseIt Computer Server - 桌面自动化服务",
        "exe": "computer_server.exe",
        "port": 8080,
    }
}

# NSSM 下载地址
NSSM_URL = "https://nssm.cc/release/nssm-2.24.zip"

# ============================================================
# 工具函数
# ============================================================

def is_admin() -> bool:
    """检查是否具有管理员权限"""
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False

def run_as_admin(args: list) -> int:
    """以管理员权限运行命令"""
    import ctypes
    
    # 重新运行当前脚本
    script = sys.argv[0]
    params = ' '.join([script] + args)
    
    ret = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, params, None, 1
    )
    
    return ret > 32  # ShellExecute 返回值 > 32 表示成功

def find_nssm() -> Optional[Path]:
    """查找 NSSM 可执行文件"""
    # 检查 PATH
    nssm_path = shutil.which("nssm")
    if nssm_path:
        return Path(nssm_path)
    
    # 检查常见位置
    common_paths = [
        Path("nssm.exe"),
        Path("bin/nssm.exe"),
        Path("tools/nssm.exe"),
        Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "nssm" / "nssm.exe",
        Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")) / "nssm" / "nssm.exe",
    ]
    
    for p in common_paths:
        if p.exists():
            return p
    
    return None

def get_service_exe_path(service_key: str) -> Optional[Path]:
    """获取服务可执行文件路径"""
    service = SERVICES.get(service_key)
    if not service:
        return None
    
    exe_name = service["exe"]
    
    # 检查当前目录
    current = Path(exe_name)
    if current.exists():
        return current.absolute()
    
    # 检查 dist 目录
    dist_path = Path("dist") / service_key / exe_name
    if dist_path.exists():
        return dist_path.absolute()
    
    # 检查 release 目录
    for release_dir in Path("release").glob("*"):
        if release_dir.is_dir():
            exe_path = release_dir / exe_name
            if exe_path.exists():
                return exe_path.absolute()
    
    return None

def run_command(cmd: list, check: bool = True) -> Tuple[int, str, str]:
    """运行命令并返回结果"""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            shell=True
        )
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return -1, "", str(e)

# ============================================================
# NSSM 方式安装服务
# ============================================================

def install_service_nssm(service_key: str, nssm_path: Path) -> bool:
    """使用 NSSM 安装服务"""
    service = SERVICES.get(service_key)
    if not service:
        print(f"Unknown service: {service_key}")
        return False
    
    exe_path = get_service_exe_path(service_key)
    if not exe_path:
        print(f"Service executable not found: {service['exe']}")
        print("Please build the service first: python build_nuitka.py")
        return False
    
    service_name = service["name"]
    
    print(f"Installing service: {service_name}")
    print(f"  Executable: {exe_path}")
    
    # 安装服务
    code, out, err = run_command([str(nssm_path), "install", service_name, str(exe_path)])
    if code != 0 and "already exists" not in err.lower():
        print(f"  Failed to install: {err}")
        return False
    
    # 设置显示名称
    run_command([str(nssm_path), "set", service_name, "DisplayName", service["display_name"]])
    
    # 设置描述
    run_command([str(nssm_path), "set", service_name, "Description", service["description"]])
    
    # 设置工作目录
    run_command([str(nssm_path), "set", service_name, "AppDirectory", str(exe_path.parent)])
    
    # 设置日志
    log_dir = exe_path.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    run_command([str(nssm_path), "set", service_name, "AppStdout", str(log_dir / f"{service_key}.log")])
    run_command([str(nssm_path), "set", service_name, "AppStderr", str(log_dir / f"{service_key}_error.log")])
    run_command([str(nssm_path), "set", service_name, "AppStdoutCreationDisposition", "4"])  # Append
    run_command([str(nssm_path), "set", service_name, "AppStderrCreationDisposition", "4"])
    
    # 设置自动启动
    run_command([str(nssm_path), "set", service_name, "Start", "SERVICE_AUTO_START"])
    
    # 设置失败后自动重启
    run_command([str(nssm_path), "set", service_name, "AppExit", "Default", "Restart"])
    run_command([str(nssm_path), "set", service_name, "AppRestartDelay", "5000"])  # 5秒后重启
    
    print(f"  ✓ Service installed: {service_name}")
    return True

def uninstall_service_nssm(service_key: str, nssm_path: Path) -> bool:
    """使用 NSSM 卸载服务"""
    service = SERVICES.get(service_key)
    if not service:
        print(f"Unknown service: {service_key}")
        return False
    
    service_name = service["name"]
    
    print(f"Uninstalling service: {service_name}")
    
    # 先停止服务
    run_command([str(nssm_path), "stop", service_name])
    
    # 卸载服务
    code, out, err = run_command([str(nssm_path), "remove", service_name, "confirm"])
    if code != 0:
        print(f"  Failed to uninstall: {err}")
        return False
    
    print(f"  ✓ Service uninstalled: {service_name}")
    return True

def start_service_nssm(service_key: str, nssm_path: Path) -> bool:
    """使用 NSSM 启动服务"""
    service = SERVICES.get(service_key)
    if not service:
        return False
    
    service_name = service["name"]
    code, out, err = run_command([str(nssm_path), "start", service_name])
    
    if code == 0:
        print(f"  ✓ Service started: {service_name}")
        return True
    else:
        print(f"  ✗ Failed to start: {err}")
        return False

def stop_service_nssm(service_key: str, nssm_path: Path) -> bool:
    """使用 NSSM 停止服务"""
    service = SERVICES.get(service_key)
    if not service:
        return False
    
    service_name = service["name"]
    code, out, err = run_command([str(nssm_path), "stop", service_name])
    
    if code == 0:
        print(f"  ✓ Service stopped: {service_name}")
        return True
    else:
        print(f"  ✗ Failed to stop: {err}")
        return False

def get_service_status_nssm(service_key: str, nssm_path: Path) -> str:
    """使用 NSSM 获取服务状态"""
    service = SERVICES.get(service_key)
    if not service:
        return "UNKNOWN"
    
    service_name = service["name"]
    code, out, err = run_command([str(nssm_path), "status", service_name])
    
    return out.strip() if code == 0 else "NOT_INSTALLED"

# ============================================================
# SC 命令方式 (备选)
# ============================================================

def install_service_sc(service_key: str) -> bool:
    """使用 sc 命令安装服务 (简单方式)"""
    service = SERVICES.get(service_key)
    if not service:
        return False
    
    exe_path = get_service_exe_path(service_key)
    if not exe_path:
        print(f"Service executable not found: {service['exe']}")
        return False
    
    service_name = service["name"]
    
    # 使用 sc create 创建服务
    cmd = [
        "sc", "create", service_name,
        f'binPath="{exe_path}"',
        f'DisplayName="{service["display_name"]}"',
        "start=auto"
    ]
    
    code, out, err = run_command(cmd)
    
    if code == 0:
        # 设置描述
        run_command(["sc", "description", service_name, service["description"]])
        print(f"  ✓ Service installed: {service_name}")
        return True
    else:
        print(f"  ✗ Failed to install: {err}")
        return False

# ============================================================
# 主命令处理
# ============================================================

def cmd_install(args):
    """安装服务"""
    if not is_admin():
        print("Installing services requires administrator privileges.")
        print("Please run this script as administrator.")
        return False
    
    nssm_path = find_nssm() if args.nssm else None
    
    if args.nssm and not nssm_path:
        print("NSSM not found. Please install NSSM or add it to PATH.")
        print(f"Download: {NSSM_URL}")
        return False
    
    services_to_install = args.services or list(SERVICES.keys())
    
    success = True
    for service_key in services_to_install:
        if nssm_path:
            if not install_service_nssm(service_key, nssm_path):
                success = False
        else:
            if not install_service_sc(service_key):
                success = False
    
    return success

def cmd_uninstall(args):
    """卸载服务"""
    if not is_admin():
        print("Uninstalling services requires administrator privileges.")
        return False
    
    nssm_path = find_nssm()
    services_to_uninstall = args.services or list(SERVICES.keys())
    
    success = True
    for service_key in services_to_uninstall:
        if nssm_path:
            if not uninstall_service_nssm(service_key, nssm_path):
                success = False
        else:
            service_name = SERVICES[service_key]["name"]
            code, _, err = run_command(["sc", "delete", service_name])
            if code != 0:
                print(f"  ✗ Failed to uninstall {service_name}: {err}")
                success = False
            else:
                print(f"  ✓ Service uninstalled: {service_name}")
    
    return success

def cmd_start(args):
    """启动服务"""
    nssm_path = find_nssm()
    services_to_start = args.services or list(SERVICES.keys())
    
    # 先启动 computer_server，再启动 local_engine
    if "computer_server" in services_to_start and "local_engine" in services_to_start:
        services_to_start = ["computer_server", "local_engine"]
    
    success = True
    for service_key in services_to_start:
        if nssm_path:
            if not start_service_nssm(service_key, nssm_path):
                success = False
        else:
            service_name = SERVICES[service_key]["name"]
            code, _, err = run_command(["sc", "start", service_name])
            if code != 0:
                print(f"  ✗ Failed to start {service_name}: {err}")
                success = False
            else:
                print(f"  ✓ Service started: {service_name}")
    
    return success

def cmd_stop(args):
    """停止服务"""
    nssm_path = find_nssm()
    services_to_stop = args.services or list(SERVICES.keys())
    
    success = True
    for service_key in services_to_stop:
        if nssm_path:
            if not stop_service_nssm(service_key, nssm_path):
                success = False
        else:
            service_name = SERVICES[service_key]["name"]
            code, _, err = run_command(["sc", "stop", service_name])
            if code != 0:
                print(f"  ✗ Failed to stop {service_name}: {err}")
                success = False
            else:
                print(f"  ✓ Service stopped: {service_name}")
    
    return success

def cmd_status(args):
    """查看服务状态"""
    nssm_path = find_nssm()
    services_to_check = args.services or list(SERVICES.keys())
    
    print("\n" + "=" * 50)
    print("  UseIt Services Status")
    print("=" * 50)
    
    for service_key in services_to_check:
        service = SERVICES[service_key]
        
        if nssm_path:
            status = get_service_status_nssm(service_key, nssm_path)
        else:
            code, out, _ = run_command(["sc", "query", service["name"]])
            if code == 0 and "RUNNING" in out:
                status = "SERVICE_RUNNING"
            elif code == 0 and "STOPPED" in out:
                status = "SERVICE_STOPPED"
            else:
                status = "NOT_INSTALLED"
        
        status_icon = "✓" if "RUNNING" in status else "✗"
        print(f"  {status_icon} {service['display_name']}")
        print(f"      Status: {status}")
        print(f"      Port: {service['port']}")
        
        exe_path = get_service_exe_path(service_key)
        if exe_path:
            print(f"      Executable: {exe_path}")
        else:
            print(f"      Executable: NOT FOUND")
        print()
    
    print("=" * 50)

def cmd_restart(args):
    """重启服务"""
    cmd_stop(args)
    import time
    time.sleep(2)
    cmd_start(args)

# ============================================================
# 主函数
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="UseIt Services - Windows Service Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python service_wrapper.py install --nssm    # Install using NSSM
  python service_wrapper.py start             # Start all services
  python service_wrapper.py stop              # Stop all services
  python service_wrapper.py status            # Show service status
  python service_wrapper.py uninstall         # Uninstall all services
  
  # Operate on specific service
  python service_wrapper.py start local_engine
  python service_wrapper.py stop computer_server
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # install 命令
    install_parser = subparsers.add_parser('install', help='Install services')
    install_parser.add_argument('services', nargs='*', help='Services to install (default: all)')
    install_parser.add_argument('--nssm', action='store_true', help='Use NSSM for installation')
    
    # uninstall 命令
    uninstall_parser = subparsers.add_parser('uninstall', help='Uninstall services')
    uninstall_parser.add_argument('services', nargs='*', help='Services to uninstall (default: all)')
    
    # start 命令
    start_parser = subparsers.add_parser('start', help='Start services')
    start_parser.add_argument('services', nargs='*', help='Services to start (default: all)')
    
    # stop 命令
    stop_parser = subparsers.add_parser('stop', help='Stop services')
    stop_parser.add_argument('services', nargs='*', help='Services to stop (default: all)')
    
    # restart 命令
    restart_parser = subparsers.add_parser('restart', help='Restart services')
    restart_parser.add_argument('services', nargs='*', help='Services to restart (default: all)')
    
    # status 命令
    status_parser = subparsers.add_parser('status', help='Show service status')
    status_parser.add_argument('services', nargs='*', help='Services to check (default: all)')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    commands = {
        'install': cmd_install,
        'uninstall': cmd_uninstall,
        'start': cmd_start,
        'stop': cmd_stop,
        'restart': cmd_restart,
        'status': cmd_status,
    }
    
    cmd_func = commands.get(args.command)
    if cmd_func:
        cmd_func(args)

if __name__ == '__main__':
    main()


