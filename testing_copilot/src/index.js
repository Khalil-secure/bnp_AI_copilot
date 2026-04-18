'use strict';
if (require('electron-squirrel-startup')) process.exit(0);

const { app, ipcMain, BrowserWindow } = require('electron');
const { spawn } = require('child_process');
const path = require('path');

const PROJECT_ROOT  = path.join(__dirname, '..', '..');
const VENV_PYTHON   = path.join(PROJECT_ROOT, '.venv', 'Scripts', 'python.exe');
const MAIN_PY       = path.join(PROJECT_ROOT, 'main.py');

let mainWindow = null;
let pyProcess  = null;

function startPython() {
    pyProcess = spawn(VENV_PYTHON, ['-u', MAIN_PY], {
        cwd: PROJECT_ROOT,
        stdio: ['pipe', 'pipe', 'pipe'],
    });

    // Auto-select mode 3 (Meeting Monitor)
    setTimeout(() => {
        if (pyProcess && pyProcess.stdin.writable)
            pyProcess.stdin.write('3\n');
    }, 500);

    pyProcess.stdout.on('data', d => {
        if (mainWindow && !mainWindow.isDestroyed())
            mainWindow.webContents.send('py-out', d.toString());
    });
    pyProcess.stderr.on('data', d => {
        if (mainWindow && !mainWindow.isDestroyed())
            mainWindow.webContents.send('py-err', d.toString());
    });
    pyProcess.on('exit', () => {
        if (mainWindow && !mainWindow.isDestroyed())
            mainWindow.webContents.send('py-out', '\n[Process exited]\n');
    });
}

ipcMain.on('py-in',      (_, text) => { if (pyProcess?.stdin.writable) pyProcess.stdin.write(text + '\n'); });
ipcMain.on('close-app',  ()        => { pyProcess?.kill(); app.quit(); });
ipcMain.on('minimize-app', ()      => mainWindow?.minimize());

app.whenReady().then(() => {
    mainWindow = new BrowserWindow({
        width: 620, height: 560,
        frame: false,
        transparent: false,
        resizable: true,
        alwaysOnTop: true,
        backgroundColor: '#0d0d14',
        webPreferences: { nodeIntegration: true, contextIsolation: false },
    });
    mainWindow.setContentProtection(true); // invisible to screen share / OBS
    mainWindow.loadFile(path.join(__dirname, 'index.html'));
    startPython();
});

app.on('window-all-closed', () => { pyProcess?.kill(); app.quit(); });
