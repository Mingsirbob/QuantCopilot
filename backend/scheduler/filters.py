"""
调度过滤器与心跳静默检测器 (filters.py)
1. TradingHoursFilter: 交易时钟感知，支持 A股交易时段窗口过滤
2. SilenceChecker: 参考 OpenClaw 的 HEARTBEAT_OK 静默与防骚扰机制
"""

from datetime import datetime, time
from typing import Optional


class TradingHoursFilter:
    """
    A 股交易时间过滤器。
    默认交易时段：
    - 周一至周五 (0~4)
    - 早盘: 09:15 ~ 11:30 (含集合竞价)
    - 午盘: 13:00 ~ 15:05
    """

    def __init__(
        self,
        morning_start: time = time(9, 15),
        morning_end: time = time(11, 30),
        afternoon_start: time = time(13, 0),
        afternoon_end: time = time(15, 5),
    ):
        self.morning_start = morning_start
        self.morning_end = morning_end
        self.afternoon_start = afternoon_start
        self.afternoon_end = afternoon_end

    def is_trading_time(self, now: Optional[datetime] = None) -> bool:
        """检查指定时间（默认为当前时间）是否在交易时段内"""
        dt = now or datetime.now()
        # 周末不开盘 (0 是周一, 4 是周五, 5/6 是周末)
        if dt.weekday() >= 5:
            return False

        t = dt.time()
        in_morning = self.morning_start <= t <= self.morning_end
        in_afternoon = self.afternoon_start <= t <= self.afternoon_end
        return in_morning or in_afternoon


class SilenceChecker:
    """
    心跳静默检测器。
    参考 OpenClaw 设计：当 Agent 在巡检中评估所有指标正常无需打扰时，
    输出以 'HEARTBEAT_OK' 开头，调度系统据此识别为静默状态，仅留存审计日志，不向用户弹窗或发送外部推送。
    """

    SILENCE_TOKEN = "HEARTBEAT_OK"

    @classmethod
    def is_silent(cls, response: Optional[str]) -> bool:
        if not response:
            return False
        clean = response.strip()
        return clean.startswith(cls.SILENCE_TOKEN) or clean == cls.SILENCE_TOKEN
