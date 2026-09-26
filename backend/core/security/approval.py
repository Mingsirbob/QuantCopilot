"""
安全审批围栏模块 (Security & Tool Approval Module)

实现对智能体敏感操作（如代码执行 execute_python_code、写文件 write_file、敏感外部调用等）的安全防护与人类介入审批 (Human-In-The-Loop)。

核心能力：
1. 动态敏感工具拦截：可配置敏感工具清单，模型调用时自动中断（Interrupt）挂起。
2. 多样化审批决策：
   - approve: 批准执行
   - reject: 拒绝执行并向大模型反馈拒绝原因
   - edit: 人工修正参数后执行
   - approve_always: 批准并将该工具加入会话白名单（“记住选择/不再询问”）
3. 动态白名单策略 (ToolApprovalPolicy)：支持会话级与全局免审批白名单。
4. 原生 AgentMiddleware 封装 (create_approval_middleware)。
"""

import json
import logging
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Union
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain.agents.middleware.human_in_the_loop import InterruptOnConfig
from langgraph.types import Command

logger = logging.getLogger("core.security")


class ToolApprovalPolicy:
    """
    工具安全审批策略管理器。
    维护敏感工具清单、会话级动态白名单（不再询问）与判定逻辑。
    """

    def __init__(
        self,
        sensitive_tools: Optional[Sequence[str]] = None,
        initial_whitelist: Optional[Sequence[str]] = None,
    ):
        self.sensitive_tools: Set[str] = set(
            sensitive_tools or ["execute_python_code", "write_file"]
        )
        self.global_whitelist: Set[str] = set(initial_whitelist or [])
        # 会话级白名单：{thread_id: set(tool_names)}
        self.session_whitelists: Dict[str, Set[str]] = {}

    def is_tool_sensitive(self, tool_name: str) -> bool:
        """判断工具是否在敏感工具保护清单中"""
        return tool_name in self.sensitive_tools

    def is_tool_whitelisted(self, tool_name: str, thread_id: Optional[str] = None) -> bool:
        """检查工具是否在全局或会话级白名单中（免审批）"""
        if tool_name in self.global_whitelist:
            return True
        if thread_id:
            pure_id = thread_id.split(":")[-1] if ":" in thread_id else thread_id
            if thread_id in self.session_whitelists and tool_name in self.session_whitelists[thread_id]:
                return True
            if pure_id in self.session_whitelists and tool_name in self.session_whitelists[pure_id]:
                return True
        return False

    def add_to_whitelist(self, tool_name: str, thread_id: Optional[str] = None) -> None:
        """将工具加入白名单（如用户勾选“不再询问”）"""
        if thread_id:
            pure_id = thread_id.split(":")[-1] if ":" in thread_id else thread_id
            for tid in (thread_id, pure_id):
                if tid not in self.session_whitelists:
                    self.session_whitelists[tid] = set()
                self.session_whitelists[tid].add(tool_name)
            logger.info(f"会话 [{thread_id}] 将工具 '{tool_name}' 加入免审批白名单（不再询问）")
        else:
            self.global_whitelist.add(tool_name)
            logger.info(f"全局将工具 '{tool_name}' 加入免审批白名单")

    def remove_from_whitelist(self, tool_name: str, thread_id: Optional[str] = None) -> None:
        """从白名单移除工具"""
        if thread_id:
            pure_id = thread_id.split(":")[-1] if ":" in thread_id else thread_id
            if thread_id in self.session_whitelists:
                self.session_whitelists[thread_id].discard(tool_name)
            if pure_id in self.session_whitelists:
                self.session_whitelists[pure_id].discard(tool_name)
        self.global_whitelist.discard(tool_name)

    def should_interrupt(self, request: Any) -> bool:
        """
        供 HumanInTheLoopMiddleware 动态调用的判定钩子：
        若返回 True 则触发安全拦截挂起；返回 False 则放行。
        """
        tool_call = getattr(request, "tool_call", {})
        tool_name = tool_call.get("name", "")

        # 1. 如果并非敏感工具，直接放行
        if not self.is_tool_sensitive(tool_name):
            return False

        # 2. 从 request.runtime.config 中准确提取当前会话 thread_id
        thread_id = None
        runtime = getattr(request, "runtime", None)
        if runtime and hasattr(runtime, "config") and isinstance(runtime.config, dict):
            configurable = runtime.config.get("configurable", {})
            thread_id = configurable.get("thread_id")
            if not thread_id:
                metadata = runtime.config.get("metadata", {})
                thread_id = metadata.get("thread_id")

        if not thread_id:
            state = getattr(request, "state", {})
            if isinstance(state, dict):
                thread_id = state.get("thread_id")

        # 3. 检查白名单
        if self.is_tool_whitelisted(tool_name, thread_id):
            logger.debug(f"工具 '{tool_name}' 在免审批白名单中，自动放行。")
            return False

        logger.info(f"触发安全审批拦截：工具 '{tool_name}' 需要人类介入审批。")
        return True


def create_approval_middleware(
    policy: ToolApprovalPolicy,
    description_prefix: str = "【安全审批警告】智能体请求执行敏感工具，需要人类审批",
) -> HumanInTheLoopMiddleware:
    """
    工厂函数：根据安全策略构建 LangChain 原生 HumanInTheLoopMiddleware。
    """
    interrupt_on: Dict[str, Union[bool, InterruptOnConfig]] = {}
    for tool_name in policy.sensitive_tools:
        interrupt_on[tool_name] = InterruptOnConfig(
            allowed_decisions=["approve", "edit", "reject", "respond"],
            when=policy.should_interrupt,
        )

    return HumanInTheLoopMiddleware(
        interrupt_on=interrupt_on,
        description_prefix=description_prefix,
    )
