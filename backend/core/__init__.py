"""
Agent 模块包接口
提供快速构建独立 Agent 的入口与配置工具。
"""

from core.config import AgentConfig
from core.builder import build_agent, StandaloneAgent
from core.tools import DEFAULT_TOOLS, get_current_time, calculate

__all__ = [
    "AgentConfig",
    "build_agent",
    "StandaloneAgent",
    "DEFAULT_TOOLS",
    "get_current_time",
    "calculate",
]
