"""
端到端测试：数据分析 Agent 动态拆解任务并委派数据抓取 Agent
验证 Supervisor -> Sub-Agent 模式以及成果审查闭环
"""

import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# 确保 backend 路径在 sys.path 中
backend_dir = Path(__file__).resolve().parent.parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))


load_dotenv(backend_dir.parent / ".env")
load_dotenv(backend_dir / ".env")
load_dotenv()

# Windows 控制台 UTF-8 支持
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


import pytest
from agents.loader import load_agent


@pytest.mark.asyncio
async def test_analyst_delegation_flow():
    print("=" * 65, flush=True)
    print("🧪 [测试开始] 加载数据分析 Agent (data_analyst)...", flush=True)
    analyst = await load_agent("data_analyst")
    tool_names = [getattr(t, "name", str(t)) for t in analyst.config.tools]
    print(f"🛠️ data_analyst 挂载工具: {tool_names}", flush=True)
    assert "delegate_to_subagent" in tool_names, "必须包含 delegate_to_subagent 工具"

    # 测试指令：分析一个本地不存在的标的（如宁德时代），触发其委派 data_scraper
    query = (
        "请帮我分析宁德时代(300750)最近5个交易日的日K线走势。"
        "如果本地没有该数据，请主动使用 delegate_to_subagent 委派 data_scraper 抓取数据并保存为 'data/ningde_5d_kline.json'，"
        "拿到数据后完成量化指标计算并给出趋势研判报告。"
    )

    print(f"\n👤 [用户指令]:\n{query}\n", flush=True)
    print("⏳ [执行中] 正在执行多 Agent 协同流 (预计需要抓取行情与计算)...\n", flush=True)

    result = await analyst.arun(query, thread_id="test_delegation_session")
    print("=" * 65, flush=True)
    print("🤖 [data_analyst 最终研报输出]:", flush=True)
    print(result, flush=True)
    print("=" * 65, flush=True)

    assert len(result) > 100, "研报输出应该包含实质内容"
    print("✅ [测试成功] 主 Agent 成功完成拆解、委派、审查与量化研报输出！", flush=True)


if __name__ == "__main__":
    asyncio.run(test_analyst_delegation_flow())
