"""
MultiAgent 对话终端根目录快捷启动脚本
使用方法：
    uv run python chat.py
或指定 Agent：
    uv run python chat.py data_scraper
"""

import sys
import os
from pathlib import Path

# Windows 控制台中文输出保障
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# 将 backend 加入搜索路径
project_root = Path(__file__).resolve().parent
backend_dir = project_root / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import asyncio
from chat_cli import main

if __name__ == "__main__":
    exit_code = 0
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
    except Exception as e:
        print(f"\n❌ 程序异常退出: {e}", file=sys.stderr)
        exit_code = 1
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        # 在 Windows 终端下若存在残留后台线程或网络连接，保证进程干净退还控制权
        try:
            os._exit(exit_code)
        except Exception:
            sys.exit(exit_code)

