"""
Agent 任务适配器 (agent_task.py)
动态加载 workspace/agents/<agent_name> 模板并执行异步推理。
"""

from datetime import datetime
from typing import Any, Dict, Optional
from ..base import BaseTask, ExecutionContext, TaskResult
from ..filters import SilenceChecker


class AgentTask(BaseTask):
    """
    负责调度具体 Agent 的任务封装。
    支持动态模板渲染 Prompt、指定会话 ID（支持连续记忆巡检）以及自动检测 HEARTBEAT_OK 静默响应。
    """

    def __init__(
        self,
        name: str,
        agent_name: str,
        prompt_template: str,
        thread_id: Optional[str] = None,
        check_silence: bool = True,
        description: str = "",
    ):
        super().__init__(
            name=name,
            description=description or f"调度 Agent [{agent_name}] 任务",
            task_type="agent",
        )
        self.agent_name = agent_name
        self.prompt_template = prompt_template
        self.thread_id = thread_id
        self.check_silence = check_silence

    async def run(self, context: ExecutionContext) -> TaskResult:
        start_time = datetime.now()
        context.logger.info(f"🚀 [AgentTask] 正在启动 Agent [{self.agent_name}] (任务: {self.name})...")

        try:
            # 延迟引入，保证不产生循环依赖并利用项目统一加载器
            from agents.loader import load_agent

            agent = await load_agent(self.agent_name)

            # 组装格式化 Prompt 上下文（合并 params 与 shared_data）
            format_vars = {**context.shared_data, **context.params}
            try:
                prompt = self.prompt_template.format(**format_vars)
            except KeyError as ke:
                # 若缺少占位符，降级为原模板输出并告警
                context.logger.warning(f"⚠️ [AgentTask] 模板格式化缺少参数 {ke}，使用原始提示词")
                prompt = self.prompt_template

            # 会话 ID：优先使用显式指定的 thread_id（便于连续记忆），未指定则动态生成
            active_thread_id = self.thread_id or f"sched_{self.name}_{context.run_id}"

            # 执行异步推理
            response = await agent.arun(prompt, thread_id=active_thread_id)

            end_time = datetime.now()
            is_silent = False
            if self.check_silence and isinstance(response, str):
                is_silent = SilenceChecker.is_silent(response)

            metadata = {
                "agent_name": self.agent_name,
                "thread_id": active_thread_id,
                "is_silent": is_silent,
            }

            if is_silent:
                context.logger.info(f"🔕 [AgentTask] Agent [{self.agent_name}] 返回 HEARTBEAT_OK，触发自动静默。")

            return TaskResult(
                task_name=self.name,
                success=True,
                data=response,
                start_time=start_time,
                end_time=end_time,
                metadata=metadata,
            )

        except Exception as e:
            end_time = datetime.now()
            context.logger.error(f"❌ [AgentTask] Agent [{self.agent_name}] 执行失败: {e}", exc_info=True)
            return TaskResult(
                task_name=self.name,
                success=False,
                error=str(e),
                start_time=start_time,
                end_time=end_time,
                metadata={"agent_name": self.agent_name},
            )
