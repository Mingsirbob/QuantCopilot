"""
Python 模块/分析函数任务适配器 (module_task.py)
动态加载并执行原生 Python 分析函数或类方法，零 Token 消耗、高执行性能。
"""

import asyncio
import importlib
import inspect
from datetime import datetime
from typing import Any, Callable, Dict, Optional, Union
from ..base import BaseTask, ExecutionContext, TaskResult


class ModuleTask(BaseTask):
    """
    负责执行原生 Python 分析函数/算法模块。
    - 支持直接传入 callable 对象或字符串路径 (例如 'workspace.modules.quant.indicators:calc_indicators')
    - 自动识别异步协程 (async def) 与同步阻塞函数；同步函数自动投递到线程池 (asyncio.to_thread)，保障调度主循环永不阻塞
    """

    def __init__(
        self,
        name: str,
        target: Union[Callable, str],
        default_params: Optional[Dict[str, Any]] = None,
        description: str = "",
    ):
        super().__init__(
            name=name,
            description=description or f"Python 模块任务 [{getattr(target, '__name__', str(target))}]",
            task_type="module",
        )
        self.target = target
        self.default_params = default_params or {}

    def _resolve_target(self) -> Callable:
        """解析目标可调用对象"""
        if callable(self.target):
            return self.target
        if isinstance(self.target, str):
            if ":" not in self.target:
                raise ValueError(
                    f"模块导入字符串格式必须为 'module.path:func_name'，收到: '{self.target}'"
                )
            mod_path, func_name = self.target.split(":", 1)
            mod = importlib.import_module(mod_path)
            func = getattr(mod, func_name)
            if not callable(func):
                raise TypeError(f"从 '{self.target}' 解析出的对象不可调用: {type(func)}")
            return func
        raise TypeError(f"不支持的目标类型: {type(self.target)}")

    async def run(self, context: ExecutionContext) -> TaskResult:
        start_time = datetime.now()
        context.logger.info(f"⚙️ [ModuleTask] 正在调用原生分析模块 [{self.name}]...")

        try:
            func = self._resolve_target()

            # 合并调用参数：优先级 params > shared_data > default_params
            merged_params = dict(self.default_params)
            merged_params.update(context.shared_data)
            merged_params.update(context.params)

            # 检查函数签名，仅传递函数支持的参数，避免多余参数报错（除非函数接收 **kwargs）
            sig = inspect.signature(func)
            has_var_keyword = any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
            )
            if has_var_keyword:
                call_args = merged_params
            else:
                call_args = {
                    k: v for k, v in merged_params.items() if k in sig.parameters
                }

            # 区分异步与同步调用
            if inspect.iscoroutinefunction(func):
                output = await func(**call_args)
            else:
                output = await asyncio.to_thread(func, **call_args)

            end_time = datetime.now()
            return TaskResult(
                task_name=self.name,
                success=True,
                data=output,
                start_time=start_time,
                end_time=end_time,
                metadata={"target": str(self.target)},
            )

        except Exception as e:
            end_time = datetime.now()
            context.logger.error(f"❌ [ModuleTask] 模块 [{self.name}] 执行失败: {e}", exc_info=True)
            return TaskResult(
                task_name=self.name,
                success=False,
                error=str(e),
                start_time=start_time,
                end_time=end_time,
                metadata={"target": str(self.target)},
            )
