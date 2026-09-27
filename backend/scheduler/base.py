"""
统一任务调度系统 - 基础契约与数据模型 (base.py)
定义任务执行上下文、标准化结果封装以及所有调度单元的抽象基类。
"""

import abc
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
import uuid

logger = logging.getLogger("backend.scheduler")


@dataclass
class TaskResult:
    """标准化任务执行结果"""
    task_name: str
    success: bool
    data: Any = None
    error: Optional[str] = None
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration_seconds(self) -> float:
        """执行耗时 (秒)"""
        if self.end_time and self.start_time:
            return round((self.end_time - self.start_time).total_seconds(), 3)
        return 0.0

    def summary(self) -> str:
        """获取简要结果摘要"""
        if not self.success:
            return f"❌ 失败: {self.error}"
        if isinstance(self.data, str):
            # 截取前 100 字符展示
            clean_str = self.data.strip().replace("\n", " ")
            return f"✅ 成功 ({self.duration_seconds}s): {clean_str[:100]}..." if len(clean_str) > 100 else f"✅ 成功 ({self.duration_seconds}s): {clean_str}"
        return f"✅ 成功 ({self.duration_seconds}s): {type(self.data).__name__}"


@dataclass
class ExecutionContext:
    """任务执行上下文 (包含共享数据字典、运行ID与专属日志器)"""
    task_name: str
    run_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    params: Dict[str, Any] = field(default_factory=dict)
    shared_data: Dict[str, Any] = field(default_factory=dict)
    workspace_dir: Optional[Path] = None
    logger: logging.Logger = field(default_factory=lambda: logger)

    def get(self, key: str, default: Any = None) -> Any:
        """优先从 params 获取，未找到再从 shared_data 获取"""
        if key in self.params:
            return self.params[key]
        return self.shared_data.get(key, default)


class BaseTask(abc.ABC):
    """
    所有可调度实体的统一抽象基类。
    无论是 LLM Agent、Python 原生分析模块、外部脚本还是流水线，都必须实现该接口。
    """
    def __init__(self, name: str, description: str = "", task_type: str = "generic"):
        self.name = name
        self.description = description
        self.task_type = task_type

    @abc.abstractmethod
    async def run(self, context: ExecutionContext) -> TaskResult:
        """
        统一异步执行方法
        :param context: 执行上下文 (含入参、共享上下文及日志器)
        :return: TaskResult 封装对象
        """
        pass

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name='{self.name}' type='{self.task_type}'>"
