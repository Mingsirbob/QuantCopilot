"""
调度器 HTTP API 服务端 (server.py)
基于 FastAPI 构建轻量级调度中枢服务端。
支持远程/跨终端提交任务、动态预约延时 Agent、查询任务清单与账本历史。
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from .base import TaskResult
from .engine import TaskScheduler
from .ledger import TaskLedger

logger = logging.getLogger("backend.scheduler.server")


# =====================================================================
# 1. 契约请求与响应数据模型 (Pydantic)
# =====================================================================

class SubmitAgentRequest(BaseModel):
    agent_name: str = Field(..., description="目标智能体名称 (对应 workspace/agents/ 下目录名)")
    prompt: str = Field(..., description="执行提示词或任务指令")
    delay_seconds: int = Field(default=0, ge=0, description="延时执行秒数 (0 代表立刻异步触发)")
    thread_id: Optional[str] = Field(default=None, description="会话 ID (可选，不传自动生成)")


class TriggerTaskRequest(BaseModel):
    task_name: str = Field(..., description="已注册的任务名称 (如 quant_indicator_calc)")
    params: Optional[Dict[str, Any]] = Field(default=None, description="传递给任务的运行时参数")


class ScheduleDelayedTaskRequest(BaseModel):
    task_name: str = Field(..., description="已注册的任务名称")
    delay_seconds: int = Field(..., gt=0, description="延时秒数")
    params: Optional[Dict[str, Any]] = Field(default=None, description="运行时参数")


class ApiResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Any] = None


# =====================================================================
# 2. FastAPI 服务工厂
# =====================================================================

def create_scheduler_app(
    scheduler: Optional[TaskScheduler] = None,
    config_path: Optional[str | Path] = None,
) -> FastAPI:
    """创建并配置 FastAPI 调度应用实例"""

    # 若未传入调度器实例，则自动初始化
    if scheduler is None:
        scheduler = TaskScheduler()

    # 默认加载 workspace/schedules/schedule.yaml
    if config_path:
        cfg = Path(config_path).resolve()
        if cfg.exists():
            scheduler.load_from_yaml(cfg)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """服务生命周期管理：启动调度引擎，并在退出时安全释放连接"""
        logger.info("🚀 [SchedulerServer] 正在启动底层调度引擎与时钟...")
        scheduler.start()
        yield
        logger.info("🛑 [SchedulerServer] 正在关闭底层调度引擎...")
        scheduler.shutdown(wait=False)
        try:
            from core.memory import SessionManager
            if SessionManager._instance:
                await SessionManager._instance.close()
        except Exception:
            pass

    app = FastAPI(
        title="MultiAgent 任务调度中枢 API",
        description="支持跨进程/跨终端提交定时与延时任务、Agent 编排与历史账本查询",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.state.scheduler = scheduler


    # 挂载 CORS 跨域中间件，支持 React / Vite 前端看板交互
    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


    # -----------------------------------------------------------------
    # API 路由
    # -----------------------------------------------------------------

    @app.get("/health", response_model=ApiResponse)
    async def health_check():
        """健康检查"""
        jobs_count = len(scheduler.scheduler.get_jobs())
        tasks_count = len(scheduler.tasks)
        return ApiResponse(
            success=True,
            message="调度中枢服务运行正常",
            data={
                "status": "RUNNING",
                "registered_tasks_count": tasks_count,
                "active_jobs_count": jobs_count,
                "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
        )

    @app.get("/api/tasks", response_model=ApiResponse)
    async def list_tasks():
        """获取所有已注册任务与当前激活的定时作业"""
        registered = [
            {
                "name": t.name,
                "type": t.task_type,
                "description": t.description,
            }
            for t in scheduler.tasks.values()
        ]
        active_jobs = [
            {
                "job_id": j.id,
                "trigger": str(j.trigger),
                "next_run_time": j.next_run_time.strftime("%Y-%m-%d %H:%M:%S") if j.next_run_time else None,
            }
            for j in scheduler.scheduler.get_jobs()
        ]
        return ApiResponse(
            success=True,
            message="获取成功",
            data={"tasks": registered, "jobs": active_jobs},
        )

    @app.post("/api/tasks/submit-agent", response_model=ApiResponse)
    async def submit_agent_task(req: SubmitAgentRequest):
        """
        向服务端提交一个 Agent 任务 (支持立即触发或未来延时触发)
        """
        # 1. 延时触发 (例如 300 秒后)
        if req.delay_seconds > 0:
            target_time = datetime.now() + timedelta(seconds=req.delay_seconds)
            job_id = scheduler.schedule_agent_after(
                agent_name=req.agent_name,
                prompt=req.prompt,
                delay_seconds=req.delay_seconds,
                thread_id=req.thread_id,
            )
            return ApiResponse(
                success=True,
                message=f"已成功将 Agent [{req.agent_name}] 任务预约至 {req.delay_seconds} 秒后执行",
                data={
                    "job_id": job_id,
                    "agent_name": req.agent_name,
                    "delay_seconds": req.delay_seconds,
                    "scheduled_execution_time": target_time.strftime("%Y-%m-%d %H:%M:%S"),
                },
            )

        # 2. 立即触发 (delay=0) - 放入后台异步运行并立刻返回响应
        import uuid
        tname = f"dynamic_agent_{req.agent_name}_{uuid.uuid4().hex[:6]}"
        from .tasks import AgentTask
        task = AgentTask(name=tname, agent_name=req.agent_name, prompt_template=req.prompt, thread_id=req.thread_id)
        scheduler.register_task(task)

        # 异步启动任务，不阻塞客户端 HTTP 请求
        asyncio.create_task(scheduler.trigger_now(tname))

        return ApiResponse(
            success=True,
            message=f"Agent [{req.agent_name}] 任务已提交至后台立即执行",
            data={"task_name": tname, "status": "SUBMITTED"},
        )

    @app.post("/api/tasks/trigger", response_model=ApiResponse)
    async def trigger_task(req: TriggerTaskRequest):
        """立即在服务端触发一个已注册的任务"""
        if req.task_name not in scheduler.tasks:
            raise HTTPException(status_code=404, detail=f"未找到已注册任务: {req.task_name}")

        # 后台异步执行
        asyncio.create_task(scheduler.trigger_now(req.task_name, params=req.params))
        return ApiResponse(
            success=True,
            message=f"已下发执行任务: {req.task_name}",
            data={"task_name": req.task_name, "status": "QUEUED"},
        )

    @app.post("/api/tasks/schedule-delayed", response_model=ApiResponse)
    async def schedule_delayed_task(req: ScheduleDelayedTaskRequest):
        """预约延时执行已注册的任务"""
        if req.task_name not in scheduler.tasks:
            raise HTTPException(status_code=404, detail=f"未找到已注册任务: {req.task_name}")

        target_time = datetime.now() + timedelta(seconds=req.delay_seconds)
        job_id = scheduler.schedule_after(
            task_name=req.task_name,
            delay_seconds=req.delay_seconds,
            params=req.params,
        )
        return ApiResponse(
            success=True,
            message=f"任务 [{req.task_name}] 已预约至 {req.delay_seconds} 秒后执行",
            data={
                "job_id": job_id,
                "task_name": req.task_name,
                "delay_seconds": req.delay_seconds,
                "scheduled_execution_time": target_time.strftime("%Y-%m-%d %H:%M:%S"),
            },
        )

    @app.get("/api/ledger", response_model=ApiResponse)
    async def get_ledger_history(limit: int = 20, task_name: Optional[str] = None):
        """查询任务执行账本历史"""
        runs = await scheduler.ledger.get_recent_runs(task_name=task_name, limit=limit)
        return ApiResponse(
            success=True,
            message=f"查询到最近 {len(runs)} 条运行记录",
            data=runs,
        )

    return app
