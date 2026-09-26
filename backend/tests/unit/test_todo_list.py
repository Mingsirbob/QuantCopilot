"""
单元测试：TodoListMiddleware 待办任务清单管理机制
验证：
1. AgentConfig 参数与 loader 解析
2. build_agent 挂载 TodoListMiddleware
3. 工具调用后的 todos 状态更新与 agent.get_todos() 接口查询
"""

import sys
from pathlib import Path
import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

backend_dir = Path(__file__).resolve().parent.parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from core import AgentConfig, build_agent
from agents.loader import AgentTemplateLoader


class FakeToolModel(GenericFakeChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


def test_todo_config_and_loader():
    """测试配置与工作区模板解析"""
    config = AgentConfig(name="TodoAgent", enable_todo_list=True)
    assert config.enable_todo_list is True

    # 测试从 data_analyst 模板解析
    loader = AgentTemplateLoader()
    spec = loader.load_spec("data_analyst")
    assert spec.get("enable_todo_list") is True


@pytest.mark.asyncio
async def test_todo_list_execution_and_get_todos():
    """测试通过 write_todos 工具更新待办清单，并通过 get_todos 获取"""
    mock_messages = iter([
        AIMessage(
            content="我将规划以下任务：",
            tool_calls=[{
                "name": "write_todos",
                "args": {
                    "todos": [
                        {"content": "第1步：读取数据", "status": "completed"},
                        {"content": "第2步：计算MA5指标", "status": "in_progress"},
                        {"content": "第3步：生成研报", "status": "pending"},
                    ]
                },
                "id": "call_todo_1",
            }],
        ),
        AIMessage(content="第一阶段任务规划已保存，正在执行中。"),
    ])

    model = FakeToolModel(messages=mock_messages)
    checkpointer = InMemorySaver()

    config = AgentConfig(
        name="TestTodoAgent",
        provider="custom",
        system_prompt="你是一个长任务规划专家",
        enable_memory=True,
        enable_todo_list=True,
    )

    agent = build_agent(config=config, model=model, checkpointer=checkpointer)

    # 1. 验证待办清单中间件已生效
    thread_id = "session_plan_test"
    result = await agent.ainvoke("开始执行复杂量化任务", thread_id=thread_id)

    # 2. 验证返回的 state 中包含 todos 状态
    todos = result.get("todos", [])
    assert len(todos) == 3
    assert todos[0]["content"] == "第1步：读取数据"
    assert todos[0]["status"] == "completed"
    assert todos[1]["status"] == "in_progress"

    # 3. 验证通过 get_todos 接口查询会话级持久化任务清单
    saved_todos = agent.get_todos(thread_id=thread_id)
    assert len(saved_todos) == 3
    assert saved_todos[2]["content"] == "第3步：生成研报"
    assert saved_todos[2]["status"] == "pending"
