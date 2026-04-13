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

    ui.pendingCount.textContent = entries.length
        ? `(${entries.length})`
        : '';
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

// Sync with server
async function attemptSync() {
    const cfg = state.config;
    if (!state.isOnline || !cfg.serverUrl || !cfg.apiKey) {
        return;
    }

    const tx = state.db.transaction(STORE_NAME, 'readonly');
    const store = tx.objectStore(STORE_NAME);
    const pending = await new Promise((resolve) => {
        const req = store.getAll();
        req.onsuccess = () => resolve(req.result);
    });

    if (pending.length === 0) {
        ui.lastSync.textContent = 'Gönderilecek kayıt yok';
        return;
    }

    ui.syncBtn.disabled = true;
    ui.lastSync.textContent = `${pending.length} kayıt gönderiliyor...`;

    // Build push entries
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

    try {
        const response = await fetch(`${cfg.serverUrl}/sync`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                Authorization: `Bearer ${cfg.apiKey}`,
            },
            body: JSON.stringify({
                method: 'push',
                body: {
                    entries: pushEntries,
                    device_id: cfg.deviceId,
                },
            }),
        });

        if (!response.ok) {
            const errText = await response.text();
            throw new Error(`${response.status}: ${errText}`);
        }

        const result = await response.json();

        // Upload attachments
        for (const entry of pending) {
            if (entry.attachment) {
                await uploadAttachment(entry.attachment);
            }
        }

        // Clear pending entries
        const clearTx = state.db.transaction(STORE_NAME, 'readwrite');
        clearTx.objectStore(STORE_NAME).clear();
        await renderOfflineEntries();

        const accepted = result.body?.accepted || 0;
        const time = new Date().toLocaleTimeString('tr-TR');
        ui.lastSync.textContent =
            `${accepted} kayıt gönderildi (${time})`;
    } catch (err) {
        console.error('Sync failed:', err);
        ui.lastSync.textContent = `Hata: ${err.message}`;
    } finally {
        ui.syncBtn.disabled = false;
    }
}

async function uploadAttachment(attachment) {
    const cfg = state.config;
    try {
        await fetch(`${cfg.serverUrl}/sync`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                Authorization: `Bearer ${cfg.apiKey}`,
            },
            body: JSON.stringify({
                method: 'attachment_put',
                body: {
                    filename: attachment.name,
                    data: attachment.data,
                },
            }),
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
