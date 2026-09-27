"""
独立脚本/进程任务适配器 (script_task.py)
用于异步拉起独立的 Python 脚本、外部抓取程序或 Shell 脚本。
"""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from ..base import BaseTask, ExecutionContext, TaskResult


class ScriptTask(BaseTask):
    """
    负责执行外部独立脚本或 CLI 命令的任务封装。
    采用 asyncio 异步非阻塞子进程，支持设定运行工作目录、超时控制以及捕获标准输出。
    """

    def __init__(
        self,
        name: str,
        script_path: str,
        args: Optional[List[str]] = None,
        cwd: Optional[str | Path] = None,
        timeout: Optional[float] = 120.0,
        description: str = "",
    ):
        super().__init__(
            name=name,
            description=description or f"外部脚本任务 [{script_path}]",
            task_type="script",
        )
        self.script_path = script_path
        self.args = args or []
        self.cwd = cwd
        self.timeout = timeout

    async def run(self, context: ExecutionContext) -> TaskResult:
        start_time = datetime.now()
        context.logger.info(f"📜 [ScriptTask] 正在启动外部脚本 [{self.name}] ({self.script_path})...")

        try:
            # 解析脚本路径：若为相对路径，优先尝试相对项目根目录解析
            project_root = Path(__file__).resolve().parents[3]
            target_path = Path(self.script_path)
            if not target_path.is_absolute():
                target_path = (project_root / self.script_path).resolve()

            if not target_path.exists():
                raise FileNotFoundError(f"指定的脚本文件不存在: {target_path}")

            # 默认使用当前环境的 Python 解释器
            cmd = [sys.executable, str(target_path)] + [str(a) for a in self.args]
            work_dir = Path(self.cwd).resolve() if self.cwd else project_root

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(work_dir),
                env=os.environ.copy(),
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=self.timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                raise TimeoutError(f"脚本执行超时 (超过 {self.timeout} 秒)")

            stdout_text = stdout_bytes.decode("utf-8", errors="replace").strip()
            stderr_text = stderr_bytes.decode("utf-8", errors="replace").strip()

            end_time = datetime.now()

            if proc.returncode == 0:
                return TaskResult(
                    task_name=self.name,
                    success=True,
                    data=stdout_text,
                    start_time=start_time,
                    end_time=end_time,
                    metadata={"returncode": 0, "script_path": str(target_path)},
                )
            else:
                return TaskResult(
                    task_name=self.name,
                    success=False,
                    error=f"退出码 {proc.returncode}。错误输出: {stderr_text or stdout_text}",
                    start_time=start_time,
                    end_time=end_time,
                    metadata={"returncode": proc.returncode, "script_path": str(target_path)},
                )

        except Exception as e:
            end_time = datetime.now()
            context.logger.error(f"❌ [ScriptTask] 脚本 [{self.name}] 执行异常: {e}", exc_info=True)
            return TaskResult(
                task_name=self.name,
                success=False,
                error=str(e),
                start_time=start_time,
                end_time=end_time,
                metadata={"script_path": self.script_path},
            )
