// Store dynamic items
let departments = [];
let teams = [];

// Helper: escape HTML
function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/[&<>]/g, function(m) {
        if (m === '&') return '&amp;';
        if (m === '<') return '&lt;';
        if (m === '>') return '&gt;';
        return m;
    });
}

// Render departments list
function renderDepartments() {
    const container = document.getElementById('departmentsList');
    container.innerHTML = '';
    departments.forEach((dept, idx) => {
        const div = document.createElement('div');
        div.className = 'dynamic-item';
        div.innerHTML = `
            <input type="text" class="dept-name" data-idx="${idx}" value="${escapeHtml(dept.name)}" placeholder="Department name">
            <input type="text" class="dept-desc" data-idx="${idx}" value="${escapeHtml(dept.description || '')}" placeholder="Description (optional)">
            <button type="button" class="remove-item" data-idx="${idx}">Remove</button>
        `;
        container.appendChild(div);
    });
    // Attach event listeners for updates
    document.querySelectorAll('.dept-name').forEach(inp => {
        inp.addEventListener('change', (e) => {
            const idx = parseInt(e.target.dataset.idx);
            departments[idx].name = e.target.value;
        });
    });
    document.querySelectorAll('.dept-desc').forEach(inp => {
        inp.addEventListener('change', (e) => {
            const idx = parseInt(e.target.dataset.idx);
            departments[idx].description = e.target.value;
        });
    });
    document.querySelectorAll('.remove-item').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const idx = parseInt(btn.dataset.idx);
            departments.splice(idx, 1);
            renderDepartments();
            renderTeams(); // teams dropdown may need update
        });
    });
}

// Render teams list (department dropdown populated from departments)
function renderTeams() {
    const container = document.getElementById('teamsList');
    container.innerHTML = '';
    teams.forEach((team, idx) => {
        const div = document.createElement('div');
        div.className = 'dynamic-item';
        let deptOptions = '<option value="">Select Department</option>';
        departments.forEach(d => {
            deptOptions += `<option value="${escapeHtml(d.name)}" ${team.department_name === d.name ? 'selected' : ''}>${escapeHtml(d.name)}</option>`;
        });
        div.innerHTML = `
            <input type="text" class="team-name" data-idx="${idx}" value="${escapeHtml(team.name)}" placeholder="Team name">
            <select class="team-dept" data-idx="${idx}">${deptOptions}</select>
            <input type="text" class="team-desc" data-idx="${idx}" value="${escapeHtml(team.description || '')}" placeholder="Description (optional)">
            <button type="button" class="remove-item" data-idx="${idx}">Remove</button>
        `;
        container.appendChild(div);
    });
    // Attach listeners
    document.querySelectorAll('.team-name').forEach(inp => {
        inp.addEventListener('change', (e) => {
            const idx = parseInt(e.target.dataset.idx);
            teams[idx].name = e.target.value;
        });
    });
    document.querySelectorAll('.team-dept').forEach(sel => {
        sel.addEventListener('change', (e) => {
            const idx = parseInt(e.target.dataset.idx);
            teams[idx].department_name = e.target.value;
        });
    });
    document.querySelectorAll('.team-desc').forEach(inp => {
        inp.addEventListener('change', (e) => {
            const idx = parseInt(e.target.dataset.idx);
            teams[idx].description = e.target.value;
        });
    });
    document.querySelectorAll('.remove-item').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const idx = parseInt(btn.dataset.idx);
            teams.splice(idx, 1);
            renderTeams();
        });
    });
}

document.getElementById('addDepartmentBtn').addEventListener('click', () => {
    departments.push({ name: '', description: '' });
    renderDepartments();
    renderTeams(); // update team department dropdown
});

document.getElementById('addTeamBtn').addEventListener('click', () => {
    teams.push({ name: '', department_name: '', description: '' });
    renderTeams();
});

// Form submission
document.getElementById('orgRegisterForm').addEventListener('submit', async (e) => {
    e.preventDefault();

    // Gather company info
    const company_name = document.getElementById('companyName').value.trim();
    const company_email = document.getElementById('companyEmail').value.trim();
    const company_phone = document.getElementById('companyPhone').value.trim();
    const company_website = document.getElementById('companyWebsite').value.trim();
    const industry = document.getElementById('industry').value.trim();
    const company_size = document.getElementById('companySize').value;
    const country = document.getElementById('country').value.trim();
    const state = document.getElementById('state').value.trim();
    const city = document.getElementById('city').value.trim();
    const address = document.getElementById('address').value.trim();
    const domain = document.getElementById('domain').value.trim().toLowerCase();

    const admin_name = document.getElementById('adminName').value.trim();
    const admin_email = document.getElementById('adminEmail').value.trim();
    const admin_mobile = document.getElementById('adminMobile').value.trim();
    const admin_role = document.getElementById('adminRole').value.trim() || 'Admin';
    const admin_password = document.getElementById('adminPassword').value;
    const confirm_password = document.getElementById('confirmPassword').value;

    const errorDiv = document.getElementById('errorMsg');
    const successDiv = document.getElementById('successMsg');
    errorDiv.style.display = 'none';
    successDiv.style.display = 'none';

    if (!company_name || !company_email || !domain || !admin_name || !admin_email || !admin_password) {
        errorDiv.textContent = 'Please fill in all required fields (*).';
        errorDiv.style.display = 'block';
        return;
    }
    if (admin_password !== confirm_password) {
        errorDiv.textContent = 'Passwords do not match.';
        errorDiv.style.display = 'block';
        return;
    }
    if (admin_password.length < 6) {
        errorDiv.textContent = 'Password must be at least 6 characters.';
        errorDiv.style.display = 'block';
        return;
    }
    if (!domain.includes('.')) {
        errorDiv.textContent = 'Please enter a valid domain (e.g., acme.com).';
        errorDiv.style.display = 'block';
        return;
    }

    // Prepare departments and teams for payload (only non-empty names)
    const departmentsPayload = departments.filter(d => d.name && d.name.trim()).map(d => ({
        name: d.name.trim(),
        description: d.description || null
    }));
    const teamsPayload = teams.filter(t => t.name && t.name.trim() && t.department_name && t.department_name.trim()).map(t => ({
        name: t.name.trim(),
        department_name: t.department_name.trim(),
        description: t.description || null
    }));

    const payload = {
        company_name,
        company_email,
        company_phone: company_phone || "",
        company_website: company_website || "",
        industry: industry || "",
        company_size,
        country: country || "",
        state: state || "",
        city: city || "",
        address: address || "",
        domain,
        admin_name,
        admin_email,
        admin_mobile: admin_mobile || "",
        admin_password,
        admin_role: admin_role || "Admin",
        confirm_password: admin_password,
        departments: departmentsPayload,
        teams: teamsPayload
    };

    try {
        const submitBtn = e.target.querySelector('button[type="submit"]');
        submitBtn.innerHTML = '<div class="aesthetic-loader" style="padding:0;"><div class="aesthetic-wave" style="height:8px; background:white;"></div><div class="aesthetic-wave" style="height:8px; background:white;"></div><div class="aesthetic-wave" style="height:8px; background:white;"></div></div> Registering...';
        submitBtn.disabled = true;
        
        const res = await fetch('/api/auth/org/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!res.ok) {
            errorDiv.textContent = data.detail || 'Registration failed.';
            errorDiv.style.display = 'block';
            submitBtn.innerHTML = 'Register Organization';
            submitBtn.disabled = false;
            return;
        }
        // Success
        localStorage.setItem('access_token', data.access_token);
        localStorage.setItem('user', JSON.stringify(data.user));
        window.location.href = '/start';
    } catch (err) {
        errorDiv.textContent = 'Network error. Please try again.';
        errorDiv.style.display = 'block';
        console.error(err);
        const submitBtn = e.target.querySelector('button[type="submit"]');
        submitBtn.innerHTML = 'Register Organization';
        submitBtn.disabled = false;
    }
});

// Initial render (empty lists)
renderDepartments();
renderTeams();