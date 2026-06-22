
(function () {
    // ---------- Axios Setup ----------
    const api = axios.create({ baseURL: '' });
    api.interceptors.request.use(config => {
        const token = localStorage.getItem('access_token');
        if (token) config.headers.Authorization = `Bearer ${token}`;
        return config;
    });
    api.interceptors.response.use(res => res, error => {
        if (error.response?.status === 401) { localStorage.clear(); window.location.href = '/'; }
        showToast(error.response?.data?.detail || 'Request failed', 'error');
        return Promise.reject(error);
    });

    // ---------- Global State ----------
    let currentUser = null;
    let conversations = [];
    let activeConversationId = null;
    let allAccessibleFiles = [];
    let systemData = { departments: [], teams: [] };
    let pendingFiles = [];
    let uploadTargets = { departments: [], teams: [] };

    // ---------- Helper Functions ----------
    function showToast(message, type = 'success') {
        const container = document.getElementById('toastContainer');
        const toast = document.createElement('div');
        toast.className = 'toast';
        toast.innerHTML = `<span class="material-symbols-outlined" style="color:${type === 'error' ? '#ff7b72' : 'var(--primary)'}">${type === 'error' ? 'error' : 'check_circle'}</span> ${escapeHtml(message)}`;
        container.appendChild(toast);
        setTimeout(() => toast.remove(), 3000);
    }
    function escapeHtml(str) { if (!str) return ''; return String(str).replace(/[&<>]/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[m] || m)); }
    async function copyToClipboard(text) {
        try { await navigator.clipboard.writeText(text); showToast('Copied to clipboard', 'success'); } catch (err) { const ta = document.createElement("textarea"); ta.value = text; document.body.appendChild(ta); ta.select(); try { document.execCommand('copy'); showToast('Copied to clipboard', 'success'); } catch (e) { showToast('Copy failed', 'error'); } document.body.removeChild(ta); }
    }
    function applyTheme(theme) { document.documentElement.setAttribute('data-theme', theme); localStorage.setItem('trustai_theme', theme); const selector = document.getElementById('themeSelectDropdown'); if (selector) selector.value = theme; }
    const savedTheme = localStorage.getItem('trustai_theme') || 'dark'; applyTheme(savedTheme);

    // ---------- User & System Data ----------
    async function fetchCurrentUser() {
        try {
            const res = await api.get('/api/user/profile');
            currentUser = res.data;
            document.getElementById('sidebarUserName').innerText = currentUser.name;
            document.getElementById('sidebarUserEmail').innerText = currentUser.email;
            document.getElementById('userAvatar').innerText = currentUser.name.charAt(0).toUpperCase();
            document.getElementById('dropdownUserName').innerText = currentUser.name;
            document.getElementById('dropdownUserEmail').innerText = currentUser.email;
            document.getElementById('greetingText').innerText = `Hi ${currentUser.name.split(' ')[0]}, what's on your mind?`;

            // Show Admin Dashboard button only for org_admin
            const adminBtn = document.getElementById('adminDashboardBtn');
            if (currentUser.role === 'org_admin') {
                adminBtn.style.display = 'flex';
            } else {
                adminBtn.style.display = 'none';
            }
            if (currentUser.role === 'org_admin') {
                document.getElementById('adminDashboardBtn').style.display = 'flex';
                document.getElementById('adminPageBtn').style.display = 'flex';
            }
        } catch (e) {
            console.log("Mocking user for UI testing");
            currentUser = { name: "User", email: "user@example.com", role: "employee" };
            document.getElementById('greetingText').innerText = `Hi User, what's on your mind?`;
            document.getElementById('adminDashboardBtn').style.display = 'none';
        }
    }

    async function loadSystemData() {
        try {
            const [depts, teams] = await Promise.all([api.get('/admin/departments'), api.get('/admin/teams')]);
            systemData.departments = depts.data;
            systemData.teams = teams.data;
            const deptSelect = document.getElementById('scopeDepartmentSelect');
            deptSelect.innerHTML = ''; systemData.departments.forEach(d => deptSelect.innerHTML += `<option value="${d.id}">${escapeHtml(d.name)}</option>`);
            const teamSelect = document.getElementById('scopeTeamSelect');
            teamSelect.innerHTML = ''; systemData.teams.forEach(t => teamSelect.innerHTML += `<option value="${t.id}">${escapeHtml(t.name)}</option>`);
        } catch (e) { }
    }

    async function loadUploadTargets() {
        try {
            const res = await api.get('/api/files/upload-targets');
            uploadTargets = res.data;
            const deptSelect = document.getElementById('uploadDepartmentSelect');
            deptSelect.innerHTML = '<option value="">-- Select Department --</option>';
            (uploadTargets.departments || []).forEach(d => deptSelect.innerHTML += `<option value="${d.id}">${escapeHtml(d.name)}</option>`);
            const teamSelect = document.getElementById('uploadTeamSelect');
            teamSelect.innerHTML = '<option value="">-- Select Team --</option>';
            (uploadTargets.teams || []).forEach(t => teamSelect.innerHTML += `<option value="${t.id}">${escapeHtml(t.name)}</option>`);
        } catch (e) { console.warn('Failed to load upload targets', e); }
    }

    function buildUploadScopeOptions() {
        const role = currentUser?.role || 'employee';
        const container = document.getElementById('uploadScopeOptions');
        container.innerHTML = '';
        const options = [];
        // Always show Company
        options.push({ value: 'company', label: '🏢 Company' });
        if (role === 'org_admin') {
            options.push({ value: 'department', label: '🏛️ Department' });
            options.push({ value: 'team', label: '👥 Team' });
            options.push({ value: 'private', label: '🔒 Personal' });
        } else if (role === 'department_manager') {
            options.push({ value: 'department', label: `🏛️ Department (${currentUser.department?.name || 'Your Dept'})` });
            options.push({ value: 'team', label: '👥 Team' });
            options.push({ value: 'private', label: '🔒 Personal' });
        } else { // employee or team_lead
            options.push({ value: 'department', label: `🏛️ Department (${currentUser.department?.name || 'My Dept'})` });
            options.push({ value: 'team', label: `👥 Team (${currentUser.team?.name || 'My Team'})` });
            options.push({ value: 'private', label: '🔒 Personal' });
        }
        options.forEach(opt => {
            const radioId = `uploadScope_${opt.value}`;
            const radio = document.createElement('input');
            radio.type = 'radio';
            radio.name = 'uploadScope';
            radio.value = opt.value;
            radio.id = radioId;
            radio.className = 'scope-radio';
            radio.hidden = true;
            const label = document.createElement('label');
            label.htmlFor = radioId;
            label.className = 'scope-label';
            label.innerText = opt.label;
            container.appendChild(radio);
            container.appendChild(label);
        });
        // Default select company
        const companyRadio = document.querySelector('input[name="uploadScope"][value="company"]');
        if (companyRadio) companyRadio.checked = true;
        // Attach change event
        document.querySelectorAll('input[name="uploadScope"]').forEach(r => r.addEventListener('change', onUploadScopeChange));
        onUploadScopeChange();
    }

    function onUploadScopeChange() {
        const selected = document.querySelector('input[name="uploadScope"]:checked')?.value;
        const role = currentUser?.role || 'employee';
        const deptContainer = document.getElementById('uploadDepartmentContainer');
        const teamContainer = document.getElementById('uploadTeamContainer');
        const deptSelect = document.getElementById('uploadDepartmentSelect');
        const teamSelect = document.getElementById('uploadTeamSelect');

        deptContainer.style.display = 'none';
        teamContainer.style.display = 'none';

        if (selected === 'department') {
            if (role === 'org_admin') {
                deptContainer.style.display = 'block';
                // Populate departments from uploadTargets
                deptSelect.innerHTML = '<option value="">-- Select Department --</option>';
                (uploadTargets.departments || []).forEach(d => {
                    deptSelect.innerHTML += `<option value="${d.id}">${escapeHtml(d.name)}</option>`;
                });
            }
            // For others, no dropdown; backend uses their own department
        } else if (selected === 'team') {
            if (role === 'org_admin' || role === 'department_manager') {
                teamContainer.style.display = 'block';
                // Populate teams based on role
                teamSelect.innerHTML = '<option value="">-- Select Team --</option>';
                if (role === 'org_admin') {
                    (uploadTargets.teams || []).forEach(t => {
                        teamSelect.innerHTML += `<option value="${t.id}">${escapeHtml(t.name)}</option>`;
                    });
                } else if (role === 'department_manager' && currentUser.department_id) {
                    const allowedTeams = (uploadTargets.teams || []).filter(t => t.department_id === currentUser.department_id);
                    allowedTeams.forEach(t => {
                        teamSelect.innerHTML += `<option value="${t.id}">${escapeHtml(t.name)}</option>`;
                    });
                }
            }
            // For team_lead/employee, no dropdown; backend uses their own team
        }
    }

    function getSearchScopeFromUI() {
        const scopeEl = document.querySelector('input[name="scopeType"]:checked');
        if (!scopeEl) return { type: 'company' };
        const scope = scopeEl.value;
        const role = currentUser?.role || 'employee';
        let department_ids = [], team_ids = [], user_emails = [];
        if (role === 'org_admin') {
            if (scope === 'department') department_ids = Array.from(document.getElementById('scopeDepartmentSelect').selectedOptions).map(o => parseInt(o.value));
            if (scope === 'team') team_ids = Array.from(document.getElementById('scopeTeamSelect').selectedOptions).map(o => parseInt(o.value));
            if (scope === 'private') { const email = document.getElementById('scopeUserEmail').value.trim(); if (email) user_emails = [email]; }
        } else if (role === 'department_manager') {
            if (scope === 'department') department_ids = [currentUser.department_id];
            if (scope === 'team') team_ids = Array.from(document.getElementById('scopeTeamSelect').selectedOptions).map(o => parseInt(o.value));
        } else {
            if (scope === 'department') department_ids = [currentUser.department_id];
            if (scope === 'team') team_ids = [currentUser.team_id];
        }
        return { type: scope, department_ids, team_ids, user_emails };
    }

    function saveScopeForConversation(convId, scope) { if (!convId) return; localStorage.setItem(`chat_scope_${convId}`, JSON.stringify(scope)); }
    function loadScopeForConversation(convId) { const saved = localStorage.getItem(`chat_scope_${convId}`); if (saved) try { return JSON.parse(saved); } catch (e) { return null; } return null; }
    function updateScopeUI() {
        const scope = document.querySelector('input[name="scopeType"]:checked')?.value;
        const role = currentUser?.role || 'employee';

        const deptDiv = document.getElementById('scopeDepartmentContainer');
        const teamDiv = document.getElementById('scopeTeamContainer');
        const emailDiv = document.getElementById('scopeEmailContainer');

        if (deptDiv) deptDiv.style.display = (scope === 'department' && role === 'org_admin') ? 'block' : 'none';
        if (teamDiv) teamDiv.style.display = (scope === 'team' && (role === 'org_admin' || role === 'department_manager')) ? 'block' : 'none';
        if (emailDiv) emailDiv.style.display = (scope === 'private' && role === 'org_admin') ? 'block' : 'none';
    }

    function applyScopeToUI(scope) { if (!scope) return; const radio = document.querySelector(`input[name="scopeType"][value="${scope.type}"]`); if (radio) radio.checked = true; updateScopeUI(); setTimeout(() => { if (scope.type === 'department' && scope.department_ids) { const deptSelect = document.getElementById('scopeDepartmentSelect'); Array.from(deptSelect.options).forEach(opt => { if (scope.department_ids.includes(parseInt(opt.value))) opt.selected = true; }); } if (scope.type === 'team' && scope.team_ids) { const teamSelect = document.getElementById('scopeTeamSelect'); Array.from(teamSelect.options).forEach(opt => { if (scope.team_ids.includes(parseInt(opt.value))) opt.selected = true; }); } if (scope.type === 'private' && scope.user_emails) { document.getElementById('scopeUserEmail').value = scope.user_emails[0] || ''; } }, 100); }

    // ---------- Conversations ----------
    async function loadConversations() {
        try {
            const res = await api.get('/api/conversations');
            conversations = res.data.conversations || res.data || [];
            renderSidebar();

            // Do not auto-select the first conversation if on /start
            const pathParts = window.location.pathname.split('/');
            if (pathParts[1] === 'chat' && pathParts[2]) {
                const urlConvId = pathParts[2];
                if (!activeConversationId || activeConversationId !== urlConvId) {
                    await switchConversation(urlConvId, false);
                }
            } else {
                // If on /start, explicitly show new chat view
                if (!activeConversationId) {
                    showNewChatView();
                }
            }
        } catch (e) { console.warn('Failed to load conversations'); }
    }

    async function switchConversation(convId, updateUrl = true) {
        activeConversationId = convId;
        if (updateUrl) {
            window.history.pushState({}, '', '/chat/' + convId);
        }
        renderSidebar();
        document.getElementById('appSidebar').classList.remove('mobile-open');
        try {
            const res = await api.get(`/api/conversations/${convId}/messages`);
            await renderCurrentChat(res.data.messages || res.data || []);
            await api.post(`/api/chat/activate/${convId}`);
            const savedScope = loadScopeForConversation(convId);
            if (savedScope) applyScopeToUI(savedScope);
            else {
                const compRadio = document.querySelector('input[name="scopeType"][value="company"]');
                if (compRadio) compRadio.checked = true;
                updateScopeUI();
            }
        } catch (e) {
            console.error("switchConversation Error:", e);
            renderCurrentChat([]);
        }
    }

    function showNewChatView() {
        activeConversationId = null;
        renderSidebar();
        renderCurrentChat([]);
        document.body.classList.remove('chat-active');
        document.getElementById('chatContainer').innerHTML = '<div id="emptyState" style="text-align:center; margin-top:60px;"><h1 style="font-family:Google Sans; font-size: 24px;">✨ Ask with inline citations</h1><p style="color: var(--text-muted); margin-top: 8px;">Upload documents and get source‑linked answers</p></div>';
        window.history.pushState({}, '', '/start');
    }

    async function createNewConversation(initialMessage) {
        try {
            const name = initialMessage ? initialMessage.substring(0, 50) : "New Chat";
            const res = await api.post('/api/conversations', { name: name });
            conversations.unshift(res.data);
            await switchConversation(res.data.id, true);
            showToast('New conversation started', 'success');
        } catch (e) { showToast('Failed to create chat', 'error'); }
    }

    function renderSidebar() {
        const container = document.getElementById('convList');
        container.innerHTML = '';
        conversations.forEach(conv => {
            const div = document.createElement('div');
            div.className = 'conv-item' + (conv.id === activeConversationId ? ' active' : '');
            div.innerHTML = `
                <div class="conv-item-left" style="display:flex; gap:8px; align-items:center; flex:1;" onclick="window.switchChat('${conv.id}')">
                    <span class="material-symbols-outlined" style="font-size:18px;">chat_bubble</span>
                    <span class="conv-title">${escapeHtml(conv.name || 'New Chat')}</span>
                </div>
                <div class="conv-actions">
                    <button onclick="event.stopPropagation(); window.showDeleteDialog('${conv.id}')" title="Delete">
                        <span class="material-symbols-outlined" style="font-size:18px;">delete</span>
                    </button>
                </div>
            `;
            container.appendChild(div);
        });
    }

    // ========== DELETE CONVERSATION WITH CONFIRMATION ==========
    let deleteTargetId = null;

    window.showDeleteDialog = function (convId) {
        deleteTargetId = convId;
        document.getElementById('confirmDialog').style.display = 'flex';
    };

    document.getElementById('confirmCancel').addEventListener('click', () => {
        document.getElementById('confirmDialog').style.display = 'none';
        deleteTargetId = null;
    });

    document.getElementById('confirmDeleteAll').addEventListener('click', async () => {
        const id = deleteTargetId;
        if (!id) return;
        document.getElementById('confirmDialog').style.display = 'none';
        await performDelete(id, true);
        deleteTargetId = null;
    });

    document.getElementById('confirmDeleteOnly').addEventListener('click', async () => {
        const id = deleteTargetId;
        if (!id) return;
        document.getElementById('confirmDialog').style.display = 'none';
        await performDelete(id, false);
        deleteTargetId = null;
    });

    async function performDelete(convId, deleteFiles) {
        try {
            // Call backend with query param delete_files
            await api.delete(`/api/conversations/${convId}?delete_files=${deleteFiles}`);
            conversations = conversations.filter(c => c.id !== convId);
            if (activeConversationId === convId) {
                if (conversations.length > 0) await switchConversation(conversations[0].id);
                else { activeConversationId = null; renderCurrentChat([]); document.body.classList.remove('chat-active'); document.getElementById('chatContainer').innerHTML = '<div id="emptyState" style="text-align:center; margin-top:60px;"><h1 style="font-family:Google Sans; font-size: 24px;">✨ Ask with inline citations</h1><p style="color: var(--text-muted); margin-top: 8px;">Upload documents and get source‑linked answers</p></div>'; }
            }
            renderSidebar();
            // Refresh file explorer if files were deleted or not
            if (deleteFiles) {
                await loadAccessibleFiles(); // updates file list
            }
            showToast(deleteFiles ? 'Conversation and all files deleted' : 'Conversation deleted, files kept', 'success');
        } catch (e) {
            showToast('Deletion failed', 'error');
            console.error(e);
        }
    }

    // ---------- End Delete ----------

    window.switchChat = switchConversation;
    // Remove old deleteChat; replaced by showDeleteDialog

    // ========== UNIFIED MESSAGE RENDERING ==========
    async function createMessageElement(msg) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${msg.role === 'user' ? 'user-message' : 'bot-message'}`;
        if (msg.role === 'user') {
            const bubble = document.createElement('div');
            bubble.className = 'bubble';
            bubble.innerText = msg.content;
            messageDiv.appendChild(bubble);
        } else {
            const avatar = document.createElement('div');
            avatar.className = 'avatar';
            avatar.innerHTML = '<span class="material-symbols-outlined">auto_awesome</span>';
            const bubble = document.createElement('div');
            bubble.className = 'bubble';
            const contentDiv = document.createElement('div');
            contentDiv.className = 'markdown-body';

            let rawContent = msg.content;
            if (!rawContent && msg.role === 'bot') {
                rawContent = "*(No response generated)*";
            }
            let html = await marked.parse(rawContent || "");
            html = DOMPurify.sanitize(html);
            html = html.replace(/\[(\d+)\]/g, (match, num) => `<sup class="citation-number" data-idx="${num}">[${num}]</sup>`);
            contentDiv.innerHTML = html;
            bubble.appendChild(contentDiv);
            const citations = msg.citations || [];
            if (citations.length > 0) {
                const sourcesPanel = document.createElement('div');
                sourcesPanel.className = 'sources-panel';
                sourcesPanel.innerHTML = `<div class="sources-title">📚 Sources</div>`;
                citations.forEach((cite, idx) => {
                    const id = cite.id || idx + 1;
                    const title = cite.document_name || cite.title || 'Unknown document';
                    const page = cite.page ? `Page ${cite.page}` : '';
                    const score = cite.similarity ? `${Math.round(cite.similarity * 100)}% match` : '';
                    const preview = cite.text ? cite.text.substring(0, 150) + '...' : '';
                    const card = document.createElement('div');
                    card.className = 'source-card';
                    card.setAttribute('data-citation-id', id);
                    card.innerHTML = `<div class="source-title"><span class="material-symbols-outlined" style="font-size:18px;">description</span><span>${escapeHtml(title)}</span></div><div class="source-meta">${page ? `<span>📄 ${page}</span>` : ''}${score ? `<span>🔗 ${score}</span>` : ''}</div>${preview ? `<div class="source-preview">${escapeHtml(preview)}</div>` : ''}`;
                    if (cite.file_id) { card.style.cursor = 'pointer'; card.addEventListener('click', (e) => { e.stopPropagation(); openDocumentViewerById(cite.file_id); }); }
                    sourcesPanel.appendChild(card);
                });
                bubble.appendChild(sourcesPanel);
            }
            const feedbackDiv = document.createElement('div');
            feedbackDiv.className = 'feedback-buttons';
            if (msg.query_log_id) {
                const qId = msg.query_log_id;
                const likeBtn = document.createElement('button');
                likeBtn.className = 'feedback-btn';
                likeBtn.innerHTML = '<span class="material-symbols-outlined">thumb_up</span> Helpful';
                const dislikeBtn = document.createElement('button');
                dislikeBtn.className = 'feedback-btn';
                dislikeBtn.innerHTML = '<span class="material-symbols-outlined">thumb_down</span> Not helpful';
                const submitFeedback = async (rating) => {
                    try { await api.post('/api/chat/feedback', { query_log_id: qId, rating: rating, comment: null }); likeBtn.disabled = true; dislikeBtn.disabled = true; showToast(`Feedback recorded`, 'success'); } catch (e) { showToast('Feedback failed', 'error'); }
                };
                likeBtn.onclick = () => submitFeedback('helpful');
                dislikeBtn.onclick = () => submitFeedback('not_helpful');
                feedbackDiv.appendChild(likeBtn);
                feedbackDiv.appendChild(dislikeBtn);
            }
            const copyBtn = document.createElement('button');
            copyBtn.className = 'copy-btn';
            copyBtn.innerHTML = '<span class="material-symbols-outlined">content_copy</span> Copy';
            copyBtn.onclick = () => copyToClipboard(msg.content);
            feedbackDiv.appendChild(copyBtn);
            bubble.appendChild(feedbackDiv);
            messageDiv.appendChild(avatar);
            messageDiv.appendChild(bubble);
        }
        return messageDiv;
    }

    async function renderCurrentChat(messages) {
        const container = document.getElementById('chatContainer');
        container.innerHTML = '';
        if (!messages || messages.length === 0) {
            document.body.classList.remove('chat-active');
            container.innerHTML = '<div id="emptyState" style="text-align:center; margin-top:60px;"><h1 style="font-family:Google Sans; font-size: 24px;">✨ Ask with inline citations</h1><p style="color: var(--text-muted); margin-top: 8px;">Upload documents and get source‑linked answers</p></div>';
            return;
        }
        document.body.classList.add('chat-active');
        for (const msg of messages) {
            const msgElement = await createMessageElement(msg);
            container.appendChild(msgElement);
        }
        container.scrollTop = container.scrollHeight;
    }

    function addTypingIndicator() {
        const id = 'typing-' + Date.now();
        const div = document.createElement('div');
        div.id = id;
        div.className = 'message bot-message typing-indicator';
        div.innerHTML = `<div class="avatar"><span class="material-symbols-outlined">auto_awesome</span></div><div class="bubble"><div class="aesthetic-loader"><div class="aesthetic-wave"></div><div class="aesthetic-wave"></div><div class="aesthetic-wave"></div><div class="aesthetic-wave"></div><div class="aesthetic-wave"></div></div></div>`;
        document.getElementById('chatContainer').appendChild(div);
        document.getElementById('chatContainer').scrollTop = document.getElementById('chatContainer').scrollHeight;
        return id;
    }
    function removeTypingIndicator(id) { const el = document.getElementById(id); if (el) el.remove(); }

    async function sendMessage() {
        const input = document.getElementById('chatInput');
        const text = input.value.trim();
        if (!text) return;
        if (!activeConversationId) {
            await createNewConversation(text);
        }
        const searchScope = getSearchScopeFromUI();
        if (activeConversationId) saveScopeForConversation(activeConversationId, searchScope);
        const userMsgObj = { role: 'user', content: text };
        const userDiv = await createMessageElement(userMsgObj);
        document.getElementById('chatContainer').appendChild(userDiv);
        document.getElementById('chatContainer').scrollTop = document.getElementById('chatContainer').scrollHeight;
        document.getElementById('emptyState')?.remove();
        document.body.classList.add('chat-active');
        input.value = ''; input.style.height = 'auto';
        document.getElementById('sendBtn').disabled = true;
        const typingId = addTypingIndicator();
        let botDiv = null;
        try {
            const response = await fetch('/api/chat/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${localStorage.getItem('access_token')}`
                },
                body: JSON.stringify({ input: text, conversation_id: activeConversationId, search_scope: searchScope })
            });

            removeTypingIndicator(typingId);
            if (!response.ok) throw new Error('Network response was not ok');

            const botMsgObj = { role: 'bot', content: '', citations: [], query_log_id: null };
            botDiv = await createMessageElement(botMsgObj);
            document.getElementById('chatContainer').appendChild(botDiv);
            document.getElementById('chatContainer').scrollTop = document.getElementById('chatContainer').scrollHeight;

            const contentDiv = botDiv.querySelector('.markdown-body');

            const reader = response.body.getReader();
            const decoder = new TextDecoder('utf-8');
            let buffer = '';
            let fullText = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n\n');
                buffer = lines.pop();

                for (let line of lines) {
                    line = line.trim();
                    if (line.startsWith('data:')) {
                        const dataStr = line.substring(5).trim();
                        if (!dataStr) continue;
                        try {
                            const data = JSON.parse(dataStr);
                            if (data.type === 'chunk') {
                                fullText += data.content;
                                let html = await marked.parse(fullText);
                                html = DOMPurify.sanitize(html);
                                html = html.replace(/\[(\d+)\]/g, (match, num) => `<sup class="citation-number" data-idx="${num}">[${num}]</sup>`);
                                contentDiv.innerHTML = html;
                                document.getElementById('chatContainer').scrollTop = document.getElementById('chatContainer').scrollHeight;
                            } else if (data.type === 'final') {
                                botMsgObj.content = fullText;
                                botMsgObj.citations = data.citations || [];
                                botMsgObj.query_log_id = data.query_log_id;

                                const finalBotDiv = await createMessageElement(botMsgObj);
                                document.getElementById('chatContainer').replaceChild(finalBotDiv, botDiv);
                                document.getElementById('chatContainer').scrollTop = document.getElementById('chatContainer').scrollHeight;
                            } else if (data.type === 'error') {
                                showToast('Error from server: ' + data.content, 'error');
                            }
                        } catch (e) {
                            console.error('Error parsing SSE data', e, dataStr);
                        }
                    }
                }
            }
            await loadConversations();
        } catch (error) {
            console.error("Chat Error:", error);
            showToast("Failed to connect to chat server.", "error");
            if (botDiv && botDiv.parentNode) {
                document.getElementById('chatContainer').removeChild(botDiv);
            }
        } finally {
            document.getElementById('sendBtn').disabled = false;
            input.focus();
        }
    }

    const chatInput = document.getElementById('chatInput');
    chatInput.addEventListener('input', function () { this.style.height = 'auto'; this.style.height = (this.scrollHeight) + 'px'; document.getElementById('sendBtn').disabled = this.value.trim() === ''; });

    // ---------- File Upload (sequential) ----------
    function updateFileListUI() {
        const container = document.getElementById('fileManagerContainer');
        const listDiv = document.getElementById('fileUploadList');
        listDiv.innerHTML = '';
        if (pendingFiles.length === 0) { container.style.display = 'none'; return; }
        container.style.display = 'block';
        pendingFiles.forEach((file, idx) => {
            const badge = document.createElement('div');
            badge.className = 'file-badge';
            badge.style.background = 'var(--bg-hover)';
            badge.style.borderRadius = '8px';
            badge.style.padding = '4px 8px';
            badge.style.display = 'inline-flex';
            badge.style.alignItems = 'center';
            badge.style.gap = '6px';
            badge.innerHTML = `<span class="material-symbols-outlined" style="font-size:16px;">description</span> ${escapeHtml(file.name)} <span class="remove-file" data-index="${idx}" style="cursor:pointer; color: #ef4444;">✖</span>`;
            listDiv.appendChild(badge);
        });
        document.querySelectorAll('.remove-file').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const idx = parseInt(btn.dataset.index);
                pendingFiles.splice(idx, 1);
                updateFileListUI();
            });
        });
    }

    async function uploadFiles() {
        if (pendingFiles.length === 0) { showToast('No files selected', 'error'); return; }
        const selectedScope = document.querySelector('input[name="uploadScope"]:checked')?.value;
        if (!selectedScope) { showToast('Please select an access level', 'error'); return; }
        let target_department_id = null, target_team_id = null;
        const role = currentUser?.role || 'employee';
        if (selectedScope === 'department' && role === 'org_admin') {
            target_department_id = document.getElementById('uploadDepartmentSelect').value;
            if (!target_department_id) { showToast('Please select a department', 'error'); return; }
        } else if (selectedScope === 'team' && (role === 'org_admin' || role === 'department_manager')) {
            target_team_id = document.getElementById('uploadTeamSelect').value;
            if (!target_team_id) { showToast('Please select a team', 'error'); return; }
        }
        const uploadBtn = document.getElementById('executeUploadBtn');
        uploadBtn.disabled = true;
        let successCount = 0, failCount = 0;
        for (const file of pendingFiles) {
            const formData = new FormData();
            formData.append('input_file', file);
            if (activeConversationId) formData.append('conversation_id', activeConversationId);
            formData.append('scope', selectedScope);
            if (target_department_id) formData.append('target_department_id', target_department_id);
            if (target_team_id) formData.append('target_team_id', target_team_id);
            try {
                uploadBtn.innerText = `Uploading ${file.name}...`;
                await api.post('/api/files/upload', formData, { headers: { 'Content-Type': 'multipart/form-data' } });
                successCount++;
            } catch (e) { failCount++; console.error(`Upload failed: ${file.name}`, e); }
        }
        uploadBtn.innerText = 'Upload';
        uploadBtn.disabled = false;
        if (successCount > 0) { showToast(`Uploaded ${successCount} file(s). ${failCount} failed.`, failCount === 0 ? 'success' : 'error'); pendingFiles = []; updateFileListUI(); await loadAccessibleFiles(); } else { showToast('All uploads failed', 'error'); }
    }

    // ---------- File Explorer ----------
    async function loadAccessibleFiles() {
        try {
            const res = await api.get('/api/files/accessible');
            allAccessibleFiles = res.data;
            renderAccessibleFiles('all');
        } catch (e) { console.warn('Failed to load files', e); }
    }

    function renderAccessibleFiles(filterType = 'all', subValue = null) {
        const container = document.getElementById('driveFileContainer');
        container.innerHTML = '';
        let filtered = [...allAccessibleFiles];
        if (filterType === 'company') filtered = filtered.filter(f => f.access_level === 'company');
        else if (filterType === 'department') { filtered = filtered.filter(f => f.access_level === 'department'); if (subValue) filtered = filtered.filter(f => f.department === subValue); }
        else if (filterType === 'team') { filtered = filtered.filter(f => f.access_level === 'team'); if (subValue) filtered = filtered.filter(f => f.team === subValue); }
        else if (filterType === 'private') filtered = filtered.filter(f => f.access_level === 'private');
        if (filtered.length === 0) { container.innerHTML = '<div style="grid-column:1/-1; text-align:center; color: var(--text-muted); padding: 20px;">No files found</div>'; return; }
        filtered.forEach(file => {
            const card = document.createElement('div');
            card.className = 'drive-card';
            let accessLabel = '', ownerInfo = '';
            if (file.access_level === 'company') accessLabel = '🏢 Company';
            else if (file.access_level === 'department') accessLabel = `🏛️ Department: ${file.department || 'N/A'}`;
            else if (file.access_level === 'team') accessLabel = `👥 Team: ${file.team || 'N/A'}`;
            else if (file.access_level === 'private') { accessLabel = '🔒 Personal'; if (file.owner_email) ownerInfo = `<div style="font-size:11px; color:var(--text-muted); margin-top:4px;">Owner: ${escapeHtml(file.owner_email)}</div>`; }
            card.innerHTML = `<span class="material-symbols-outlined" style="font-size:32px; color:var(--primary);">description</span><div style="font-weight:500; margin-top:8px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(file.original_filename || file.filename)}</div><div style="font-size:11px; color:var(--text-muted); margin-top:4px;">${(file.file_size / 1024).toFixed(1)} KB</div><div style="margin-top:6px;"><span class="access-badge">${accessLabel}</span></div>${ownerInfo}`;
            card.onclick = () => openDocumentViewer(file);
            container.appendChild(card);
        });
    }

    function openDocumentViewer(file) {
        const token = localStorage.getItem('access_token');
        const viewUrl = `/api/files/download/${file.id}?token=${token}&inline=1`;
        document.getElementById('documentIframe').src = viewUrl;
        document.getElementById('viewerNewTabBtn').href = viewUrl;
        document.getElementById('viewerFileName').innerHTML = `<span class="material-symbols-outlined" style="vertical-align: middle;">description</span> ${escapeHtml(file.original_filename || file.filename)}`;
        const modal = document.getElementById('documentViewerModal');
        modal.style.display = 'flex';
        setTimeout(() => modal.classList.add('show'), 10);
    }

    function openDocumentViewerById(fileId) {
        const token = localStorage.getItem('access_token');
        const viewUrl = `/api/files/download/${fileId}?token=${token}&inline=1`;
        document.getElementById('documentIframe').src = viewUrl;
        document.getElementById('viewerNewTabBtn').href = viewUrl;
        document.getElementById('viewerFileName').innerHTML = `<span class="material-symbols-outlined" style="vertical-align: middle;">description</span> Viewing Document`;
        const modal = document.getElementById('documentViewerModal');
        modal.style.display = 'flex';
        setTimeout(() => modal.classList.add('show'), 10);
    }

    // ---------- Event Listeners & Init ----------
    function initEventListeners() {
        document.getElementById('mobileMenuBtn').addEventListener('click', (e) => { e.stopPropagation(); document.getElementById('appSidebar').classList.toggle('mobile-open'); });
        document.getElementById('mainArea').addEventListener('click', () => { if (window.innerWidth <= 768) document.getElementById('appSidebar').classList.remove('mobile-open'); });
        document.getElementById('newChatBtn').addEventListener('click', showNewChatView);
        document.getElementById('sendBtn').addEventListener('click', sendMessage);
        document.getElementById('chatInput').addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); if (!document.getElementById('sendBtn').disabled) sendMessage(); } });
        document.getElementById('scopeToggleBtn').addEventListener('click', () => { const panel = document.getElementById('searchScopePanel'); panel.style.display = panel.style.display === 'block' ? 'none' : 'block'; });
        document.getElementById('fileUploadBtn').addEventListener('click', () => document.getElementById('pdfInput').click());
        document.getElementById('pdfInput').addEventListener('change', (e) => { if (e.target.files.length) { pendingFiles = pendingFiles.concat(Array.from(e.target.files)); updateFileListUI(); } e.target.value = ''; });
        document.getElementById('executeUploadBtn').addEventListener('click', uploadFiles);
        document.getElementById('openExplorerBtn').addEventListener('click', async () => { await loadAccessibleFiles(); const modal = document.getElementById('driveExplorerModal'); modal.style.display = 'flex'; setTimeout(() => modal.classList.add('show'), 10); });
        document.getElementById('closeExplorerBtn').addEventListener('click', () => { const modal = document.getElementById('driveExplorerModal'); modal.classList.remove('show'); setTimeout(() => modal.style.display = 'none', 200); });
        document.getElementById('closeViewerBtn').addEventListener('click', () => { const modal = document.getElementById('documentViewerModal'); modal.classList.remove('show'); setTimeout(() => { modal.style.display = 'none'; document.getElementById('documentIframe').src = ''; }, 200); });
        document.getElementById('sidebarProfileBtn').addEventListener('click', () => { const modal = document.getElementById('profileDropdownModal'); modal.style.display = 'flex'; setTimeout(() => modal.classList.add('show'), 10); });
        document.getElementById('closeProfileDropdown').addEventListener('click', () => { const modal = document.getElementById('profileDropdownModal'); modal.classList.remove('show'); setTimeout(() => modal.style.display = 'none', 200); });
        document.getElementById('saveProfileDropdownBtn').addEventListener('click', () => { const theme = document.getElementById('themeSelectDropdown').value; applyTheme(theme); showToast('Settings saved', 'success'); document.getElementById('profileDropdownModal').classList.remove('show'); setTimeout(() => document.getElementById('profileDropdownModal').style.display = 'none', 200); });
        document.getElementById('logoutBtn').addEventListener('click', () => { localStorage.clear(); window.location.href = '/'; });
        document.querySelectorAll('input[name="scopeType"]').forEach(r => r.addEventListener('change', updateScopeUI));

        // Admin Dashboard button
        document.getElementById('adminDashboardBtn').addEventListener('click', () => {
            window.location.href = '/admin/dashboard';
        });

        // File explorer filter tabs
        const tabs = document.querySelectorAll('.filter-tab');
        const subFilterDiv = document.getElementById('explorerSubFilters');
        const dynamicFilter = document.getElementById('explorerDynamicFilter');
        tabs.forEach(tab => {
            tab.addEventListener('click', () => {
                tabs.forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                const filter = tab.dataset.filter;
                if (filter === 'department') {
                    const depts = [...new Set(allAccessibleFiles.filter(f => f.access_level === 'department').map(f => f.department).filter(Boolean))];
                    dynamicFilter.innerHTML = '<option value="">All Departments</option>' + depts.map(d => `<option value="${d}">${d}</option>`).join('');
                    subFilterDiv.style.display = 'flex';
                    dynamicFilter.onchange = () => renderAccessibleFiles('department', dynamicFilter.value);
                    renderAccessibleFiles('department', dynamicFilter.value);
                } else if (filter === 'team') {
                    const teams = [...new Set(allAccessibleFiles.filter(f => f.access_level === 'team').map(f => f.team).filter(Boolean))];
                    dynamicFilter.innerHTML = '<option value="">All Teams</option>' + teams.map(t => `<option value="${t}">${t}</option>`).join('');
                    subFilterDiv.style.display = 'flex';
                    dynamicFilter.onchange = () => renderAccessibleFiles('team', dynamicFilter.value);
                    renderAccessibleFiles('team', dynamicFilter.value);
                } else {
                    subFilterDiv.style.display = 'none';
                    renderAccessibleFiles(filter);
                }
            });
        });
    }

    // ---------- Init ----------
    async function init() {

        await fetchCurrentUser();
        await loadSystemData();
        await loadUploadTargets();
        await loadConversations();
        buildUploadScopeOptions();
        initEventListeners();
        document.getElementById('chatInput').focus();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
