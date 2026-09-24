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

# 将 backend 加入搜索路径
backend_dir = Path(__file__).resolve().parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import asyncio
from chat_cli import main

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
    except Exception as e:
        print(f"\n❌ 程序异常退出: {e}")
    finally:
        # 在 Windows 终端下彻底释放后台网络连接与线程，干脆利落地将控制权归还给操作系统
        try:
            os._exit(0)
        except Exception:
            sys.exit(0)
