# QuantCopilot 🚀 - AI 多智能体量化投研框架

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![LangChain](https://img.shields.io/badge/LangChain-v1.4+-green.svg)](https://github.com/langchain-ai/langchain)
[![LangGraph](https://img.shields.io/badge/LangGraph-Ready-orange.svg)](https://github.com/langchain-ai/langgraph)

**QuantCopilot** 是一个基于 LangChain / LangGraph 现代 Agent 架构（`Agent = Model + Harness`）构建的开源 AI 多智能体量化投研与执行框架。具备**全栈三层解耦、独立代码执行沙箱、自包含 Agent 资产、C/S 架构统一任务调度与前端实时运维监控**能力。

---

## 🌟 核心特性

- **🤖 全栈三层解耦架构**
  - **核心运行时引擎 (`backend/`)**：纯 Python 引擎层，提供统一大模型适配、LangGraph 状态图编译、安全围栏与沙箱隔离，不与具体业务硬编码；
  - **用户资产工作区 (`workspace/`)**：Agent 模板自包含独立配置（YAML、Prompt、Skills、本地专用 Tools），即插即用；
  - **交互与调度大屏 (`frontend/` & `chat.py`)**：原生支持现代暗黑极客风格 Web 监控大屏与富交互终端 CLI。

- **🛡️ 原生隔离代码沙箱 (AgentSandbox)**
  - 拥有专属独立的工作目录与严格的防路径穿越安全机制；
  - Agent 可自主编写并执行 Python 数据处理与回测代码，生成的研报、JSON、数据图表均安全隔离在沙箱内部。

- **🕰️ 自主统一任务调度器 (C/S 架构)**
  - 基于 APScheduler 与 FastAPI，提供跨进程、守护进程运行的统一调度中枢；
  - 支持 **Cron 定时调度**、**延迟任务** 与 **脚本事件驱动触发**（如监测脚本发现指标异动一键拉起 Agent）；
  - 内置 A 股交易时钟感知与 `HEARTBEAT_OK` 静默防骚扰过滤。

- **🔌 多源数据接入与量化工具库**
  - 原生支持同花顺 Fuyao MCP 智能体协议快速对接；
  - 模块化集成多种量化指标计算工具与行情数据回测接口。

---

## 📁 目录结构

```text
QuantCopilot/
├── backend/                              # 【核心运行时引擎源码】（通用底座，无硬编码）
│   ├── core/                             # 通用底层组件 (模型工厂/沙箱/会话持久化/LangGraph编译)
│   ├── agents/                           # 动态 Agent 加载器与生命周期管理
│   ├── scheduler/                        # 统一任务调度服务器 (FastAPI + APScheduler + SQLite 账本)
│   └── tests/                            # 自动化测试套件 (包含 30+ 项单元测试与集成测试)
│
├── workspace/                            # 【用户资产与数据工作区】（与代码解耦）
│   ├── agents/                           # 智能体模板目录 (Master, Data Scraper, Data Analyst 等)
│   ├── scripts/                          # 条件触发监测脚本 (如 stock_monitor.py)
│   ├── schedules/                        # 声明式调度配置 (schedule.yaml)
│   └── data/                             # 行情与业务数据
│
├── frontend/                             # 【Web 监控与调度大屏】(React + Vite + 暗黑极客设计系统)
│
├── chat.py                               # 交互式终端 CLI 对话入口 (支持流式输出与会话管理)
├── run_backend.py                        # 后端主流程快速运行脚本
├── run_scheduler.py                      # 任务调度中枢常驻服务 (监听 8765 端口)
├── submit_task.py                        # 任务提交与监控客户端工具
├── pyproject.toml                        # 现代 Python 项目配置 (uv)
└── LICENSE                               # MIT 开源许可证
```

---

## 🚀 快速上手

### 1. 环境准备
推荐使用现代化 Python 包管理器 [`uv`](https://github.com/astral-sh/uv)：

```bash
# 克隆仓库
git clone https://github.com/Mingsirbob/QuantCopilot.git
cd QuantCopilot

# 创建并同步 Python 3.12+ 虚拟环境
uv sync
```

### 2. 配置环境变量
复制 `.env.example` 为 `.env` 并填写您的大模型及相关 API 密钥：

```bash
cp .env.example .env
```

### 3. 运行体验

- **启动交互式终端对话 (CLI Chat)**：
  ```bash
  uv run python chat.py
  # 或指定特定 Agent 角色：
  uv run python chat.py data_analyst
  ```

- **启动后台任务调度中枢**：
  ```bash
  uv run python run_scheduler.py
  ```

- **向调度器提交任务**：
  ```bash
  uv run python submit_task.py --agent data_analyst --prompt "请读取行情数据研判短期走势" --delay 60
  # 查看当前活动任务与历史运行账本
  uv run python submit_task.py --list
  uv run python submit_task.py --ledger
  ```

- **启动 Web 运维态势大屏**：
  ```bash
  cd frontend
  npm install
  npm run dev
  ```

---

## 📄 开源许可证

本项目基于 [MIT License](LICENSE) 协议开源。
