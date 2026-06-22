const api = axios.create({
    baseURL: '',
    headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` }
});
api.interceptors.response.use(res => res, error => {
    if (error.response?.status === 401) window.location.href = '/';
    showToast(error.response?.data?.detail || 'Error', 'error');
    return Promise.reject(error);
});

function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `<span>${type === 'success' ? '✓' : type === 'error' ? '⚠' : 'ℹ'}</span> <span>${message}</span>`;
    container.appendChild(toast);
    setTimeout(() => { toast.style.animation = 'fadeOut 0.3s forwards'; setTimeout(() => toast.remove(), 300); }, 3000);
}

// Load users with department AND team dropdowns
async function loadUsers() {
    const res = await api.get('/admin/users');
    const tbody = document.querySelector('#users-table tbody');
    tbody.innerHTML = '';
    const deptsRes = await api.get('/admin/departments');
    const teamsRes = await api.get('/admin/teams');
    const deptMap = deptsRes.data;
    const teamMap = teamsRes.data;

    for (const u of res.data.users) {
        const row = tbody.insertRow();
        row.insertCell(0).innerText = u.id;
        row.insertCell(1).innerText = u.name;
        row.insertCell(2).innerText = u.email;

        // Role dropdown
        const roleSelect = document.createElement('select');
        roleSelect.className = 'role-select';
        ['org_admin', 'department_manager', 'team_lead', 'employee'].forEach(r => {
            const opt = document.createElement('option');
            opt.value = r; opt.textContent = r;
            if (u.role === r) opt.selected = true;
            roleSelect.appendChild(opt);
        });
        row.insertCell(3).appendChild(roleSelect);

        // Department dropdown
        const deptSelect = document.createElement('select');
        deptSelect.className = 'dept-select';
        deptSelect.innerHTML = '<option value="">None</option>';
        deptMap.forEach(d => {
            const opt = document.createElement('option');
            opt.value = d.id;
            opt.textContent = d.name;
            if (u.department_id === d.id) opt.selected = true;
            deptSelect.appendChild(opt);
        });
        row.insertCell(4).appendChild(deptSelect);

        // Team dropdown (dynamic, depends on selected department)
        const teamSelect = document.createElement('select');
        teamSelect.className = 'team-select';
        teamSelect.innerHTML = '<option value="">None</option>';
        // Filter teams by selected department
        function populateTeams() {
            const selectedDeptId = deptSelect.value;
            teamSelect.innerHTML = '<option value="">None</option>';
            teamMap.forEach(t => {
                if (t.department_id == selectedDeptId || (selectedDeptId === '' && t.department_id === null)) {
                    const opt = document.createElement('option');
                    opt.value = t.id;
                    opt.textContent = t.name;
                    if (u.team_id === t.id) opt.selected = true;
                    teamSelect.appendChild(opt);
                }
            });
        }
        deptSelect.addEventListener('change', populateTeams);
        populateTeams();
        row.insertCell(5).appendChild(teamSelect);

        // Save button
        const saveBtn = document.createElement('button');
        saveBtn.textContent = 'Save';
        saveBtn.className = 'save-user';
        saveBtn.onclick = async () => {
            await api.put(`/admin/users/${u.id}`, {
                role: roleSelect.value,
                department_id: deptSelect.value ? parseInt(deptSelect.value) : null,
                team_id: teamSelect.value ? parseInt(teamSelect.value) : null
            });
            showToast('User updated', 'success');
        };
        row.insertCell(6).appendChild(saveBtn);
    }
}

// Departments CRUD (unchanged)
async function loadDepartments() {
    const res = await api.get('/admin/departments');
    const tbody = document.querySelector('#departments-table tbody');
    tbody.innerHTML = '';
    for (const d of res.data) {
        const row = tbody.insertRow();
        row.insertCell(0).innerText = d.id;
        row.insertCell(1).innerText = d.name;
        row.insertCell(2).innerText = d.description || '';
        const editBtn = document.createElement('button');
        editBtn.textContent = 'Edit'; editBtn.className = 'action-btn';
        editBtn.onclick = () => editDepartment(d.id, d.name, d.description);
        const delBtn = document.createElement('button');
        delBtn.textContent = 'Delete'; delBtn.className = 'action-btn delete-btn';
        delBtn.onclick = async () => { if(confirm('Delete department?')) { await api.delete(`/admin/departments/${d.id}`); loadDepartments(); loadTeams(); loadUsers(); showToast('Deleted', 'success'); } };
        const td = row.insertCell(3);
        td.appendChild(editBtn); td.appendChild(delBtn);
    }
}
async function editDepartment(id, oldName, oldDesc) {
    const newName = prompt('New department name:', oldName);
    if (!newName) return;
    const newDesc = prompt('New description (optional):', oldDesc) || '';
    await api.put(`/admin/departments/${id}`, { name: newName, description: newDesc });
    loadDepartments(); loadTeams(); loadUsers();
    showToast('Department updated', 'success');
}
document.getElementById('add-dept-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const formData = new FormData(e.target);
    await api.post('/admin/departments', { name: formData.get('name'), description: formData.get('description') || null });
    e.target.reset();
    loadDepartments(); loadTeams(); loadUsers();
    showToast('Department added', 'success');
});

// Teams CRUD (unchanged)
async function loadTeams() {
    const res = await api.get('/admin/teams');
    const deptsRes = await api.get('/admin/departments');
    const deptMap = Object.fromEntries(deptsRes.data.map(d => [d.id, d.name]));
    const tbody = document.querySelector('#teams-table tbody');
    tbody.innerHTML = '';
    for (const t of res.data) {
        const row = tbody.insertRow();
        row.insertCell(0).innerText = t.id;
        row.insertCell(1).innerText = t.name;
        row.insertCell(2).innerText = deptMap[t.department_id] || '-';
        row.insertCell(3).innerText = t.description || '';
        const editBtn = document.createElement('button');
        editBtn.textContent = 'Edit'; editBtn.className = 'action-btn';
        editBtn.onclick = () => editTeam(t.id, t.name, t.department_id, t.description);
        const delBtn = document.createElement('button');
        delBtn.textContent = 'Delete'; delBtn.className = 'action-btn delete-btn';
        delBtn.onclick = async () => { if(confirm('Delete team?')) { await api.delete(`/admin/teams/${t.id}`); loadTeams(); showToast('Deleted', 'success'); } };
        const td = row.insertCell(4);
        td.appendChild(editBtn); td.appendChild(delBtn);
    }
    // Populate team form department dropdown
    const deptSelect = document.querySelector('#add-team-form select[name="department_id"]');
    deptSelect.innerHTML = '<option value="">Select Department</option>';
    for (const d of deptsRes.data) {
        deptSelect.innerHTML += `<option value="${d.id}">${d.name}</option>`;
    }
}
async function editTeam(id, oldName, oldDeptId, oldDesc) {
    const newName = prompt('New team name:', oldName);
    if (!newName) return;
    const newDeptId = prompt('New department ID (enter number, or 0 for none):', oldDeptId || '0');
    const newDesc = prompt('New description (optional):', oldDesc || '');
    await api.put(`/admin/teams/${id}`, { name: newName, department_id: parseInt(newDeptId) || null, description: newDesc || null });
    loadTeams();
    showToast('Team updated', 'success');
}
document.getElementById('add-team-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const formData = new FormData(e.target);
    const deptId = formData.get('department_id');
    if (!deptId) { showToast('Please select a department', 'error'); return; }
    await api.post('/admin/teams', { name: formData.get('name'), department_id: parseInt(deptId), description: formData.get('description') || null });
    e.target.reset();
    loadTeams();
    showToast('Team added', 'success');
});

// API Keys (same as before)
async function loadApiKeys() {
    const res = await api.get('/admin/api-keys');
    const tbody = document.querySelector('#api-keys-table tbody');
    tbody.innerHTML = '';
    for (const k of res.data.keys) {
        const row = tbody.insertRow();
        row.insertCell(0).innerText = k.provider;
        row.insertCell(1).innerText = k.description || '-';
        row.insertCell(2).innerText = new Date(k.created_at).toLocaleString();
        row.insertCell(3).innerText = k.is_active ? 'Active' : 'Inactive';
    }
}
document.getElementById('add-api-key-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    await api.post('/admin/api-keys', { provider: fd.get('provider'), api_key: fd.get('api_key'), description: fd.get('description') });
    e.target.reset();
    loadApiKeys();
    showToast('API key added', 'success');
});

// Model Assignments (same as before)
async function loadUsersForSelect() {
    const res = await api.get('/admin/users');
    const select = document.getElementById('assign-user-id');
    select.innerHTML = '<option value="" disabled selected>Select User</option>';
    for (const u of res.data.users) select.innerHTML += `<option value="${u.id}">${u.name} (${u.email})</option>`;
}
async function loadAssignments() {
    const res = await api.get('/admin/model-assignments');
    const tbody = document.querySelector('#assignments-table tbody');
    tbody.innerHTML = '';
    for (const a of res.data.assignments) {
        const row = tbody.insertRow();
        row.insertCell(0).innerText = a.user_name;
        row.insertCell(1).innerText = a.provider;
        row.insertCell(2).innerText = a.model_name;
        row.insertCell(3).innerText = a.is_active ? 'Active' : 'Inactive';
    }
}
document.getElementById('assign-model-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    await api.post('/admin/model-assignments', { user_id: parseInt(fd.get('user_id')), provider: fd.get('provider'), model_name: fd.get('model_name') });
    e.target.reset();
    loadAssignments();
    showToast('Model assigned', 'success');
});

// Files (unchanged)
async function loadFiles() {
    const res = await api.get('/admin/files');
    const tbody = document.querySelector('#files-table tbody');
    tbody.innerHTML = '';
    for (const f of res.data.files) {
        const row = tbody.insertRow();
        row.insertCell(0).innerText = f.filename;
        row.insertCell(1).innerText = f.uploaded_by;
        row.insertCell(2).innerText = new Date(f.uploaded_at).toLocaleString();
        row.insertCell(3).innerText = (f.file_size / 1024).toFixed(1);
    }
}
async function loadUserFilter() {
    const res = await api.get('/admin/users');
    const select = document.getElementById('file-user-filter');
    select.innerHTML = '<option value="">All Users</option>';
    for (const u of res.data.users) select.innerHTML += `<option value="${u.id}">${u.name}</option>`;
    select.onchange = loadFiles;
}

// Tab switching
document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(tc => tc.classList.remove('active'));
        btn.classList.add('active');
        document.getElementById(`${btn.dataset.tab}-tab`).classList.add('active');
        if (btn.dataset.tab === 'users') loadUsers();
        else if (btn.dataset.tab === 'departments') loadDepartments();
        else if (btn.dataset.tab === 'teams') loadTeams();
        else if (btn.dataset.tab === 'api-keys') loadApiKeys();
        else if (btn.dataset.tab === 'models') { loadUsersForSelect(); loadAssignments(); }
        else if (btn.dataset.tab === 'files') { loadUserFilter(); loadFiles(); }
    });
});

// Initial load
loadUsers();
loadDepartments();
loadTeams();
loadApiKeys();
loadUsersForSelect();
loadAssignments();
loadUserFilter();
loadFiles();
