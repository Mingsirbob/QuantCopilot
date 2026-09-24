# MultiAgent 工作空间资产与存储规划 (Workspace Guide)

本目录是 MultiAgent 智能体系统的资产与数据中心。根据企业级安全与分层设计原则，本目录分为两大核心分区：

---

## 目录分层架构

```text
workspace/
├── agents/                  # 📂 静态智能体定义（版本受控资产，纳入 Git）
│   ├── data_analyst/        #   - 金融量化分析智能体（agent.yaml, prompt.md, skills/）
│   └── data_scraper/        #   - 金融数据采集智能体（agent.yaml, prompt.md, skills/）
├── data/                    # 📂 共享业务数据集与知识资产（版本受控）
│   └── (用户提供的基础静态股票表、行业映射、参考研报模板等)
└── runtime/                 # 📂 动态运行环境与持久化存储（被 .gitignore 忽略，宿主隔离）
    ├── sessions/            #   - SQLite 会话库（sessions.db 及 checkpointer 断点）
    ├── sandboxes/           #   - 各智能体的专属安全隔离目录（执行 Python 与写入文件的沙箱）
    │   ├── FinancialDataAnalystAgent/
    │   └── FinancialDataScraperAgent/
    └── logs/                #   - 智能体系统运行与安全审计日志
```

---

## 分区职责与规范

### 1. `workspace/agents/`（纯配置与技能资产）
- **特点**：纯文本声明（YAML + Markdown + Python 工具定义）。
- **管理要求**：纳入 Git 版本管理。修改此处可实现智能体能力的即插即用与在线迭代。

### 2. `workspace/data/`（共享知识与数据）
- **特点**：存放跨 Agent 共享的只读数据、测试样本文件。

### 3. `workspace/runtime/`（隔离运行沙箱与存储）
- **特点**：运行时动态产生，严禁提交到代码仓库。
- **安全性**：
  - 各 Agent 仅能通过 `AgentSandbox` 访问自身专属的 `runtime/sandboxes/{agent_name}/` 目录；
  - 严禁通过 `../` 越界读取宿主系统的敏感文件；
  - 会话数据集中持久化至 `runtime/sessions/sessions.db`。
