"""
Agent 专属独立工作空间沙箱执行器模块
为每个 Agent 实例分配独立的目录空间，并提供安全受控的代码执行与文件读写能力。
"""

import os
import sys
import subprocess
from pathlib import Path
from typing import List, Optional, Union
from langchain_core.tools import BaseTool


class AgentSandbox:
    """
    Agent 独立工作空间沙箱类。
    每个 Agent 拥有自己专属的目录，所有代码执行与文件读写均严格限定在该目录下。
    """

    def __init__(
        self,
        agent_name: str,
        base_dir: Optional[Union[str, Path]] = None,
        timeout_seconds: int = 30,
    ):
        self.agent_name = agent_name
        self.timeout_seconds = timeout_seconds

        if base_dir is not None:
            self.sandbox_dir = Path(base_dir).resolve() / agent_name
        else:
            env_ws = os.getenv("WORKSPACE_DIR")
            if env_ws:
                root_ws = Path(env_ws).resolve()
            else:
                project_root = Path(__file__).resolve().parents[3]
                root_ws = project_root / "workspace"

            self.sandbox_dir = (root_ws / "runtime" / "sandboxes" / agent_name).resolve()

            # 平滑兼容：若旧位置 workspace/sandboxes/{agent_name} 存在而新位置尚未建立，自动迁移
            old_sandbox_dir = (root_ws / "sandboxes" / agent_name).resolve()
            if old_sandbox_dir.exists() and not self.sandbox_dir.exists():
                import shutil
                self.sandbox_dir.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(old_sandbox_dir), str(self.sandbox_dir))

        # 确保沙箱目录存在
        self.sandbox_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_safe_path(self, relative_path: str) -> Path:
        """安全路径校验，杜绝通过 ../ 越界访问沙箱之外的宿主机文件"""
        target = (self.sandbox_dir / relative_path).resolve()
        try:
            target.relative_to(self.sandbox_dir)
        except ValueError:
            raise PermissionError(f"安全违规: 禁止越界访问沙箱外部路径 '{relative_path}'！")
        return target

    def get_tools(self) -> List[BaseTool]:
        """生成并返回一组绑定到当前沙箱上下文的 LangChain 动态工具"""
        from core.sandbox.tools import create_sandbox_tools
        return create_sandbox_tools(self)
