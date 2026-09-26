"""
核心安全审批与围栏子系统 (Core Security Package)
提供针对敏感工具（代码执行、写文件等）的人机协同安全拦截 (Human-In-The-Loop) 与动态免审批白名单。
"""

from core.security.approval import ToolApprovalPolicy, create_approval_middleware

__all__ = ["ToolApprovalPolicy", "create_approval_middleware"]
