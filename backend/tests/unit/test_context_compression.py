"""
智能上下文压缩机制单元测试
验证 5 大核心压缩策略及其在 Agent 中的集成：
1. ToolResultCompactionStrategy (工具结果精简)
2. SummarizationStrategy (大模型摘要)
3. SlidingWindowStrategy & TruncationStrategy (滑动窗口与硬截断)
4. TokenBudgetComposedStrategy (预算组合拳)
5. ContextCompressionMiddleware (中间件无缝集成)
"""

import pytest
import asyncio
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.language_models.fake_chat_models import FakeListChatModel

import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from core import AgentConfig, build_agent
from core.memory import (
    count_tokens,
    compact_tool_messages,
    trim_history,
    TokenBudgetComposedCompressor,
    ContextCompressionMiddleware,
)
from core.memory.compression import (
    summarize_messages_sync,
    summarize_messages_async,
)


def test_token_counter():
    """测试通用 Token 计数器"""
    msgs = [
        SystemMessage(content="You are a helpful assistant."),
        HumanMessage(content="Hello world!"),
    ]
    tokens = count_tokens(msgs)
    assert tokens > 0
    # 多模态/复杂 content
    complex_msg = [HumanMessage(content=[{"type": "text", "text": "structured test"}])]
    assert count_tokens(complex_msg) > 0


def test_tool_result_compaction():
    """测试策略：ToolResultCompactionStrategy"""
    huge_json = '{"status": "ok", "items": [' + ', '.join([f'{{"id": {i}, "data": "val_{i}"}}' for i in range(100)]) + ']}'
    tool_msg = ToolMessage(
        content=huge_json,
        tool_call_id="call_test_123",
        name="fetch_kline",
    )
    short_msg = ToolMessage(
        content="short result",
        tool_call_id="call_test_456",
        name="short_tool",
    )

    messages = [
        HumanMessage(content="查询数据"),
        tool_msg,
        short_msg,
    ]

    compacted = compact_tool_messages(messages, max_tool_chars=100)
    assert len(compacted) == 3
    # 冗长的 tool_msg 被精简折叠
    assert len(compacted[1].content) < len(huge_json)
    assert "工具结果已自动折叠" in compacted[1].content
    assert compacted[1].tool_call_id == "call_test_123"
    assert compacted[1].name == "fetch_kline"
    # 短的 short_msg 保持原样
    assert compacted[2].content == "short result"


def test_trim_history_sliding_and_truncation():
    """测试策略：SlidingWindowStrategy 与 TruncationStrategy"""
    msgs = [
        SystemMessage(content="系统提示词"),
        HumanMessage(content="问题一"),
        AIMessage(content="回答一"),
        HumanMessage(content="问题二"),
        AIMessage(content="回答二"),
        HumanMessage(content="问题三"),
        AIMessage(content="回答三"),
    ]

    # 给定较小预算，只允许保留最近 1~2 轮
    trimmed = trim_history(msgs, max_tokens=30, include_system=True)
    assert len(trimmed) < len(msgs)
    # 确保从 HumanMessage 开始（除了系统提示词之外）
    assert any(isinstance(m, HumanMessage) for m in trimmed)


def test_summarization_sync_and_async():
    """测试策略：SummarizationStrategy"""
    fake_summary_model = FakeListChatModel(responses=["用户此前了解了贵州茅台的近5日走势，并计算了MA5指标。"])

    msgs = [
        HumanMessage(content="你好，请问贵州茅台今天走势如何？"),
        AIMessage(content="茅台今日微涨 0.5%，站上 1400 元。"),
        HumanMessage(content="帮我算一下它的 MA5 均线。"),
        AIMessage(content="MA5 目前在 1395 元附近。"),
        HumanMessage(content="好的，那未来两天有什么建议？"),
        AIMessage(content="建议观察量能配合情况。"),
        HumanMessage(content="请继续"),
        AIMessage(content="收到"),
    ]

    # 保留最近 4 条，早期被摘要
    result_sync = summarize_messages_sync(
        msgs,
        keep_recent_messages=4,
        summary_model=fake_summary_model,
    )

    assert any("[早期历史对话记忆摘要]" in str(m.content) for m in result_sync)
    # 最近的 4 条被完整保留
    assert result_sync[-1].content == "收到"
    assert result_sync[-2].content == "请继续"


@pytest.mark.asyncio
async def test_summarization_async():
    """测试异步大模型摘要"""
    fake_summary_model = FakeListChatModel(responses=["早期对话摘要测试"])

    msgs = [
        HumanMessage(content=f"轮次 {i}") if i % 2 == 0 else AIMessage(content=f"回答 {i}")
        for i in range(10)
    ]

    result_async = await summarize_messages_async(
        msgs,
        keep_recent_messages=4,
        summary_model=fake_summary_model,
    )
    assert any("[早期历史对话记忆摘要]" in str(m.content) for m in result_async)
    assert len(result_async) <= 6


def test_token_budget_composed_compressor():
    """测试策略：TokenBudgetComposedStrategy 预算组合拳逐步压缩流程"""
    huge_text = "重要金融量化数据 " * 100
    tool_msg = ToolMessage(content=huge_text, tool_call_id="call_999", name="deep_scan")

    msgs = [
        HumanMessage(content="开始分析"),
        AIMessage(content="正在调用工具"),
        tool_msg,
        HumanMessage(content="收到，下一步呢？"),
        AIMessage(content="已完成"),
    ]

    initial_tokens = count_tokens(msgs)

    # 设定一个低于原始 Token 但高于压缩后 Token 的预算
    compressor = TokenBudgetComposedCompressor(
        token_budget=150,
        max_tool_chars=50,
        keep_recent_messages=4,
    )

    compressed = compressor.compress(msgs)
    final_tokens = count_tokens(compressed)

    assert final_tokens < initial_tokens
    assert final_tokens <= 150


@pytest.mark.asyncio
async def test_agent_middleware_e2e_integration():
    """端到端验证：ContextCompressionMiddleware 在 build_agent 与运行时的拦截生效"""
    fake_model = FakeListChatModel(responses=["分析完成，当前趋势向上。"])

    config = AgentConfig(
        name="TestCompressionAgent",
        provider="custom",
        system_prompt="你是一个金融分析师",
        enable_memory=False,
        enable_context_compression=True,
        context_token_budget=100,
        context_tool_max_len=50,
        context_window_keep_messages=4,
    )

    # 用 mock 模型构建 Agent
    agent = build_agent(config=config, model=fake_model)

    # 执行异步调用
    res = await agent.arun("请帮我分析茅台走势")
    assert "分析完成" in res
