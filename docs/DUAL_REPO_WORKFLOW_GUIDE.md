# 双仓库协同开发与开源维护工作流指南 (Dual-Repo Workflow Guide)

本文档面向项目研发团队与后续维护者，详细规范了**“一个私有闭源主仓 (`MultiAgent`) + 一个公开开源外发仓 (`QuantCopilot`)”**的双轨制开发、分支管理、安全审查与一键发版完整工作流。

---

## 一、双仓库架构与拓扑关系

本项目采用**单本地工程、双远程源绑定（Dual-Remote Binding）**的架构模型。核心研发在私有闭源仓库中进行，定期或按版本里程碑将通用框架与能力单向同步至公开开源仓库。

### 1. 架构拓扑图

```mermaid
graph TD
    subgraph 本地开发机 [本地工作区 (Local Repo)]
        L_Main["main 分支<br/>(私有全量研发主干)"]
        L_OS["opensource 分支<br/>(开源版本与定制分支)"]
        
        L_Main -- "里程碑合并 (git merge main)" --> L_OS
    end

    subgraph 远端私有闭源仓 [GitHub: MultiAgent (Private)]
        R_Private["origin/main<br/>(包含完整历史、内部私有配置、实验性功能)"]
    end

    subgraph 远端公开开源仓 [GitHub: QuantCopilot (Public)]
        R_Public["opensource/main<br/>(面向社区、标准文档、MIT 许可、脱敏纯净)"]
    end

    L_Main -- "日常推送 (git push origin main)" --> R_Private
    L_OS -- "开源发布 (git push opensource)" --> R_Public
```

### 2. 仓库与分支绑定清单

| 实体名称 | Remote 名称 | 远程仓库地址 | 本地绑定分支 | 仓库定位与安全等级 |
| :--- | :--- | :--- | :--- | :--- |
| **私有主仓** | `origin` | `https://github.com/Mingsirbob/MultiAgent.git` | `main` | **Private (最高安全级)**：日常迭代主阵地，包含所有业务提交记录 |
| **开源公仓** | `opensource` | `https://github.com/Mingsirbob/QuantCopilot.git` | `opensource` | **Public (社区公开级)**：对外开源展示、统一品牌 `QuantCopilot`、MIT 协议 |

---

## 二、初始环境与 Remote 配置检查

如果您在全新的设备或新克隆的目录中工作，只需执行以下命令建立双 Remote 绑定：

```bash
# 1. 检查当前已配置的远程源
git remote -v

# 2. 如果缺少 opensource 远程源，执行添加：
git remote add opensource https://github.com/Mingsirbob/QuantCopilot.git

# 3. 检查分支绑定关系
git branch -vv
```
正确的输出应类似：
```text
  main       0b76d7c [origin/main] ...
* opensource 10cace0 [opensource/main] chore: initial open-source release for QuantCopilot
```

---

## 三、标准研发与发版生命周期

### 阶段 1：日常内部研发（在 `main` 分支）

平时所有的功能开发、Bug 修复、自动化测试均在 `main`（或个人 feature 分支）上进行，**绝不直接在 `opensource` 分支上日常编码**。

```bash
# 1. 确保处于私有主分支
git checkout main

# 2. 编写代码、进行单元测试
uv run pytest backend/tests/unit/

# 3. 正常提交并推送到私有闭源仓库
git add .
git commit -m "feat: implement new indicator algorithm"
git push origin main
```

---

### 阶段 2：开源版本发布与同步（向 `opensource` 同步）

当完成阶段性里程碑、版本发布或修复了通用底层 bug，需要同步至开源社区时，执行本流程。

#### Step 1: 切换到开源分支
```bash
git checkout opensource
```

#### Step 2: 合并私有主干更新
```bash
git merge main -m "chore: sync features from main branch"
```

> **注意：可能遇到的合并差异与冲突处理：**
> 
> 由于 `opensource` 分支对以下文件做过开源化定制：
> - `pyproject.toml`（包名为 `quantcopilot`）
> - `README.md`（项目标题为 `QuantCopilot`，包含开源 badge）
> - `LICENSE`（包含 MIT 协议）
> - `frontend/index.html` 与 `frontend/src/App.jsx`（标题为 `QuantCopilot`）
> 
> 若 `main` 分支对上述文件也有改动而产生冲突，可按如下原则解决：
> - **保留开源分支自身的配置**：
>   ```bash
>   git checkout --ours README.md pyproject.toml
>   ```
> - 或者手动编辑冲突标记，保留开源品牌信息后 `git add . && git commit`。

#### Step 3: 开源前安全合规检查（Checklist）

在执行推送之前，**必须严格逐项核对以下 5 条安全红线**：

- [ ] **1. 秘钥与凭据防护**：确认 `.env`、私有 token、内网 IP/密码未被提交（运行 `git status` 确保工作树干净）；
- [ ] **2. 测试通过性**：执行 `uv run pytest backend/tests/unit/`，确保核心测试全部 PASS；
- [ ] **3. 文档品牌检查**：确认开源版 [README.md](file:///d:/Project/MultiAgent/README.md) 中无私有内部敏感链接或内网服务地址；
- [ ] **4. 样例与数据脱敏**：检查 `workspace/data/` 下的数据均为脱敏后的公开样例行情，无任何个人私密交易记录；
- [ ] **5. 协议有效性**：根目录下保留有效的 [LICENSE](file:///d:/Project/MultiAgent/LICENSE) (MIT)。

#### Step 4: 一键推送到开源仓库
```bash
git push opensource opensource:main
```
推送完成后，社区用户即可在 `https://github.com/Mingsirbob/QuantCopilot` 查看到最新开源版本。

---

## 四、差异化文件与配置隔离原则

为确保两套仓库既能共享 95% 以上的核心框架源码，又能保持各自独立的配置，请遵循以下文件分类准则：

| 模块分类 | 具体路径/文件 | 处理原则 |
| :--- | :--- | :--- |
| **开源专属展示层** | `LICENSE`, `README.md` | 在 `opensource` 分支中保持为 QuantCopilot 品牌与 MIT 声明；合并主干冲突时优先保留开源版 |
| **通用框架底层** | `backend/core/`, `backend/scheduler/`, `backend/agents/` | **两端 100% 保持一致**，无任何业务硬编码 |
| **样例与测试资产** | `workspace/agents/data_scraper/`, `workspace/agents/data_analyst/` | 保持通用公开模板，作为社区开发者体验的 Quickstart |
| **私有交易/敏感策略** | 专有实盘下单脚本、内部账号配置 | **严禁合并至 `opensource` 分支**；或配置在 `.gitignore` 忽略目录中 |
| **动态运行环境** | `workspace/runtime/`, `.env`, `*.db` | **全部列入 `.gitignore`**，两端均不追踪，确保安全隔离 |

---

## 五、常用 Git 操作速查表（Cheat Sheet）

| 操作场景 | 执行命令 |
| :--- | :--- |
| **切换到私有主分支** | `git checkout main` |
| **提交并推送到私有仓** | `git add . && git commit -m "..." && git push origin main` |
| **切换到开源分支** | `git checkout opensource` |
| **同步私有最新代码** | `git merge main` |
| **推送到开源仓库** | `git push opensource opensource:main` |
| **强制覆盖开源仓（慎用）** | `git push -f opensource opensource:main` |
| **查看当前所有分支与追踪源**| `git branch -vv` |
| **查看远程源配置** | `git remote -v` |

---

## 六、应急与回退预案 (FAQ)

### Q1: 如果不小心将包含敏感信息（如 API Key）的 commit 推到了开源仓库，怎么办？
1. **立即重置/回退开源分支本地提交**：
   ```bash
   git checkout opensource
   git reset --hard HEAD~1   # 回退到上一个安全的提交
   ```
2. **强制覆盖远端开源仓库**：
   ```bash
   git push -f opensource opensource:main
   ```
3. **安全凭据轮换（极为重要）**：
   如果秘钥曾暴露在公共网络哪怕 1 秒钟，也必须立即前往对应的服务商控制台（如 OpenAI、DeepSeek、同花顺等）**注销旧 API Key 并重新生成**，绝不可心存侥幸。

### Q2: 开源社区有外部开发者提交了 PR，如何合并并同步回私有主仓？
1. 在 `opensource` 分支拉取并合并外部 PR：
   ```bash
   git checkout opensource
   git pull opensource main
   ```
2. 审查与测试无误后，切回 `main` 分支反向合并：
   ```bash
   git checkout main
   git merge opensource -m "chore: sync community contributions from QuantCopilot"
   git push origin main
   ```
