'use strict';
const { ipcRenderer } = require('electron');

// ── State ──────────────────────────────────────────────────────────────────
let isReady       = false;
let isBusy        = false;
let meetingActive = false;
let recognition   = null;
let meetingRec    = null;
let meetingPollTimer = null;
let selectedClient = { id: '', name: '' };

const BACKEND = 'http://127.0.0.1:7799';

// ── DOM refs ───────────────────────────────────────────────────────────────
const status      = document.getElementById('status');
const clientSel   = document.getElementById('client-select');
const clearBtn    = document.getElementById('clear-btn');
const minBtn      = document.getElementById('min-btn');
const kwGrid      = document.getElementById('kw-grid');
const meetingToggle = document.getElementById('meeting-toggle');
const meetingInfo = document.getElementById('meeting-info');
const micBtn      = document.getElementById('mic-btn');
const voiceLabel  = document.getElementById('voice-label');
const voiceInterim= document.getElementById('voice-interim');
const promptInput = document.getElementById('prompt-input');
const askBtn      = document.getElementById('ask-btn');
const placeholder = document.getElementById('placeholder');
const thinking    = document.getElementById('thinking');
const responseContent = document.getElementById('response-content');
const responseLabel   = document.getElementById('response-label');
const responseText    = document.getElementById('response-text');

// ── Backend readiness ──────────────────────────────────────────────────────
ipcRenderer.on('backend-ready', async () => {
  isReady = true;
  setStatus('ready', 'Ready');
  enableInputs();
  await loadClients();
  await loadKeywords();
});

ipcRenderer.on('backend-error', (_, msg) => {
  setStatus('error', 'Error');
  showResponse('Backend failed: ' + msg, 'Error');
});

// ── Tabs ───────────────────────────────────────────────────────────────────
document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById(tab.dataset.tab + '-panel').classList.add('active');
  });
});

// ── Client selector ────────────────────────────────────────────────────────
async function loadClients() {
  try {
    const res = await fetch(`${BACKEND}/clients`);
    const clients = await res.json();
    clients.forEach(c => {
      const opt = document.createElement('option');
      opt.value = c.id;
      opt.textContent = c.name;
      opt.dataset.name = c.name;
      clientSel.appendChild(opt);
    });
  } catch(e) { console.error('loadClients', e); }
}

clientSel.addEventListener('change', () => {
  const opt = clientSel.selectedOptions[0];
  selectedClient = { id: opt.value, name: opt.dataset.name || opt.value };
});

// ── Keywords ───────────────────────────────────────────────────────────────
async function loadKeywords() {
  try {
    const res = await fetch(`${BACKEND}/keywords`);
    const kws  = await res.json();
    kwGrid.innerHTML = '';
    kws.forEach(kw => {
      const btn = document.createElement('button');
      btn.className = 'kw-btn';
      btn.innerHTML = `<span class="icon">${kw.icon}</span><span class="lbl">${kw.label}</span>`;
      btn.addEventListener('click', () => fireKeyword(kw));
      kwGrid.appendChild(btn);
    });
  } catch(e) { console.error('loadKeywords', e); }
}

async function fireKeyword(kw) {
  if (!isReady || isBusy) return;
  const client = selectedClient.name || 'the client';
  setBusy(true, `${kw.icon} ${kw.label}…`);
  try {
    const res = await fetch(`${BACKEND}/quick`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ keyword_id: kw.id, client_id: selectedClient.id, client_name: client })
    });
    const data = await res.json();
    showResponse(data.response || data.error, `${kw.icon} ${kw.label} — ${client}`);
  } catch(e) {
    showResponse('Network error: ' + e.message, 'Error');
  } finally { setBusy(false); }
}

// ── Meeting mode ───────────────────────────────────────────────────────────
meetingToggle.addEventListener('click', () => {
  meetingActive ? stopMeeting() : startMeeting();
});

function startMeeting() {
  if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
    meetingInfo.textContent = 'Speech API not available in this browser.';
    return;
  }
  meetingActive = true;
  meetingToggle.textContent = '⏹ Stop Meeting';
  meetingToggle.classList.add('active');
  setStatus('meeting', 'Meeting');
  meetingInfo.textContent = 'Listening… say a trigger phrase to pull data.';

  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  meetingRec = new SR();
  meetingRec.continuous = true;
  meetingRec.interimResults = false;
  meetingRec.lang = 'fr-FR';

  meetingRec.onresult = async (e) => {
    for (let i = e.resultIndex; i < e.results.length; i++) {
      if (!e.results[i].isFinal) continue;
      const utt = e.results[i][0].transcript.trim();
      if (!utt) continue;
      meetingInfo.textContent = `[${timestamp()}] "${utt.slice(0,60)}"`;
      try {
        const res = await fetch(`${BACKEND}/meeting/utterance`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: utt })
        });
        const data = await res.json();
        if (data.triggered) {
          meetingInfo.textContent = `🔍 Detected: "${data.question}"`;
          setStatus('thinking', 'Searching…');
          pollMeetingResult();
        }
      } catch(e) { console.error('meeting utterance', e); }
    }
  };

  meetingRec.onerror = (e) => meetingInfo.textContent = 'Mic error: ' + e.error;
  meetingRec.onend   = () => { if (meetingActive) meetingRec.start(); }; // auto-restart
  meetingRec.start();
}

function stopMeeting() {
  meetingActive = false;
  if (meetingRec) { meetingRec.onend = null; meetingRec.stop(); meetingRec = null; }
  if (meetingPollTimer) { clearInterval(meetingPollTimer); meetingPollTimer = null; }
  meetingToggle.textContent = '🎙 Meeting Mode';
  meetingToggle.classList.remove('active');
  setStatus('ready', 'Ready');
  meetingInfo.textContent = 'Off — say a trigger phrase to fire agents';
}

function pollMeetingResult() {
  if (meetingPollTimer) clearInterval(meetingPollTimer);
  meetingPollTimer = setInterval(async () => {
    try {
      const res  = await fetch(`${BACKEND}/meeting/result`);
      const data = await res.json();
      if (data.status === 'done') {
        clearInterval(meetingPollTimer);
        meetingPollTimer = null;
        showResponse(data.response, '🔍 Meeting — ' + (data.question || '').slice(0,50));
        setStatus('meeting', 'Meeting');
      } else if (data.status === 'error') {
        clearInterval(meetingPollTimer);
        showResponse('Error: ' + data.error, 'Meeting Error');
        setStatus('meeting', 'Meeting');
      }
    } catch(e) { console.error('poll', e); }
  }, 1200);
}

// ── Voice mode (single question) ───────────────────────────────────────────
micBtn.addEventListener('click', () => {
  if (!isReady || isBusy) return;
  if (recognition) { recognition.stop(); return; }

  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { voiceLabel.textContent = 'Speech API not supported.'; return; }

  recognition = new SR();
  recognition.continuous = false;
  recognition.interimResults = true;
  recognition.lang = 'fr-FR';

  micBtn.classList.add('recording');
  voiceLabel.textContent = 'Listening… click to stop';
  setStatus('listening', 'Listening');

  recognition.onresult = (e) => {
    let interim = '', final = '';
    for (let i = 0; i < e.results.length; i++) {
      e.results[i].isFinal ? final += e.results[i][0].transcript : interim += e.results[i][0].transcript;
    }
    voiceInterim.textContent = final || interim;
    if (final) { recognition.stop(); submitVoice(final); }
  };

  recognition.onerror  = (e) => { stopVoiceUI(); voiceLabel.textContent = 'Error: ' + e.error; };
  recognition.onend    = ()  => stopVoiceUI();
  recognition.start();
});

function stopVoiceUI() {
  recognition = null;
  micBtn.classList.remove('recording');
  voiceLabel.textContent = 'Click to speak your question';
  if (!isBusy) setStatus('ready', 'Ready');
}

async function submitVoice(text) {
  voiceInterim.textContent = text;
  setBusy(true, 'Voice…');
  try {
    const res  = await fetch(`${BACKEND}/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: selectedClient.name ? `[Client: ${selectedClient.name}] ${text}` : text })
    });
    const data = await res.json();
    showResponse(data.response || data.error, '🎙 ' + text.slice(0, 50));
  } catch(e) {
    showResponse('Network error: ' + e.message, 'Error');
  } finally { setBusy(false); voiceInterim.textContent = ''; }
}

// ── Prompt mode ────────────────────────────────────────────────────────────
async function submitPrompt() {
  const text = promptInput.value.trim();
  if (!text || !isReady || isBusy) return;
  const prompt = selectedClient.name ? `[Client: ${selectedClient.name}] ${text}` : text;
  setBusy(true, 'Prompt…');
  try {
    const res  = await fetch(`${BACKEND}/ask`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt })
    });
    const data = await res.json();
    showResponse(data.response || data.error, '⌨ ' + text.slice(0, 50));
    promptInput.value = '';
    autoResize();
  } catch(e) {
    showResponse('Network error: ' + e.message, 'Error');
  } finally { setBusy(false); }
}

askBtn.addEventListener('click', submitPrompt);
promptInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submitPrompt(); }
});
function autoResize() {
  promptInput.style.height = 'auto';
  promptInput.style.height = Math.min(promptInput.scrollHeight, 100) + 'px';
}
promptInput.addEventListener('input', autoResize);

// ── UI helpers ─────────────────────────────────────────────────────────────
function setStatus(cls, label) {
  status.className = cls;
  status.textContent = label;
}

function setBusy(val, statusLabel) {
  isBusy = val;
  if (val) {
    setStatus('thinking', statusLabel || 'Thinking…');
    placeholder.style.display = 'none';
    thinking.style.display    = 'block';
    responseContent.style.display = 'none';
    askBtn.disabled = true;
    promptInput.disabled = true;
  } else {
    thinking.style.display = 'none';
    if (!meetingActive) setStatus('ready', 'Ready');
    askBtn.disabled    = !isReady;
    promptInput.disabled = !isReady;
  }
}

function showResponse(text, label) {
  placeholder.style.display     = 'none';
  thinking.style.display        = 'none';
  responseContent.style.display = 'block';
  responseLabel.textContent     = label || '';
  responseText.textContent      = text || '(no response)';
  document.getElementById('response-area').scrollTop = 0;
}

function enableInputs() {
  askBtn.disabled      = false;
  promptInput.disabled = false;
}

clearBtn.addEventListener('click', () => {
  placeholder.style.display     = 'block';
  responseContent.style.display = 'none';
  thinking.style.display        = 'none';
  if (!isBusy && !meetingActive) setStatus('ready', 'Ready');
});

minBtn.addEventListener('click', () => ipcRenderer.invoke('window-minimize'));

function timestamp() {
  return new Date().toLocaleTimeString('fr-FR', {hour:'2-digit',minute:'2-digit',second:'2-digit'});
}
