"""
系统任务调度中枢管理工具 (Scheduler Tools)
支持主控智能体 (Master Agent) 维护、管理与监控底层调度器：
1. schedule_agent_task: 向调度中枢提交或预约延时 Agent 任务
2. trigger_registered_task: 触发已注册的系统或管道任务
3. list_scheduled_jobs: 查看调度中枢的注册任务与排班作业
4. inspect_scheduler_ledger: 审计近期任务执行历史与失败记录
"""

import os
from typing import Optional
import httpx
from langchain_core.tools import tool

# 获取调度服务地址
def _get_server_url() -> str:
    host = os.getenv("SCHEDULER_HOST", "127.0.0.1")
    port = os.getenv("SCHEDULER_PORT", "8765")
    return os.getenv("SCHEDULER_SERVER_URL", f"http://{host}:{port}").rstrip("/")


@tool
async def schedule_agent_task(
    agent_name: str,
    prompt: str,
    delay_seconds: int = 0,
) -> str:
    """
    向后台任务调度中枢提交或预约一个智能体 (Agent) 任务。
    当用户要求在未来某个时间点执行、周期性执行、或者将耗时任务脱离当前会话放入后台异步运行时使用此工具。

    :param agent_name: 目标智能体名称，例如 'data_scraper' (行情抓取), 'data_analyst' (数据分析) 等已注册 Agent。
    :param prompt: 指派给目标智能体的具体执行指令与提示词（如 "请抓取贵州茅台的5日K线并保存为 'workspace/data/maotai_5d_kline.json'"）。
    :param delay_seconds: 延时执行的秒数。0 代表立即放入后台队列执行；大于 0 代表在指定秒数后由调度器准点触发（例如 300 代表 5 分钟后）。
    :return: 任务排班确认信息，包含作业编号 job_id、预计执行时间或后台状态。
    """
    base_url = _get_server_url()
    payload = {
        "agent_name": agent_name,
        "prompt": prompt,
        "delay_seconds": max(0, delay_seconds),
    }

    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.post(f"{base_url}/api/tasks/submit-agent", json=payload)
            if resp.status_code == 200:
                data = resp.json().get("data") or {}
                if delay_seconds > 0:
                    return (
                        f"✅ [调度中枢排班成功]:\n"
                        f"• 目标智能体: {agent_name}\n"
                        f"• 预约倒计时: {delay_seconds} 秒后自动唤醒\n"
                        f"• 预计触发时间: {data.get('scheduled_execution_time', '未定')}\n"
                        f"• 服务端作业编号 (Job ID): {data.get('job_id', '未知')}\n"
                        f"提示: 任务已由调度中枢接管，用户退出当前会话亦不影响后台准点执行。"
                    )
                else:
                    return (
                        f"✅ [调度中枢任务已派发]:\n"
                        f"• 目标智能体: {agent_name}\n"
                        f"• 状态: 已进入服务端后台队列并发起执行\n"
                        f"• 任务标识: {data.get('task_name', '未知')}"
                    )
            else:
                return f"❌ 调度中枢拒绝排班 (HTTP {resp.status_code}): {resp.text}"
    except Exception as e:
        return (
            f"❌ 无法连接到调度服务器 ({base_url})。\n"
            f"原因: 调度中枢未启动或网络异常 ({e})。\n"
            f"请提示用户在后台或独立终端中运行: uv run python run_scheduler.py"
        )


@tool
async def trigger_registered_task(task_name: str) -> str:
    """
    在调度中枢立即触发执行一个已注册的内置系统/脚本/计算任务 (如 'quant_indicator_calc')。

    :param task_name: 已在调度器注册的任务标识名称（例如 'quant_indicator_calc'）。
    :return: 触发确认与队列状态。
    """
    base_url = _get_server_url()
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.post(f"{base_url}/api/tasks/trigger", json={"task_name": task_name})
            if resp.status_code == 200:
                return f"✅ 已成功触发后台任务 [{task_name}]，任务正在调度服务器后台执行中。"
            elif resp.status_code == 404:
                return f"❌ 触发失败: 调度中枢中未找到名为 '{task_name}' 的注册任务，请使用 list_scheduled_jobs 查看可用清单。"
            else:
                return f"❌ 触发失败 (HTTP {resp.status_code}): {resp.text}"
    except Exception as e:
        return (
            f"❌ 无法连接到调度服务器 ({base_url}): {e}\n"
            f"请确认后台调度服务是否正在运行 (uv run python run_scheduler.py)。"
        )


@tool
async def list_scheduled_jobs() -> str:
    """
    查询后台调度中枢当前所有已注册的任务清单，以及当前所有处于排班激活状态的定时/延时作业。
    当用户询问系统有什么定时任务、当前排班情况如何时使用此工具。

    :return: 已注册任务列表与当前激活排班作业详情。
    """
    base_url = _get_server_url()
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.get(f"{base_url}/api/tasks")
            if resp.status_code == 200:
                data = resp.json().get("data") or {}
                tasks = data.get("tasks", [])
                jobs = data.get("jobs", [])

                lines = ["📋 【调度中枢任务与排班总览】:"]
                lines.append(f"\n1. 已注册可用任务 ({len(tasks)} 个):")
                if not tasks:
                    lines.append("  (暂无已注册任务)")
                for t in tasks:
                    lines.append(f"  • [{t.get('type', 'TASK').upper()}] {t.get('name')}: {t.get('description', '')}")

                lines.append(f"\n2. 当前激活排班作业 ({len(jobs)} 个):")
                if not jobs:
                    lines.append("  (当前队列中暂无排班作业)")
                for j in jobs:
                    lines.append(f"  • 作业: {j.get('job_id')} | 规则: {j.get('trigger')} | 下次执行: {j.get('next_run_time') or '已就绪/未定'}")

                return "\n".join(lines)
            else:
                return f"❌ 获取任务清单失败 (HTTP {resp.status_code}): {resp.text}"
    except Exception as e:
        return (
            f"❌ 无法连接到调度服务器 ({base_url}): {e}\n"
            f"请确认后台调度服务是否正在运行 (uv run python run_scheduler.py)。"
        )


@tool
async def inspect_scheduler_ledger(limit: int = 5) -> str:
    """
    查询后台调度中枢近期的任务执行审计账本 (Ledger)，查看最近任务的成功/失败状态、执行耗时与产物摘要。
    当需要巡检系统健康状况、确认刚才提交的任务是否执行完毕、或排查失败原因时使用此工具。

    :param limit: 获取最近的记录条数 (默认 5 条，最大 20 条)。
    :return: 结构化历史执行记录清单。
    """
    base_url = _get_server_url()
    limit = max(1, min(limit, 20))
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.get(f"{base_url}/api/ledger?limit={limit}")
            if resp.status_code == 200:
                runs = resp.json().get("data") or []
                if not runs:
                    return "📜 【调度审计账本】: 暂无任务执行记录。"

                lines = [f"📜 【调度审计账本 - 最近 {len(runs)} 条记录】:"]
                for r in runs:
                    status = r.get("status", "UNKNOWN")
                    icon = "✅" if status == "SUCCESS" else ("⏸️" if status == "SKIPPED" else "❌")
                    start_time = r.get("start_time", "")[:19]
                    name = r.get("task_name", "unknown")
                    duration = r.get("duration_seconds", 0)
                    summary = (r.get("result_summary") or "").replace("\n", " ")
                    if len(summary) > 80:
                        summary = summary[:80] + "..."

                    lines.append(f"  {icon} [{start_time}] 任务: {name} (耗时: {duration}s) -> 状态: {status}")
                    if summary:
                        lines.append(f"     产物摘要: {summary}")
                    if status == "FAILED" and r.get("error_trace"):
                        err = r.get("error_trace", "").split("\n")[-2]
                        lines.append(f"     错误详情: {err}")

                return "\n".join(lines)
            else:
                return f"❌ 获取账本记录失败 (HTTP {resp.status_code}): {resp.text}"
    except Exception as e:
        return (
            f"❌ 无法连接到调度服务器 ({base_url}): {e}\n"
            f"请确认后台调度服务是否正在运行 (uv run python run_scheduler.py)。"
        )


SCHEDULER_TOOLS = [
    schedule_agent_task,
    trigger_registered_task,
    list_scheduled_jobs,
    inspect_scheduler_ledger,
]
