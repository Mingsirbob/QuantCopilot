"""
Agent 核心构建器与运行包装器
提供 StandaloneAgent 封装类与 build_agent 工厂函数。
"""

from typing import Any, Dict, Generator, List, Optional, Union
from langchain.agents import create_agent
from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph

from core.config import AgentConfig
from core.model import create_chat_model


class StandaloneAgent:
    """
    独立 Agent 封装类。
    包装了底层的 CompiledStateGraph，提供简单易用的交互接口。
    """

    def __init__(
        self,
        config: AgentConfig,
        graph: CompiledStateGraph,
        checkpointer: Optional[InMemorySaver] = None,
    ):
        self.config = config
        self.graph = graph
        self.checkpointer = checkpointer

    def _extract_content(self, result: Dict[str, Any]) -> str:
        """从 invoke 结果中提取最后一轮文本"""
        messages = result.get("messages", [])
        if not messages:
            return ""
        last_message = messages[-1]
        if isinstance(last_message.content, str):
            return last_message.content
        elif isinstance(last_message.content, list):
            texts = [
                b.get("text", "") if isinstance(b, dict) else str(b)
                for b in last_message.content
            ]
            return "".join(texts)
        return str(last_message.content)

    async def arun(self, prompt: str, thread_id: str = "default") -> str:
        """
        官方标准异步调用接口，直接传入用户指令，返回助手的最终文本回复。

        :param prompt: 用户输入提示词
        :param thread_id: 对话会话标识，相同 thread_id 将共享对话历史记忆
        :return: 最终回复文本
        """
        result = await self.ainvoke(prompt, thread_id=thread_id)
        return self._extract_content(result)

    async def ainvoke(
        self,
        input_data: Union[dict, str, List[Any]],
        thread_id: str = "default",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        官方标准异步底层调用接口，返回包含完整 messages 状态的字典。
        """
        call_config = {"configurable": {"thread_id": thread_id}} if self.checkpointer else {}
        if "config" in kwargs:
            call_config.update(kwargs.pop("config"))

        if isinstance(input_data, str):
            payload = {"messages": [HumanMessage(content=input_data)]}
        elif isinstance(input_data, list):
            payload = {"messages": input_data}
        else:
            payload = input_data

        return await self.graph.ainvoke(payload, config=call_config, **kwargs)

    def run(self, prompt: str, thread_id: str = "default") -> str:
        """同步调用接口（适用于无异步工具的 Agent）"""
        result = self.invoke(prompt, thread_id=thread_id)
        return self._extract_content(result)

    def invoke(
        self,
        input_data: Union[dict, str, List[Any]],
        thread_id: str = "default",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """同步底层调用接口（适用于无异步工具的 Agent）"""
        call_config = {"configurable": {"thread_id": thread_id}} if self.checkpointer else {}
        if "config" in kwargs:
            call_config.update(kwargs.pop("config"))

        if isinstance(input_data, str):
            payload = {"messages": [HumanMessage(content=input_data)]}
        elif isinstance(input_data, list):
            payload = {"messages": input_data}
        else:
            payload = input_data

        return self.graph.invoke(payload, config=call_config, **kwargs)

    def stream(
        self,
        prompt: str,
        thread_id: str = "default",
        stream_mode: str = "values",
    ) -> Generator[Dict[str, Any], None, None]:
        """
        流式执行接口。

        :param prompt: 用户提示词
        :param thread_id: 会话标识
        :param stream_mode: 模式，如 "values" 或 "updates"
        """
        call_config = {"configurable": {"thread_id": thread_id}} if self.checkpointer else {}
        payload = {"messages": [HumanMessage(content=prompt)]}

        for event in self.graph.stream(payload, config=call_config, stream_mode=stream_mode):
            yield event

    def get_history(self, thread_id: str = "default") -> List[BaseMessage]:
        """获取指定会话的完整历史消息列表"""
        if not self.checkpointer:
            return []
        state = self.graph.get_state({"configurable": {"thread_id": thread_id}})
        if state and state.values:
            return state.values.get("messages", [])
        return []

    def __repr__(self) -> str:
        tool_names = [getattr(t, "name", str(t)) for t in self.config.tools]
        return (
            f"<StandaloneAgent name={self.config.name!r} "
            f"provider={self.config.provider!r} "
            f"model={self.config.model_name!r} "
            f"tools={tool_names} "
            f"memory={self.config.enable_memory}>"
        )


def build_agent(
    config: Optional[Union[AgentConfig, Dict[str, Any]]] = None,
    **kwargs: Any,
) -> StandaloneAgent:
    """
    Agent 构建工厂函数。
    支持传入 AgentConfig 实例、字典，或通过关键字参数直接配置。

    示例 1 (通过配置对象):
        cfg = AgentConfig(name="MyAgent", system_prompt="...", tools=[...])
        agent = build_agent(cfg)

    示例 2 (通过关键字参数):
        agent = build_agent(
            name="MathBot",
            system_prompt="你是一个数学小助手",
            provider="deepseek",
            tools=[calculate]
        )
    """
    if config is None:
        agent_config = AgentConfig(**kwargs)
    elif isinstance(config, dict):
        merged = {**config, **kwargs}
        agent_config = AgentConfig(**merged)
    elif isinstance(config, AgentConfig):
        if kwargs:
            agent_config = config.model_copy(update=kwargs)
        else:
            agent_config = config
    else:
        raise TypeError(f"不支持的 config 类型: {type(config)}")

    # 1. 初始化 Chat 模型
    model = create_chat_model(agent_config)

    # 2. 配置记忆 Checkpointer
    checkpointer = InMemorySaver() if agent_config.enable_memory else None

    # 3. 使用 LangChain 核心 create_agent 构建图
    graph = create_agent(
        model=model,
        tools=agent_config.tools,
        system_prompt=agent_config.system_prompt,
        checkpointer=checkpointer,
        debug=agent_config.debug,
    )

    return StandaloneAgent(config=agent_config, graph=graph, checkpointer=checkpointer)
