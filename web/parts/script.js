// === Helpers ===
async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error('HTTP ' + res.status);
  return res.json();
}

function escapeHtml(s) {
  if (s == null) return '';
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function timeAgo(ts) {
  if (!ts) return '';
  const diff = Date.now() - new Date(ts).getTime();
  if (diff < 0) return 'just now';
  if (diff < 60000) return 'just now';
  if (diff < 3600000) return Math.floor(diff/60000) + 'm ago';
  if (diff < 86400000) return Math.floor(diff/3600000) + 'h ago';
  return Math.floor(diff/86400000) + 'd ago';
}

function fmtTime(ts) {
  if (!ts) return '';
  const d = new Date(ts);
  return d.toLocaleString('zh-CN', {month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'});
}

// === Executor icons ===
const executorIcons = {codex:'⚡',codewhale:'🐋',opencode:'📂',ollama:'🦙',mimo:'🎮',hermes:'✉️'};
function getExecutorIcon(cmd) { return executorIcons[cmd] || '🔧'; }

// === State ===
let agentsCache = [];
let tasksCache = [];
let selectedTaskId = null;
let logSSE = null;
let taskChart = null;
let costChart = null;

// === KPI ===
function renderKPIs(tasks, cost) {
  const stats = tasks.stats || {};
  const total = (tasks.tasks || []).length;
  document.getElementById('kpi-total').textContent = total;
  document.getElementById('kpi-pending').textContent = stats.pending || 0;
  document.getElementById('kpi-done').textContent = stats.done || 0;
  document.getElementById('kpi-failed').textContent = stats.failed || 0;
  document.getElementById('kpi-cost').textContent = '$' + (cost.totalCost || 0).toFixed(4);
  document.getElementById('last-updated').textContent = 'Updated ' + new Date().toLocaleTimeString('zh-CN');
}

// === Charts ===
function initTaskChart(stats) {
  const ctx = document.getElementById('chart-tasks').getContext('2d');
  const labels = ['pending','in_progress','done','failed','cancelled'];
  const colors = ['#5c8aff','#4a7cff','#22c55e','#f44336','#9e9e9e'];
  const data = labels.map(l => stats[l] || 0);
  if (taskChart) { taskChart.data.datasets[0].data = data; taskChart.update(); return; }
  taskChart = new Chart(ctx, {
    type: 'doughnut',
    data: { labels, datasets: [{ data, backgroundColor: colors, borderWidth: 0 }] },
    options: {
      cutout: '70%',
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: 'right', labels: { font: { size: 11 }, color: '#5a6a80', padding: 8 } }
      }
    }
  });
}

function initCostChart(byAgent) {
  const ctx = document.getElementById('chart-cost').getContext('2d');
  const labels = Object.keys(byAgent);
  const values = labels.map(k => byAgent[k].cost);
  if (costChart) { costChart.data.labels = labels; costChart.data.datasets[0].data = values; costChart.update(); return; }
  costChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: 'rgba(74,124,255,0.6)',
        borderColor: 'rgba(74,124,255,1)',
        borderWidth: 1,
        borderRadius: 4
      }]
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { color: 'rgba(200,210,230,.3)' }, ticks: { color: '#8c9ab0', font: { size: 10 } } },
        y: { grid: { display: false }, ticks: { color: '#5a6a80', font: { size: 11 } } }
      }
    }
  });
}

// === Agents ===
function renderAgents(data) {
  const grid = document.getElementById('agents-grid');
  agentsCache = data.agents || [];
  document.getElementById('agents-count').textContent = agentsCache.length + ' agents';
  if (!agentsCache.length) { grid.innerHTML = '<div class="loading">No agents configured.</div>'; return; }
  grid.innerHTML = agentsCache.map(a => {
    const name = escapeHtml(a.displayName || a.id);
    const id = escapeHtml(a.id);
    const enabled = a.enabled !== false;
    const cmd = escapeHtml(a.executorCommand || 'N/A');
    const type = escapeHtml(a.executorType || 'N/A');
    const icon = getExecutorIcon(a.executorCommand);
    const role = escapeHtml(a.role || 'unknown');
    const risk = escapeHtml(a.riskLevel || 'unknown');
    const badgeCls = enabled ? 'badge-enabled' : 'badge-disabled';
    const badgeTxt = enabled ? 'ACTIVE' : 'DISABLED';
    const cardCls = enabled ? 'agent-card' : 'agent-card disabled';
    return '<div class="'+cardCls+'">' +
      '<div class="agent-header"><div><div class="agent-name">'+name+'</div><div class="agent-id">'+id+'</div></div>' +
      '<span class="agent-badge '+badgeCls+'">'+badgeTxt+'</span></div>' +
      '<div class="executor-tag"><span>'+icon+'</span> '+cmd+' <span style="color:#8c9ab0">· '+type+'</span></div>' +
      '<div class="agent-meta"><span>Role: '+role+'</span><span>Risk: '+risk+'</span></div></div>';
  }).join('');
}

// === Tasks ===
function renderTasks(data) {
  const list = document.getElementById('task-list');
  tasksCache = data.tasks || [];
  document.getElementById('tasks-count').textContent = tasksCache.length + ' tasks';
  if (!tasksCache.length) { list.innerHTML = '<div class="loading">No tasks found.</div>'; return; }
  list.innerHTML = tasksCache.slice().reverse().map(t => {
    const status = escapeHtml(t.status || 'unknown');
    const title = escapeHtml(t.title || t.id);
    const assignee = escapeHtml(t.assignee || '—');
    const tid = escapeHtml(t.id);
    const isPending = status === 'pending';
    const isInProgress = status === 'in_progress' || status === 'running';
    const sel = tid === selectedTaskId ? ' selected' : '';
    let pulseHtml = isInProgress ? '<span class="pulse-dot"></span>' : '';
    let right = '<div class="task-right">';
    if (isPending) {
      right += '<select class="agent-select" id="sel-'+tid+'">' +
        agentsCache.map(a => '<option value="'+escapeHtml(a.id)+'">'+escapeHtml(a.displayName||a.id)+'</option>').join('') +
        '</select>';
      right += '<button class="exec-btn" onclick="executeTask(\''+tid+'\')">▶ Execute</button>';
    }
    right += '<span class="task-status status-'+status+'">'+pulseHtml+status+'</span></div>';
    return '<div class="task-item'+sel+'" onclick="selectTask(\''+tid+'\')">' +
      '<div><div class="task-title">'+title+'</div><div class="task-sub">'+tid+' · '+assignee+'</div></div>' +
      right + '</div>';
  }).join('');
}

// === Create Task ===
function toggleCreateForm() {
  document.getElementById('create-form').classList.toggle('open');
}

async function createTask() {
  const title = document.getElementById('new-task-title').value.trim();
  const priority = document.getElementById('new-task-priority').value;
  if (!title) { alert('请输入任务标题'); return; }
  try {
    const res = await fetch('/api/tasks/create', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({title, priority})
    });
    const data = await res.json();
    if (data.ok) {
      document.getElementById('new-task-title').value = '';
      toggleCreateForm();
      loadAll();
    } else {
      alert('创建失败: ' + (data.error || 'Unknown'));
    }
  } catch(e) {
    alert('请求失败: ' + e.message);
  }
}

// === Execute Task ===
async function executeTask(taskId) {
  const sel = document.getElementById('sel-'+taskId);
  const assignee = sel ? sel.value : 'agent-exec-01';
  if (!confirm('Start execution of '+taskId+' with '+assignee+'?')) return;
  try {
    const res = await fetch('/api/tasks/execute', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({id: taskId, assignee: assignee})
    });
    const data = await res.json();
    if (data.ok) {
      selectTask(taskId);
      setTimeout(loadAll, 2000);
    } else {
      alert('Execution failed: ' + (data.error || 'Unknown'));
    }
  } catch(e) {
    alert('Request failed: ' + e.message);
  }
}

// === Task Selection + Log SSE ===
function selectTask(taskId) {
  selectedTaskId = taskId;
  // Re-render to show selection
  renderTasks({tasks: tasksCache, stats: {}});
  // Connect log SSE
  if (logSSE) logSSE.close();
  const panel = document.getElementById('log-panel');
  panel.innerHTML = '';
  logSSE = new EventSource('/api/stream/tasks/'+taskId+'/logs');
  logSSE.addEventListener('message', function(e) {
    try {
      const msg = JSON.parse(e.data);
      if (msg.type === 'log') {
        const line = document.createElement('div');
        line.className = 'log-line';
        const text = msg.data.line || '';
        if (text.includes('[ERROR]') || text.includes('error')) line.classList.add('log-error');
        else if (text.includes('[WARN]') || text.includes('warn')) line.classList.add('log-warn');
        else if (text.includes('[INFO]') || text.includes('info')) line.classList.add('log-info');
        line.textContent = text;
        panel.appendChild(line);
        panel.scrollTop = panel.scrollHeight;
      } else if (msg.type === 'status') {
        const st = msg.data.status || 'unknown';
        let badge = '<div class="log-status running">'+st+'</div>';
        if (st === 'done' || st === 'failed' || st === 'cancelled') {
          badge = '<div class="log-status '+st+'">'+st.toUpperCase()+' ✓</div>';
        }
        const existing = panel.querySelector('.log-status');
        if (existing) existing.remove();
        panel.insertAdjacentHTML('beforeend', badge);
        panel.scrollTop = panel.scrollHeight;
      } else if (msg.type === 'end') {
        const st = msg.data.status || 'done';
        const existing = panel.querySelector('.log-status');
        if (existing) existing.remove();
        panel.insertAdjacentHTML('beforeend', '<div class="log-status '+st+'">'+st.toUpperCase()+' ✓</div>');
        panel.scrollTop = panel.scrollHeight;
        logSSE.close();
      }
    } catch(err) {}
  });
  logSSE.onerror = function() {
    panel.insertAdjacentHTML('beforeend', '<div class="log-line log-warn">— connection lost —</div>');
    panel.scrollTop = panel.scrollHeight;
  };
}

// === Messages ===
function renderMessages(data) {
  const list = document.getElementById('msg-list');
  if (!data.entries || !data.entries.length) { list.innerHTML = '<div class="loading">No messages.</div>'; return; }
  list.innerHTML = data.entries.map(m => {
    const from = escapeHtml(m.from || m.fromId || 'unknown');
    const to = escapeHtml(m.to || m.toId || 'unknown');
    const msg = escapeHtml((m.message || m.content || '').substring(0, 120));
    const time = m.timestamp || m.ts || '';
    return '<div class="msg-item"><span class="msg-time">'+timeAgo(time)+'</span>' +
      '<span class="msg-from">'+from+'</span> → <span class="msg-to">'+to+'</span>' +
      '<div class="msg-content">'+msg+'</div></div>';
  }).join('');
}

// === Audit Timeline ===
function renderAudit(data) {
  const tl = document.getElementById('audit-timeline');
  if (!data.entries || !data.entries.length) { tl.innerHTML = '<div class="loading">No audit entries.</div>'; return; }
  tl.innerHTML = data.entries.map(e => {
    const evt = escapeHtml(e.event || e.type || 'unknown');
    const tid = escapeHtml(e.taskId || e.task_id || e.id || '');
    const time = e.timestamp || e.ts || e.time || '';
    const cls = 'audit-item event-' + (e.event || e.type || '').toLowerCase().replace(/_/g,'-');
    return '<div class="'+cls+'"><div class="audit-time">'+fmtTime(time)+'</div>' +
      '<div class="audit-event">'+evt+'</div>' +
      (tid ? '<div class="audit-taskid">'+tid+'</div>' : '') + '</div>';
  }).join('');
}

// === Alerts ===
function renderAlerts(data) {
  const list = document.getElementById('alerts-list');
  const dot = document.getElementById('status-dot');
  const text = document.getElementById('status-text');
  if (data.level === 'green') { dot.className = 'status-dot'; text.textContent = 'All systems normal'; }
  else if (data.level === 'yellow') { dot.className = 'status-dot yellow'; text.textContent = 'Warnings'; }
  else { dot.className = 'status-dot red'; text.textContent = 'Critical issues'; }
  if (!data.alerts || !data.alerts.length) {
    list.innerHTML = '<div class="alert-item alert-green">✅ All systems normal.</div>';
    return;
  }
  list.innerHTML = data.alerts.map(a => {
    const cls = a.level === 'red' ? 'alert-red' : (a.level === 'yellow' ? 'alert-yellow' : 'alert-green');
    const icon = a.level === 'red' ? '🔴' : (a.level === 'yellow' ? '🟡' : '🟢');
    return '<div class="alert-item '+cls+'">'+icon+' '+escapeHtml(a.text)+'</div>';
  }).join('');
}

// === Load All ===
async function loadAll() {
  try {
    const [agents, tasks, messages, alerts, audit, cost] = await Promise.all([
      fetchJSON('/api/agents'),
      fetchJSON('/api/tasks'),
      fetchJSON('/api/messages?limit=30'),
      fetchJSON('/api/alerts'),
      fetchJSON('/api/audit?limit=20'),
      fetchJSON('/api/cost')
    ]);
    agentsCache = agents.agents || [];
    renderAgents(agents);
    renderTasks(tasks);
    renderMessages(messages);
    renderAlerts(alerts);
    renderAudit(audit);
    renderKPIs(tasks, cost);
    initTaskChart(tasks.stats || {});
    initCostChart(cost.byAgent || {});
    document.getElementById('footer').textContent =
      'Data as of ' + new Date().toLocaleString('zh-CN') + ' · Auto-refresh 30s';
  } catch(e) {
    console.error('Load error:', e);
    document.getElementById('status-text').textContent = 'Error: ' + e.message;
  }
}

// === Global SSE ===
function connectSSE() {
  const es = new EventSource('/api/stream/events');
  es.addEventListener('message', function(e) {
    try {
      const msg = JSON.parse(e.data);
      if (msg.type === 'tasks') { renderTasks(msg.data); renderKPIs(msg.data, {}); }
      else if (msg.type === 'agents') renderAgents(msg.data);
      else if (msg.type === 'audit') renderAudit({entries:[msg.data]});
    } catch(err) {}
  });
  es.onerror = function() {
    document.getElementById('status-text').textContent = 'Reconnecting…';
  };
}

// === Init ===
loadAll();
connectSSE();
setInterval(loadAll, 30000);
