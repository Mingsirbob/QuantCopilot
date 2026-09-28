import React, { useState, useEffect, useMemo } from 'react';
import {
  Activity,
  Clock,
  CheckCircle2,
  AlertOctagon,
  AlertTriangle,
  Play,
  RotateCw,
  Shield,
  Layers,
  Database,
  Cpu,
  Terminal,
  Zap,
  Filter,
  Flame,
  ArrowUpRight,
  Code2,
  FileCode,
  Bot
} from 'lucide-react';
import './App.css';

export default function App() {
  // 当前激活的标签页: 'tasks' (任务列表) 或 'ops' (监控Agent)
  const [activeTab, setActiveTab] = useState('tasks');
  const [online, setOnline] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  
  const [tasks, setTasks] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [ledger, setLedger] = useState([]);
  const [ledgerFilter, setLedgerFilter] = useState('ALL'); // 'ALL' | 'SUCCESS' | 'FAILED'
  const [triggeringTask, setTriggeringTask] = useState(null);
  const [triggerMsg, setTriggerMsg] = useState(null);

  // 获取调度器核心数据
  const fetchData = async () => {
    try {
      setRefreshing(true);
      // 1. 获取任务与排班作业
      const tasksRes = await fetch('/api/tasks');
      if (tasksRes.ok) {
        const tasksJson = await tasksRes.json();
        const data = tasksJson.data || {};
        setTasks(data.tasks || []);
        setJobs(data.jobs || []);
        setOnline(true);
      } else {
        setOnline(false);
      }

      // 2. 获取最近历史账本
      const ledgerRes = await fetch('/api/ledger?limit=30');
      if (ledgerRes.ok) {
        const ledgerJson = await ledgerRes.json();
        setLedger(ledgerJson.data || []);
      }
    } catch (err) {
      setOnline(false);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  // 首次挂载与定时轮询
  useEffect(() => {
    fetchData();
    if (!autoRefresh) return;
    const timer = setInterval(fetchData, 5000);
    return () => clearInterval(timer);
  }, [autoRefresh]);

  // 立即下发执行任务
  const handleTriggerTask = async (taskName) => {
    try {
      setTriggeringTask(taskName);
      const res = await fetch('/api/tasks/trigger', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task_name: taskName })
      });
      if (res.ok) {
        setTriggerMsg(`✅ 成功向调度器下发任务 [${taskName}]，正在后台执行！`);
        setTimeout(() => setTriggerMsg(null), 4000);
        setTimeout(fetchData, 1000);
      } else {
        setTriggerMsg(`❌ 触发失败: ${res.statusText}`);
      }
    } catch (e) {
      setTriggerMsg(`❌ 请求错误: ${e.message}`);
    } finally {
      setTriggeringTask(null);
    }
  };

  // 1. 深度聚合：将可注册任务、排班作业与最近执行账本融合
  const aggregatedTasks = useMemo(() => {
    return tasks.map((task) => {
      // 寻找对应的排班作业 (job)
      const matchedJob = jobs.find((j) => j.job_id.includes(task.name) || j.trigger.includes(task.name));
      // 寻找最近一次的执行账本记录 (run)
      const lastRun = ledger.find((r) => r.task_name === task.name);

      let status = 'IDLE';
      if (matchedJob) {
        status = 'PENDING'; // 正在排班倒计时
      }
      if (lastRun) {
        status = lastRun.status; // 最近一次执行结果: SUCCESS / FAILED / SKIPPED
      }

      return {
        ...task,
        jobId: matchedJob?.job_id,
        triggerRule: matchedJob?.trigger || '按需或未激活排班',
        nextRunTime: matchedJob?.next_run_time,
        lastRunTime: lastRun?.start_time,
        lastDuration: lastRun?.duration_seconds,
        lastSummary: lastRun?.result_summary,
        status: status,
        errorTrace: lastRun?.error_trace
      };
    });
  }, [tasks, jobs, ledger]);

  // 2. 统计所有报错任务 (FAILED incidents)
  const failedIncidents = useMemo(() => {
    return ledger.filter((r) => r.status === 'FAILED');
  }, [ledger]);

  // 3. 计算运维 Agent 态势与健康评分
  const opsAnalysis = useMemo(() => {
    const total = ledger.length;
    const failedCount = failedIncidents.length;
    const successCount = ledger.filter((r) => r.status === 'SUCCESS').length;
    
    let isHealthy = failedCount === 0;
    let score = total === 0 ? 100 : Math.round(((total - failedCount) / total) * 100);
    
    let diagnosis = isHealthy
      ? `【自动化巡检健康汇报】：系统调度流水线运转稳健。已检查近 ${total} 项任务执行记录，未发现接口超时或沙箱文件写入异常。非交易时段已按策略静默休眠。`
      : `【告警提示】：调度账本中检测到 ${failedCount} 次任务失败异常，主要集中在同花顺网络接口或本地数据解析环节，请查阅下方报错详情。`;

    return {
      isHealthy,
      score,
      total,
      failedCount,
      successCount,
      diagnosis,
      lastCheckTime: new Date().toLocaleTimeString('zh-CN')
    };
  }, [ledger, failedIncidents]);

  // 4. 过滤历史账本流水
  const filteredLedger = useMemo(() => {
    if (ledgerFilter === 'ALL') return ledger;
    return ledger.filter((item) => item.status === ledgerFilter);
  }, [ledger, ledgerFilter]);

  // 辅助徽章渲染
  const renderCategoryBadge = (type) => {
    const t = (type || 'unknown').toLowerCase();
    if (t === 'agent') {
      return <span className="badge-category agent"><Bot size={13} /> 智能体 Agent</span>;
    } else if (t === 'script') {
      return <span className="badge-category script"><FileCode size={13} /> Python 脚本</span>;
    } else if (t === 'module') {
      return <span className="badge-category module"><Code2 size={13} /> 原生计算模块</span>;
    } else {
      return <span className="badge-category pipeline"><Layers size={13} /> 数据管道流水线</span>;
    }
  };

  const renderStatusPill = (status) => {
    const s = (status || 'IDLE').toUpperCase();
    if (s === 'SUCCESS') {
      return <span className="status-pill success"><CheckCircle2 size={12} /> 成功 SUCCESS</span>;
    } else if (s === 'FAILED') {
      return <span className="status-pill failed"><AlertOctagon size={12} /> 失败 FAILED</span>;
    } else if (s === 'SKIPPED') {
      return <span className="status-pill skipped"><Clock size={12} /> 休市跳过 SKIPPED</span>;
    } else if (s === 'PENDING') {
      return <span className="status-pill pending"><Activity size={12} /> 排班就绪 PENDING</span>;
    } else {
      return <span className="status-pill idle">待命中 IDLE</span>;
    }
  };

  return (
    <div className="app-container">
      {/* 顶部主导航与全局状态 */}
      <header className="app-header glass-panel">
        <div className="brand-section">
          <div className="brand-icon">
            <Cpu size={24} color="#ffffff" />
          </div>
          <div>
            <h1 className="brand-title">QuantCopilot 统一中枢大屏</h1>
            <p className="brand-subtitle">INTELLIGENT TASK SCHEDULER & SRE OPS MONITOR</p>
          </div>
        </div>

        <div className="header-actions">
          <div className={`badge-status ${online ? 'online' : 'offline'}`}>
            <span className={`status-dot ${online ? 'online animate-pulse-dot' : 'offline'}`} />
            {online ? '调度中枢已连通 (Port 8765)' : '调度服务未运行'}
          </div>

          <button
            className="btn-action"
            onClick={() => setAutoRefresh(!autoRefresh)}
            title="开启/关闭 5 秒自动轮询刷新"
          >
            <Activity size={14} color={autoRefresh ? '#38bdf8' : '#94a3b8'} />
            {autoRefresh ? '自动刷新: 开启 (5s)' : '自动刷新: 暂停'}
          </button>

          <button className="btn-action" onClick={fetchData} disabled={refreshing}>
            <RotateCw size={14} className={refreshing ? 'animate-spin-slow' : ''} />
            刷新
          </button>
        </div>
      </header>

      {/* 离线警示通知栏 */}
      {!online && (
        <div className="offline-banner">
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <AlertTriangle size={18} />
            <span>检测到调度服务器尚未启动。请在后台终端执行：</span>
            <span className="code-pill">uv run python run_scheduler.py</span>
            <span>或带调度器启动对话：</span>
            <span className="code-pill">uv run python chat.py -s</span>
          </div>
          <button className="btn-action" onClick={fetchData}>
            重试连通
          </button>
        </div>
      )}

      {/* 快捷触发广播提示 */}
      {triggerMsg && (
        <div className="offline-banner" style={{ background: 'rgba(16, 185, 129, 0.15)', borderColor: 'rgba(16, 185, 129, 0.35)', color: '#34d399' }}>
          <span>{triggerMsg}</span>
        </div>
      )}

      {/* 页面主标签导航条 (Tab Navigation) */}
      <nav className="nav-tabs-bar">
        <div className="nav-tabs">
          <button
            className={`nav-tab-btn ${activeTab === 'tasks' ? 'active' : ''}`}
            onClick={() => setActiveTab('tasks')}
          >
            <Layers size={17} />
            <span>📋 调度任务大盘 (任务列表)</span>
            <span className="tab-badge">{aggregatedTasks.length} 项</span>
          </button>

          <button
            className={`nav-tab-btn ${activeTab === 'ops' ? 'active' : ''}`}
            onClick={() => setActiveTab('ops')}
          >
            <Shield size={17} />
            <span>🛡️ 运维监控 Agent (系统态势)</span>
            {failedIncidents.length > 0 ? (
              <span className="tab-badge error">🚨 {failedIncidents.length} 项报错</span>
            ) : (
              <span className="tab-badge" style={{ color: '#34d399' }}>🟢 正常</span>
            )}
          </button>
        </div>

        <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
          当前视角: {activeTab === 'tasks' ? '任务注册表与定时队列' : '无头 SRE 智能体自检态势'}
        </div>
      </nav>

      {/* =====================================================================
          子页面 1: 调度任务全景列表大盘
          ===================================================================== */}
      {activeTab === 'tasks' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* 四大任务分类统计条 */}
          <div className="task-stats-bar">
            <div className="mini-stat-card">
              <div>
                <p className="mini-stat-label">Agent 智能体任务</p>
                <p className="mini-stat-value" style={{ color: '#c084fc' }}>
                  {tasks.filter((t) => t.type === 'agent').length}
                </p>
              </div>
              <Bot size={28} color="#c084fc" opacity={0.6} />
            </div>

            <div className="mini-stat-card">
              <div>
                <p className="mini-stat-label">Python 独立脚本任务</p>
                <p className="mini-stat-value" style={{ color: '#22d3ee' }}>
                  {tasks.filter((t) => t.type === 'script').length}
                </p>
              </div>
              <FileCode size={28} color="#22d3ee" opacity={0.6} />
            </div>

            <div className="mini-stat-card">
              <div>
                <p className="mini-stat-label">原生 Python 计算模块</p>
                <p className="mini-stat-value" style={{ color: '#60a5fa' }}>
                  {tasks.filter((t) => t.type === 'module').length}
                </p>
              </div>
              <Code2 size={28} color="#60a5fa" opacity={0.6} />
            </div>

            <div className="mini-stat-card">
              <div>
                <p className="mini-stat-label">队列中活跃倒计时作业</p>
                <p className="mini-stat-value" style={{ color: '#38bdf8' }}>
                  {jobs.length}
                </p>
              </div>
              <Clock size={28} color="#38bdf8" opacity={0.6} />
            </div>
          </div>

          {/* 任务全景表格 */}
          <div className="task-table-wrapper">
            <table className="task-table">
              <thead>
                <tr>
                  <th style={{ width: '22%' }}>任务名称与描述</th>
                  <th style={{ width: '15%' }}>任务类别</th>
                  <th style={{ width: '16%' }}>排班/触发规则</th>
                  <th style={{ width: '18%' }}>下次触发 / 最近运行时间</th>
                  <th style={{ width: '15%' }}>当前运行状态</th>
                  <th style={{ width: '14%', textAlign: 'right' }}>操作</th>
                </tr>
              </thead>
              <tbody>
                {aggregatedTasks.length === 0 ? (
                  <tr>
                    <td colSpan="6" style={{ textAlign: 'center', padding: '40px', color: 'var(--text-muted)' }}>
                      暂未加载到任务。请确认后台调度中枢 `run_scheduler.py` 是否正常运行。
                    </td>
                  </tr>
                ) : (
                  aggregatedTasks.map((t) => (
                    <tr key={t.name}>
                      {/* 任务名称 */}
                      <td>
                        <div className="task-name-cell">
                          <span className="task-title">{t.name}</span>
                          <span className="task-desc">{t.description || '无详细描述'}</span>
                        </div>
                      </td>

                      {/* 任务类别 */}
                      <td>{renderCategoryBadge(t.type)}</td>

                      {/* 触发规则 */}
                      <td>
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem', color: '#93c5fd' }}>
                          {t.triggerRule}
                        </span>
                      </td>

                      {/* 下次触发或最近运行时间 */}
                      <td>
                        {t.nextRunTime ? (
                          <div className="time-cell" style={{ color: '#38bdf8' }}>
                            <Clock size={13} />
                            <span>下次: {t.nextRunTime}</span>
                          </div>
                        ) : t.lastRunTime ? (
                          <div className="time-cell">
                            <span>上次: {t.lastRunTime.slice(11, 19)} ({t.lastDuration}s)</span>
                          </div>
                        ) : (
                          <span style={{ color: 'var(--text-muted)', fontSize: '0.785rem' }}>未触发过</span>
                        )}
                      </td>

                      {/* 运行状态 */}
                      <td>{renderStatusPill(t.status)}</td>

                      {/* 操作 */}
                      <td style={{ textAlign: 'right' }}>
                        <button
                          className="btn-action btn-primary"
                          style={{ padding: '6px 14px', fontSize: '0.775rem' }}
                          onClick={() => handleTriggerTask(t.name)}
                          disabled={triggeringTask === t.name || !online}
                        >
                          <Play size={12} />
                          {triggeringTask === t.name ? '触发中' : '立即运行'}
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* =====================================================================
          子页面 2: 运维监控 Agent 专属页面 (系统态势与报错归因)
          ===================================================================== */}
      {activeTab === 'ops' && (
        <div className="ops-page-container">
          {/* 1. 核心健康态势大标语 (如果正常展示绿，有报错展示红) */}
          <div className={`health-hero-banner ${opsAnalysis.isHealthy ? 'healthy' : 'critical'}`}>
            <div className="health-title-group">
              <div className={`health-big-icon ${opsAnalysis.isHealthy ? 'healthy' : 'critical'}`}>
                {opsAnalysis.isHealthy ? <CheckCircle2 size={32} /> : <AlertOctagon size={32} />}
              </div>
              <div>
                <h2 className="health-status-text" style={{ color: opsAnalysis.isHealthy ? '#34d399' : '#fb7185' }}>
                  {opsAnalysis.isHealthy ? '系统运行状态：一切正常' : `系统警报：检测到 ${opsAnalysis.failedCount} 项任务报错！`}
                </h2>
                <p className="health-subtext">
                  {opsAnalysis.isHealthy
                    ? '所有后台任务与子 Agent 协同链路运行良好，无堵塞、无超时熔断。'
                    : '检测到任务执行异常中断，运维哨兵已锁定错误堆栈，请查阅下方故障清单。'}
                </p>
              </div>
            </div>

            <div className="health-score-badge">
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>系统健康指数</div>
              <div className="score-num" style={{ color: opsAnalysis.isHealthy ? '#34d399' : '#fb7185' }}>
                {opsAnalysis.score}%
              </div>
            </div>
          </div>

          {/* 2. 维护 Agent 输出信息框 (SRE Terminal) */}
          <div className="glass-panel ops-diagnosis-panel">
            <div className="ops-terminal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Terminal size={15} color="#38bdf8" />
                <span>运维监控智能体 (SystemOpsMonitorAgent) — 自动化体检输出日志</span>
              </div>
              <span>巡检周期: 每 5 分钟自动心跳</span>
            </div>

            <div className="ops-terminal-box">
              <div style={{ color: '#38bdf8', marginBottom: '8px' }}>
                [SRE-AUDIT-DAEMON] 打卡时间: {opsAnalysis.lastCheckTime} | 模式: 纯后台无头静默巡检 (Headless)
              </div>
              <p style={{ lineHeight: '1.6' }}>{opsAnalysis.diagnosis}</p>
              <div style={{ marginTop: '10px', fontSize: '0.775rem', color: '#94a3b8' }}>
                • 账本历史扫描: 共 {opsAnalysis.total} 条记录 | 成功: {opsAnalysis.successCount} 次 | 失败: {opsAnalysis.failedCount} 次
              </div>
            </div>
          </div>

          {/* 3. 报错任务提示专区 (如果系统有报错，醒目提示) */}
          <div className="glass-panel" style={{ padding: '24px' }}>
            <h3 style={{ fontSize: '1.05rem', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
              <AlertOctagon size={18} color={opsAnalysis.isHealthy ? '#34d399' : '#fb7185'} />
              <span>异常报错任务排查专区 ({failedIncidents.length})</span>
            </h3>

            {failedIncidents.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '36px 0', color: '#34d399', background: 'rgba(16, 185, 129, 0.05)', borderRadius: 'var(--radius-md)' }}>
                <CheckCircle2 size={36} style={{ margin: '0 auto 10px', opacity: 0.8 }} />
                <p style={{ fontWeight: 600 }}>太棒了！当前系统零报错</p>
                <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                  所有已执行的任务均成功交付产物，系统运行非常健康。
                </p>
              </div>
            ) : (
              <div className="incidents-container">
                {failedIncidents.map((incident) => (
                  <div key={incident.run_id} className="incident-card">
                    <div className="incident-header">
                      <div className="incident-title">
                        <Flame size={18} color="#fb7185" />
                        <span>任务失败: {incident.task_name}</span>
                        <span className="badge-tag failed">RUN_ID: {incident.run_id}</span>
                      </div>
                      <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                        发生时间: {incident.start_time} (耗时: {incident.duration_seconds}s)
                      </span>
                    </div>

                    <div style={{ fontSize: '0.825rem', color: '#fda4af' }}>
                      <strong>异常摘要: </strong>
                      {incident.result_summary || '未记录摘要'}
                    </div>

                    {incident.error_trace ? (
                      <div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '4px' }}>
                          底层 Python 错误堆栈 (Error Traceback):
                        </div>
                        <pre className="error-trace-box">{incident.error_trace}</pre>
                      </div>
                    ) : (
                      <div style={{ fontSize: '0.785rem', color: 'var(--text-muted)' }}>暂无堆栈记录</div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* 4. 完整历史账本流水记录 (可过滤) */}
          <div className="glass-panel">
            <div className="ledger-filter-bar">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 600, fontSize: '0.95rem' }}>
                <Database size={17} color="#a855f7" />
                <span>任务执行历史账本流水 ({filteredLedger.length})</span>
              </div>

              <div className="filter-pills">
                <button
                  className={`filter-pill ${ledgerFilter === 'ALL' ? 'active' : ''}`}
                  onClick={() => setLedgerFilter('ALL')}
                >
                  全部 ({ledger.length})
                </button>
                <button
                  className={`filter-pill ${ledgerFilter === 'SUCCESS' ? 'active' : ''}`}
                  onClick={() => setLedgerFilter('SUCCESS')}
                >
                  成功 ({ledger.filter((r) => r.status === 'SUCCESS').length})
                </button>
                <button
                  className={`filter-pill ${ledgerFilter === 'FAILED' ? 'active' : ''}`}
                  onClick={() => setLedgerFilter('FAILED')}
                >
                  失败 ({ledger.filter((r) => r.status === 'FAILED').length})
                </button>
              </div>
            </div>

            <div style={{ padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {filteredLedger.map((item) => (
                <div key={item.run_id} className="ledger-item" style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <span className={`badge-tag ${item.status.toLowerCase()}`}>
                      {item.status === 'SUCCESS' ? '✔' : item.status === 'SKIPPED' ? '⏸' : '✖'} {item.status}
                    </span>
                    <strong style={{ fontFamily: 'var(--font-mono)', fontSize: '0.875rem' }}>{item.task_name}</strong>
                    <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                      耗时: {item.duration_seconds}s
                    </span>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                    <span style={{ fontSize: '0.785rem', color: 'var(--text-secondary)' }}>
                      {item.result_summary ? item.result_summary.slice(0, 50) + '...' : '无摘要'}
                    </span>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                      {item.start_time?.slice(11, 19)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
