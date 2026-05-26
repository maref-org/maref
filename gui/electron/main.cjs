const { app, BrowserWindow, shell, ipcMain, dialog, session } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const { autoUpdater } = require('electron-updater');
const windowStateKeeper = require('electron-window-state');

const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });
}

app.commandLine.appendSwitch('disable-gpu-sandbox');
app.commandLine.appendSwitch('no-sandbox');

let mainWindow = null;
let sidecarProcess = null;
let ptyProcess = null;

function createWindow() {
  const mainWindowState = windowStateKeeper({
    defaultWidth: 1400,
    defaultHeight: 900,
  });

  mainWindow = new BrowserWindow({
    x: mainWindowState.x,
    y: mainWindowState.y,
    width: mainWindowState.width,
    height: mainWindowState.height,
    minWidth: 900,
    minHeight: 600,
    title: 'MAREF Agent',
    titleBarStyle: 'hiddenInset',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.cjs'),
    },
  });

  mainWindowState.manage(mainWindow);

  const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged;
  if (isDev) {
    mainWindow.loadURL('http://localhost:5173');
    mainWindow.webContents.openDevTools({ mode: 'detach' });
  } else {
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'));
  }

  startSidecar();

  mainWindow.on('closed', () => {
    mainWindow = null;
    stopSidecar();
  });
}

function startSidecar() {
  try {
    sidecarProcess = spawn('maref', ['serve', '--port', '8000', '--gui'], {
      stdio: 'pipe',
      env: { ...process.env },
    });
    sidecarProcess.stdout?.on('data', (data) => console.log('[sidecar]', data.toString()));
    sidecarProcess.stderr?.on('data', (data) => console.error('[sidecar]', data.toString()));
    sidecarProcess.on('error', (err) => console.error('[sidecar] failed to start:', err.message));
  } catch (e) {
    console.error('[sidecar] spawn failed:', e.message);
  }
}

function stopSidecar() {
  if (sidecarProcess) { sidecarProcess.kill(); sidecarProcess = null; }
}

ipcMain.handle('pty:spawn', async (event, { shell }) => {
  const osShell = shell || process.env.SHELL || '/bin/zsh';
  const pty = require('node-pty');
  ptyProcess = pty.spawn(osShell, [], {
    name: 'xterm-256color',
    cols: 80, rows: 24,
    cwd: process.env.HOME || '/',
    env: process.env,
  });
  ptyProcess.onData((data) => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('pty:data', data);
    }
  });
  return { pid: ptyProcess.pid };
});

ipcMain.handle('pty:write', (event, data) => {
  if (ptyProcess) { ptyProcess.write(data); }
});

ipcMain.handle('pty:resize', (event, { cols, rows }) => {
  if (ptyProcess) { ptyProcess.resize(cols, rows); }
});

ipcMain.handle('pty:kill', () => {
  if (ptyProcess) { ptyProcess.kill(); ptyProcess = null; }
});

ipcMain.handle('dialog:openDirectory', async () => {
  const result = await dialog.showOpenDialog(mainWindow, { properties: ['openDirectory'] });
  return result.canceled ? null : result.filePaths[0];
});

ipcMain.handle('shell:openExternal', async (event, url) => {
  await shell.openExternal(url);
});

app.whenReady().then(() => {
  if (app.isPackaged) {
    session.defaultSession.webRequest.onHeadersReceived((details, callback) => {
      callback({
        responseHeaders: {
          ...details.responseHeaders,
          'Content-Security-Policy': [
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' http://localhost:*;",
          ],
        },
      });
    });
  }

  createWindow();
  if (app.isPackaged) {
    autoUpdater.checkForUpdatesAndNotify();
    autoUpdater.on('update-available', (info) => {
      dialog.showMessageBox({
        type: 'info',
        title: 'Update Available',
        message: `Version ${info.version} is available and will be installed on quit.`,
      });
    });
    autoUpdater.on('error', (err) => console.error('[auto-updater]', err.message));
  }
});
app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit(); });
app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
app.on('before-quit', () => { stopSidecar(); });
