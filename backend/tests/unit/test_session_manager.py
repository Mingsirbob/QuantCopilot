"""
单元测试：SessionManager 会话持久化与标题管理模块
纯本地与内存测试，不依赖外部网络与模型 API，秒级执行完成。
"""

import sys
import tempfile
import pytest
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from core.session_manager import SessionManager


@pytest.mark.asyncio
async def test_session_manager_init_and_table_creation():
    """测试数据库初始化与 sessions_meta 表建立"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        db_path = Path(tmp_dir) / "test_sessions.db"
        sm = SessionManager(str(db_path))
        try:
            await sm.initialize()
            assert db_path.exists(), "SQLite 数据库文件应当被成功创建"
            checkpointer = sm.get_checkpointer()
            assert checkpointer is not None, "应当成功生成 AsyncSqliteSaver 检查点实例"
        finally:
            await sm.close()


@pytest.mark.asyncio
async def test_ensure_session_title_fallback():
    """测试在无外部大模型时的标题兜底生成逻辑与更新逻辑"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        db_path = Path(tmp_dir) / "test_sessions.db"
        sm = SessionManager(str(db_path))
        try:
            await sm.initialize()
            session_id = "unit_sess_001"
            agent_name = "MockAgent"
            long_message = "请帮我计算一下今年上半年所有A股制造业企业的净利润总额以及环比增长率"

            # 1. 首次调用生成标题
            title = await sm.ensure_session_title(
                session_id=session_id,
                agent_name=agent_name,
                first_user_message=long_message,
                llm=None,  # 测试纯本地兜底提取
            )
            assert title is not None
            assert len(title) <= 16, "标题长度应当被截断控制在精炼范围内"
            assert title.startswith("请帮我计算一下今年")

            # 2. 第二次调用应该直接返回已存标题
            second_title = await sm.ensure_session_title(
                session_id=session_id,
                agent_name=agent_name,
                first_user_message="第二句话应该不影响旧标题",
                llm=None,
            )
            assert second_title == title, "对于已有会话，标题应当保持稳定不变"
        finally:
            await sm.close()


@pytest.mark.asyncio
async def test_list_sessions_filter():
    """测试按智能体名称过滤会话列表功能"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        db_path = Path(tmp_dir) / "test_sessions.db"
        sm = SessionManager(str(db_path))
        try:
            await sm.initialize()

            # 插入不同 Agent 的记录
            await sm.ensure_session_title("sess_a_1", "AgentA", "A的第一句话")
            await sm.ensure_session_title("sess_a_2", "AgentA", "A的第二句话")
            await sm.ensure_session_title("sess_b_1", "AgentB", "B的第一句话")

            # 查询 AgentA 的会话
            sessions_a = await sm.list_sessions_async(agent_name="AgentA")
            assert len(sessions_a) == 2
            assert all(s["agent_name"] == "AgentA" for s in sessions_a)

            # 查询 AgentB 的会话
            sessions_b = await sm.list_sessions_async(agent_name="AgentB")
            assert len(sessions_b) == 1
            assert sessions_b[0]["session_id"] == "sess_b_1"

            # 全局查询全部会话
            sessions_all = await sm.list_sessions_async()
            assert len(sessions_all) == 3
        finally:
            await sm.close()

