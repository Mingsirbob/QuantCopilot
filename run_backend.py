"""
根目录便捷启动入口
引导执行 backend/main.py
"""

import sys
import subprocess
from pathlib import Path

if __name__ == "__main__":
    backend_main = Path(__file__).resolve().parent / "backend" / "main.py"
    cmd = [sys.executable, str(backend_main)] + sys.argv[1:]
    sys.exit(subprocess.call(cmd))
