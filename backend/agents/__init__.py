"""
Agents 模板仓库包
管理与加载各个业务领域的独立 Agent 模板。
"""

from agents.loader import AgentTemplateLoader, load_agent


def list_available_agents(base_agents_dir=None):
    """查询并列出当前工作区中所有已配置的 Agent 列表"""
    return AgentTemplateLoader(base_agents_dir).list_available_agents()


__all__ = ["AgentTemplateLoader", "load_agent", "list_available_agents"]
