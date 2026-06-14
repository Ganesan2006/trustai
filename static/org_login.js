// Organization Registration Form Handler
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

    // Gather admin info
    const admin_name = document.getElementById('adminName').value.trim();
    const admin_email = document.getElementById('adminEmail').value.trim();
    const admin_mobile = document.getElementById('adminMobile').value.trim();
    const admin_role = document.getElementById('adminRole').value.trim() || 'Admin';   // default to 'Admin'
    const admin_password = document.getElementById('adminPassword').value;
    const confirm_password = document.getElementById('confirmPassword').value;        // get confirm password

    const errorDiv = document.getElementById('registerError');

    // Basic validations
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

    // Prepare payload with confirm_password
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
        confirm_password: admin_password   // ← THIS LINE IS ESSENTIAL
    };
    try {
        const res = await fetch('/api/auth/org/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();

        if (!res.ok) {
            errorDiv.textContent = data.detail || 'Registration failed.';
            errorDiv.style.display = 'block';
            return;
        }

        // Success: store token and redirect to chat
        localStorage.setItem('access_token', data.access_token);
        localStorage.setItem('user', JSON.stringify(data.user));
        window.location.href = '/start';
    } catch (err) {
        errorDiv.textContent = 'Network error. Please try again.';
        errorDiv.style.display = 'block';
        console.error(err);
    }
});
// Global arrays
let departments = [];
let teams = [];

// Render departments list
function renderDepartments() {
    const container = document.getElementById('departmentsList');
    container.innerHTML = '';
    departments.forEach((dept, idx) => {
        const row = document.createElement('div');
        row.className = 'dept-row';
        row.innerHTML = `
            <input type="text" value="${escapeHtml(dept.name)}" placeholder="Department name" class="dept-name" data-idx="${idx}">
            <input type="text" value="${escapeHtml(dept.description || '')}" placeholder="Description" class="dept-desc" data-idx="${idx}">
            <button class="remove-dept" data-idx="${idx}">Remove</button>
        `;
        container.appendChild(row);
    });
    // Attach event listeners for updates and removal
}

// Similarly for teams, with department dropdown
function renderTeams() {
    const container = document.getElementById('teamsList');
    container.innerHTML = '';
    teams.forEach((team, idx) => {
        const row = document.createElement('div');
        row.className = 'team-row';
        let deptOptions = '<option value="">Select department</option>';
        departments.forEach(d => {
            deptOptions += `<option value="${escapeHtml(d.name)}" ${team.department_name === d.name ? 'selected' : ''}>${escapeHtml(d.name)}</option>`;
        });
        row.innerHTML = `
            <input type="text" value="${escapeHtml(team.name)}" placeholder="Team name" class="team-name" data-idx="${idx}">
            <select class="team-dept" data-idx="${idx}">${deptOptions}</select>
            <input type="text" value="${escapeHtml(team.description || '')}" placeholder="Description" class="team-desc" data-idx="${idx}">
            <button class="remove-team" data-idx="${idx}">Remove</button>
        `;
        container.appendChild(row);
    });
    // attach events
}

// Add Department button
document.getElementById('addDepartmentBtn').addEventListener('click', () => {
    departments.push({ name: '', description: '' });
    renderDepartments();
    renderTeams(); // because team dropdown depends on departments
});

// Add Team button
document.getElementById('addTeamBtn').addEventListener('click', () => {
    teams.push({ name: '', department_name: '', description: '' });
    renderTeams();
});

// In the form submission, after building the payload, add:
payload.departments = departments.filter(d => d.name.trim());
payload.teams = teams.filter(t => t.name.trim() && t.department_name);