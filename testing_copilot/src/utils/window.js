const { BrowserWindow, globalShortcut, ipcMain, screen } = require('electron');
const path = require('node:path');

let mouseEventsIgnored = false;

function createWindow() {
    const primaryDisplay = screen.getPrimaryDisplay();
    const { width: screenWidth } = primaryDisplay.workAreaSize;

    const winWidth = 860;
    const winHeight = 420;

    const mainWindow = new BrowserWindow({
        width: winWidth,
        height: winHeight,
        frame: false,
        transparent: true,
        hasShadow: false,
        alwaysOnTop: true,
        webPreferences: {
            nodeIntegration: true,
            contextIsolation: false,
            backgroundThrottling: false,
        },
        backgroundColor: '#00000000',
    });

    mainWindow.setResizable(false);
    mainWindow.setContentProtection(true);
    mainWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });

    if (process.platform === 'win32') {
        mainWindow.setSkipTaskbar(true);
        mainWindow.setAlwaysOnTop(true, 'screen-saver', 1);
    }

    // Center at top of screen
    const x = Math.floor((screenWidth - winWidth) / 2);
    mainWindow.setPosition(x, 0);

    mainWindow.loadFile(path.join(__dirname, '../index.html'));

    setupShortcuts(mainWindow);
    setupIpc(mainWindow);

    return mainWindow;
}

function setupShortcuts(win) {
    globalShortcut.unregisterAll();

    const isMac = process.platform === 'darwin';
    const mod = isMac ? 'Cmd' : 'Ctrl';

    const { width, height } = screen.getPrimaryDisplay().workAreaSize;
    const step = Math.floor(Math.min(width, height) * 0.1);

    const moves = {
        [`${mod}+Up`]:    () => { const [x, y] = win.getPosition(); win.setPosition(x, y - step); },
        [`${mod}+Down`]:  () => { const [x, y] = win.getPosition(); win.setPosition(x, y + step); },
        [`${mod}+Left`]:  () => { const [x, y] = win.getPosition(); win.setPosition(x - step, y); },
        [`${mod}+Right`]: () => { const [x, y] = win.getPosition(); win.setPosition(x + step, y); },
    };
    Object.entries(moves).forEach(([key, fn]) => {
        try { globalShortcut.register(key, fn); } catch (_) {}
    });

    // Toggle visibility
    try {
        globalShortcut.register(`${mod}+\\`, () => {
            win.isVisible() ? win.hide() : win.showInactive();
        });
    } catch (_) {}

    // Toggle click-through
    try {
        globalShortcut.register(`${mod}+M`, () => {
            mouseEventsIgnored = !mouseEventsIgnored;
            win.setIgnoreMouseEvents(mouseEventsIgnored, { forward: true });
            win.webContents.send('click-through-toggled', mouseEventsIgnored);
        });
    } catch (_) {}

    // Emergency erase
    try {
        globalShortcut.register(`${mod}+Shift+E`, () => {
            win.hide();
            win.webContents.send('clear-data');
            setTimeout(() => require('electron').app.quit(), 300);
        });
    } catch (_) {}
}

function setupIpc(win) {
    ipcMain.handle('window-minimize', () => {
        if (!win.isDestroyed()) win.minimize();
    });
}

module.exports = { createWindow };
