"""
调度任务提交客户端 (submit_task.py)
在任意终端或进程中，将任务快速提交给常驻的调度服务器 (Client-Server 架构)。

使用示例:
1. 预约 Agent 在 5 分钟后分析茅台 (提交后 0.1 秒返回，终端不卡住):
   uv run python submit_task.py --agent data_analyst --prompt "请读取 'workspace/data/maotai_5d_kline.json' 分析茅台走势" --delay 300

2. 让服务端立即触发一个已注册的任务:
   uv run python submit_task.py --run-task quant_indicator_calc

3. 查看服务端当前所有已激活的定时任务清单:
   uv run python submit_task.py --list

4. 查看服务端的最近执行账本记录:
   uv run python submit_task.py --ledger
"""

import argparse
import sys
import httpx

# Windows 控制台中文输出保障
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

DEFAULT_SERVER_URL = "http://127.0.0.1:8765"


def check_server(client: httpx.Client, base_url: str) -> bool:
    """检查服务端是否存活"""
    try:
        resp = client.get(f"{base_url}/health", timeout=3.0)
        return resp.status_code == 200
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(description="MultiAgent 调度中枢客户端 (Task Submitter)")
    parser.add_argument("--server", type=str, default=DEFAULT_SERVER_URL, help=f"调度服务器地址 (默认: {DEFAULT_SERVER_URL})")
    parser.add_argument("--agent", type=str, default=None, help="目标 Agent 名称 (例如: data_analyst)")
    parser.add_argument("--prompt", type=str, default=None, help="传递给 Agent 的指令或提示词")
    parser.add_argument("--delay", type=int, default=0, help="延时秒数 (默认 0 即立即触发，例如 300 代表 5 分钟后)")
    parser.add_argument("--run-task", type=str, default=None, help="立即在服务端触发已注册的任务 (例如: quant_indicator_calc)")
    parser.add_argument("--list", action="store_true", help="列出服务端已注册的任务与当前排班作业")
    parser.add_argument("--ledger", action="store_true", help="查看服务端最近的任务执行账本")

    args = parser.parse_args()
    base_url = args.server.rstrip("/")

    with httpx.Client() as client:
        # 1. 验证服务器连通性
        if not check_server(client, base_url):
            print("=" * 70)
            print(f"❌ 无法连接到调度服务器: {base_url}")
            print("💡 原因: 调度服务器未启动，请先在另一个终端窗口中运行：")
            print("   👉 uv run python run_scheduler.py")
            print("=" * 70)
            sys.exit(1)

        # 2. 查看当前任务清单 (--list)
        if args.list:
            resp = client.get(f"{base_url}/api/tasks", timeout=5.0)
            data = resp.json().get("data", {})
            print("=" * 70)
            print("📋 【调度服务器当前可用任务清单】:")
            for t in data.get("tasks", []):
                print(f"  • [{t['type'].upper()}] {t['name']}: {t['description']}")
            print("\n⏰ 【已激活定时作业列表】:")
            jobs = data.get("jobs", [])
            if not jobs:
                print("  (暂无激活作业)")
            for j in jobs:
                print(f"  • 作业: {j['job_id']} | 触发器: {j['trigger']} | 下次执行: {j.get('next_run_time') or '未定'}")
            print("=" * 70)
            return

        # 3. 查看账本记录 (--ledger)
        if args.ledger:
            resp = client.get(f"{base_url}/api/ledger?limit=10", timeout=5.0)
            runs = resp.json().get("data", [])
            print("=" * 70)
            print(f"📜 【调度服务器最近 {len(runs)} 条执行历史】:")
            for r in runs:
                status_icon = "✅" if r['status'] == 'SUCCESS' else ("⏸️" if r['status'] == 'SKIPPED' else "❌")
                print(f"  {status_icon} [{r['start_time'][:19]}] {r['task_name']} ({r['duration_seconds']}s) -> 状态: {r['status']}")
                if r.get('result_summary'):
                    summary = r['result_summary'].replace('\n', ' ')
                    print(f"     产物: {summary[:80]}...")
            print("=" * 70)
            return

        # 4. 立即触发已注册任务 (--run-task)
        if args.run_task:
            print(f"⚡ 正在向服务器发送触发请求: {args.run_task}...")
            resp = client.post(f"{base_url}/api/tasks/trigger", json={"task_name": args.run_task}, timeout=5.0)
            if resp.status_code == 200:
                print(f"✅ 成功！服务端已接收任务 [{args.run_task}] 并在后台执行。")
                print("💡 你可以在服务端的终端窗口查看实时产物，或稍后通过 '--ledger' 查看执行记录。")
            else:
                print(f"❌ 触发失败: {resp.text}")
            return

        # 5. 提交 Agent 任务 (--agent)
        if args.agent:
            prompt = args.prompt or "请执行默认业务分析"
            payload = {
                "agent_name": args.agent,
                "prompt": prompt,
                "delay_seconds": args.delay,
            }

            print(f"🚀 正在向调度服务器提交 Agent [{args.agent}] 任务...")
            resp = client.post(f"{base_url}/api/tasks/submit-agent", json=payload, timeout=5.0)

            if resp.status_code == 200:
                res_data = resp.json().get("data", {})
                print("=" * 70)
                print("🎉 【任务提交成功！】")
                print(f"  • 目标智能体: {args.agent}")
                print(f"  • 指令内容: {prompt}")
                if args.delay > 0:
                    print(f"  • 倒计时: 将在 {args.delay} 秒后由服务端自动唤醒执行")
                    print(f"  • 预计执行时间: {res_data.get('scheduled_execution_time')}")
                    print(f"  • 服务端作业编号: {res_data.get('job_id')}")
                else:
                    print(f"  • 状态: 已进入服务端后台队列并立即执行")
                print("\n💡 提示: 客户端已完成派发并退出，你可以随时关闭当前终端，任务将由服务器按时执行。")
                print("=" * 70)
            else:
                print(f"❌ 提交失败: {resp.text}")
            return

        # 若无任何参数，打印帮助
        parser.print_help()


if __name__ == "__main__":
    main()
