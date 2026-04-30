import { app, ipcMain } from "electron";
import * as fs from 'fs';
import path from "path";

//TOTO: Respone Data 可优化为 {code, data, message}

class AppConfig {
  init() {
    // 获取应用配置
    ipcMain.handle('get-app-config', async (_event, key?: string) => {
      const config = loadConfig();
      if (key) {
        return { success: true, value: config[key] };
      }
      return { success: true, config };
    });

    // 保存应用配置
    ipcMain.handle('set-app-config', async (_event, newConfig: any) => {
      saveConfig(newConfig);
      return { success: true };
    });

    // 获取系统路径
    ipcMain.handle('get-path', async (_event, name: string) => {
      try {
        return { success: true, path: app.getPath(name as any) };
      } catch (error: any) {
        return { success: false, error: error.message };
      }
    });
  }
}

// 配置文件路径
const getConfigPath = () => path.join(app.getPath('userData'), 'app-config.json');

// 保存配置
export const saveConfig = (newConfig: any) => {
  try {
    const configPath = getConfigPath();
    const currentConfig = loadConfig();
    fs.writeFileSync(configPath, JSON.stringify({ ...currentConfig, ...newConfig }, null, 2));
  } catch (e) {
    console.error('Failed to save config:', e);
  }
};

// 读取配置
export const loadConfig = () => {
  try {
    const configPath = getConfigPath();
    if (fs.existsSync(configPath)) {
      const data = fs.readFileSync(configPath, 'utf-8');
      return JSON.parse(data);
    }
  } catch (e) {
    console.error('Failed to load config:', e);
  }
  return {};
};

export default new AppConfig();