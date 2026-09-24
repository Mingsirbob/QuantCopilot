"""
Agent 专属独立工作空间沙箱模块 (方案一：工作目录隔离 + 本地 Python 执行器)
为每个 Agent 实例分配独立的目录空间，并提供安全受控的代码执行与文件读写能力。
"""

import os
import sys
import subprocess
from pathlib import Path
from typing import List, Optional, Union
from langchain_core.tools import BaseTool, tool


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
            # 优先从环境变量获取，默认指向项目根目录下的 workspace/sandboxes/{agent_name}
            env_ws = os.getenv("WORKSPACE_DIR")
            if env_ws:
                root_ws = Path(env_ws).resolve()
            else:
                project_root = Path(__file__).resolve().parent.parent.parent
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
        sandbox = self

        @tool
        def execute_python_code(code: str) -> str:
            """
            在当前 Agent 的专属隔离工作空间中执行 Python 代码。
            工作目录(CWD)已锁定为当前沙箱，可自由使用 Python 运行数学计算、数据处理（如 pandas/numpy）以及读写本目录文件。
            :param code: 待执行的完整 Python 代码字符串
            :return: 标准输出(stdout)或错误堆栈(stderr)
            """
            try:
                # 使用当前 Python 运行环境（包含虚拟环境已安装的三方库），并在专属沙箱目录中执行
                proc = subprocess.run(
                    [sys.executable, "-c", code],
                    cwd=str(sandbox.sandbox_dir),
                    capture_output=True,
                    text=True,
                    timeout=sandbox.timeout_seconds,
                    encoding="utf-8",
                    errors="replace",
                )
                output = proc.stdout or ""
                if proc.stderr:
                    output += f"\n[Stderr/错误信息]:\n{proc.stderr}"
                if proc.returncode != 0:
                    output += f"\n[进程退出码]: {proc.returncode}"
                return output if output.strip() else "[代码执行成功，无终端标准输出]"
            except subprocess.TimeoutExpired:
                return f"执行失败: 代码执行超时 (超过 {sandbox.timeout_seconds} 秒)，已被系统强制终止。"
            except Exception as e:
                return f"执行失败: {e}"

        @tool
        def write_file(file_path: str, content: str) -> str:
            """
            在当前 Agent 的专属工作空间内创建或覆盖写入文件。
            :param file_path: 相对沙箱目录的文件路径，例如 'result.json' 或 'reports/summary.md'
            :param content: 文件内容
            """
            try:
                target = sandbox._resolve_safe_path(file_path)
                target.parent.mkdir(parents=True, exist_ok=True)
                with open(target, "w", encoding="utf-8") as f:
                    f.write(content)
                return f"成功: 已将内容写入工作空间文件 '{file_path}'"
            except Exception as e:
                return f"写入文件失败: {e}"

        @tool
        def read_file(file_path: str) -> str:
            """
            读取当前 Agent 专属工作空间内的文件内容。
            :param file_path: 相对沙箱目录的文件路径
            """
            try:
                target = sandbox._resolve_safe_path(file_path)
                if not target.exists():
                    return f"错误: 文件 '{file_path}' 在当前工作空间中不存在。"
                with open(target, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception as e:
                return f"读取文件失败: {e}"

        @tool
        def list_files(sub_directory: str = "") -> str:
            """
            列出当前 Agent 专属工作空间中的所有文件和文件夹。
            :param sub_directory: 相对沙箱目录的子文件夹路径，默认为当前沙箱根目录
            """
            try:
                target = sandbox._resolve_safe_path(sub_directory)
                if not target.exists() or not target.is_dir():
                    return f"错误: 目录 '{sub_directory}' 不存在。"
                items = []
                for p in sorted(target.iterdir()):
                    tag = "[目录]" if p.is_dir() else f"[{p.stat().st_size} 字节]"
                    items.append(f"{tag} {p.name}")
                return "\n".join(items) if items else "[当前工作空间目录为空]"
            except Exception as e:
                return f"列出文件失败: {e}"

        return [execute_python_code, write_file, read_file, list_files]
