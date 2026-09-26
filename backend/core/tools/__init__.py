"""
核心通用工具子系统 (Core Tools Package)
统一汇集导出：
1. 内置通用工具 (get_current_time, calculate)
2. 任务委派编排工具 (delegate_to_subagent)
3. 长期记忆读写工具 (recall_entity_memory, save_entity_memory, append_user_preference)
"""

from core.tools.builtin import get_current_time, calculate, BUILTIN_TOOLS
from core.tools.delegation import delegate_to_subagent
from core.tools.memory import (
    recall_entity_memory,
    save_entity_memory,
    append_user_preference,
    MEMORY_TOOLS,
)

# 默认全局内置工具列表
DEFAULT_TOOLS = [
    get_current_time,
    calculate,
    delegate_to_subagent,
    recall_entity_memory,
    save_entity_memory,
    append_user_preference,
]

__all__ = [
    "get_current_time",
    "calculate",
    "BUILTIN_TOOLS",
    "delegate_to_subagent",
    "recall_entity_memory",
    "save_entity_memory",
    "append_user_preference",
    "MEMORY_TOOLS",
    "DEFAULT_TOOLS",
]
