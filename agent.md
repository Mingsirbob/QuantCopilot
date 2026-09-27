# MultiAgent 项目架构与 AI 协作指南 (agent.md)

> 本文档专为后续接手的 **AI 编程助手（AI Agents / AI Coding Assistants）** 编写，旨在提供该项目的全局架构设计、核心开发规范、各模块职责分工以及未来的关键演进路线图。在协助人类工程师进行代码编写、重构或功能迭代前，请务必完整阅读本文档。

---

## 一、项目定位与核心设计哲学

本项目是基于 **LangChain / LangGraph 现代 Agent 架构（`Agent = Model + Harness`）** 构建的高性能、模板化、自包含、支持 MCP 与本地代码沙箱的多智能体开发与执行框架。

### 核心设计原则
1. **全栈三层解耦（Three-Tier Decoupling）**：
   * **底层引擎层 (`backend/`)**：纯 Python 逻辑，充当通用运行时引擎，不硬编码具体业务。
   * **用户资产工作区 (`workspace/`)**：纯配置、提示词、本地工具、数据及沙箱运行产物，与底层引擎完全解耦。
   * **交互层（预留）**：未来接入 Web 前端（React / Vue / Vite）或 API 网关。
2. **配置自包含与即插即用（Self-Contained Agents）**：
   * 新增或修改智能体只需在 `workspace/agents/<agent_name>/` 下配置独立的 YAML、Prompt、Skills 和专用 Tools，底层加载器会自动扫描并编译生效。
3. **原生全异步链路（Native Async-First）**：
   * 采用 `asyncio`、`aiosqlite`、`AsyncSqliteSaver` 以及 LangGraph 原生异步接口（`arun` / `ainvoke`），保障高并发能力。
4. **安全沙箱环境隔离（Sandboxed Execution）**：
   * 具有独立工作目录与路径穿越防护，Agent 生成的研报、图表以及执行的代码均隔离在专属沙箱内部。

---

## 二、当前完整目录结构与职责速查

```text
MultiAgent/
├── backend/                              # 【核心运行时引擎源码】（严禁掺杂业务硬编码）
│   ├── core/                             # 通用底层核心组件
│   │   ├── config.py                     # 参数契约模型 (Pydantic，支持环境变量动态注入、沙箱参数)
│   │   ├── model.py                      # 统一大模型工厂 (适配 OpenAI / DeepSeek / 兼容接口)
│   │   ├── sandbox.py                    # 专属代码沙箱与文件隔离引擎 (提供读写工具与 Python 执行器)
│   │   ├── session_manager.py            # 原生异步会话管理器 (aiosqlite，自动生成 4~12 字精炼会话标题)
│   │   ├── context_compression.py        # 5大核心上下文压缩引擎与 LangChain 原生 AgentMiddleware
│   │   ├── security.py                   # 安全审批围栏策略管理器与 HumanInTheLoopMiddleware
│   │   ├── builder.py                    # LangGraph 状态图编译引擎 (组装沙箱、中间件、工具与 Prompt)
│   │   └── tools.py                      # 通用基础工具集
│   │
│   ├── agents/                           # Agent 模板加载与解析模块
│   │   └── loader.py                     # 自动扫描 workspace/agents/，解析 YAML、挂载 MCP 与本地工具
│   │
│   ├── tests/                            # 自动化测试套件
│   │   ├── unit/                         # 单元测试 (test_sandbox.py, test_session_manager.py, test_context_compression.py, test_todo_list.py, test_security_approval.py)
│   │   └── integration/                  # 端到端集成测试 (test_sessions_e2e.py)
│   │
│   └── main.py                           # 后端全流程运行入口示例
│
├── workspace/                            # 【用户资产与数据工作区】（与后端代码解耦）
│   ├── agents/                           # 用户自建或派生的 Agent 模板
│   │   ├── data_scraper/                 # 【数据抓取 Agent】接入同花顺 Fuyao MCP，负责 A 股行情快照
│   │   │   ├── agent.yaml                # 声明模型、MCP 连接与环境变量映射
│   │   │   ├── prompt.md                 # 核心提示词与角色定位
│   │   │   └── skills/                   # 扩展技能描述
│   │   └── data_analyst/                 # 【数据分析 Agent】量化趋势研判，开启代码沙箱与专用算法
│   │       ├── agent.yaml                # 声明模型、开启沙箱
│   │       ├── prompt.md                 # 提示词
│   │       ├── tools.py                  # 本地专用量化算法工具 (如 read_kline_json, calculate_trend_indicators)
│   │       └── skills/
│   │
│   ├── data/                             # 外部输入业务共享数据（如原始行情、行业映射表等）
│   └── runtime/                          # 【运行时动态生成环境】（宿主隔离，被 .gitignore 忽略）
│       ├── sessions/                     # SQLite 数据库（存储 sessions.db 会话元数据与检查点）
│       ├── sandboxes/                    # 各智能体专属隔离沙箱（生成的 JSON、图表、研报集中于此）
│       │   ├── FinancialDataAnalystAgent/
│       │   └── FinancialDataScraperAgent/
│       └── logs/                         # 运行与安全审计日志
│
├── pyproject.toml                        # 现代 Python 项目依赖规范 (Python >=3.12, 基于 uv)
├── uv.lock                               # 依赖版本精确锁定文件
├── run_backend.py                        # 根目录便捷执行入口代理脚本
├── README.md                             # 项目介绍与基础使用文档
└── .env / .env.example                   # API 密钥与环境变量声明
```

---

## 三、AI 编程助手协作开发规范

当你在本仓库进行功能开发、Bug 修复或重构时，**必须严格遵守以下规范**：

1. **坚持“引擎与资产分离”原则**：
   * **不可在 `backend/` 下硬编码特定业务逻辑**（如针对茅台的分析算法、特定股票代码的处理）；业务逻辑应作为工具或技能放置在 `workspace/agents/<agent_name>/tools.py` 或 `skills/` 中。
   * 新建智能体时，只需在 `workspace/agents/` 下新建对应文件夹并编写 `agent.yaml` 与 `prompt.md`。
2. **异步优先（Async First）**：
   * 所有涉及 I/O（数据库、网络请求、MCP 通信、模型调用、文件异步流）的操作，必须使用原生 `async / await`。
   * 会话与状态存储依赖 `SessionManager` 和 `AsyncSqliteSaver`，禁止引入阻塞主事件循环的同步 I/O。
3. **沙箱边界与路径安全**：
   * 凡是需要生成文件（如 Markdown 研报、CSV、图片）或执行动态 Python 代码的 Agent，必须通过 [`AgentSandbox`](file:///backend/core/sandbox.py) 进行限制。
   * 严禁绕过沙箱直接在根目录或项目源码目录写入运行产物，防止路径穿越攻击（Path Traversal）。
4. **统一会话管理与标题提炼**：
   * 会话调用必须传入或自动生成 `thread_id`。
   * 首轮交互由 [`SessionManager`](file:///backend/core/session_manager.py) 自动调用 LLM 压缩生成 4~12 字的精炼中文标题，存储于 `sessions_meta` 表中。
5. **依赖管理规范**：
   * 本项目使用 `uv` 管理依赖。如需新增外部包，请通过 `uv add <package>` 添加并更新 `pyproject.toml`，禁止破坏 `uv.lock` 的环境一致性。

---

## 四、核心改进与演进方向：引入类 OpenClaw 的主动心跳机制

### 1. 现状痛点
目前本项目的 Agent 属于**被动响应模式（Passive Request-Response）**，即用户输入一条 prompt，Agent 响应一次。然而在金融量化、风险控制、实时盯盘场景中，核心诉求是**主动监测、事件驱动、异动预警**。

### 2. 参考 OpenClaw 心跳机制（Heartbeat）的改造规划
OpenClaw 通过心跳机制实现了真正的“主动智能（Proactive Agent）”。本项目后续将按以下蓝图进行改造落地：

#### (1) 引入 Agent 级主动巡检清单 (`HEARTBEAT.md`)
* **设计**：在 `workspace/` 或特定 Agent 目录下允许配置 `HEARTBEAT.md` 或在 `agent.yaml` 中配置 `heartbeat` 策略（例如：巡检频率、自选标的清单、监控阈值）。
* **行为**：调度系统在心跳周期自动读取清单，转化为巡检 Prompt 驱动 Agent 唤醒执行。

#### (2) 实现 `HEARTBEAT_OK` 静默与防骚扰机制（关键特性）
* **设计**：借鉴 OpenClaw 的静默机制，在 Prompt 中约定：“*若所有指标均在正常阈值范围内、无需人类介入，请仅输出 `HEARTBEAT_OK`*”。
* **行为**：调度器检测到回复为 `HEARTBEAT_OK` 时，自动**静默吞没通知**，仅记录轻量心跳日志，避免产生信息轰炸；仅当指标异动（如“放量破位”、“涨跌幅异动”）时，才触发主动通知或生成深度研报。

#### (3) 与现有 [`SessionManager`](file:///backend/core/session_manager.py) 的上下文深度融合
* **设计**：为巡检任务分配固定的 `thread_id`（例如 `thread_id="market_monitor_session"`）。
* **优势**：心跳轮次在同一个会话状态图中递增，Agent 拥有连续记忆，能记住前几次心跳的历史状态（例如：“5分钟前已提醒过跌破 2%，若当前维持在 2.1% 则无需重复唠叨”），避免机械式循环告警。

#### (4) “Heartbeat（微巡检）”与“Cron（批处理）”双轨分工
* **Heartbeat（轻量高频）**：由 `data_scraper` 负责，每隔 3~5 分钟调用轻量 MCP 抓取实时快照与分时数据，快速评估。
* **Cron（重型定时）**：每个交易日收盘（如 15:05），定时触发 `data_analyst`，调度沙箱运行 Python 代码计算全天指标，产出完整的 Markdown 研报。

#### (5) 适配 A 股交易时钟感知（Trading Hours Filter）
* **设计**：结合本项目已有 A 股交易日历能力，实现智能活动窗口：仅在交易日开盘时段（`09:30~11:30, 13:00~15:00`）激活高频心跳，盘前执行一次早盘巡检，休市与周末自动休眠。

#### (6) 实施完成状态与模块落地
已在 `backend/scheduler/` 下完整落地统一异步调度引擎与执行器族 (C/S 客户端-服务端架构)：
* **调度器核心**：[`TaskScheduler`](file:///backend/scheduler/engine.py) (基于 APScheduler 与原生 AsyncIO 事件循环)
* **REST API 服务端**：[`create_scheduler_app`](file:///backend/scheduler/server.py) (基于 FastAPI 构建，提供 Swagger UI 与远程任务提交)
* **客户端交互工具**：[`submit_task.py`](file:///submit_task.py) (跨终端快速提交、排班、查询任务与账本)
* **执行器适配族**：[`AgentTask`](file:///backend/scheduler/tasks/agent_task.py)、[`ModuleTask`](file:///backend/scheduler/tasks/module_task.py)、[`ScriptTask`](file:///backend/scheduler/tasks/script_task.py)、[`PipelineTask`](file:///backend/scheduler/tasks/pipeline_task.py)
* **状态持久化账本**：[`TaskLedger`](file:///backend/scheduler/ledger.py) (SQLite 账本存储于 `workspace/runtime/scheduler/ledger.db`)
* **时钟与静默过滤**：[`TradingHoursFilter`](file:///backend/scheduler/filters.py) (A股交易窗口感知) 与 [`SilenceChecker`](file:///backend/scheduler/filters.py) (`HEARTBEAT_OK` 静默防骚扰)
* **声明式配置文件**：`workspace/schedules/schedule.yaml`

---

## 五、常用工程化调试指令

```bash
# 1. 运行全套单元测试 (含最新调度服务端与各模块 32 项测试全部通过)
uv run pytest backend/tests/unit/

# 2. 运行调度系统专属测试 (8 项测试)
uv run pytest backend/tests/unit/test_scheduler.py

# 3. 运行端到端集成测试 (验证 SQLite 会话持久化与标题自动生成)
uv run pytest backend/tests/integration/test_sessions_e2e.py

# 4. 执行后端主流程演示 (加载两个 Agent 并演示抓取与研报生成)
uv run python run_backend.py

# 5. 启动交互式终端对话 (CLI Chat，支持流式输出、待办看板、安全审批、会话切换)
uv run python chat.py
# 或指定目标智能体：
uv run python chat.py data_analyst

# 6. 【终端 1】：启动常驻调度中枢服务器 (监听 http://127.0.0.1:8765)
uv run python run_scheduler.py

# 7. 【终端 2】：向常驻服务器随时提交任务 (提交后 0.1s 立即退出，不卡死)
# 预约 5 分钟后由服务端自动分析茅台
uv run python submit_task.py --agent data_analyst --prompt "请读取 'workspace/data/maotai_5d_kline.json' 分析茅台走势" --delay 300
# 查看服务器当前激活的任务与作业
uv run python submit_task.py --list
# 查看服务器最近的历史运行账本
uv run python submit_task.py --ledger
# 立即触发服务端某个已注册的任务
uv run python submit_task.py --run-task quant_indicator_calc

# 8. 本地单次快速测试 (不启动 Web Server)
uv run python run_scheduler.py --run-once quant_indicator_calc
```

