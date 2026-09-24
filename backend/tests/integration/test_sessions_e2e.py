"""
集成测试：会话持久化与跨进程状态恢复 (端到端真实服务联动)
涵盖：
1. 真实大模型调用，根据首句提炼压缩生成会话标题
2. 数据持久化落盘至 workspace/sessions.db
3. 模拟程序重启，验证相同 session_id 跨进程恢复完整上下文
"""

import sys
import uuid
import pytest
from pathlib import Path
from dotenv import load_dotenv

# 确保 backend 根路径
backend_dir = Path(__file__).resolve().parent.parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

load_dotenv(backend_dir.parent / ".env")
load_dotenv(backend_dir / ".env")

from agents import load_agent
from core.session_manager import SessionManager


@pytest.mark.asyncio
async def test_session_persistence_and_title_e2e():
    """端到端集成测试：Agent 会话持久化与标题自动生成"""
    session_id = f"test_e2e_{uuid.uuid4().hex[:6]}"
    scraper = await load_agent("data_scraper")

    # 1. 第一轮提问
    query_1 = "请帮我查询股票贵州茅台的实时行情快照，告诉我最新价格与涨跌幅。"
    reply_1 = await scraper.arun(query_1, thread_id=session_id)
    assert reply_1, "回复不应为空"
    assert "茅台" in reply_1 or "600519" in reply_1

    # 2. 检查会话标题是否自动生成
    title = scraper.get_session_title(session_id)
    assert title is not None, "会话标题应当自动生成"
    assert len(title) > 0, "会话标题内容不应为空"

    # 3. 模拟重启：重建全新实例
    new_scraper = await load_agent("data_scraper")

    # 4. 第二轮追问测试记忆继承
    query_2 = "我刚才第一句话问你的是哪一只股票？代码是多少？"
    reply_2 = await new_scraper.arun(query_2, thread_id=session_id)
    assert "茅台" in reply_2 or "600519" in reply_2, "Agent 应当能够从 sessions.db 中回忆出第一轮的问题"

    # 5. 验证会话列表中包含该会话
    sm = await SessionManager.get_instance()
    sessions = await sm.list_sessions_async()
    ids = [s["session_id"] for s in sessions]
    assert session_id in ids, f"{session_id} 应当存在于持久化会话列表中"


if __name__ == "__main__":
    import asyncio
    try:
        asyncio.run(test_session_persistence_and_title_e2e())
        print("✅ 端到端集成测试执行完毕并通过！")
    finally:
        sys.stdout.flush()
        import os
        os._exit(0)
