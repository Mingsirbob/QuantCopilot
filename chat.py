"""
MultiAgent 对话终端根目录快捷启动脚本
使用方法：
    uv run python chat.py
或指定 Agent：
    uv run python chat.py data_scraper
"""

import sys
import os
import time
import subprocess
from pathlib import Path
import httpx
from dotenv import load_dotenv

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

load_dotenv(project_root / ".env")
load_dotenv(backend_dir / ".env")

import asyncio
from chat_cli import main


def _check_server_healthy(base_url: str) -> bool:
    """检查调度服务健康检查接口"""
    try:
        with httpx.Client(timeout=0.6) as client:
            resp = client.get(f"{base_url}/health")
            return resp.status_code == 200
    except Exception:
        return False


def _start_background_scheduler(project_root: Path):
    """顺带在后台拉起调度中枢服务"""
    host = os.getenv("SCHEDULER_HOST", "127.0.0.1")
    port = os.getenv("SCHEDULER_PORT", "8765")
    base_url = f"http://{host}:{port}"

    # 1. 如果已存在运行中的调度服务，直接复用
    if _check_server_healthy(base_url):
        print(f"🕰️  [调度中枢] 检测到运行中的调度服务 ({base_url})，已自动接入复用。")
        return None

    # 2. 如果未运行，以后台子进程方式拉起
    print(f"🕰️  [调度中枢] 正在后台随同拉起调度服务器 (run_scheduler.py)...")
    logs_dir = project_root / "workspace" / "runtime" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = open(logs_dir / "scheduler_auto.log", "a", encoding="utf-8")

    cmd = [sys.executable, str(project_root / "run_scheduler.py")]
    proc = subprocess.Popen(
        cmd,
        cwd=str(project_root),
        stdout=log_file,
        stderr=log_file,
    )

    # 快速轮询等待服务就绪
    started = False
    for _ in range(25):
        time.sleep(0.12)
        if _check_server_healthy(base_url):
            started = True
            break

    if started:
        print(f"✅ [调度中枢就绪] 调度服务器已成功拉起 (PID: {proc.pid}, {base_url})")
    else:
        print(f"⚠️ [调度中枢警告] 调度服务子进程已启动 (PID: {proc.pid})，但等待心跳超时，详情请查看 logs/scheduler_auto.log")

    return proc


if __name__ == "__main__":
    # 解析 --with-scheduler / -s 参数 (并从 sys.argv 移除，避免干扰下层 Agent 名称解析)
    with_scheduler = False
    if "--with-scheduler" in sys.argv:
        with_scheduler = True
        sys.argv.remove("--with-scheduler")
    if "-s" in sys.argv:
        with_scheduler = True
        sys.argv.remove("-s")

    scheduler_proc = None
    if with_scheduler:
        scheduler_proc = _start_background_scheduler(project_root)

    exit_code = 0
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
    except Exception as e:
        print(f"\n❌ 程序异常退出: {e}", file=sys.stderr)
        exit_code = 1
    finally:
        # 清理随同启动的后台调度服务子进程
        if scheduler_proc is not None:
            try:
                if scheduler_proc.poll() is None:
                    scheduler_proc.terminate()
                    print("\n🛑 已随同停止临时后台调度服务。")
            except Exception:
                pass

        sys.stdout.flush()
        sys.stderr.flush()
        # 在 Windows 终端下若存在残留后台线程或网络连接，保证进程干净退还控制权
        try:
            os._exit(exit_code)
        except Exception:
            sys.exit(exit_code)


