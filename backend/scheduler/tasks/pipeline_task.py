"""
复合流水线任务适配器 (pipeline_task.py)
实现多任务有序串联 (例如: 模块计算指标 -> 脚本拉取新闻 -> Agent 综合写研报)。
上游步骤的输出数据自动管道式透传至下游步骤上下文。
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from ..base import BaseTask, ExecutionContext, TaskResult


class PipelineTask(BaseTask):
    """
    负责按顺序编排执行一组任务。
    任一关键步骤失败则中断返回；前序任务的成功产物将以 `{task_name}_output` 注入上下文，供后续 Agent 或模块使用。
    """

    def __init__(
        self,
        name: str,
        tasks: List[BaseTask],
        stop_on_error: bool = True,
        description: str = "",
    ):
        super().__init__(
            name=name,
            description=description or f"流水线任务 (包含 {len(tasks)} 个步骤)",
            task_type="pipeline",
        )
        self.tasks = tasks
        self.stop_on_error = stop_on_error

    async def run(self, context: ExecutionContext) -> TaskResult:
        start_time = datetime.now()
        context.logger.info(f"🔄 [PipelineTask] 启动流水线 [{self.name}] (步骤数: {len(self.tasks)})...")

        step_logs: List[Dict[str, Any]] = []

        for idx, sub_task in enumerate(self.tasks, 1):
            context.logger.info(f"  └── 正在执行步骤 [{idx}/{len(self.tasks)}]: {sub_task.name} ({sub_task.task_type})")
            
            sub_res = await sub_task.run(context)
            step_logs.append({
                "step": idx,
                "task_name": sub_task.name,
                "task_type": sub_task.task_type,
                "success": sub_res.success,
                "duration": sub_res.duration_seconds,
                "error": sub_res.error,
            })

            if not sub_res.success and self.stop_on_error:
                end_time = datetime.now()
                err_msg = f"步骤 [{sub_task.name}] 失败: {sub_res.error}"
                context.logger.error(f"❌ [PipelineTask] 流水线 [{self.name}] 中断: {err_msg}")
                return TaskResult(
                    task_name=self.name,
                    success=False,
                    error=err_msg,
                    data={"steps": step_logs},
                    start_time=start_time,
                    end_time=end_time,
                    metadata={"failed_step": sub_task.name},
                )

            # 成功产物透传进入共享上下文字典
            context.shared_data[f"{sub_task.name}_output"] = sub_res.data
            context.shared_data["last_output"] = sub_res.data

        end_time = datetime.now()
        context.logger.info(f"✅ [PipelineTask] 流水线 [{self.name}] 全部步骤执行完毕。")
        return TaskResult(
            task_name=self.name,
            success=True,
            data={"steps": step_logs, "final_output": context.shared_data.get("last_output")},
            start_time=start_time,
            end_time=end_time,
            metadata={"total_steps": len(self.tasks)},
        )
