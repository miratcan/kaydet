/**
 * Kaydet PWA — Sync client for mobile capture.
 */

const DB_NAME = 'kaydet_pwa_db';
const STORE_NAME = 'pending_entries';

// IndexedDB
async function initDB() {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open(DB_NAME, 1);
        request.onupgradeneeded = (e) => {
            const db = e.target.result;
            if (!db.objectStoreNames.contains(STORE_NAME)) {
                db.createObjectStore(STORE_NAME, {
                    keyPath: 'id',
                    autoIncrement: true,
                });
            }
        };
        request.onsuccess = (e) => resolve(e.target.result);
        request.onerror = (e) => reject(e.target.error);
    });
}

// State
const state = {
    db: null,
    isOnline: navigator.onLine,
    currentAttachment: null,
    get config() {
        return {
            serverUrl: localStorage.getItem('sync_server') || '',
            apiKey: localStorage.getItem('sync_api_key') || '',
            deviceId: 'pwa-mobile',
        };
    },
};

// UI refs
const ui = {};

function bindUI() {
    ui.input = document.getElementById('entry-input');
    ui.saveBtn = document.getElementById('save-btn');
    ui.offlineList = document.getElementById('offline-list');
    ui.entriesList = document.getElementById('entries-list');
    ui.statusDot = document.getElementById('status-dot');
    ui.syncBtn = document.getElementById('sync-now');
    ui.lastSync = document.getElementById('last-sync');
    ui.fileInput = document.getElementById('attach-file');
    ui.preview = document.getElementById('attachment-preview');
    ui.settingsBtn = document.getElementById('settings-btn');
    ui.settingsPanel = document.getElementById('settings-panel');
    ui.serverInput = document.getElementById('server-url');
    ui.apiKeyInput = document.getElementById('api-key');
    ui.saveSettingsBtn = document.getElementById('save-settings');
    ui.pendingCount = document.getElementById('pending-count');
    ui.pendingSection = document.getElementById('pending-section');
}

function updateStatus() {
    state.isOnline = navigator.onLine;
    ui.statusDot.className = state.isOnline ? 'online' : 'offline';
}

async function renderOfflineEntries() {
    const tx = state.db.transaction(STORE_NAME, 'readonly');
    const store = tx.objectStore(STORE_NAME);
    const entries = await new Promise((resolve) => {
        const req = store.getAll();
        req.onsuccess = () => resolve(req.result);
    });

    ui.offlineList.innerHTML = entries
        .map(
            (e) => `
        <li>
            <strong>${e.timestamp}</strong>: ${e.text.substring(0, 40)}${e.text.length > 40 ? '...' : ''}
            ${e.attachment ? ' 📷' : ''}
        </li>
    `
        )
        .join('');

    const count = entries.length;
    ui.pendingCount.textContent = count ? `(${count})` : '';
    ui.pendingSection.hidden = count === 0;
}

// Save entry to IndexedDB
async function saveEntry() {
    const text = ui.input.value.trim();
    if (!text) return;

    const now = new Date();
    const entry = {
        text: text,
        timestamp: now.toLocaleTimeString('tr-TR', {
            hour: '2-digit',
            minute: '2-digit',
        }),
        source_file: now.toISOString().split('T')[0] + '.txt',
        updated_at: now.toISOString(),
        tags: [],
        metadata: {},
        attachment: state.currentAttachment || null,
    };

    const tx = state.db.transaction(STORE_NAME, 'readwrite');
    tx.objectStore(STORE_NAME).add(entry);

    ui.input.value = '';
    state.currentAttachment = null;
    ui.preview.hidden = true;

    await renderOfflineEntries();

    if (state.isOnline && state.config.apiKey) {
        attemptSync();
    }
}

// Send a protocol message to the server
async function sendMessage(method, body) {
    const cfg = state.config;
    const response = await fetch(`${cfg.serverUrl}/sync`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${cfg.apiKey}`,
        },
        body: JSON.stringify({ method, body }),
    });

    if (!response.ok) {
        const errText = await response.text();
        throw new Error(`${response.status}: ${errText}`);
    }

    return await response.json();
}

// Fetch recent entries from server
async function fetchRecentEntries() {
    const cfg = state.config;
    if (!cfg.serverUrl || !cfg.apiKey) return;

    try {
        // Get latest changes
        const changesResult = await sendMessage('changes', { since: 0 });
        const changes = changesResult.body?.changes || [];

        if (changes.length === 0) {
            ui.entriesList.innerHTML =
                '<li class="empty">Sunucuda kayit yok.</li>';
            return;
        }

        // Get the last 20 unique entry IDs (most recent)
        const seen = new Set();
        const entryIds = [];
        for (let i = changes.length - 1; i >= 0; i--) {
            const c = changes[i];
            if (c.action !== 'deleted' && !seen.has(c.entry_id)) {
                seen.add(c.entry_id);
                entryIds.push(c.entry_id);
                if (entryIds.length >= 20) break;
            }
        }

        if (entryIds.length === 0) {
            ui.entriesList.innerHTML =
                '<li class="empty">Kayit bulunamadi.</li>';
            return;
        }

        // Fetch full entries
        const entriesResult = await sendMessage('entries', {
            entry_ids: entryIds,
        });
        const entries = entriesResult.body?.entries || [];

        // Sort by source_file + timestamp descending
        entries.sort((a, b) => {
            const dateCompare = b.source_file.localeCompare(a.source_file);
            if (dateCompare !== 0) return dateCompare;
            return b.timestamp.localeCompare(a.timestamp);
        });

        ui.entriesList.innerHTML = entries
            .map((e) => {
                const date = e.source_file.replace('.txt', '');
                const tags = (e.tags || [])
                    .map((t) => `<span class="tag">#${t}</span>`)
                    .join(' ');
                const attachIcon =
                    e.attachments && e.attachments.length > 0
                        ? ' 📎'
                        : '';
                return `
                <li>
                    <div class="entry-header">
                        <span class="entry-date">${date}</span>
                        <span class="entry-time">${e.timestamp}</span>
                        ${attachIcon}
                    </div>
                    <div class="entry-text">${escapeHtml(e.text)}</div>
                    ${tags ? `<div class="entry-tags">${tags}</div>` : ''}
                </li>`;
            })
            .join('');
    } catch (err) {
        console.error('Fetch entries failed:', err);
        ui.entriesList.innerHTML = `<li class="empty">Hata: ${err.message}</li>`;
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Sync: push pending then fetch entries
async function attemptSync() {
    const cfg = state.config;
    if (!state.isOnline || !cfg.serverUrl || !cfg.apiKey) return;

    ui.syncBtn.disabled = true;

    try {
        // Push pending entries
        const tx = state.db.transaction(STORE_NAME, 'readonly');
        const store = tx.objectStore(STORE_NAME);
        const pending = await new Promise((resolve) => {
            const req = store.getAll();
            req.onsuccess = () => resolve(req.result);
        });

        if (pending.length > 0) {
            ui.lastSync.textContent = `${pending.length} kayit gonderiliyor...`;

            const pushEntries = pending.map((e) => ({
                entry_id: 0,
                source_file: e.source_file,
                timestamp: e.timestamp,
                text: e.text,
                tags: e.tags || [],
                metadata: e.metadata || {},
                attachments: e.attachment ? [e.attachment.name] : [],
                encrypted_secret: null,
                updated_at: e.updated_at,
            }));

            await sendMessage('push', {
                entries: pushEntries,
                device_id: cfg.deviceId,
            });

            // Upload attachments
            for (const entry of pending) {
                if (entry.attachment) {
                    await sendMessage('attachment_put', {
                        filename: entry.attachment.name,
                        data: entry.attachment.data,
                    });
                }
            }

            // Clear pending
            const clearTx = state.db.transaction(STORE_NAME, 'readwrite');
            clearTx.objectStore(STORE_NAME).clear();
            await renderOfflineEntries();
        }

        // Fetch recent entries from server
        await fetchRecentEntries();

        const time = new Date().toLocaleTimeString('tr-TR');
        ui.lastSync.textContent = `Son sync: ${time}`;
    } catch (err) {
        console.error('Sync failed:', err);
        ui.lastSync.textContent = `Hata: ${err.message}`;
    } finally {
        ui.syncBtn.disabled = false;
    }
}

async function uploadAttachment(attachment) {
    try {
        await sendMessage('attachment_put', {
            filename: attachment.name,
            data: attachment.data,
        });
    } catch (err) {
        console.error('Attachment upload failed:', err);
    }
}

// Settings
function toggleSettings() {
    const panel = ui.settingsPanel;
    const isHidden = panel.hidden;
    panel.hidden = !isHidden;
    if (isHidden) {
        ui.serverInput.value = state.config.serverUrl;
        ui.apiKeyInput.value = state.config.apiKey;
    }
}

function saveSettings() {
    const url = ui.serverInput.value.trim().replace(/\/+$/, '');
    const key = ui.apiKeyInput.value.trim();
    localStorage.setItem('sync_server', url);
    localStorage.setItem('sync_api_key', key);
    ui.settingsPanel.hidden = true;
    ui.lastSync.textContent = 'Ayarlar kaydedildi';
    // Fetch entries after saving settings
    fetchRecentEntries();
}

// File attachment
function handleFileSelect(e) {
    const file = e.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (event) => {
        state.currentAttachment = {
            name: `${Date.now()}_${file.name}`,
            data: event.target.result.split(',')[1],
        };
        ui.preview.style.backgroundImage =
            `url(${event.target.result})`;
        ui.preview.hidden = false;
    };
    reader.readAsDataURL(file);
}

// Keyboard shortcut
function handleKeydown(e) {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        saveEntry();
    }
}

// Init
async function init() {
    bindUI();
    state.db = await initDB();
    updateStatus();
    await renderOfflineEntries();

    // Show settings if not configured
    if (!state.config.serverUrl || !state.config.apiKey) {
        toggleSettings();
    } else {
        // Auto-fetch entries on load
        fetchRecentEntries();
    }

    // Event listeners
    window.addEventListener('online', updateStatus);
    window.addEventListener('offline', updateStatus);
    ui.saveBtn.addEventListener('click', saveEntry);
    ui.syncBtn.addEventListener('click', attemptSync);
    ui.fileInput.addEventListener('change', handleFileSelect);
    ui.settingsBtn.addEventListener('click', toggleSettings);
    ui.saveSettingsBtn.addEventListener('click', saveSettings);
    ui.input.addEventListener('keydown', handleKeydown);
}

init();
