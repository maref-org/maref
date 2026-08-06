const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('marefElectron', {
  pty: {
    spawn: (shell) => ipcRenderer.invoke('pty:spawn', { shell }),
    write: (data) => ipcRenderer.invoke('pty:write', data),
    resize: (cols, rows) => ipcRenderer.invoke('pty:resize', { cols, rows }),
    kill: () => ipcRenderer.invoke('pty:kill'),
    onData: (callback) => {
      ipcRenderer.on('pty:data', (event, data) => callback(data));
      return () => ipcRenderer.removeListener('pty:data', callback);
    },
  },
  dialog: {
    openDirectory: () => ipcRenderer.invoke('dialog:openDirectory'),
  },
  shell: {
    openExternal: (url) => ipcRenderer.invoke('shell:openExternal', url),
  },
});
