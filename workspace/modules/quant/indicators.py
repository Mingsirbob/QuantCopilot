"""
原生量化指标计算模块 (indicators.py)
不经过大模型，纯 Python 数值计算，提供零延迟、确定性的技术面分析。
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def calculate_kline_indicators(
    file_path: Optional[str] = "workspace/data/maotai_5d_kline.json",
    ticker: Optional[str] = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    读取指定 K 线 JSON 文件并计算技术面指标：
    - 周期均价 (MA)
    - 累计涨跌幅与日均振幅
    - 最高价与最低价支撑压力区间
    - 趋势研判状态 (多头/空头/震荡)
    """
    project_root = Path(__file__).resolve().parents[3]
    target_path = Path(file_path) if file_path else (project_root / "workspace/data/maotai_5d_kline.json")
    if not target_path.is_absolute():
        target_path = (project_root / target_path).resolve()

    if not target_path.exists():
        return {
            "status": "error",
            "message": f"未找到行情数据文件: {target_path}",
        }

    with open(target_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    records: List[Dict[str, Any]] = raw_data.get("data", [])
    if not records:
        return {"status": "error", "message": "数据文件中无有效行情记录"}

    name = raw_data.get("name", ticker or "未知标的")
    symbol = raw_data.get("ticker", ticker or "")
    closes = [r["close"] for r in records]
    highs = [r["high"] for r in records]
    lows = [r["low"] for r in records]
    changes = [r.get("change_pct", 0.0) for r in records]

    ma = sum(closes) / len(closes)
    latest_close = closes[-1]
    first_close = closes[0]
    total_change_pct = round(((latest_close - first_close) / first_close) * 100, 2)
    max_price = max(highs)
    min_price = min(lows)

    # 简单趋势定性
    if latest_close > ma and total_change_pct > 1.0:
        trend = "强势多头上攻"
    elif latest_close < ma and total_change_pct < -1.0:
        trend = "弱势空头回调"
    else:
        trend = "区间箱体震荡"

    result = {
        "symbol": symbol,
        "name": name,
        "records_analyzed": len(records),
        "latest_close": latest_close,
        "period_ma": round(ma, 2),
        "total_change_pct": total_change_pct,
        "support_level": min_price,
        "resistance_level": max_price,
        "trend_assessment": trend,
        "raw_records_summary": f"最近交易日收盘价: {latest_close}元，区间最高 {max_price}元，区间最低 {min_price}元",
    }
    return result
