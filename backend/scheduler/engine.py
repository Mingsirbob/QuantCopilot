"""
核心调度引擎 (engine.py)
基于 APScheduler AsyncIOScheduler 实现统一异步事件循环调度。
集成任务账本持久化、交易时段感知过滤与声明式 YAML 批量加载能力。
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union
import yaml

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .base import BaseTask, ExecutionContext, TaskResult
from .filters import TradingHoursFilter
from .ledger import TaskLedger
from .tasks import AgentTask, ModuleTask, PipelineTask, ScriptTask

logger = logging.getLogger("backend.scheduler")


class TaskScheduler:
    """
    统一异步任务调度引擎。
    - 统一管理 AgentTask、ModuleTask、ScriptTask 与 PipelineTask
    - 支持 Cron、时间间隔与单次定时
    - 原生集成 TaskLedger 数据库审计
    - 支持 YAML 声明式配置批量加载
    """

    def __init__(self, ledger_db_path: Optional[str | Path] = None):
        self.scheduler = AsyncIOScheduler()
        self.tasks: Dict[str, BaseTask] = {}
        self.ledger = TaskLedger(ledger_db_path)
        self.trading_filter = TradingHoursFilter()
        self._is_running = False

    def register_task(self, task: BaseTask):
        """注册可调度的任务对象"""
        self.tasks[task.name] = task
        logger.info(f"📋 [TaskScheduler] 已注册任务: {task.name} ({task.task_type})")

    def get_task(self, name: str) -> Optional[BaseTask]:
        """获取已注册的任务"""
        return self.tasks.get(name)

    async def _execute_job_wrapper(
        self,
        task: BaseTask,
        params: Optional[Dict[str, Any]] = None,
        filter_trading_hours: bool = False,
    ) -> TaskResult:
        """任务执行全生命周期包装器 (环境感知、账本记录、异常熔断)"""
        now = datetime.now()

        # 1. 交易时段检测
        if filter_trading_hours and not self.trading_filter.is_trading_time(now):
            logger.info(f"⏸️ [TaskScheduler] 任务 [{task.name}] 触发，但当前非交易时段，自动跳过。")
            skip_res = TaskResult(
                task_name=task.name,
                success=True,
                data="SKIPPED_OUTSIDE_TRADING_HOURS",
                start_time=now,
                end_time=now,
                metadata={"skipped": True, "reason": "outside_trading_hours"},
            )
            await self.ledger.record_start(
                run_id=f"skip_{int(now.timestamp())}",
                task_name=task.name,
                task_type=task.task_type,
                params=params,
            )
            await self.ledger.record_finish(
                run_id=f"skip_{int(now.timestamp())}",
                status="SKIPPED",
                result_data="非交易时段自动跳过",
                duration_seconds=0.0,
            )
            return skip_res

        # 2. 准备执行上下文
        context = ExecutionContext(
            task_name=task.name,
            params=params or {},
            logger=logger,
        )

        # 3. 记录任务启动到账本
        await self.ledger.record_start(
            run_id=context.run_id,
            task_name=task.name,
            task_type=task.task_type,
            params=context.params,
        )

        logger.info(f"🔔 [TaskScheduler] 触发执行任务 [{task.name}] (RunID: {context.run_id})...")

        # 4. 执行具体任务
        try:
            result = await task.run(context)
        except Exception as e:
            logger.error(f"❌ [TaskScheduler] 任务 [{task.name}] 发生未捕获异常: {e}", exc_info=True)
            result = TaskResult(
                task_name=task.name,
                success=False,
                error=str(e),
                start_time=now,
                end_time=datetime.now(),
            )

        # 5. 记录执行产物与状态到账本
        status_str = "SUCCESS" if result.success else "FAILED"
        await self.ledger.record_finish(
            run_id=context.run_id,
            status=status_str,
            result_data=result.data,
            error_message=result.error,
            duration_seconds=result.duration_seconds,
            metadata=result.metadata,
        )

        if result.success:
            logger.info(f"✨ [TaskScheduler] 任务 [{task.name}] 执行完毕 ({result.duration_seconds}s)")
            if task.task_type == "agent" and isinstance(result.data, str):
                print(f"\n{'=' * 75}\n🤖 【Agent 研报/产出汇报】(任务: {task.name}):\n\n{result.data}\n{'=' * 75}\n")
        else:
            logger.warning(f"⚠️ [TaskScheduler] 任务 [{task.name}] 执行失败: {result.error}")

        return result

    def add_cron_job(
        self,
        task_name: str,
        cron_expr: str,
        job_id: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        filter_trading_hours: bool = False,
    ):
        """添加 Cron 定时任务 (标准 5 位表达式: 分 时 日 月 周)"""
        task = self.tasks.get(task_name)
        if not task:
            raise KeyError(f"未找到名称为 '{task_name}' 的已注册任务")

        trigger = CronTrigger.from_crontab(cron_expr)
        jid = job_id or f"cron_{task_name}"

        async def _job():
            await self._execute_job_wrapper(task, params, filter_trading_hours)

        self.scheduler.add_job(_job, trigger=trigger, id=jid, replace_existing=True)
        logger.info(f"⏰ [TaskScheduler] 已配置 Cron 任务 [{task_name}] -> '{cron_expr}' (JobID: {jid})")

    def add_interval_job(
        self,
        task_name: str,
        seconds: int,
        job_id: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        filter_trading_hours: bool = False,
    ):
        """添加固定时间间隔触发任务"""
        task = self.tasks.get(task_name)
        if not task:
            raise KeyError(f"未找到名称为 '{task_name}' 的已注册任务")

        trigger = IntervalTrigger(seconds=seconds)
        jid = job_id or f"interval_{task_name}"

        async def _job():
            await self._execute_job_wrapper(task, params, filter_trading_hours)

        self.scheduler.add_job(_job, trigger=trigger, id=jid, replace_existing=True)
        logger.info(f"⏱️ [TaskScheduler] 已配置 Interval 任务 [{task_name}] -> 每 {seconds} 秒 (JobID: {jid})")

    def add_date_job(
        self,
        task_name: str,
        run_date: datetime,
        job_id: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        filter_trading_hours: bool = False,
    ) -> str:
        """在未来的指定绝对时间点单次执行任务 (DateTrigger)"""
        task = self.tasks.get(task_name)
        if not task:
            raise KeyError(f"未找到名称为 '{task_name}' 的已注册任务")

        trigger = DateTrigger(run_date=run_date)
        jid = job_id or f"date_{task_name}_{int(run_date.timestamp())}"

        async def _job():
            await self._execute_job_wrapper(task, params, filter_trading_hours)

        self.scheduler.add_job(_job, trigger=trigger, id=jid, replace_existing=True)
        logger.info(f"⏳ [TaskScheduler] 已配置定点延时任务 [{task_name}] -> 将于 {run_date.strftime('%Y-%m-%d %H:%M:%S')} 执行 (JobID: {jid})")
        return jid

    def schedule_after(
        self,
        task_name: str,
        delay_seconds: int,
        job_id: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        filter_trading_hours: bool = False,
    ) -> str:
        """在指定的延迟秒数后单次执行任务 (如 300 秒后)"""
        from datetime import timedelta
        target_time = datetime.now() + timedelta(seconds=delay_seconds)
        return self.add_date_job(
            task_name=task_name,
            run_date=target_time,
            job_id=job_id,
            params=params,
            filter_trading_hours=filter_trading_hours,
        )

    def schedule_agent_after(
        self,
        agent_name: str,
        prompt: str,
        delay_seconds: int,
        task_name: Optional[str] = None,
        thread_id: Optional[str] = None,
    ) -> str:
        """
        便捷方法：无需预先定义任务，动态创建一个单次 Agent 延时任务并在 N 秒后执行
        """
        import uuid
        tname = task_name or f"dynamic_agent_{agent_name}_{uuid.uuid4().hex[:6]}"
        agent_task = AgentTask(
            name=tname,
            agent_name=agent_name,
            prompt_template=prompt,
            thread_id=thread_id,
        )
        self.register_task(agent_task)
        return self.schedule_after(task_name=tname, delay_seconds=delay_seconds)

    async def trigger_now(
        self, task_name: str, params: Optional[Dict[str, Any]] = None
    ) -> TaskResult:
        """立刻手动或编程式单次执行一次任务"""
        task = self.tasks.get(task_name)
        if not task:
            raise KeyError(f"未找到名称为 '{task_name}' 的已注册任务")

        return await self._execute_job_wrapper(task, params, filter_trading_hours=False)

    def load_from_yaml(self, yaml_path: Union[str, Path]):
        """
        从 YAML 配置文件中批量加载声明式任务与调度计划
        """
        path = Path(yaml_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"配置文件不存在: {path}")

        with open(path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}

        schedules = cfg.get("schedules", [])
        for item in schedules:
            name = item.get("name")
            t_type = item.get("type")
            trigger_str = item.get("trigger", "")
            filter_trading = item.get("filter_trading_hours", False)
            params = item.get("params", {})

            # 1. 动态构建 Task 对象
            task_obj = None
            if t_type == "agent":
                task_obj = AgentTask(
                    name=name,
                    agent_name=item.get("agent_name"),
                    prompt_template=item.get("prompt", ""),
                    thread_id=item.get("thread_id"),
                )
            elif t_type == "module":
                task_obj = ModuleTask(
                    name=name,
                    target=item.get("target"),
                    default_params=params,
                )
            elif t_type == "script":
                task_obj = ScriptTask(
                    name=name,
                    script_path=item.get("script_path"),
                    args=item.get("args", []),
                )
            elif t_type == "pipeline":
                # 流水线任务
                sub_step_tasks = []
                for sub_item in item.get("steps", []):
                    s_name = sub_item.get("name")
                    s_type = sub_item.get("type")
                    if s_type == "module":
                        sub_step_tasks.append(
                            ModuleTask(name=s_name, target=sub_item.get("target"), default_params=sub_item.get("params", {}))
                        )
                    elif s_type == "agent":
                        sub_step_tasks.append(
                            AgentTask(name=s_name, agent_name=sub_item.get("agent_name"), prompt_template=sub_item.get("prompt", ""))
                        )
                    elif s_type == "script":
                        sub_step_tasks.append(
                            ScriptTask(name=s_name, script_path=sub_item.get("script_path"))
                        )
                task_obj = PipelineTask(name=name, tasks=sub_step_tasks)

            if task_obj:
                self.register_task(task_obj)

                # 2. 解析 Trigger 并注册 Job
                if trigger_str.startswith("cron:"):
                    cron_expr = trigger_str.replace("cron:", "").strip()
                    self.add_cron_job(
                        name, cron_expr, params=params, filter_trading_hours=filter_trading
                    )
                elif trigger_str.startswith("interval:"):
                    secs = int(trigger_str.replace("interval:", "").strip())
                    self.add_interval_job(
                        name, secs, params=params, filter_trading_hours=filter_trading
                    )

        logger.info(f"📂 [TaskScheduler] 成功从 {path.name} 加载 {len(schedules)} 项定时任务")

    def start(self):
        """启动后台调度器"""
        if not self._is_running:
            self.scheduler.start()
            self._is_running = True
            logger.info("🚀 [TaskScheduler] 调度主引擎已启动 (运行中)")

    def shutdown(self, wait: bool = False):
        """关闭调度器"""
        if self._is_running:
            self.scheduler.shutdown(wait=wait)
            self._is_running = False
            logger.info("🛑 [TaskScheduler] 调度主引擎已安全关闭")
