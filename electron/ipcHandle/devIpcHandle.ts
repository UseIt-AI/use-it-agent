import { BrowserWindow, ipcMain } from "electron";

class DevIpcHandle {

  init() {
    ipcMain.on('toggle-dev-tools', (event) => {
        const win = BrowserWindow.fromWebContents(event.sender);
        if (!win) return;
        if (win.webContents.isDevToolsOpened()) {
            win.webContents.closeDevTools();
        } else {
            win.webContents.openDevTools({ mode: 'detach' });
        }
    });
  }
}

export default new DevIpcHandle();