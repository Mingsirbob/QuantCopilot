"""
Agent 核心构建器与运行包装器 (Runtime Builder)
提供 StandaloneAgent 封装类与 build_agent 工厂函数。
"""

from typing import Any, Dict, Generator, List, Optional, Union
from langchain.agents import create_agent
from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from core.runtime.config import AgentConfig
from core.runtime.model import create_chat_model
from core.memory import ContextCompressionMiddleware, TokenBudgetComposedCompressor, SessionManager
from core.sandbox import AgentSandbox
from core.security import ToolApprovalPolicy, create_approval_middleware


class StandaloneAgent:
    """
    独立 Agent 封装类。
    包装了底层的 CompiledStateGraph，提供简单易用的交互接口。
    """

    def __init__(
        self,
        config: AgentConfig,
        graph: CompiledStateGraph,
        checkpointer: Optional[Any] = None,
        sandbox: Optional[AgentSandbox] = None,
        session_manager: Optional[SessionManager] = None,
        model: Optional[Any] = None,
        security_policy: Optional[ToolApprovalPolicy] = None,
    ):
        self.config = config
        self.graph = graph
        self.checkpointer = checkpointer
        self.sandbox = sandbox
        self.session_manager = session_manager
        self.model = model
        self.security_policy = security_policy

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

    def _get_namespaced_thread_id(self, thread_id: str) -> str:
        """带 Agent 命名空间的 thread_id，保证统一集中存储于 sessions.db 时不串台"""
        return f"{self.config.name}:{thread_id}"

    async def ainvoke(
        self,
        input_data: Union[dict, str, List[Any]],
        thread_id: str = "default",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        官方标准异步底层调用接口，返回包含完整 messages 状态的字典。
        """
        # 1. 自动调用大模型生成/维护会话标题 (参考 OpenAI 机制)
        if self.session_manager:
            user_text = ""
            if isinstance(input_data, str):
                user_text = input_data
            elif isinstance(input_data, dict) and "messages" in input_data:
                msgs = input_data["messages"]
                user_text = getattr(msgs[0], "content", str(msgs[0])) if msgs else ""
            elif isinstance(input_data, list) and input_data:
                user_text = getattr(input_data[0], "content", str(input_data[0]))

            if user_text:
                await self.session_manager.ensure_session_title(
                    session_id=thread_id,
                    agent_name=self.config.name,
                    first_user_message=user_text,
                    llm=self.model,
                )

        # 2. 命名空间隔离注入配置
        namespaced_id = self._get_namespaced_thread_id(thread_id)
        call_config = {"configurable": {"thread_id": namespaced_id}} if self.checkpointer else {}
        if "config" in kwargs:
            call_config.update(kwargs.pop("config"))

        if isinstance(input_data, str):
            payload = {"messages": [HumanMessage(content=input_data)]}
        elif isinstance(input_data, list):
            payload = {"messages": input_data}
        else:
            payload = input_data

        return await self.graph.ainvoke(payload, config=call_config, **kwargs)

    def get_session_title(self, thread_id: str) -> Optional[str]:
        """获取指定会话的精炼标题"""
        if not self.session_manager:
            return None
        sessions = self.session_manager.list_sessions_sync(self.config.name)
        for s in sessions:
            if s["session_id"] == thread_id:
                return s["title"]
            if s["session_id"] == thread_id:
                return s["title"]
        return None

    def list_sessions(self) -> List[Dict[str, Any]]:
        """列出当前 Agent 的所有历史会话（包含标题、时间）"""
        if not self.session_manager:
            return []
        return self.session_manager.list_sessions_sync(agent_name=self.config.name)

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
        """获取指定会话的完整历史消息列表（同步）"""
        if not self.checkpointer:
            return []
        namespaced_id = self._get_namespaced_thread_id(thread_id)
        state = self.graph.get_state({"configurable": {"thread_id": namespaced_id}})
        if state and state.values:
            return state.values.get("messages", [])
        return []

    async def aget_history(self, thread_id: str = "default") -> List[BaseMessage]:
        """获取指定会话的完整历史消息列表（异步）"""
        if not self.checkpointer:
            return []
        namespaced_id = self._get_namespaced_thread_id(thread_id)
        state = await self.graph.aget_state({"configurable": {"thread_id": namespaced_id}})
        if state and state.values:
            return state.values.get("messages", [])
        return []

    def get_todos(self, thread_id: str = "default") -> List[Dict[str, Any]]:
        """获取指定会话当前的待办任务清单状态 (TodoListMiddleware)（同步）"""
        if not self.checkpointer:
            return []
        namespaced_id = self._get_namespaced_thread_id(thread_id)
        state = self.graph.get_state({"configurable": {"thread_id": namespaced_id}})
        if state and state.values:
            return state.values.get("todos", [])
        return []

    async def aget_todos(self, thread_id: str = "default") -> List[Dict[str, Any]]:
        """获取指定会话当前的待办任务清单状态 (TodoListMiddleware)（异步）"""
        if not self.checkpointer:
            return []
        namespaced_id = self._get_namespaced_thread_id(thread_id)
        state = await self.graph.aget_state({"configurable": {"thread_id": namespaced_id}})
        if state and state.values:
            return state.values.get("todos", [])
        return []

    def is_interrupted(self, thread_id: str = "default") -> bool:
        """检查指定会话当前是否处于被安全审批拦截挂起的状态（同步）"""
        if not self.checkpointer:
            return False
        namespaced_id = self._get_namespaced_thread_id(thread_id)
        state = self.graph.get_state({"configurable": {"thread_id": namespaced_id}})
        return bool(state and state.next)

    async def ais_interrupted(self, thread_id: str = "default") -> bool:
        """检查指定会话当前是否处于被安全审批拦截挂起的状态（异步）"""
        if not self.checkpointer:
            return False
        namespaced_id = self._get_namespaced_thread_id(thread_id)
        state = await self.graph.aget_state({"configurable": {"thread_id": namespaced_id}})
        return bool(state and state.next)

    def get_pending_approvals(self, thread_id: str = "default") -> List[Dict[str, Any]]:
        """获取当前会话待人类审批的敏感工具请求详情（同步）"""
        if not self.checkpointer:
            return []
        namespaced_id = self._get_namespaced_thread_id(thread_id)
        state = self.graph.get_state({"configurable": {"thread_id": namespaced_id}})
        if not state or not state.tasks:
            return []
        pending = []
        for task in state.tasks:
            for interrupt in getattr(task, "interrupts", []):
                val = getattr(interrupt, "value", {})
                if isinstance(val, dict) and "action_requests" in val:
                    for req in val["action_requests"]:
                        pending.append({
                            "tool_name": req.get("name"),
                            "args": req.get("args"),
                            "description": req.get("description"),
                            "interrupt_id": getattr(interrupt, "id", None),
                        })
        return pending

    async def aget_pending_approvals(self, thread_id: str = "default") -> List[Dict[str, Any]]:
        """获取当前会话待人类审批的敏感工具请求详情（异步）"""
        if not self.checkpointer:
            return []
        namespaced_id = self._get_namespaced_thread_id(thread_id)
        state = await self.graph.aget_state({"configurable": {"thread_id": namespaced_id}})
        if not state or not state.tasks:
            return []
        pending = []
        for task in state.tasks:
            for interrupt in getattr(task, "interrupts", []):
                val = getattr(interrupt, "value", {})
                if isinstance(val, dict) and "action_requests" in val:
                    for req in val["action_requests"]:
                        pending.append({
                            "tool_name": req.get("name"),
                            "args": req.get("args"),
                            "description": req.get("description"),
                            "interrupt_id": getattr(interrupt, "id", None),
                        })
        return pending

    def resume_approval(
        self,
        thread_id: str = "default",
        decision: str = "approve",
        message: Optional[str] = None,
        always_allow: bool = False,
        edited_action: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        同步对处于挂起状态的工具调用做出审批决策并恢复执行。

        :param thread_id: 会话标识
        :param decision: 决策类型，支持 'approve' (批准), 'reject' (拒绝), 'edit' (修改参数), 'respond' (人工代答)
        :param message: 拒绝原因或留言
        :param always_allow: 若为 True，则自动将该工具加入免审批白名单（不再询问）
        :param edited_action: 修改后的工具与参数（如 {'name': '...', 'args': {...}}）
        """
        if always_allow and self.security_policy:
            pending = self.get_pending_approvals(thread_id)
            for p in pending:
                if p.get("tool_name"):
                    self.security_policy.add_to_whitelist(p["tool_name"], thread_id=thread_id)

        decision_dict: Dict[str, Any] = {"type": decision}
        if decision == "reject" and message:
            decision_dict["message"] = message
        elif decision == "edit" and edited_action:
            decision_dict["edited_action"] = edited_action

        command = Command(resume={"decisions": [decision_dict]})
        namespaced_id = self._get_namespaced_thread_id(thread_id)
        call_config = {"configurable": {"thread_id": namespaced_id}}
        if "config" in kwargs:
            call_config.update(kwargs.pop("config"))
        return self.graph.invoke(command, config=call_config, **kwargs)

    async def aresume_approval(
        self,
        thread_id: str = "default",
        decision: str = "approve",
        message: Optional[str] = None,
        always_allow: bool = False,
        edited_action: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """异步恢复执行审批决策"""
        if always_allow and self.security_policy:
            pending = await self.aget_pending_approvals(thread_id)
            for p in pending:
                if p.get("tool_name"):
                    self.security_policy.add_to_whitelist(p["tool_name"], thread_id=thread_id)

        decision_dict: Dict[str, Any] = {"type": decision}
        if decision == "reject" and message:
            decision_dict["message"] = message
        elif decision == "edit" and edited_action:
            decision_dict["edited_action"] = edited_action

        command = Command(resume={"decisions": [decision_dict]})
        namespaced_id = self._get_namespaced_thread_id(thread_id)
        call_config = {"configurable": {"thread_id": namespaced_id}}
        if "config" in kwargs:
            call_config.update(kwargs.pop("config"))
        return await self.graph.ainvoke(command, config=call_config, **kwargs)

    async def aapprove(self, thread_id: str = "default", always_allow: bool = False) -> str:
        """便捷方法：异步批准当前待审工具调用"""
        res = await self.aresume_approval(thread_id=thread_id, decision="approve", always_allow=always_allow)
        return self._extract_content(res)

    async def areject(self, thread_id: str = "default", reason: str = "安全原因被用户拒绝") -> str:
        """便捷方法：异步拒绝当前待审工具调用"""
        res = await self.aresume_approval(thread_id=thread_id, decision="reject", message=reason)
        return self._extract_content(res)

    def __repr__(self) -> str:
        tool_names = [getattr(t, "name", str(t)) for t in self.config.tools]
        return (
            f"<StandaloneAgent name={self.config.name!r} "
            f"provider={self.config.provider!r} "
            f"model={self.config.model_name!r} "
            f"tools={tool_names} "
            f"memory={self.config.enable_memory} "
            f"todos={self.config.enable_todo_list} "
            f"security={self.config.enable_tool_approval}>"
        )


def build_agent(
    config: Optional[Union[AgentConfig, Dict[str, Any]]] = None,
    session_manager: Optional[SessionManager] = None,
    checkpointer: Optional[Any] = None,
    model: Optional[Any] = None,
    **kwargs: Any,
) -> StandaloneAgent:
    """
    Agent 构建工厂函数。
    支持传入 AgentConfig 实例、字典，或通过关键字参数直接配置。
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

    # 1. 初始化 Chat 模型（如果外部未显式传入 model 实例）
    if model is None:
        model = kwargs.pop("model", None) or create_chat_model(agent_config)

    # 2. 如果开启了独立沙箱空间，自动装配沙箱专属工具（代码执行/文件读写）
    sandbox = None
    tools = list(agent_config.tools)
    if agent_config.enable_code_sandbox:
        sandbox = AgentSandbox(
            agent_name=agent_config.name,
            base_dir=agent_config.sandbox_dir,
            timeout_seconds=int(agent_config.timeout),
        )
        tools.extend(sandbox.get_tools())
        agent_config = agent_config.model_copy(update={"tools": tools})

    # 3. 配置持久化记忆 Checkpointer (默认集中存储在 workspace/sessions.db)
    if checkpointer is None and agent_config.enable_memory:
        if session_manager is not None:
            checkpointer = session_manager.get_checkpointer()

    # 4. 装配中间件（待办任务清单、安全审批围栏、上下文压缩等）
    middleware = list(kwargs.pop("middleware", []))

    # 4.1 安全审批围栏中间件 (Tool Approval Fence)
    security_policy = None
    if agent_config.enable_tool_approval:
        security_policy = ToolApprovalPolicy(
            sensitive_tools=agent_config.sensitive_tools,
            initial_whitelist=agent_config.approval_whitelist,
        )
        approval_middleware = create_approval_middleware(policy=security_policy)
        middleware.append(approval_middleware)

    # 4.2 待办任务清单中间件 (Todo Planning)
    if agent_config.enable_todo_list:
        from langchain.agents.middleware import TodoListMiddleware
        middleware.append(TodoListMiddleware())

    # 4.3 智能上下文压缩中间件
    if agent_config.enable_context_compression:
        compressor = TokenBudgetComposedCompressor(
            token_budget=agent_config.context_token_budget,
            max_tool_chars=agent_config.context_tool_max_len,
            keep_recent_messages=agent_config.context_window_keep_messages,
            summary_model=model,
        )
        compression_middleware = ContextCompressionMiddleware(compressor=compressor)
        middleware.append(compression_middleware)

    # 5. 使用 LangChain 核心 create_agent 构建图
    graph = create_agent(
        model=model,
        tools=tools,
        system_prompt=agent_config.system_prompt,
        checkpointer=checkpointer,
        middleware=middleware,
        debug=agent_config.debug,
    )

    return StandaloneAgent(
        config=agent_config,
        graph=graph,
        checkpointer=checkpointer,
        sandbox=sandbox,
        session_manager=session_manager,
        model=model,
        security_policy=security_policy,
    )
