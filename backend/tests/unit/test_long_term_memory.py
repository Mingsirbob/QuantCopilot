"""
单元测试：长期记忆引擎 (LongTermMemoryManager) 与主控智能体 (Master)
验证：
1. 用户偏好画像 (User Profile) 读写与追加
2. 标的研报实体档案 (Entity Archives) 存储与召回
3. 主控 Agent (master) 自动注入用户长期画像与挂载记忆工具
"""

import sys
import tempfile
import asyncio
from pathlib import Path
import pytest

backend_dir = Path(__file__).resolve().parent.parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from core.memory import LongTermMemoryManager, MEMORY_TOOLS
from agents import load_agent, AgentTemplateLoader


def test_user_profile_crud():
    """测试用户偏好画像的读写与增量追加"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        manager = LongTermMemoryManager(Path(tmp_dir))

        # 1. 验证初始化默认画像
        profile = manager.get_user_profile()
        assert "用户长期投资画像" in profile
        assert "5日均线" in profile

        # 2. 验证追加偏好
        manager.append_user_preference("用户明确声明：禁止在研报中推荐港股标的")
        updated_profile = manager.get_user_profile()
        assert "禁止在研报中推荐港股标的" in updated_profile


def test_entity_archives_save_and_recall():
    """测试标的研报实体档案的保存与多条件模糊召回"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        manager = LongTermMemoryManager(Path(tmp_dir))

        # 1. 保存宁德时代历史档案
        manager.save_entity_archive(
            entity_id="stock:300750",
            entity_name="宁德时代",
            last_trend="向下，冲高回落转弱",
            key_levels={"support": 295.5, "resistance": 305.04, "ma5": 305.04},
            latest_summary="5日累计下跌6.09%，收盘价均位于MA5下方，呈Lower Highs结构。",
        )

        # 2. 精确与模糊召回测试
        res1 = manager.recall_entity("300750")
        assert res1 is not None
        assert res1["entity_id"] == "stock:300750"
        assert res1["entity_name"] == "宁德时代"
        assert res1["key_levels"]["support"] == 295.5

        res2 = manager.recall_entity("宁德时代")
        assert res2 is not None
        assert res2["last_trend"] == "向下，冲高回落转弱"

        # 3. 未建档标的召回
        res_none = manager.recall_entity("600519")
        assert res_none is None


@pytest.mark.asyncio
async def test_master_agent_loading_with_long_term_memory():
    """测试加载 master 主控智能体，验证长期记忆自动注入与工具挂载"""
    loader = AgentTemplateLoader()
    spec = loader.load_spec("master")
    assert spec.get("enable_long_term_memory") is True

    # 1. 验证 System Prompt 自动并入了长期记忆画像
    prompt = loader.load_prompt_and_skills("master", spec)
    assert "【核心长期记忆：用户投资画像与全局偏好】" in prompt
    assert "总指挥智能体（Master Orchestrator Agent）" in prompt

    # 2. 验证 Master 智能体完整构建
    from core.memory import SessionManager
    try:
        master = await loader.load_agent("master")
        assert master.config.enable_long_term_memory is True
        tool_names = [getattr(t, "name", str(t)) for t in master.config.tools]

        # 验证关键主控工具均已就绪
        assert "delegate_to_subagent" in tool_names
        assert "recall_entity_memory" in tool_names
        assert "save_entity_memory" in tool_names
        assert "append_user_preference" in tool_names
    finally:
        if SessionManager._instance:
            await SessionManager._instance.close()
