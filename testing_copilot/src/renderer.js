'use strict';
const { ipcRenderer } = require('electron');

const BACKEND = 'http://127.0.0.1:7799';

let isReady = false, isBusy = false, meetingActive = false;
let recognition = null, meetingRec = null, meetingPollTimer = null;
let selectedClient = { id: '', name: '' };

const chat       = document.getElementById('chat');
const typing     = document.getElementById('typing');
const input      = document.getElementById('input');
const sendBtn    = document.getElementById('send-btn');
const micBtn     = document.getElementById('mic-btn');
const clientSel  = document.getElementById('client-select');
const statusDot  = document.getElementById('status-dot');
const chipsBar   = document.getElementById('chips-bar');

// ── Window controls ────────────────────────────────────────────────────────
document.getElementById('close-btn').addEventListener('click', () => ipcRenderer.send('close-app'));
document.getElementById('min-btn').addEventListener('click',   () => ipcRenderer.send('minimize-app'));

// ── Backend ────────────────────────────────────────────────────────────────
ipcRenderer.on('backend-ready', async () => {
    isReady = true;
    setStatus('ready');
    input.disabled = false;
    sendBtn.disabled = false;
    await loadClients();
    await loadKeywords();
});

ipcRenderer.on('backend-error', (_, msg) => {
    setStatus('error');
    addMessage('ai', `⚠️ Backend failed: ${msg}`);
});

// ── Clients ────────────────────────────────────────────────────────────────
async function loadClients() {
    try {
        const clients = await api('/clients');
        clients.forEach(c => {
            const opt = document.createElement('option');
            opt.value = c.id;
            opt.textContent = c.name;
            opt.dataset.name = c.name;
            clientSel.appendChild(opt);
        });
    } catch(e) {}
}

clientSel.addEventListener('change', () => {
    const opt = clientSel.selectedOptions[0];
    selectedClient = { id: opt.value, name: opt.dataset.name || opt.value };
    if (selectedClient.name) {
        document.getElementById('welcome') && (document.getElementById('welcome').style.display = 'none');
        addMessage('ai', `Client selected: **${selectedClient.name}**\nPick a keyword above or ask me anything about them.`);
    }
});

// ── Keyword chips ──────────────────────────────────────────────────────────
async function loadKeywords() {
    try {
        const kws = await api('/keywords');
        chipsBar.innerHTML = '';
        kws.forEach(kw => {
            const btn = document.createElement('button');
            btn.className = 'chip';
            btn.textContent = `${kw.icon} ${kw.label}`;
            btn.addEventListener('click', () => fireKeyword(kw));
            chipsBar.appendChild(btn);
        });
    } catch(e) {}
}

async function fireKeyword(kw) {
    if (!isReady || isBusy) return;
    const client = selectedClient.name || 'the client';
    addMessage('user', `${kw.icon} ${kw.label}${selectedClient.name ? ' — ' + selectedClient.name : ''}`);
    setBusy(true);
    try {
        const data = await post('/quick', { keyword_id: kw.id, client_id: selectedClient.id, client_name: client });
        addMessage('ai', data.response || data.error, `${kw.icon} ${kw.label}`);
    } catch(e) { addMessage('ai', '⚠️ Network error: ' + e.message); }
    finally { setBusy(false); }
}

// ── Prompt ─────────────────────────────────────────────────────────────────
async function submit() {
    const text = input.value.trim();
    if (!text || !isReady || isBusy) return;
    const prompt = selectedClient.name ? `[Client: ${selectedClient.name}] ${text}` : text;
    addMessage('user', text);
    input.value = '';
    autoResize();
    setBusy(true);
    try {
        const data = await post('/ask', { prompt });
        addMessage('ai', data.response || data.error);
    } catch(e) { addMessage('ai', '⚠️ Network error: ' + e.message); }
    finally { setBusy(false); }
}

sendBtn.addEventListener('click', submit);
input.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); } });
input.addEventListener('input', autoResize);

function autoResize() {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 120) + 'px';
}

// ── Voice ──────────────────────────────────────────────────────────────────
micBtn.addEventListener('click', () => {
    if (!isReady || isBusy) return;
    if (recognition) { recognition.stop(); return; }
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) { addMessage('ai', '⚠️ Speech API not available.'); return; }

    recognition = new SR();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = 'fr-FR';
    micBtn.classList.add('recording');
    setStatus('listening');

    recognition.onresult = e => {
        let final = '', interim = '';
        for (let i = 0; i < e.results.length; i++)
            e.results[i].isFinal ? final += e.results[i][0].transcript : interim += e.results[i][0].transcript;
        input.value = final || interim;
        autoResize();
        if (final) { recognition.stop(); submit(); }
    };
    recognition.onerror = () => stopVoice();
    recognition.onend   = () => stopVoice();
    recognition.start();
});

function stopVoice() {
    recognition = null;
    micBtn.classList.remove('recording');
    if (isReady && !isBusy) setStatus('ready');
}

// ── Chat helpers ───────────────────────────────────────────────────────────
function addMessage(role, text, source) {
    const welcome = document.getElementById('welcome');
    if (welcome) welcome.style.display = 'none';

    const msg = document.createElement('div');
    msg.className = `msg ${role}`;

    if (role === 'ai') {
        msg.innerHTML = `
          <div class="avatar">🤖</div>
          <div>
            <div class="bubble">${escHtml(text)}</div>
            ${source ? `<div class="source">${escHtml(source)}</div>` : ''}
          </div>`;
    } else {
        msg.innerHTML = `<div class="bubble">${escHtml(text)}</div>`;
    }

    chat.insertBefore(msg, typing);
    chat.scrollTop = chat.scrollHeight;
}

function escHtml(str) {
    return String(str)
        .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
        .replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>')
        .replace(/\n/g,'<br>');
}

// ── UI state ───────────────────────────────────────────────────────────────
function setStatus(state) {
    statusDot.className = state;
}

function setBusy(val) {
    isBusy = val;
    typing.style.display = val ? 'flex' : 'none';
    if (val) {
        chat.scrollTop = chat.scrollHeight;
        setStatus('thinking');
        sendBtn.disabled = true;
        input.disabled = true;
    } else {
        setStatus('ready');
        sendBtn.disabled = false;
        input.disabled = false;
        input.focus();
    }
}

// ── Fetch ──────────────────────────────────────────────────────────────────
async function api(path) {
    const r = await fetch(BACKEND + path);
    return r.json();
}
async function post(path, body) {
    const r = await fetch(BACKEND + path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    return r.json();
}
