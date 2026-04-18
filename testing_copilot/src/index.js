'use strict';
if (require('electron-squirrel-startup')) process.exit(0);

const { app, ipcMain, BrowserWindow, session } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const http = require('http');

app.commandLine.appendSwitch('enable-features', 'WebSpeechAPI,SpeechSynthesis');

const PROJECT_ROOT  = path.join(__dirname, '..', '..');
const VENV_SCRIPTS  = path.join(PROJECT_ROOT, '.venv', 'Scripts');
const BACKEND_SCRIPT = path.join(PROJECT_ROOT, 'testing_copilot', 'backend', 'agent.py');
const BACKEND_URL   = 'http://127.0.0.1:7799';

let mainWindow = null;
let pyProcess  = null;

function startBackend() {
    pyProcess = spawn('python', [BACKEND_SCRIPT], {
        cwd: PROJECT_ROOT,
        stdio: ['ignore', 'pipe', 'pipe'],
        env: { ...process.env, PATH: VENV_SCRIPTS + ';' + process.env.PATH },
    });
    pyProcess.stdout.on('data', d => process.stdout.write(`[py] ${d}`));
    pyProcess.stderr.on('data', d => process.stderr.write(`[py] ${d}`));
}

function waitForBackend(timeout = 25000) {
    return new Promise((resolve, reject) => {
        const deadline = Date.now() + timeout;
        const ping = () => {
            http.get(`${BACKEND_URL}/health`, r => {
                r.statusCode === 200 ? resolve() : retry();
            }).on('error', retry);
        };
        const retry = () => Date.now() > deadline ? reject() : setTimeout(ping, 700);
        ping();
    });
}

ipcMain.on('close-app',    () => { if (pyProcess) pyProcess.kill(); app.quit(); });
ipcMain.on('minimize-app', () => mainWindow && mainWindow.minimize());

app.whenReady().then(async () => {
    session.defaultSession.setPermissionRequestHandler((_, perm, cb) =>
        cb(['media', 'microphone', 'audioCapture'].includes(perm))
    );

    mainWindow = new BrowserWindow({
        width: 480,
        height: 700,
        frame: false,
        transparent: false,
        resizable: true,
        alwaysOnTop: true,
        backgroundColor: '#1a1a2e',
        webPreferences: { nodeIntegration: true, contextIsolation: false },
    });
    mainWindow.loadFile(path.join(__dirname, 'index.html'));

    startBackend();

    try {
        await waitForBackend();
        mainWindow.webContents.send('backend-ready');
    } catch {
        mainWindow.webContents.send('backend-error', 'Backend failed to start');
    }
});

app.on('window-all-closed', () => { if (pyProcess) pyProcess.kill(); app.quit(); });
