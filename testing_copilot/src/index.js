if (require('electron-squirrel-startup')) process.exit(0);

const { app, ipcMain, BrowserWindow } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const http = require('http');
const { createWindow } = require('./utils/window');

let mainWindow = null;
let pythonProcess = null;
const BACKEND_URL = 'http://127.0.0.1:7799';
const BACKEND_READY_TIMEOUT = 15000;

// ─── Python backend lifecycle ─────────────────────────────────────────────────

function startPythonBackend() {
    const backendScript = path.join(__dirname, '..', 'backend', 'agent.py');

    // Prefer the venv python from the sample project (already has strands installed)
    const venvPython = path.join(
        __dirname, '..', '..', 'sample-once-upon-agentic-ai', '.venv', 'Scripts', 'python.exe'
    );
    const pythonBin = require('fs').existsSync(venvPython) ? venvPython : 'python';

    console.log(`[Backend] Starting with: ${pythonBin}`);

    pythonProcess = spawn(pythonBin, [backendScript], {
        stdio: ['ignore', 'pipe', 'pipe'],
        cwd: path.join(__dirname, '..', 'backend'),
    });

    pythonProcess.stdout.on('data', d => process.stdout.write(`[Backend] ${d}`));
    pythonProcess.stderr.on('data', d => process.stderr.write(`[Backend] ${d}`));
    pythonProcess.on('exit', code => console.log(`[Backend] Exited with code ${code}`));
}

function waitForBackend(timeout = BACKEND_READY_TIMEOUT) {
    return new Promise((resolve, reject) => {
        const deadline = Date.now() + timeout;

        function ping() {
            http.get(`${BACKEND_URL}/health`, res => {
                if (res.statusCode === 200) return resolve();
                retry();
            }).on('error', retry);
        }

        function retry() {
            if (Date.now() > deadline) return reject(new Error('Backend did not start in time'));
            setTimeout(ping, 500);
        }

        ping();
    });
}

// ─── IPC: send prompt to Python agent ────────────────────────────────────────

ipcMain.handle('ask-copilot', async (event, prompt) => {
    return new Promise((resolve, reject) => {
        const body = JSON.stringify({ prompt });
        const options = {
            hostname: '127.0.0.1',
            port: 7799,
            path: '/ask',
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Content-Length': Buffer.byteLength(body),
            },
        };

        const req = http.request(options, res => {
            let data = '';
            res.on('data', chunk => { data += chunk; });
            res.on('end', () => {
                try {
                    const json = JSON.parse(data);
                    resolve(json);
                } catch {
                    resolve({ error: 'Invalid response from backend' });
                }
            });
        });

        req.on('error', err => resolve({ error: err.message }));
        req.setTimeout(60000, () => {
            req.destroy();
            resolve({ error: 'Request timed out (60s)' });
        });
        req.write(body);
        req.end();
    });
});

ipcMain.handle('check-backend', async () => {
    return new Promise(resolve => {
        http.get(`${BACKEND_URL}/health`, res => {
            resolve(res.statusCode === 200);
        }).on('error', () => resolve(false));
    });
});

// ─── App lifecycle ────────────────────────────────────────────────────────────

app.whenReady().then(async () => {
    startPythonBackend();

    mainWindow = createWindow();

    // Notify frontend when backend is ready
    try {
        await waitForBackend();
        console.log('[Backend] Ready');
        if (mainWindow && !mainWindow.isDestroyed()) {
            mainWindow.webContents.send('backend-ready');
        }
    } catch (err) {
        console.error('[Backend] Failed to start:', err.message);
        if (mainWindow && !mainWindow.isDestroyed()) {
            mainWindow.webContents.send('backend-error', err.message);
        }
    }
});

app.on('window-all-closed', () => {
    if (pythonProcess) pythonProcess.kill();
    if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', () => {
    if (pythonProcess) pythonProcess.kill();
});

app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
        mainWindow = createWindow();
    }
});
