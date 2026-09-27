"""
调度工具单元测试 (test_scheduler_tools.py)
验证新编写的 4 个调度器管理工具定义、功能与异常处理
"""

import pytest
from core.tools.scheduler import (
    schedule_agent_task,
    trigger_registered_task,
    list_scheduled_jobs,
    inspect_scheduler_ledger,
    SCHEDULER_TOOLS,
)
from agents.loader import load_agent


def test_scheduler_tools_metadata():
    """验证调度工具的元数据与参数契约"""
    assert len(SCHEDULER_TOOLS) == 4
    tool_names = [t.name for t in SCHEDULER_TOOLS]
    assert "schedule_agent_task" in tool_names
    assert "trigger_registered_task" in tool_names
    assert "list_scheduled_jobs" in tool_names
    assert "inspect_scheduler_ledger" in tool_names


@pytest.mark.asyncio
async def test_scheduler_tools_server_down_graceful_handling():
    """验证当后台调度服务未启动时，工具能够优雅返回友好提示，不会崩溃"""
    # 1. 尝试查询作业清单
    res_list = await list_scheduled_jobs.ainvoke({})
    assert "无法连接到调度服务器" in res_list

    # 2. 尝试提交任务
    res_schedule = await schedule_agent_task.ainvoke({
        "agent_name": "data_scraper",
        "prompt": "抓取测试数据",
        "delay_seconds": 10,
    })
    assert "无法连接到调度服务器" in res_schedule

    # 3. 尝试查询账本
    res_ledger = await inspect_scheduler_ledger.ainvoke({"limit": 5})
    assert "无法连接到调度服务器" in res_ledger

    # 4. 尝试触发任务
    res_trigger = await trigger_registered_task.ainvoke({"task_name": "test_task"})
    assert "无法连接到调度服务器" in res_trigger


@pytest.mark.asyncio
async def test_master_agent_tool_assembly():
    """验证 Master Agent 资产配置成功装配了调度工具"""
    from core.memory import SessionManager
    try:
        master_agent = await load_agent("master")
        master_tool_names = [t.name for t in master_agent.config.tools]
        
        assert "schedule_agent_task" in master_tool_names
        assert "trigger_registered_task" in master_tool_names
        assert "list_scheduled_jobs" in master_tool_names
        assert "inspect_scheduler_ledger" in master_tool_names
    finally:
        if SessionManager._instance:
            await SessionManager._instance.close()

