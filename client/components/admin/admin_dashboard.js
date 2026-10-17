const api = axios.create({ baseURL: '', headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` } });
let charts = {};

// Helper to render stats grid
function renderStats(containerId, stats) {
    const container = document.getElementById(containerId);
    container.innerHTML = '';
    for (const [key, value] of Object.entries(stats)) {
        container.innerHTML += `<div class="stat-card"><div class="stat-title">${key.replace(/_/g, ' ').toUpperCase()}</div><div class="stat-value">${value}</div></div>`;
    }
}

// Overview
async function loadOverview() {
    const res = await api.get('/admin/analytics/overview?period=week');
    const data = res.data;
    renderStats('overviewStats', {
        'Total Users': data.total_users,
        'Documents': data.total_documents,
        'Conversations': data.total_conversations,
        'Queries (7d)': data.queries_today,
        'Active Users': data.active_users,
        'Avg Confidence': `${data.avg_confidence}%`,
        'AI Cost': `$${data.total_cost}`,
        'Storage': `${data.storage_gb} GB`
    });
    // Trend chart
    if (charts.trend) charts.trend.destroy();
    charts.trend = new Chart(document.getElementById('trendChart'), {
        type: 'line', data: { labels: data.trend.map(t => t.date), datasets: [{ label: 'Queries', data: data.trend.map(t => t.count), borderColor: 'rgba(37, 150, 190, 1)', tension: 0.3 }] }
    });
    if (charts.cost) charts.cost.destroy();
    charts.cost = new Chart(document.getElementById('costChart'), {
        type: 'pie', data: { labels: data.cost_by_provider.map(c => c.provider), datasets: [{ data: data.cost_by_provider.map(c => c.cost), backgroundColor: ['rgba(37, 150, 190, 1)', '#10b981', '#f59e0b', '#ef4444'] }] }
    });
}

// Users
async function loadUsers() {
    const res = await api.get('/admin/analytics/users');
    const data = res.data;
    renderStats('userStats', {
        'Total': data.total,
        'Admins': data.roles.admins,
        'Employees': data.roles.employees,
        'Departments': data.department_wise.length
    });
    if (charts.dept) charts.dept.destroy();
    charts.dept = new Chart(document.getElementById('deptChart'), {
        type: 'bar', data: { labels: data.department_wise.map(d => d.name), datasets: [{ label: 'Users', data: data.department_wise.map(d => d.count), backgroundColor: 'rgba(37, 150, 190, 1)' }] }
    });
    const activeTbody = document.querySelector('#activeUsersTable tbody');
    activeTbody.innerHTML = data.most_active.map(u => `<tr><td>${u.name}</td><td>${u.queries} queries</td></tr>`).join('');
    const usersTbody = document.querySelector('#usersTable tbody');
    usersTbody.innerHTML = data.users.map(u => `<tr><td>${u.name}</td><td>${u.email}</td><td>${u.department || '-'}</td><td>${u.team || '-'}</td><td><span class="badge">${u.role}</span></td><td>${u.queries}</td></tr>`).join('');
}

// Documents
async function loadDocuments() {
    const res = await api.get('/admin/analytics/documents');
    const data = res.data;
    renderStats('docStats', {
        'Total': data.total_documents,
        'Storage': `${data.storage_gb} GB`,
        'Duplicates': data.duplicate_files,
        'Private': data.private_files,
        'Department': data.department_files,
        'Team': data.team_files
    });
    if (charts.fileType) charts.fileType.destroy();
    charts.fileType = new Chart(document.getElementById('fileTypeChart'), {
        type: 'pie', data: { labels: data.file_types.map(f => f.type), datasets: [{ data: data.file_types.map(f => f.count), backgroundColor: ['rgba(37, 150, 190, 1)', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6'] }] }
    });
    if (charts.deptFiles) charts.deptFiles.destroy();
    charts.deptFiles = new Chart(document.getElementById('deptFilesChart'), {
        type: 'bar', data: { labels: data.department_wise.map(d => d.department), datasets: [{ label: 'Files', data: data.department_wise.map(d => d.count), backgroundColor: '#f59e0b' }] }
    });
    const recentTbody = document.querySelector('#recentUploadsTable tbody');
    recentTbody.innerHTML = data.recent_uploads.map(f => `<tr><td>${f.name}</td><td>${f.department || '-'}</td><td>${f.team || '-'}</td><td>${new Date(f.uploaded_at).toLocaleString()}</td></tr>`).join('');
}

// AI Usage
async function loadAIUsage() {
    const res = await api.get('/admin/analytics/ai-usage?period=week');
    const data = res.data;
    renderStats('aiStats', {
        'Total Queries': data.total_queries,
        'Avg Response': `${data.avg_response_time_ms} ms`,
        'Avg Confidence': `${data.avg_confidence}%`,
        'Total Cost': `$${data.total_cost}`
    });
    if (charts.hourly) charts.hourly.destroy();
    charts.hourly = new Chart(document.getElementById('hourlyChart'), {
        type: 'bar', data: { labels: data.hourly_queries.map(h => `${h.hour}:00`), datasets: [{ label: 'Queries', data: data.hourly_queries.map(h => h.count), backgroundColor: 'rgba(37, 150, 190, 1)' }] }
    });
    const topTbody = document.querySelector('#topQuestionsTable tbody');
    topTbody.innerHTML = data.top_questions.map(q => `<tr><td>${q.question}</td><td>${q.count}</td></tr>`).join('');
}

// Retrieval
async function loadRetrieval() {
    const res = await api.get('/admin/analytics/retrieval');
    const data = res.data;
    renderStats('retrievalStats', {
        'Avg Chunks': data.avg_retrieved_chunks,
        'Avg Similarity': data.avg_similarity,
        'Failed Retrievals': data.failed_retrievals,
        'Knowledge Coverage': `${data.knowledge_coverage}%`
    });
    if (charts.sim) charts.sim.destroy();
    charts.sim = new Chart(document.getElementById('simChart'), {
        type: 'bar', data: { labels: data.similarity_distribution.map(s => s.range), datasets: [{ label: 'Chunks', data: data.similarity_distribution.map(s => s.count), backgroundColor: '#10b981' }] }
    });
    const topRetrievedTbody = document.querySelector('#topRetrievedTable tbody');
    topRetrievedTbody.innerHTML = data.top_retrieved_documents.map(d => `<tr><td>${d.document}</td><td>${d.count}</td></tr>`).join('');
}

// Knowledge Gaps
async function loadKnowledgeGaps() {
    const res = await api.get('/admin/analytics/knowledge-gaps');
    const data = res.data;
    renderStats('gapStats', {
        'Total Gaps': data.total_gaps,
        'Resolved': data.resolved,
        'Pending': data.pending
    });
    const gapTbody = document.querySelector('#gapTable tbody');
    gapTbody.innerHTML = data.top_missing_topics.map(g => `<tr><td>${g.question}</td><td>${g.occurred} times</td></tr>`).join('');
}

// Feedback
async function loadFeedback() {
    const res = await api.get('/admin/analytics/feedback');
    const data = res.data;
    renderStats('feedbackStats', {
        '👍 Helpful': data.positive,
        '👎 Not Helpful': data.negative,
        '⭐ Avg Rating': `${data.average_rating}/5`
    });
    if (charts.feedbackTrend) charts.feedbackTrend.destroy();
    charts.feedbackTrend = new Chart(document.getElementById('feedbackTrendChart'), {
        type: 'line', data: { labels: data.trend.map(t => t.month), datasets: [
            { label: 'Helpful', data: data.trend.map(t => t.helpful), borderColor: '#10b981' },
            { label: 'Not Helpful', data: data.trend.map(t => t.not_helpful), borderColor: '#ef4444' }
        ] }
    });
    const worstTbody = document.querySelector('#worstQueriesTable tbody');
    worstTbody.innerHTML = data.worst_queries.map(q => `<tr><td>${q.question}</td><td>${q.confidence}%</td></tr>`).join('');
}

// Security
async function loadSecurity() {
    const res = await api.get('/admin/analytics/security');
    const data = res.data;
    const accessTbody = document.querySelector('#accessLogsTable tbody');
    accessTbody.innerHTML = data.recent_access_logs.map(log => `<tr><td>${log.user}</td><td>${log.file}</td><td>${log.action}</td><td>${log.ip}</td><td>${new Date(log.timestamp).toLocaleString()}</td></tr>`).join('');
}

// Organization
async function loadOrganization() {
    const res = await api.get('/admin/analytics/organization');
    const data = res.data;
    document.getElementById('companyName').innerText = data.name;
    renderStats('orgStats', {
        'Employees': data.employees,
        'Departments': data.departments,
        'Teams': data.teams,
        'Industry': data.industry || 'N/A'
    });
    const apiTbody = document.querySelector('#apiKeysTable tbody');
    apiTbody.innerHTML = data.api_providers.map(p => `<tr><td>${p.provider}</td><td>${p.active ? '✅ Active' : '❌ Inactive'}</td></tr>`).join('');
}

// Tab switching & loading
const tabs = document.querySelectorAll('.tab-btn');
const contents = document.querySelectorAll('.tab-content');
tabs.forEach(btn => {
    btn.addEventListener('click', () => {
        const tabId = btn.dataset.tab;
        tabs.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        contents.forEach(c => c.classList.remove('active'));
        document.getElementById(`${tabId}-tab`).classList.add('active');
        if (tabId === 'overview') loadOverview();
        else if (tabId === 'users') loadUsers();
        else if (tabId === 'documents') loadDocuments();
        else if (tabId === 'ai-usage') loadAIUsage();
        else if (tabId === 'retrieval') loadRetrieval();
        else if (tabId === 'knowledge') loadKnowledgeGaps();
        else if (tabId === 'feedback') loadFeedback();
        else if (tabId === 'security') loadSecurity();
        else if (tabId === 'organization') loadOrganization();
    });
});

// Initial load
loadOverview();
loadUsers();      // preload in background
loadDocuments();
loadAIUsage();
loadRetrieval();
loadKnowledgeGaps();
loadFeedback();
loadSecurity();
loadOrganization();
