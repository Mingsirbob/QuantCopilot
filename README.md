# MultiAgent - Agent 模板仓库与执行框架

本项目基于 LangChain 现代 Agent 架构（`Agent = Model + Harness`），构建了**模板化、自包含、支持 MCP、Skills 与本地量化工具**的多智能体目录仓库。

---

## 目录结构（全栈前后端分离架构）

```text
MultiAgent/
├── backend/                              # 【后端服务与 Agent 运行时】
│   ├── core/                             # 【底层通用 Agent 运行时引擎】
│   │   ├── __init__.py                   # 导出 AgentConfig, build_agent, StandaloneAgent
│   │   ├── config.py                     # 参数契约模型 (支持 .env 自动回退)
│   │   ├── model.py                      # 统一大模型工厂 (OpenAI / DeepSeek / 兼容模型)
│   │   ├── builder.py                    # LangGraph 状态图编译 & 异步 StandaloneAgent
│   │   └── tools.py                      # 通用基础工具库
│   │
│   ├── agents/                           # 【业务 Agent 模板仓库】
│   │   ├── __init__.py                   # 导出 load_agent, AgentTemplateLoader
│   │   ├── loader.py                     # 模板动态解析与加载器 (yaml/skills/mcp/local tools)
│   │   ├── data_scraper/                 # 【数据抓取 Agent 独立模板】(同花顺 Fuyao MCP)
│   │   └── data_analyst/                 # 【数据分析 Agent 独立模板】(量化走势分析)
│   │
│   ├── data/                             # 【本地行情与测试数据】
│   │   └── maotai_5d_kline.json          # 贵州茅台 5 个交易日日K数据
│   │
│   └── main.py                           # 后端主执行入口 (演示加载与异步执行两个 Agent)
│
├── frontend/                             # 【前端项目预留目录】(未来可接入 React / Vue / Vite)
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

