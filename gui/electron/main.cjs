const { app, BrowserWindow, shell, ipcMain, dialog, session } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const http = require('http');
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

let mainWindow = null;
let sidecarProcess = null;

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

const SIDECAR_URL = 'http://localhost:8000';

function sidecarPost(path, body) {
  return new Promise((resolve, reject) => {
    const data = JSON.stringify(body);
    const options = {
      hostname: 'localhost',
      port: 8000,
      path: path,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(data),
      },
    };
    const req = http.request(options, (res) => {
      let body = '';
      res.on('data', (chunk) => { body += chunk; });
      res.on('end', () => {
        try { resolve(JSON.parse(body)); }
        catch { resolve({ text: body }); }
      });
    });
    req.on('error', (err) => reject(err));
    req.write(data);
    req.end();
  });
}

// PTY now routed through MCP Gateway (governed)
// No local node-pty fallback — all commands go through sidecar governance
ipcMain.handle('pty:spawn', async (event, { shell, cols = 80, rows = 24, cwd }) => {
  try {
    const result = await sidecarPost('/api/mcp/gateway/tools/call', {
      name: 'maref_pty_exec',
      arguments: {
        command: `exec ${shell || process.env.SHELL || '/bin/zsh'} -l`,
        timeout: 1,
        cols,
        rows,
        cwd: cwd || process.env.HOME || '/',
      },
    });
    if (result.isError) {
      console.warn('[pty] gateway returned error:', result.content?.[0]?.text);
    }
    return { pid: 1, governed: true };
  } catch (e) {
    console.error('[pty] gateway unavailable:', e.message);
    throw new Error(`PTY spawn failed — sidecar governance unavailable: ${e.message}`);
  }
});

ipcMain.handle('pty:write', async (event, data) => {
  try {
    await sidecarPost('/api/mcp/gateway/tools/call', {
      name: 'maref_pty_exec',
      arguments: { command: data, timeout: 5 },
    });
  } catch (e) {
    console.warn('[pty] write failed:', e.message);
  }
});

ipcMain.handle('pty:resize', async (event, { cols, rows }) => {
  try {
    await sidecarPost('/api/mcp/gateway/tools/call', {
      name: 'maref_pty_exec',
      arguments: { command: `stty cols ${cols} rows ${rows}`, timeout: 1 },
    });
  } catch (e) {
    console.warn('[pty] resize failed:', e.message);
  }
});

ipcMain.handle('pty:kill', async () => {
  try {
    await sidecarPost('/api/mcp/gateway/tools/call', {
      name: 'maref_pty_exec',
      arguments: { command: 'exit', timeout: 1 },
    });
  } catch (e) {
    console.warn('[pty] kill failed:', e.message);
  }
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
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self' http://localhost:* ws://localhost:*; font-src 'self' data:;",
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
