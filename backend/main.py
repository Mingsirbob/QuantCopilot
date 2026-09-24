"""
MultiAgent 主程序入口 (官方标准原生异步架构)
演示从 agents/ 模板仓库中原生异步加载并运行：
1. 【金融数据抓取 Agent】(data_scraper): 基于同花顺 Fuyao MCP 抓取实时行情
2. 【量化数据分析 Agent】(data_analyst): 读取 5 日 K 线 JSON 数据并研判走势趋势
"""

import os
import sys
import asyncio
from pathlib import Path
from dotenv import load_dotenv

# 确保 backend 目录在 sys.path 中，支持从根目录或 backend 目录运行
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# 优先读取根目录或当前目录的 .env
load_dotenv(backend_dir.parent / ".env")
load_dotenv(backend_dir / ".env")

# 确保在 Windows 控制台下输出中文正常显示
sys.stdout.reconfigure(encoding="utf-8")

from agents import load_agent, list_available_agents


async def main():
    print("=" * 75)
    print("📂 【系统初始化】正在扫描用户资产工作区 (workspace/agents)...")
    available_agents = list_available_agents()
    print(f"📋 当前工作区中已发现的用户配置 Agent: {available_agents}")
    print("=" * 75)

    print("🚀 【阶段一】原生异步加载并运行【数据抓取 Agent (data_scraper)】...")
    print("=" * 75)

    # 1. 从 workspace/agents/ 异步加载数据抓取 Agent
    scraper_agent = await load_agent("data_scraper")
    print(f"✅ 加载成功: {scraper_agent}")
    print(f"🛠️ 已自动接入 MCP 外部工具数量: {len(scraper_agent.config.tools)} 个\n")

    query_scrape = "请帮我查询股票贵州茅台的实时行情快照，告诉我最新价格与涨跌幅。"
    print(f"👤 用户: {query_scrape}")
    print("⏳ Agent 正在调用同花顺 MCP 工具查询...\n")
    scrape_result = await scraper_agent.arun(query_scrape, thread_id="scrape_session")
    print(f"🤖 数据抓取 Agent 回复:\n{scrape_result}\n")

    print("=" * 75)
    print("🚀 【阶段二】原生异步加载并运行【数据分析 Agent (data_analyst)】...")
    print("=" * 75)

    # 2. 异步加载数据分析 Agent
    analyst_agent = await load_agent("data_analyst")
    print(f"✅ 加载成功: {analyst_agent}")
    print(f"🛠️ 包含分析工具: {[t.name for t in analyst_agent.config.tools]}\n")

    query_analysis = (
        "请帮我读取并分析 'data/maotai_5d_kline.json' 中的 5 个交易日数据，"
        "研判贵州茅台的短期走势趋势是向上还是向下，并请在你的专属工作空间中将完整的研报保存为 'reports/maotai_analysis.md' 文件。"
    )
    print(f"👤 用户: {query_analysis}")
    print("⏳ Agent 正在调用数据分析与独立沙箱工具...\n")
    analysis_result = await analyst_agent.arun(query_analysis, thread_id="analyst_session")
    print("🤖 数据分析 Agent 研报:\n")
    print(analysis_result)
    print("=" * 75)

    # 3. 验证专属沙箱内生成的文件产物
    if analyst_agent.sandbox:
        print(f"📦 【沙箱验证】Agent 专属工作空间目录: {analyst_agent.sandbox.sandbox_dir}")
        print("📁 沙箱内部现有文件列表:")
        for root, dirs, files in os.walk(analyst_agent.sandbox.sandbox_dir):
            for file in files:
                rel = Path(root, file).relative_to(analyst_agent.sandbox.sandbox_dir)
                size = Path(root, file).stat().st_size
                print(f"   └── {rel} ({size} 字节)")
    print("=" * 75)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 用户手动终止。")
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0)
