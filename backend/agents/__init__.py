"""
Agents 模板仓库包
管理与加载各个业务领域的独立 Agent 模板。
"""

from agents.loader import AgentTemplateLoader, load_agent

__all__ = ["AgentTemplateLoader", "load_agent"]
