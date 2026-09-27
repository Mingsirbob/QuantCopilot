"""
MultiAgent 核心基础底座包 (Core Framework Package)
统一组织并由子包门面导出：
- core.runtime: AgentConfig, build_agent, StandaloneAgent, create_chat_model
- core.memory: SessionManager, LongTermMemoryManager, ContextCompressionMiddleware
- core.sandbox: AgentSandbox
- core.security: ToolApprovalPolicy, create_approval_middleware
- core.tools: DEFAULT_TOOLS, MEMORY_TOOLS, delegate_to_subagent
"""

# 1. 运行时与配置子系统 (core.runtime)
from core.runtime import (
    AgentConfig,
    build_agent,
    StandaloneAgent,
    create_chat_model,
)

# 2. 记忆子系统 (core.memory)
from core.memory import (
    SessionManager,
    LongTermMemoryManager,
    ContextCompressionMiddleware,
    TokenBudgetComposedCompressor,
    compact_tool_messages,
    count_tokens,
    trim_history,
)

# 3. 沙箱子系统 (core.sandbox)
from core.sandbox import AgentSandbox

# 4. 安全审批子系统 (core.security)
from core.security import ToolApprovalPolicy, create_approval_middleware

# 5. 工具子系统 (core.tools)
from core.tools import (
    DEFAULT_TOOLS,
    MEMORY_TOOLS,
    get_current_time,
    calculate,
    delegate_to_subagent,
    recall_entity_memory,
    save_entity_memory,
    append_user_preference,
    schedule_agent_task,
    trigger_registered_task,
    list_scheduled_jobs,
    inspect_scheduler_ledger,
    SCHEDULER_TOOLS,
)

__all__ = [
    # runtime
    "AgentConfig",
    "build_agent",
    "StandaloneAgent",
    "create_chat_model",
    # memory
    "SessionManager",
    "LongTermMemoryManager",
    "ContextCompressionMiddleware",
    "TokenBudgetComposedCompressor",
    "compact_tool_messages",
    "count_tokens",
    "trim_history",
    # sandbox & security
    "AgentSandbox",
    "ToolApprovalPolicy",
    "create_approval_middleware",
    # tools
    "DEFAULT_TOOLS",
    "MEMORY_TOOLS",
    "SCHEDULER_TOOLS",
    "get_current_time",
    "calculate",
    "delegate_to_subagent",
    "recall_entity_memory",
    "save_entity_memory",
    "append_user_preference",
    "schedule_agent_task",
    "trigger_registered_task",
    "list_scheduled_jobs",
    "inspect_scheduler_ledger",
]
