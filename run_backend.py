"""
根目录便捷启动入口
引导执行 backend/main.py
"""

import sys
import subprocess
from pathlib import Path

if __name__ == "__main__":
    project_root = Path(__file__).resolve().parent
    backend_main = project_root / "backend" / "main.py"
    cmd = [sys.executable, str(backend_main)] + sys.argv[1:]
    # 显式指定 cwd 为项目根目录，防止跨目录调用时相对路径查找失败
    sys.exit(subprocess.call(cmd, cwd=str(project_root)))

