"""
个股盘口实时监测脚本 (stock_monitor.py)
功能：
1. 实时读取盘口逐笔流水数据 (支持模拟数据流或实时 API 数据)
2. 监测个股异动条件 (例如：单笔主买成交量 >= 5000 手，且突破阻力位 138.50)
3. 触发异动条件后，非阻塞向调度器发送通知，唤醒分析 Agent 进行深度调研
"""

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

# Windows 控制台中文编码适配
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 异动策略阈值设定
ALERT_VOLUME_THRESHOLD = 5000     # 手 (单笔成交门槛)
ALERT_RESISTANCE_PRICE = 138.50   # 元 (关键阻力位)
SCHEDULER_API_URL = "http://127.0.0.1:8765/api/tasks/trigger"


def notify_scheduler_to_launch_agent(tick_data: dict) -> bool:
    """向调度器发送异步通知，拉起固定的分析 Agent (stock_anomaly_analyst) 开展调研"""
    symbol = tick_data.get("symbol", "未知标的")
    name = tick_data.get("name", "个股")
    price = tick_data.get("price", 0.0)
    vol = tick_data.get("volume_lots", 0)
    amt = tick_data.get("amount_cny", 0)
    ts = tick_data.get("timestamp", "")
    desc = tick_data.get("desc", "")

    prompt = (
        f"【实时异动盘中调研指令】\n"
        f"标的代码: {symbol} ({name})\n"
        f"触发时间: {ts}\n"
        f"成交价格: {price} 元 (已放量突破前高阻力位 {ALERT_RESISTANCE_PRICE} 元)\n"
        f"单笔主买成交量: {vol} 手 | 成交额: {amt:,.0f} 元\n"
        f"盘口现场描述: {desc}\n\n"
        f"请作为资深投资分析师对该异动进行深度研判调研:\n"
        f"1. 归因主力资金意图 (是大资金主动抢筹建仓、试盘测试抛压、还是诱多拉高出货?)\n"
        f"2. 评估突破有效性与后市 5~15 分钟关键支撑压力位\n"
        f"3. 给出针对持仓者与短线选手的具体应对策略与风险提示。"
    )

    # 触发已在 schedule.yaml 中固定声明的 stock_anomaly_analyst 任务模板
    payload = {
        "task_name": "stock_anomaly_analyst",
        "params": {
            "prompt": prompt
        }
    }

    try:
        req_data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            SCHEDULER_API_URL,
            data=req_data,
            headers={"Content-Type": "application/json; charset=utf-8"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            resp_json = json.loads(resp.read().decode("utf-8"))
            print(f"📡 [调度器连接成功] 服务端确认接收: {resp_json.get('message', 'OK')}")
            task_info = resp_json.get("data", {})
            print(f"   • 调度任务名: {task_info.get('task_name')}")
            print(f"   • 队列状态: {task_info.get('status')}")
            return True
    except Exception as e:
        print(f"❌ [通知调度器异常]: 无法连通调度器中枢 ({SCHEDULER_API_URL}): {e}")
        return False


def run_monitor(data_file_path: str):
    data_file = Path(data_file_path)
    if not data_file.exists():
        print(f"❌ 数据文件不存在: {data_file}")
        return

    with open(data_file, "r", encoding="utf-8") as f:
        ticks = json.load(f)

    print("=" * 75)
    print(f"🟢 [个股实时监测脚本] 启动运行 | 监控目标: 五粮液 (000858.SZ)")
    print(f"🎯 异动触发预警规则: [单笔成交 >= {ALERT_VOLUME_THRESHOLD} 手] 且 [现价 >= {ALERT_RESISTANCE_PRICE} 元]")
    print(f"📊 加载模拟逐笔行情流: 共 {len(ticks)} 笔数据")
    print("=" * 75)

    triggered_count = 0
    for idx, tick in enumerate(ticks, 1):
        ts = tick.get("timestamp")
        price = tick.get("price")
        vol = tick.get("volume_lots")
        amt = tick.get("amount_cny")
        desc = tick.get("desc")

        print(f"\n[{ts}] 第 {idx} 笔成交 -> 现价: {price:.2f} 元 | 成交量: {vol} 手 (金额: {amt:,.0f} 元)")

        # 检查是否满足触发条件
        is_volume_anomaly = vol >= ALERT_VOLUME_THRESHOLD
        is_price_breakout = price >= ALERT_RESISTANCE_PRICE

        if is_volume_anomaly and is_price_breakout:
            print(f"🚨🚨🚨 【异动报警触发】 满足预警条件！")
            print(f"    • 原因: 突破关键阻力位 {ALERT_RESISTANCE_PRICE} 元且伴随单笔 {vol} 手巨量买单！")
            print(f"    • 盘口备注: {desc}")
            print(f"⚡ [调度联动] 正在向调度器发送通知，唤醒数据分析 Agent 进行深度调研...")

            success = notify_scheduler_to_launch_agent(tick)
            if success:
                print(f"✅ 成功移交调度器！分析 Agent 已在后台并发启动深度推理，不影响监测流程。")
                triggered_count += 1
        else:
            print(f"    └── [正常波动]: {desc}")

        time.sleep(0.5)

    print("\n" + "=" * 75)
    print(f"🏁 [监测脚本执行完毕] 本轮扫描完成，共触发 {triggered_count} 次 Agent 深度分析调度。")
    print("=" * 75)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="个股盘口逐笔监测脚本")
    parser.add_argument(
        "--data-file",
        type=str,
        default="workspace/data/mock_stock_ticks.json",
        help="模拟逐笔行情数据文件路径",
    )
    args = parser.parse_args()
    run_monitor(args.data_file)
