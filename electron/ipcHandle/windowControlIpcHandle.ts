import { BrowserWindow, ipcMain, screen } from 'electron';

class WindowControlIpcHandle {
  init() {
    ipcMain.on('window-minimize', (event) => {
      BrowserWindow.fromWebContents(event.sender)?.minimize();
    });

    ipcMain.on('window-toggle-maximize', (event) => {
      const win = BrowserWindow.fromWebContents(event.sender);
      if (!win) return;
      if (win.isFullScreen()) win.setFullScreen(false);
      if (win.isMaximized()) {
        win.unmaximize();
      } else {
        win.maximize();
      }
    });

    // 直接最大化窗口（用于进入 workspace 时自动全屏）
    ipcMain.on('window-maximize', (event) => {
      const win = BrowserWindow.fromWebContents(event.sender);
      if (!win) return;
      if (win.isFullScreen()) win.setFullScreen(false);
      if (!win.isMaximized()) win.maximize();
    });

    ipcMain.on('window-close', (event) => {
      BrowserWindow.fromWebContents(event.sender)?.close();
    });

    // 展开窗口到全屏工作区模式
    ipcMain.on('window-expand', (event) => {
      const win = BrowserWindow.fromWebContents(event.sender);
      if (!win) return;
      const { width, height } = screen.getPrimaryDisplay().workAreaSize;
      win.setAlwaysOnTop(false);
      win.setBounds({ x: 0, y: 0, width, height });
    });

    // 恢复窗口到启动时的默认尺寸并居中
    ipcMain.on('window-restore-size', (event) => {
      const win = BrowserWindow.fromWebContents(event.sender);
      if (!win) return;
      if (win.isFullScreen()) win.setFullScreen(false);
      if (win.isMaximized()) win.unmaximize();
      win.setAlwaysOnTop(false);
      const { width, height } = screen.getPrimaryDisplay().workAreaSize;
      const x = Math.round((width - 1340) / 2);
      const y = Math.round((height - 810) / 2);
      win.setBounds({ x, y, width: 1340, height: 810 }, true);
    });

    // 收缩窗口回侧边栏模式
    ipcMain.on('window-shrink', (event) => {
      const win = BrowserWindow.fromWebContents(event.sender);
      if (!win) return;
      const { width, height } = screen.getPrimaryDisplay().workAreaSize;
      const windowWidth = 400;
      if (win.isFullScreen()) win.setFullScreen(false);
      if (win.isMaximized()) win.unmaximize();
      win.setBounds({ x: width - windowWidth, y: 0, width: windowWidth, height });
      win.setAlwaysOnTop(true);
    });
  }
}

export default new WindowControlIpcHandle();
