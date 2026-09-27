"""
MultiAgent 统一任务调度服务器启动入口 (run_scheduler.py)
作为常驻后台服务 (Server Daemon) 运行，内置 FastAPI HTTP API 接口。

使用方式:
1. 作为服务器常驻启动 (监听 http://127.0.0.1:8765):
   uv run python run_scheduler.py

2. 在另一个终端中提交任务给此服务器:
   uv run python submit_task.py --agent data_analyst --prompt "分析茅台走势" --delay 300

3. 快速单次本地调试模式 (无需启动服务器):
   uv run python run_scheduler.py --run-once quant_indicator_calc
"""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# 确保 backend 与根目录在 sys.path 中
project_root = Path(__file__).resolve().parent
backend_dir = project_root / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

load_dotenv(project_root / ".env")
load_dotenv(backend_dir / ".env")

# Windows 控制台中文输出保障
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("run_scheduler")

from scheduler import TaskScheduler
from scheduler.server import create_scheduler_app


def run_standalone_once(task_name: str, config_path: Path):
    """单次独立调试运行 (不启动 Web Server)"""
    scheduler = TaskScheduler()
    if config_path.exists():
        scheduler.load_from_yaml(config_path)

    async def _runner():
        print(f"\n⚡ 【手动单次调试模式】正在执行任务: {task_name}...")
        result = await scheduler.trigger_now(task_name)
        print("\n" + "=" * 75)
        print(f"🎯 执行结果: {result.summary()}")
        if result.success:
            print("📦 产物详情:")
            print(result.data)
        else:
            print(f"❌ 错误详情: {result.error}")
        print("=" * 75)
        try:
            from core.memory import SessionManager
            if SessionManager._instance:
                await SessionManager._instance.close()
        except Exception:
            pass

    asyncio.run(_runner())


def main():
    parser = argparse.ArgumentParser(description="MultiAgent 任务调度中枢 (Server Daemon)")
    parser.add_argument(
        "--config",
        type=str,
        default="workspace/schedules/schedule.yaml",
        help="调度配置文件路径 (默认: workspace/schedules/schedule.yaml)",
    )
    parser.add_argument(
        "--run-once",
        type=str,
        default=None,
        help="立即单次触发指定任务名称并退出 (例如: quant_indicator_calc)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="服务端监听地址 (默认: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="服务端监听端口 (默认: 8765)",
    )
    args = parser.parse_args()

    config_path = (project_root / args.config).resolve()

    # 1. 若为单次调试模式，不启动 Web 服务直接执行
    if args.run_once:
        run_standalone_once(args.run_once, config_path)
        sys.stdout.flush()
        os._exit(0)

    # 2. 正常模式：启动 FastAPI + Uvicorn 调度中枢服务端
    import uvicorn

    print("=" * 75)
    print("🕰️  【MultiAgent 任务调度服务器】正在启动...")
    print(f"📄 配置文件: {config_path}")
    print(f"🌐 调度 API 服务端: http://{args.host}:{args.port}")
    print(f"📖 在线交互式文档 (Swagger): http://{args.host}:{args.port}/docs")
    print(f"📡 客户端提交指令: uv run python submit_task.py --agent data_analyst --delay 300")
    print("=" * 75)

    app = create_scheduler_app(config_path=config_path)

    # 禁用 uvicorn 侵入式访问日志，保持输出清爽干净
    uv_config = uvicorn.Config(
        app=app,
        host=args.host,
        port=args.port,
        log_level="info",
        access_log=False,
    )
    server = uvicorn.Server(uv_config)

    try:
        server.run()
    except KeyboardInterrupt:
        print("\n🛑 收到退出信号，正在安全关闭调度引擎...")
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0)


if __name__ == "__main__":
    main()
