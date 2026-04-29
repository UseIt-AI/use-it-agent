#!/usr/bin/env python
"""
停止 Local Engine 和 Computer Server 服务
"""
import subprocess
import sys


def stop_services():
    """停止所有服务"""
    services = [
        ("local_engine.exe", "Local Engine"),
        ("computer_server.exe", "Computer Server"),
    ]
    
    print("Stopping UseIt Services...")
    print("=" * 40)
    
    for exe_name, display_name in services:
        try:
            result = subprocess.run(
                ['taskkill', '/F', '/IM', exe_name],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                print(f"  [OK] {display_name} stopped")
            else:
                # 检查是否是因为进程不存在
                if "not found" in result.stderr.lower() or "找不到" in result.stderr:
                    print(f"  [--] {display_name} was not running")
                else:
                    print(f"  [--] {display_name} was not running")
        except Exception as e:
            print(f"  [X] Failed to stop {display_name}: {e}")
    
    print("=" * 40)
    print("Done.")


if __name__ == '__main__':
    stop_services()

