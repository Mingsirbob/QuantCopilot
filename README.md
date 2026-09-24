# MultiAgent - Agent 模板仓库与执行框架

本项目基于 LangChain 现代 Agent 架构（`Agent = Model + Harness`），构建了**模板化、自包含、支持 MCP、Skills 与本地量化工具**的多智能体目录仓库。

---

## 目录结构（全栈三层解耦架构）

```text
MultiAgent/
├── backend/                              # 【后端服务源码】（纯代码逻辑，无状态引擎）
│   ├── core/                             # 【底层通用 Agent 运行时引擎】
│   │   ├── __init__.py                   # 导出 AgentConfig, build_agent, StandaloneAgent, AgentSandbox
│   │   ├── config.py                     # 参数契约模型 (自适应环境变量，支持沙箱配置)
│   │   ├── model.py                      # 统一大模型工厂 (OpenAI / DeepSeek / 兼容模型)
│   │   ├── builder.py                    # LangGraph 状态图编译 & 自动挂载沙箱工具
│   │   ├── sandbox.py                    # 【专属独立沙箱引擎】(工作目录隔离 + Python代码执行 + 文件读写)
│   │   └── tools.py                      # 通用基础工具库
│   │
│   ├── agents/                           # 【Agent 模板/工作区解析与加载模块】
│   │   ├── __init__.py                   # 导出 load_agent, list_available_agents
│   │   └── loader.py                     # 自动扫描 workspace/agents/ 动态加载
│   │
│   └── main.py                           # 后端主执行入口
│
├── workspace/                            # 【用户资产工作区】（与后端代码解耦，存放用户配置与生成物）
│   ├── agents/                           # 用户自建或从模板派生的 Agent 角色
│   │   ├── data_scraper/                 # 【数据抓取 Agent】(同花顺 Fuyao MCP 声明)
│   │   └── data_analyst/                 # 【数据分析 Agent】(量化走势分析与专用算法，开启代码沙箱)
│   │
│   ├── data/                             # 用户数据存储区 (行情数据/K线文件等)
│   │   └── maotai_5d_kline.json
│   │
│   └── sandboxes/                        # 【Agent 专属隔离工作空间】(各 Agent 代码执行与文件输出根目录)
│       └── FinancialDataAnalystAgent/    # 分析 Agent 专属目录 (生成的研报/图表均隔离在此)
│           └── reports/maotai_analysis.md
│
├── frontend/                             # 【前端项目预留目录】(未来接入 React / Vue / Vite)
│
├── run_backend.py                        # 根目录便捷启动脚本代理
├── .env                                  # API 密钥与环境变量（包含 Financial-API-KEY、OpenAI 等）
└── pyproject.toml                        # 依赖声明
```

---

## 核心 Agent 介绍与使用

### 1. 数据抓取 Agent (`data_scraper`)
- **定位**：连接同花顺 Fuyao MCP 服务，负责 A 股标的检索、代码消歧与实时行情快照抓取；
- **配置**：默认采用 OpenAI `gpt-5.6-luna` 模型，动态注入 `${Financial-API-KEY}`；
- **调用**：
  ```python
  import asyncio
  from agents import load_agent

  async def main():
      scraper = await load_agent("data_scraper")
      reply = await scraper.arun("请帮我查询股票贵州茅台的实时行情快照。")
      print(reply)

  asyncio.run(main())
  ```

### 2. 数据分析 Agent (`data_analyst`)
- **定位**：基于本地行情 JSON 数据，执行量化统计（MA5、区间收益率、高低点推移、量价配合），给出明确走势趋势（向上/向下/震荡偏弱）；
- **配置**：默认采用 OpenAI `gpt-5.6-luna` 模型，内置 `read_kline_json` 和 `calculate_trend_indicators` 算力工具；
- **调用**：
  ```python
  import asyncio
  from agents import load_agent

  async def main():
      analyst = await load_agent("data_analyst")
      report = await analyst.arun("请帮我读取并分析 'data/maotai_5d_kline.json' 的数据，研判短期走势趋势。")
      print(report)

  asyncio.run(main())
  ```

