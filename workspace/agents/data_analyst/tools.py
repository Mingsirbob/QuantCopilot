"""
数据分析 Agent 专用工具库
提供读取行情 JSON 文件以及量化趋势指标计算工具。
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional
from langchain_core.tools import tool


def _resolve_file_path(file_path: str) -> Optional[str]:
    """自适应探测文件路径，优先查找 workspace/ 以及当前工作区"""
    raw_p = Path(file_path)
    file_name = raw_p.name
    project_root = Path(__file__).resolve().parent.parent.parent.parent  # 项目根目录

    candidates = [
        raw_p,
        Path("workspace") / file_path,
        Path("workspace/data") / file_name,
        project_root / "workspace" / file_path,
        project_root / "workspace" / "data" / file_name,
        project_root / file_path,
    ]
    for p in candidates:
        if p.exists() and p.is_file():
            return str(p.resolve())
    return None


@tool
def read_kline_json(file_path: str) -> str:
    """
    读取指定的 K 线 JSON 数据文件，并返回 JSON 文本内容。
    :param file_path: JSON 文件的本地路径，如 'data/maotai_5d_kline.json'
    """
    resolved = _resolve_file_path(file_path)
    if not resolved:
        return f"错误: 文件 '{file_path}' 不存在，请检查路径。"

    try:
        with open(resolved, "r", encoding="utf-8") as f:
            data = json.load(f)
        return json.dumps(data, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"读取或解析 JSON 文件失败: {e}"


@tool
def calculate_trend_indicators(file_path: str) -> str:
    """
    读取 K 线 JSON 文件，精确计算 5 日区间的核心量化趋势指标：
    包括：区间收益率、5日均价(MA5)、最高/最低价、涨跌天数统计、成交量变化趋势等。
    :param file_path: JSON 文件的本地路径，如 'data/maotai_5d_kline.json'
    """
    resolved = _resolve_file_path(file_path)
    if not resolved:
        return f"错误: 文件 '{file_path}' 不存在。"

    try:
        with open(resolved, "r", encoding="utf-8") as f:
            raw = json.load(f)

        records = raw.get("data", [])
        if not records:
            return "错误: JSON 文件中未找到有效的 'data' 行情数据列表。"

        # 按交易日期排序
        sorted_records = sorted(records, key=lambda x: x.get("trade_date", ""))
        n = len(sorted_records)
        if n < 2:
            return "错误: 数据记录不足 2 条，无法计算走势趋势。"

        closes = [r["close"] for r in sorted_records]
        highs = [r["high"] for r in sorted_records]
        lows = [r["low"] for r in sorted_records]
        volumes = [r["volume"] for r in sorted_records]

        start_date = sorted_records[0].get("trade_date")
        end_date = sorted_records[-1].get("trade_date")
        start_close = closes[0]
        end_close = closes[-1]

        # 1. 区间整体涨跌幅
        period_change = round(end_close - start_close, 2)
        period_return_pct = round(((end_close - start_close) / start_close) * 100, 2)

        # 2. 均线与极值
        ma = round(sum(closes) / n, 2)
        max_high = max(highs)
        min_low = min(lows)

        # 3. 涨跌天数
        up_days = sum(1 for r in sorted_records if r.get("change_pct", 0) > 0)
        down_days = sum(1 for r in sorted_records if r.get("change_pct", 0) < 0)
        flat_days = n - up_days - down_days

        # 4. 前后期量能对比（若 >= 4 天，对比前半段与后半段平均成交量）
        mid = n // 2
        vol_first_half = sum(volumes[:mid]) / mid
        vol_second_half = sum(volumes[mid:]) / (n - mid)
        vol_change_pct = round(
            ((vol_second_half - vol_first_half) / (vol_first_half or 1)) * 100, 2
        )

        # 5. 最新收盘价与均线关系
        is_above_ma = end_close >= ma

        metrics = {
            "ticker": raw.get("ticker"),
            "name": raw.get("name"),
            "period_days": n,
            "date_range": f"{start_date} ~ {end_date}",
            "start_close": start_close,
            "end_close": end_close,
            "period_change": period_change,
            "period_return_pct": f"{period_return_pct}%",
            "ma_price": ma,
            "current_vs_ma": "高于均线" if is_above_ma else "低于均线",
            "highest_price": max_high,
            "lowest_price": min_low,
            "up_down_ratio": f"{up_days}涨 / {down_days}跌 / {flat_days}平",
            "volume_change_pct": f"{vol_change_pct}%",
            "summary_signals": {
                "net_gain": period_change > 0,
                "above_ma": is_above_ma,
                "majority_up_days": up_days > down_days,
            },
        }

        return json.dumps(metrics, ensure_ascii=False, indent=2)

    except Exception as e:
        return f"计算指标失败: {e}"


# 声明给 Loader 自动加载的本地工具
LOCAL_TOOLS = [read_kline_json, calculate_trend_indicators]
