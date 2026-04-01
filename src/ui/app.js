// MCP JSON-RPC client
const MCP = {
    token: null,
    baseUrl: '',

    sessionId: null,

    init() {
        const params = new URLSearchParams(window.location.search);
        this.token = params.get('token') || localStorage.getItem('mcp_token');
        this.baseUrl = window.location.origin + '/mcp/';
    },

    async _post(method, params = {}) {
        const headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/event-stream',
            'Authorization': `Bearer ${this.token}`,
        };
        if (this.sessionId) {
            headers['Mcp-Session-Id'] = this.sessionId;
        }
        const resp = await fetch(this.baseUrl, {
            method: 'POST',
            headers,
            body: JSON.stringify({
                jsonrpc: '2.0',
                method,
                params,
                id: Date.now(),
            }),
            mode: 'same-origin',
        });
        if (!resp.ok) {
            const text = await resp.text();
            console.error(`MCP ${method} failed: ${resp.status}`, text);
            throw new Error(`HTTP ${resp.status}: ${text}`);
        }
        const sid = resp.headers.get('Mcp-Session-Id');
        if (sid) this.sessionId = sid;
        const contentType = resp.headers.get('Content-Type') || '';
        let data;
        if (contentType.includes('text/event-stream')) {
            const text = await resp.text();
            const lines = text.split('\n');
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    data = JSON.parse(line.substring(6));
                    break;
                }
            }
            if (!data) throw new Error('No data in SSE response');
        } else {
            data = await resp.json();
        }
        if (data.error) throw new Error(data.error.message);
        return data;
    },

    async initialize() {
        const data = await this._post('initialize', {
            protocolVersion: '2024-11-05',
            capabilities: {},
            clientInfo: { name: 'gmail-hygiene-ui', version: '1.0.0' },
        });
        console.log('MCP initialized:', data.result?.serverInfo);
        return data.result;
    },

    async call(toolName, args = {}) {
        const data = await this._post('tools/call', { name: toolName, arguments: args });
        const text = data.result?.content?.[0]?.text || '';
        return text;
    },

    async listTools() {
        const data = await this._post('tools/list', {});
        return data.result?.tools || [];
    },
};

// App controller
const App = {
    currentTab: 'inbox',
    accounts: [],
    currentAccount: null,

    async init() {
        MCP.init();
        if (!MCP.token) {
            document.getElementById('auth-screen').style.display = '';
            return;
        }
        try {
            await MCP.initialize();
            await MCP.listTools();
            localStorage.setItem('mcp_token', MCP.token);
            document.getElementById('auth-screen').style.display = 'none';
            document.getElementById('main').style.display = '';
            const acctText = await MCP.call('gmail_list_accounts');
            this.accounts = JSON.parse(acctText);
            this.currentAccount = this.accounts.find(a => a.default)?.email || this.accounts[0]?.email;
            this.renderAccounts();
            Inbox.load();
        } catch (e) {
            document.getElementById('auth-screen').style.display = '';
            console.error('Auth failed:', e);
        }
    },

    authenticate() {
        const token = document.getElementById('token-input').value.trim();
        if (!token) return;
        MCP.token = token;
        this.init();
    },

    switchTab(tab) {
        this.currentTab = tab;
        document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
        document.querySelectorAll('.tab-content').forEach(c => c.style.display = 'none');
        document.getElementById(`tab-${tab}`).style.display = '';
        if (tab === 'inbox') Inbox.load();
        else if (tab === 'priority') Priority.load();
        else if (tab === 'newsletters') Newsletters.load();
    },

    renderAccounts() {
        const bar = document.getElementById('account-bar');
        bar.innerHTML = this.accounts.map(a =>
            `<div class="account-btn ${a.email === this.currentAccount ? 'active' : ''}"
                  onclick="App.switchAccount('${a.email}')">${a.email}</div>`
        ).join('');
    },

    switchAccount(email) {
        this.currentAccount = email;
        this.renderAccounts();
        if (this.currentTab === 'inbox') Inbox.load();
    },
};

// Inbox controller
const Inbox = {
    messages: [],
    selected: new Set(),
    currentFilter: 'is:unread',
    currentSort: 'score',
    pageSize: 10,
    page: 0,
    pageToken: null,
    filters: [
        { id: 'attention', label: 'Needs Attention', query: 'is:unread is:important' },
        { id: 'unread', label: 'Unread', query: 'is:unread' },
        { id: 'people', label: 'People', query: 'is:unread category:primary' },
        { id: 'newsletters', label: 'Newsletters', query: 'has:nousersubs' },
        { id: 'promo', label: 'Promotional', query: 'category:promotions' },
        { id: 'unknown', label: 'Unknown Senders', query: 'is:unread -category:primary -category:social' },
    ],
    activeFilter: 'unread',

    async load() {
        const list = document.getElementById('message-list');
        list.innerHTML = '<div class="loading">Loading messages...</div>';
        this.selected.clear();
        this.updateBulkBar();
        this.renderFilters();

        try {
            const filter = this.filters.find(f => f.id === this.activeFilter);
            const query = filter ? filter.query : this.activeFilter;
            const args = { q: query, maxResults: this.pageSize };
            if (App.currentAccount) args.account = App.currentAccount;
            if (this.pageToken) args.pageToken = this.pageToken;

            const text = await MCP.call('gmail_search_messages', args);
            const lines = text.split('\n');
            this.messages = [];
            let nextToken = null;
            let totalEstimate = 0;

            for (const line of lines) {
                const idMatch = line.match(/id:\s*(\S+)\s+threadId:\s*(\S+)/);
                if (idMatch) {
                    this.messages.push({ id: idMatch[1], threadId: idMatch[2], loaded: false });
                }
                const tokenMatch = line.match(/Next page token:\s*(\S+)/);
                if (tokenMatch) nextToken = tokenMatch[1];
                const countMatch = line.match(/Found (\d+) results/);
                if (countMatch) totalEstimate = parseInt(countMatch[1]);
            }
            this.pageToken = nextToken;
            this.totalEstimate = totalEstimate;
            await this.renderMessages();
        } catch (e) {
            list.innerHTML = `<div class="empty">Error: ${e.message}</div>`;
        }
    },

    renderFilters() {
        const bar = document.getElementById('filter-bar');
        bar.innerHTML = this.filters.map(f =>
            `<div class="chip ${f.id === this.activeFilter ? 'active' : ''} ${f.id === 'unknown' ? 'alert' : ''}"
                  onclick="Inbox.setFilter('${f.id}')">${f.label}<span class="count"></span></div>`
        ).join('') + '<div class="chip" onclick="Inbox.customFilter()" style="border:1px dashed var(--border);">Custom...</div>';
    },

    setFilter(id) {
        this.activeFilter = id;
        this.pageToken = null;
        this.load();
    },

    customFilter() {
        const query = prompt('Enter Gmail search query:');
        if (query) {
            this.activeFilter = query;
            this.pageToken = null;
            this.load();
        }
    },

    async renderMessages() {
        const list = document.getElementById('message-list');
        if (!this.messages.length) {
            list.innerHTML = '<div class="empty">No messages found</div>';
            return;
        }

        list.innerHTML = `<div class="loading">Loading ${this.messages.length} messages...</div>`;
        let html = '';
        let loaded = 0;
        for (const msg of this.messages) {
            try {
                const args = { messageId: msg.id };
                if (App.currentAccount) args.account = App.currentAccount;
                const text = await MCP.call('gmail_read_message', args);
                const parsed = this.parseMessage(text, msg.id);
                html += this.renderRow(parsed);
                loaded++;
                list.innerHTML = html + `<div class="loading">Loaded ${loaded}/${this.messages.length}...</div>`;
            } catch (e) {
                html += `<div class="msg-row"><div class="msg-content" style="color:var(--accent)">Error loading ${msg.id}: ${e.message}</div></div>`;
                loaded++;
            }
        }
        list.innerHTML = html;
        this.renderPagination();
    },

    parseMessage(text, id) {
        const lines = text.split('\n');
        const get = (prefix) => {
            const line = lines.find(l => l.startsWith(prefix));
            return line ? line.substring(prefix.length).trim() : '';
        };
        return {
            id,
            from: get('From:'),
            to: get('To:'),
            subject: get('Subject:'),
            date: get('Date:'),
            labels: get('Labels:'),
            threadId: get('Thread ID:'),
        };
    },

    renderRow(msg) {
        const sender = msg.from.split('<')[0].trim() || msg.from;
        const email = (msg.from.match(/<(.+)>/) || ['', msg.from])[1];
        const isUnread = msg.labels.includes('UNREAD');
        const checked = this.selected.has(msg.id) ? 'checked' : '';
        const escapedEmail = email.replace(/'/g, "\\'");
        const escapedSender = sender.replace(/'/g, "\\'");

        return `<div class="msg-row" data-id="${msg.id}" data-email="${email}">
            <input type="checkbox" ${checked} onchange="Inbox.toggleSelect('${msg.id}')">
            <div class="priority-dot normal"></div>
            <div class="msg-content">
                <div class="msg-header">
                    <span class="msg-sender" onclick="Inbox.filterBySender('${escapedEmail}')" title="Show all from ${escapedSender}" style="cursor:pointer">${sender}<span class="msg-email">${email}</span></span>
                    <span class="msg-date">${this.formatDate(msg.date)}</span>
                </div>
                <div class="msg-subject" style="${isUnread ? 'color:var(--text-primary);font-weight:600' : ''}">${msg.subject}</div>
            </div>
            <div class="msg-actions">
                <button class="action-btn" onclick="Inbox.unsub('${msg.id}')" title="Unsubscribe">U</button>
                <button class="action-btn" onclick="Inbox.trash(['${msg.id}'])" title="Trash">T</button>
                <button class="action-btn" onclick="Inbox.spam(['${msg.id}'])" title="Spam">S</button>
                <button class="action-btn" onclick="Inbox.blockSender('${escapedEmail}')" title="Block">B</button>
            </div>
        </div>`;
    },

    filterBySender(email) {
        this.activeFilter = 'from:' + email;
        this.pageToken = null;
        this.load();
    },

    async unsub(msgId) {
        try {
            const args = { messageId: msgId };
            if (App.currentAccount) args.account = App.currentAccount;
            const result = await MCP.call('gmail_get_unsubscribe_link', args);
            const urlMatch = result.match(/URL:\s*(\S+)/);
            const mailtoMatch = result.match(/Email:\s*(\S+)/);
            if (urlMatch) {
                window.open(urlMatch[1], '_blank');
            } else if (mailtoMatch) {
                window.open(mailtoMatch[1], '_blank');
            } else {
                alert('No unsubscribe link found in this message.');
            }
        } catch (e) {
            alert('Error: ' + e.message);
        }
    },

    formatDate(dateStr) {
        if (!dateStr) return '';
        try {
            const d = new Date(dateStr);
            const now = new Date();
            const diffMs = now - d;
            const diffH = Math.floor(diffMs / 3600000);
            if (diffH < 24) return `${diffH}h ago`;
            const diffD = Math.floor(diffH / 24);
            if (diffD < 7) return `${diffD}d ago`;
            return d.toLocaleDateString();
        } catch { return dateStr; }
    },

    toggleSelect(id) {
        if (this.selected.has(id)) this.selected.delete(id);
        else this.selected.add(id);
        this.updateBulkBar();
    },

    toggleSelectAll() {
        const all = document.getElementById('select-all').checked;
        this.messages.forEach(m => {
            if (all) this.selected.add(m.id); else this.selected.delete(m.id);
        });
        document.querySelectorAll('.msg-row input[type="checkbox"]').forEach(cb => cb.checked = all);
        this.updateBulkBar();
    },

    changePageSize() {
        this.pageSize = parseInt(document.getElementById('page-size').value);
        this.pageToken = null;
        this.load();
    },

    selectAll() {
        document.getElementById('select-all').checked = true;
        this.toggleSelectAll();
    },

    selectNone() {
        document.getElementById('select-all').checked = false;
        this.toggleSelectAll();
    },

    updateBulkBar() {
        const bar = document.getElementById('bulk-bar');
        const count = document.getElementById('selected-count');
        if (this.selected.size > 0) {
            bar.style.display = '';
            count.textContent = `${this.selected.size} selected`;
        } else {
            bar.style.display = 'none';
        }
    },

    async trash(ids) {
        if (!confirm(`Trash ${ids.length} message(s)?`)) return;
        const args = { messageIds: ids };
        if (App.currentAccount) args.account = App.currentAccount;
        await MCP.call('gmail_trash_messages', args);
        this.load();
    },

    async spam(ids) {
        if (!confirm(`Report ${ids.length} message(s) as spam?`)) return;
        const args = { messageIds: ids };
        if (App.currentAccount) args.account = App.currentAccount;
        await MCP.call('gmail_report_spam', args);
        this.load();
    },

    async blockSender(email) {
        if (!confirm(`Block all email from ${email}?`)) return;
        const args = { sender: email };
        if (App.currentAccount) args.account = App.currentAccount;
        await MCP.call('gmail_block_sender', args);
        this.load();
    },

    bulkTrash() { this.trash([...this.selected]); },
    bulkSpam() { this.spam([...this.selected]); },

    async bulkBlock() {
        const ids = [...this.selected];
        if (!confirm(`Block senders of ${ids.length} selected message(s)?`)) return;
        for (const id of ids) {
            const row = document.querySelector(`.msg-row[data-id="${id}"]`);
            const email = row?.querySelector('.msg-email')?.textContent;
            if (email) {
                const args = { sender: email };
                if (App.currentAccount) args.account = App.currentAccount;
                await MCP.call('gmail_block_sender', args);
            }
        }
        this.load();
    },

    async bulkUnsub() {
        let found = 0;
        for (const id of [...this.selected]) {
            try {
                const args = { messageId: id };
                if (App.currentAccount) args.account = App.currentAccount;
                const result = await MCP.call('gmail_get_unsubscribe_link', args);
                const urlMatch = result.match(/URL:\s*(\S+)/);
                if (urlMatch) {
                    window.open(urlMatch[1], '_blank');
                    found++;
                }
            } catch (e) { /* skip */ }
        }
        if (found === 0) alert('No unsubscribe links found in selected messages.');
        else alert(`Opened ${found} unsubscribe link(s) in new tabs.`);
    },

    async bulkPriority() {
        const tier = prompt('Priority tier (critical/high/normal):', 'normal');
        if (!tier) return;
        for (const id of [...this.selected]) {
            const row = document.querySelector(`.msg-row[data-id="${id}"]`);
            const email = row?.querySelector('.msg-email')?.textContent;
            const name = row?.querySelector('.msg-sender')?.childNodes[0]?.textContent?.trim();
            if (email) {
                await MCP.call('gmail_add_priority_sender', {
                    pattern: email, tier, label: name || email,
                });
            }
        }
        alert('Added to priority senders');
    },

    bulkMoveTo() {
        Labels.show(async (labelId) => {
            const args = { threadId: '', addLabelIds: [labelId], removeLabelIds: ['INBOX'] };
            for (const id of [...this.selected]) {
                const msg = this.messages.find(m => m.id === id);
                if (msg) {
                    args.threadId = msg.threadId;
                    if (App.currentAccount) args.account = App.currentAccount;
                    await MCP.call('gmail_modify_thread_labels', args);
                }
            }
            this.load();
        });
    },

    sort(by) {
        this.currentSort = by;
        document.querySelectorAll('.sort-options span').forEach(s => s.classList.remove('active'));
        event.target.classList.add('active');
        // Re-sort is handled server-side by different queries for now
    },

    preview(id) {
        // Could open a detail panel; for now just highlights the row
    },

    renderPagination() {
        const pag = document.getElementById('pagination');
        pag.innerHTML = `
            <span>Showing ${this.messages.length} messages</span>
            ${this.pageToken ? `<a onclick="Inbox.nextPage()">Next &rarr;</a>` : ''}
        `;
    },

    nextPage() { this.load(); },
};

// Labels helper
const Labels = {
    items: [],
    callback: null,

    async show(cb) {
        this.callback = cb;
        if (!this.items.length) {
            const text = await MCP.call('gmail_list_labels');
            try { this.items = JSON.parse(text); } catch { this.items = []; }
        }
        const dd = document.getElementById('label-dropdown');
        dd.innerHTML = this.items
            .filter(l => l.type === 'user')
            .map(l => `<div class="label-item" onclick="Labels.select('${l.id}')">${l.name}</div>`)
            .join('') +
            '<div class="label-item create" onclick="Labels.create()">+ Create new label</div>';
        dd.style.display = '';
        dd.style.position = 'fixed';
        dd.style.top = '50%';
        dd.style.left = '50%';
        dd.style.transform = 'translate(-50%, -50%)';
        document.addEventListener('keydown', Labels.dismiss, { once: true });
    },

    select(id) {
        document.getElementById('label-dropdown').style.display = 'none';
        if (this.callback) this.callback(id);
    },

    async create() {
        const name = prompt('New label name:');
        if (!name) return;
        const text = await MCP.call('gmail_create_label', { name });
        this.items = []; // force refresh
        Labels.show(this.callback);
    },

    dismiss(e) {
        if (e.key === 'Escape') document.getElementById('label-dropdown').style.display = 'none';
    },
};

// Priority Senders controller
const Priority = {
    senders: [],

    async load() {
        const list = document.getElementById('priority-list');
        list.innerHTML = '<div class="loading">Loading...</div>';
        try {
            const text = await MCP.call('gmail_list_priority_senders');
            this.senders = this.parseSenders(text);
            this.render();
        } catch (e) {
            list.innerHTML = `<div class="empty">Error: ${e.message}</div>`;
        }
    },

    parseSenders(text) {
        if (text.startsWith('No priority')) return [];
        const senders = [];
        let currentTier = '';
        for (const line of text.split('\n')) {
            const tierMatch = line.match(/^(CRITICAL|HIGH|NORMAL)/i);
            if (tierMatch) { currentTier = tierMatch[1].toLowerCase(); continue; }
            const entryMatch = line.match(/^\s+(.+?)\s+\((.+)\)$/);
            if (entryMatch) {
                senders.push({ pattern: entryMatch[1], label: entryMatch[2], tier: currentTier });
            }
        }
        return senders;
    },

    render() {
        const list = document.getElementById('priority-list');
        const search = (document.getElementById('ps-search')?.value || '').toLowerCase();
        const filtered = search
            ? this.senders.filter(s => s.pattern.toLowerCase().includes(search) || s.label.toLowerCase().includes(search))
            : this.senders;

        const grouped = { critical: [], high: [], normal: [] };
        filtered.forEach(s => (grouped[s.tier] || grouped.normal).push(s));

        let html = '';
        for (const [tier, senders] of Object.entries(grouped)) {
            if (!senders.length) continue;
            html += `<div class="ps-section"><h3>${tier.toUpperCase()} (${senders.length})</h3>`;
            for (const s of senders) {
                html += `<div class="ps-row">
                    <span class="ps-pattern">${s.pattern}</span>
                    <span class="ps-label">${s.label}</span>
                    <button class="ps-remove" onclick="Priority.remove('${s.pattern}')">Remove</button>
                </div>`;
            }
            html += '</div>';
        }
        list.innerHTML = html || '<div class="empty">No priority senders configured</div>';
    },

    filter() { this.render(); },

    async addSender() {
        const pattern = document.getElementById('ps-pattern').value.trim();
        const tier = document.getElementById('ps-tier').value;
        const label = document.getElementById('ps-label').value.trim();
        if (!pattern || !label) { alert('Pattern and label required'); return; }
        await MCP.call('gmail_add_priority_sender', { pattern, tier, label });
        document.getElementById('ps-pattern').value = '';
        document.getElementById('ps-label').value = '';
        this.load();
    },

    async remove(pattern) {
        if (!confirm(`Remove ${pattern}?`)) return;
        await MCP.call('gmail_remove_priority_sender', { pattern });
        await MCP.call('gmail_dismiss_contact', { pattern });
        this.load();
    },

    async importContacts() {
        if (!confirm('Import all Google contacts as normal-tier priority senders?')) return;
        const result = await MCP.call('gmail_import_contacts_as_priority', { tier: 'normal' });
        alert(result);
        this.load();
    },

    async resyncContacts() {
        if (!confirm('Re-sync contacts? Dismissed contacts will be skipped.')) return;
        const result = await MCP.call('gmail_import_contacts_as_priority', { tier: 'normal' });
        alert(result);
        this.load();
    },
};

// Newsletters controller
const Newsletters = {
    items: [],
    selected: new Set(),

    async load() {
        const list = document.getElementById('newsletter-list');
        list.innerHTML = '<div class="loading">Scanning for newsletters...</div>';
        try {
            await this.scan();
        } catch (e) {
            list.innerHTML = `<div class="empty">Error: ${e.message}</div>`;
        }
    },

    async scan() {
        const list = document.getElementById('newsletter-list');
        const args = { q: 'has:nousersubs', maxResults: 50 };
        if (App.currentAccount) args.account = App.currentAccount;
        const text = await MCP.call('gmail_search_messages', args);

        const lines = text.split('\n');
        const msgIds = [];
        for (const line of lines) {
            const m = line.match(/id:\s*(\S+)/);
            if (m) msgIds.push(m[1]);
        }

        // Group by sender
        const senderMap = {};
        for (const id of msgIds.slice(0, 30)) {
            try {
                const rArgs = { messageId: id };
                if (App.currentAccount) rArgs.account = App.currentAccount;
                const msgText = await MCP.call('gmail_read_message', rArgs);
                const fromLine = msgText.split('\n').find(l => l.startsWith('From:'));
                const from = fromLine ? fromLine.substring(5).trim() : 'Unknown';
                const email = (from.match(/<(.+)>/) || ['', from])[1];
                const name = from.split('<')[0].trim() || email;
                const key = email.toLowerCase();
                if (!senderMap[key]) senderMap[key] = { name, email, count: 0, lastId: id };
                senderMap[key].count++;
            } catch { /* skip */ }
        }

        this.items = Object.values(senderMap).sort((a, b) => b.count - a.count);
        this.render();
    },

    render() {
        const list = document.getElementById('newsletter-list');
        if (!this.items.length) {
            list.innerHTML = '<div class="empty">No newsletters detected</div>';
            return;
        }
        list.innerHTML = this.items.map(nl => `
            <div class="nl-row">
                <input type="checkbox" onchange="Newsletters.toggle('${nl.email}')">
                <div class="nl-info">
                    <div class="nl-sender">${nl.name}</div>
                    <div class="nl-meta">${nl.email} &middot; ${nl.count} emails</div>
                </div>
                <div class="nl-actions">
                    <button class="bulk-btn" onclick="Newsletters.unsubscribe('${nl.lastId}')">Unsubscribe</button>
                    <button class="bulk-btn" onclick="Newsletters.trashAll('${nl.email}')">Trash All</button>
                    <button class="bulk-btn" onclick="Newsletters.block('${nl.email}')">Block</button>
                </div>
            </div>
        `).join('');
    },

    toggle(email) {
        if (this.selected.has(email)) this.selected.delete(email);
        else this.selected.add(email);
    },

    async unsubscribe(msgId) {
        const args = { messageId: msgId };
        if (App.currentAccount) args.account = App.currentAccount;
        const result = await MCP.call('gmail_get_unsubscribe_link', args);
        const urlMatch = result.match(/URL:\s*(\S+)/);
        if (urlMatch) {
            window.open(urlMatch[1], '_blank');
        } else {
            alert(result);
        }
    },

    async trashAll(email) {
        if (!confirm(`Trash all emails from ${email}?`)) return;
        const args = { query: `from:${email}` };
        if (App.currentAccount) args.account = App.currentAccount;
        const result = await MCP.call('gmail_trash_messages', args);
        alert(result);
        this.scan();
    },

    async block(email) {
        if (!confirm(`Block ${email}?`)) return;
        const args = { sender: email };
        if (App.currentAccount) args.account = App.currentAccount;
        await MCP.call('gmail_block_sender', args);
        this.scan();
    },

    async bulkTrash() {
        for (const email of [...this.selected]) await this.trashAll(email);
    },

    async bulkBlock() {
        for (const email of [...this.selected]) await this.block(email);
    },
};

// Boot
document.addEventListener('DOMContentLoaded', () => App.init());
