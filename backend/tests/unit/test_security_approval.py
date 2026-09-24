"""
单元测试：安全审批围栏 (ToolApprovalMiddleware & Security Policy)
验证：
1. ToolApprovalPolicy 白名单策略与动态中断条件
2. 敏感工具触发安全拦截挂起 (is_interrupted, get_pending_approvals)
3. 人工批准执行 (approve / aapprove)
4. 人工拒绝执行并反馈原因 (reject / areject)
5. “不再询问” (always_allow) 会话级白名单放行机制
"""

import sys
from pathlib import Path
import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

backend_dir = Path(__file__).resolve().parent.parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from core.config import AgentConfig
from core.builder import build_agent
from core.security import ToolApprovalPolicy


@tool
def dangerous_calculator(expression: str) -> str:
    """敏感计算器工具"""
    return f"Result: {eval(expression)}"


@tool
def safe_echo(text: str) -> str:
    """普通安全工具"""
    return f"Echo: {text}"


class FakeToolModel(GenericFakeChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


def test_tool_approval_policy():
    """测试安全审批策略的基础判定与白名单增删"""
    policy = ToolApprovalPolicy(
        sensitive_tools=["execute_python_code", "write_file"],
        initial_whitelist=["write_file"],
    )

    assert policy.is_tool_sensitive("execute_python_code") is True
    assert policy.is_tool_sensitive("safe_echo") is False

    # write_file 初始在全局白名单中
    assert policy.is_tool_whitelisted("write_file") is True
    assert policy.is_tool_whitelisted("execute_python_code") is False

    # 动态将会话加入白名单（不再询问）
    policy.add_to_whitelist("execute_python_code", thread_id="t_123")
    assert policy.is_tool_whitelisted("execute_python_code", thread_id="t_123") is True
    # 其它会话不受影响
    assert policy.is_tool_whitelisted("execute_python_code", thread_id="t_456") is False


@pytest.mark.asyncio
async def test_sensitive_tool_interrupt_and_approve():
    """测试敏感工具触发中断挂起，并由人类批准后恢复执行"""
    mock_messages = iter([
        AIMessage(
            content="即将执行高危运算",
            tool_calls=[{"name": "dangerous_calculator", "args": {"expression": "100 * 2"}, "id": "call_calc_1"}],
        ),
        AIMessage(content="高危运算已执行完毕，结果为 200。"),
    ])

    model = FakeToolModel(messages=mock_messages)
    checkpointer = InMemorySaver()

    config = AgentConfig(
        name="SecurityAgent",
        provider="custom",
        system_prompt="安全助理",
        enable_memory=True,
        enable_tool_approval=True,
        sensitive_tools=["dangerous_calculator"],
    )

    agent = build_agent(
        config=config,
        model=model,
        checkpointer=checkpointer,
        tools=[dangerous_calculator, safe_echo],
    )

    thread_id = "session_security_1"

    # 1. 触发敏感工具，智能体应被挂起 (Interrupted)
    await agent.ainvoke("执行计算", thread_id=thread_id)
    assert agent.is_interrupted(thread_id=thread_id) is True

    # 2. 检查待审批详情
    pending = agent.get_pending_approvals(thread_id=thread_id)
    assert len(pending) == 1
    assert pending[0]["tool_name"] == "dangerous_calculator"
    assert pending[0]["args"] == {"expression": "100 * 2"}

    # 3. 人类批准执行 (aapprove)
    final_text = await agent.aapprove(thread_id=thread_id)
    assert "200" in final_text
    assert agent.is_interrupted(thread_id=thread_id) is False


@pytest.mark.asyncio
async def test_sensitive_tool_reject_with_reason():
    """测试敏感工具被人类拒绝，大模型收到拒绝原因并终止"""
    mock_messages = iter([
        AIMessage(
            content="即将执行高危运算",
            tool_calls=[{"name": "dangerous_calculator", "args": {"expression": "0 / 0"}, "id": "call_calc_2"}],
        ),
        AIMessage(content="用户已拒绝该运算操作，取消执行。"),
    ])

    model = FakeToolModel(messages=mock_messages)
    checkpointer = InMemorySaver()

    config = AgentConfig(
        name="SecurityAgentReject",
        provider="custom",
        system_prompt="安全助理",
        enable_memory=True,
        enable_tool_approval=True,
        sensitive_tools=["dangerous_calculator"],
    )

    agent = build_agent(
        config=config,
        model=model,
        checkpointer=checkpointer,
        tools=[dangerous_calculator],
    )

    thread_id = "session_security_reject"
    await agent.ainvoke("执行除零运算", thread_id=thread_id)
    assert agent.is_interrupted(thread_id=thread_id) is True

    # 人类拒绝执行 (areject)
    final_text = await agent.areject(thread_id=thread_id, reason="操作存在除零崩溃隐患")
    assert "取消执行" in final_text
    assert agent.is_interrupted(thread_id=thread_id) is False


@pytest.mark.asyncio
async def test_always_allow_whitelist_workflow():
    """测试用户选择'不再询问 (always_allow=True)'后，后续调用自动免审批放行"""
    mock_messages = iter([
        # 第一次调用，触发中断
        AIMessage(
            content="第1次调用",
            tool_calls=[{"name": "dangerous_calculator", "args": {"expression": "1 + 1"}, "id": "c1"}],
        ),
        AIMessage(content="第1次完成"),
        # 第二次调用，应因白名单免审批自动完成
        AIMessage(
            content="第2次调用",
            tool_calls=[{"name": "dangerous_calculator", "args": {"expression": "2 + 2"}, "id": "c2"}],
        ),
        AIMessage(content="第2次完成"),
    ])

    model = FakeToolModel(messages=mock_messages)
    checkpointer = InMemorySaver()

    config = AgentConfig(
        name="SecurityAgentWhitelist",
        provider="custom",
        system_prompt="安全助理",
        enable_memory=True,
        enable_tool_approval=True,
        sensitive_tools=["dangerous_calculator"],
    )

    agent = build_agent(
        config=config,
        model=model,
        checkpointer=checkpointer,
        tools=[dangerous_calculator],
    )

    thread_id = "session_always_allow"

    # 第 1 轮：被拦截
    await agent.ainvoke("第1次计算", thread_id=thread_id)
    assert agent.is_interrupted(thread_id=thread_id) is True

    # 批准并勾选“不再询问 / always_allow=True”
    await agent.aapprove(thread_id=thread_id, always_allow=True)
    assert agent.is_interrupted(thread_id=thread_id) is False

    # 第 2 轮：再次调用相同的敏感工具，此时已在白名单中，应全自动完成，不再中断！
    await agent.ainvoke("第2次计算", thread_id=thread_id)
    assert agent.is_interrupted(thread_id=thread_id) is False
