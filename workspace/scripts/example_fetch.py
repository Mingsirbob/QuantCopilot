"""
独立外部抓取示例脚本 (example_fetch.py)
演示作为 ScriptTask 被调度器异步拉起执行并捕获输出。
"""

import json
import sys
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main():
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # 模拟抓取到的早盘外围市场与宏观要闻
    news_snapshot = {
        "timestamp": now_str,
        "source": "FinancialNewsCrawler",
        "market_sentiment": "中性偏多",
        "headlines": [
            "【隔夜外盘】欧美主要股指小幅收涨，科技成长板块领跑。",
            "【宏观要闻】央行公开市场净投放流动性，资金面平稳充裕。",
            "【行业动态】白酒与消费板块获主力机构资金连续 3 日净流入。"
        ]
    }
    # 打印到标准输出供调度器捕获
    print(json.dumps(news_snapshot, ensure_ascii=False, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()
