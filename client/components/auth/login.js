// DOM elements
const loginTab = document.getElementById('loginTab');
const signupTab = document.getElementById('signupTab');
const loginFormDiv = document.getElementById('loginForm');
const signupFormDiv = document.getElementById('signupForm');
const switchToSignup = document.getElementById('switchToSignup');
const switchToLogin = document.getElementById('switchToLogin');

function showLogin() {
    loginFormDiv.classList.add('active-form');
    signupFormDiv.classList.remove('active-form');
    loginTab.classList.add('active');
    signupTab.classList.remove('active');
    document.getElementById('loginError').style.display = 'none';
    document.getElementById('signupError').style.display = 'none';
    document.getElementById('loginEmail').focus();
}

function showSignup() {
    signupFormDiv.classList.add('active-form');
    loginFormDiv.classList.remove('active-form');
    signupTab.classList.add('active');
    loginTab.classList.remove('active');
    document.getElementById('loginError').style.display = 'none';
    document.getElementById('signupError').style.display = 'none';
    document.getElementById('signupName').focus();
}

loginTab.addEventListener('click', showLogin);
signupTab.addEventListener('click', showSignup);
switchToSignup.addEventListener('click', (e) => { e.preventDefault(); showSignup(); });
switchToLogin.addEventListener('click', (e) => { e.preventDefault(); showLogin(); });

// Login
document.getElementById('login').addEventListener('submit', async (e) => {
    e.preventDefault();
    const email = document.getElementById('loginEmail').value.trim();
    const password = document.getElementById('loginPassword').value;
    const errorDiv = document.getElementById('loginError');
    const submitBtn = e.target.querySelector('button');

    if (!email || !password) {
        errorDiv.textContent = 'Please fill in all fields.';
        errorDiv.style.display = 'block';
        return;
    }

    try {
        submitBtn.innerHTML = '<div class="aesthetic-loader" style="padding:0;"><div class="aesthetic-wave" style="height:8px; background:white;"></div><div class="aesthetic-wave" style="height:8px; background:white;"></div><div class="aesthetic-wave" style="height:8px; background:white;"></div></div> Logging in...';
        submitBtn.disabled = true;
        const res = await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Login failed');
        localStorage.setItem('access_token', data.access_token);
        localStorage.setItem('user', JSON.stringify(data.user));
        window.location.href = '/start';
    } catch (err) {
        errorDiv.textContent = err.message;
        errorDiv.style.display = 'block';
        submitBtn.innerHTML = 'Log In';
        submitBtn.disabled = false;
    }
});

// Fetch departments when org_id is entered
const signupOrgInput = document.getElementById('signupOrg');
const signupDepartmentSelect = document.getElementById('signupDepartment');
signupOrgInput.addEventListener('blur', async () => {
    const orgId = signupOrgInput.value.trim();
    if (!orgId) return;
    try {
        const res = await fetch(`/api/auth/organizations/${orgId}/departments`);
        if (!res.ok) throw new Error();
        const depts = await res.json();
        signupDepartmentSelect.innerHTML = '<option value="">Select Department</option>';
        depts.forEach(d => {
            const opt = document.createElement('option');
            opt.value = d.id;
            opt.textContent = d.name;
            signupDepartmentSelect.appendChild(opt);
        });
    } catch (err) {
        console.error('Failed to load departments', err);
    }
});

// Signup (with department_id)
document.getElementById('signup').addEventListener('submit', async (e) => {
    e.preventDefault();
    const name = document.getElementById('signupName').value.trim();
    const email = document.getElementById('signupEmail').value.trim();
    const orgId = document.getElementById('signupOrg').value.trim();
    const password = document.getElementById('signupPassword').value;
    const confirm = document.getElementById('signupConfirm').value;
    const department_id = document.getElementById('signupDepartment').value;
    const errorDiv = document.getElementById('signupError');
    const submitBtn = e.target.querySelector('button');

    if (!name || !email || !orgId || !password || !confirm) {
        errorDiv.textContent = 'All fields are required.';
        errorDiv.style.display = 'block';
        return;
    }
    if (password !== confirm) {
        errorDiv.textContent = 'Passwords do not match.';
        errorDiv.style.display = 'block';
        return;
    }
    if (password.length < 6) {
        errorDiv.textContent = 'Password must be at least 6 characters.';
        errorDiv.style.display = 'block';
        return;
    }

    try {
        submitBtn.innerHTML = '<div class="aesthetic-loader" style="padding:0;"><div class="aesthetic-wave" style="height:8px; background:white;"></div><div class="aesthetic-wave" style="height:8px; background:white;"></div><div class="aesthetic-wave" style="height:8px; background:white;"></div></div> Creating account...';
        submitBtn.disabled = true;
        const res = await fetch('/api/auth/signup', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, email, org_id: orgId, password, department_id: department_id ? parseInt(department_id) : null })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Signup failed');
        localStorage.setItem('access_token', data.access_token);
        localStorage.setItem('user', JSON.stringify(data.user));
        window.location.href = '/start';
    } catch (err) {
        errorDiv.textContent = err.message;
        errorDiv.style.display = 'block';
        submitBtn.innerHTML = 'Create Account';
        submitBtn.disabled = false;
    }
});
