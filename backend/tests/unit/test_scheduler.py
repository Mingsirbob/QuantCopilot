"""
单元测试：统一任务调度系统 (test_scheduler.py)
测试 ModuleTask、ScriptTask、PipelineTask、TaskLedger、Filters 以及 TaskScheduler 核心能力。
"""

import asyncio
import sys
from datetime import datetime, time
from pathlib import Path
import tempfile
import pytest

backend_dir = Path(__file__).resolve().parent.parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from scheduler import (
    BaseTask,
    ExecutionContext,
    ModuleTask,
    PipelineTask,
    ScriptTask,
    SilenceChecker,
    TaskLedger,
    TaskResult,
    TaskScheduler,
    TradingHoursFilter,
)


# 1. 模拟的分析函数
def sample_sync_calc(a: int, b: int = 10) -> int:
    return a * b + 42


async def sample_async_calc(symbol: str, threshold: float = 0.05) -> dict:
    await asyncio.sleep(0.01)
    return {"symbol": symbol, "alert": threshold > 0.01}


@pytest.mark.asyncio
async def test_module_task_execution():
    """测试 ModuleTask 同步与异步函数调用及参数合并"""
    ctx = ExecutionContext(task_name="test_sync", params={"a": 5, "b": 2})
    task_sync = ModuleTask(name="sync_calc", target=sample_sync_calc)
    res_sync = await task_sync.run(ctx)

    assert res_sync.success is True
    assert res_sync.data == 5 * 2 + 42  # 52

    ctx_async = ExecutionContext(task_name="test_async", params={"symbol": "600519"})
    task_async = ModuleTask(name="async_calc", target=sample_async_calc)
    res_async = await task_async.run(ctx_async)

    assert res_async.success is True
    assert res_async.data["symbol"] == "600519"
    assert res_async.data["alert"] is True


@pytest.mark.asyncio
async def test_script_task_execution(tmp_path):
    """测试 ScriptTask 异步进程启动并捕获输出"""
    test_script = tmp_path / "hello.py"
    test_script.write_text("print('HELLO_FROM_SCRIPT')", encoding="utf-8")

    task = ScriptTask(name="run_hello", script_path=str(test_script))
    ctx = ExecutionContext(task_name="run_hello")
    res = await task.run(ctx)

    assert res.success is True
    assert "HELLO_FROM_SCRIPT" in res.data


@pytest.mark.asyncio
async def test_pipeline_task():
    """测试 PipelineTask 数据管道链式传递"""
    step1 = ModuleTask(
        name="step1",
        target=lambda: {"indicator": 88.5},
    )
    step2 = ModuleTask(
        name="step2",
        target=lambda step1_output: f"Received: {step1_output['indicator']}",
    )

    pipeline = PipelineTask(name="calc_pipe", tasks=[step1, step2])
    ctx = ExecutionContext(task_name="test_pipe")
    res = await pipeline.run(ctx)

    assert res.success is True
    assert "Received: 88.5" in res.data["final_output"]


@pytest.mark.asyncio
async def test_task_ledger(tmp_path):
    """测试 SQLite 任务账本持久化与历史回溯"""
    db_file = tmp_path / "test_ledger.db"
    ledger = TaskLedger(db_file)

    await ledger.record_start("run_001", "my_task", "module", {"foo": "bar"})
    await ledger.record_finish(
        "run_001",
        status="SUCCESS",
        result_data="Done successfully",
        duration_seconds=1.23,
    )

    runs = await ledger.get_recent_runs("my_task")
    assert len(runs) == 1
    assert runs[0]["run_id"] == "run_001"
    assert runs[0]["status"] == "SUCCESS"
    assert runs[0]["duration_seconds"] == 1.23


def test_filters():
    """测试交易时段过滤器与心跳静默检测器"""
    filter_inst = TradingHoursFilter()

    # 构造交易日开盘时间: 周二上午 10:00 (属于交易时间)
    trading_dt = datetime(2026, 9, 22, 10, 0, 0)
    assert filter_inst.is_trading_time(trading_dt) is True

    # 构造周末: 周六上午 10:00 (非交易时间)
    weekend_dt = datetime(2026, 9, 26, 10, 0, 0)
    assert filter_inst.is_trading_time(weekend_dt) is False

    # 构造夜间: 周二晚上 22:00 (非交易时间)
    night_dt = datetime(2026, 9, 22, 22, 0, 0)
    assert filter_inst.is_trading_time(night_dt) is False

    # 静默检测
    assert SilenceChecker.is_silent("HEARTBEAT_OK") is True
    assert SilenceChecker.is_silent("HEARTBEAT_OK: 标的平稳无异动") is True
    assert SilenceChecker.is_silent("⚠️ 预警: 突发大单抛售！") is False


@pytest.mark.asyncio
async def test_scheduler_lifecycle(tmp_path):
    """测试 TaskScheduler 注册与 trigger_now"""
    ledger_db = tmp_path / "sched_ledger.db"
    scheduler = TaskScheduler(ledger_db_path=ledger_db)

    task = ModuleTask(name="quick_calc", target=lambda x: x * 2, default_params={"x": 21})
    scheduler.register_task(task)

    res = await scheduler.trigger_now("quick_calc")
    assert res.success is True
    assert res.data == 42

    # 账本应写入记录
    runs = await scheduler.ledger.get_recent_runs("quick_calc")
    assert len(runs) == 1
    assert runs[0]["status"] == "SUCCESS"


@pytest.mark.asyncio
async def test_scheduler_delayed_execution(tmp_path):
    """测试 schedule_after 延时调度能力"""
    ledger_db = tmp_path / "sched_delayed.db"
    scheduler = TaskScheduler(ledger_db_path=ledger_db)

    results = []
    task = ModuleTask(name="delay_calc", target=lambda: results.append("executed"))
    scheduler.register_task(task)

    # 安排 1 秒后执行
    scheduler.schedule_after("delay_calc", delay_seconds=1)
    scheduler.start()

    try:
        assert len(results) == 0
        await asyncio.sleep(1.5)
        assert len(results) == 1
        assert results[0] == "executed"
    finally:
        scheduler.shutdown(wait=False)


@pytest.mark.asyncio
async def test_scheduler_server_api(tmp_path):
    """测试 FastAPI 服务端 API 接口交互"""
    from httpx import ASGITransport, AsyncClient
    from scheduler.server import create_scheduler_app

    ledger_db = tmp_path / "server_test_ledger.db"
    scheduler = TaskScheduler(ledger_db_path=ledger_db)
    scheduler.register_task(ModuleTask(name="echo_task", target=lambda: "ECHO_OK"))

    app = create_scheduler_app(scheduler=scheduler)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. 验证健康检查
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "RUNNING"

        # 2. 验证任务列表查询
        resp_tasks = await client.get("/api/tasks")
        assert resp_tasks.status_code == 200
        task_names = [t["name"] for t in resp_tasks.json()["data"]["tasks"]]
        assert "echo_task" in task_names

        # 3. 验证触发任务
        resp_trigger = await client.post("/api/tasks/trigger", json={"task_name": "echo_task"})
        assert resp_trigger.status_code == 200
        assert resp_trigger.json()["success"] is True

        # 等待后台执行写入账本
        await asyncio.sleep(0.1)
        resp_ledger = await client.get("/api/ledger")
        assert resp_ledger.status_code == 200
        assert len(resp_ledger.json()["data"]) >= 1


