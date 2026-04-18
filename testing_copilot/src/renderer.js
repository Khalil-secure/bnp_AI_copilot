'use strict';
const { ipcRenderer } = require('electron');

const output = document.getElementById('output');
const input  = document.getElementById('input');

document.getElementById('close-btn').addEventListener('click', () => ipcRenderer.send('close-app'));
document.getElementById('min-btn').addEventListener('click',   () => ipcRenderer.send('minimize-app'));

ipcRenderer.on('py-out', (_, text) => append(text, 'out'));
ipcRenderer.on('py-err', (_, text) => append(text, 'err'));

function append(text, cls) {
    const span = document.createElement('span');
    span.className = cls;
    span.textContent = text;
    output.appendChild(span);
    output.scrollTop = output.scrollHeight;
}

function send() {
    const text = input.value;
    if (!text.trim()) return;
    append('› ' + text + '\n', 'in');
    ipcRenderer.send('py-in', text);
    input.value = '';
}

document.getElementById('send-btn').addEventListener('click', send);
input.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); send(); } });

input.focus();
