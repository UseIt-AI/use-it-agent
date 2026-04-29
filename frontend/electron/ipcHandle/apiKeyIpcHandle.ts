import { app, ipcMain } from 'electron';
import * as fs from 'fs';
import path from 'path';

interface ApiKeyEntry {
  apiKey: string;
  savedAt: string;
  isEnabled: boolean;
}

interface ApiConfigFile {
  providers: Record<string, ApiKeyEntry>;
}

const getApiConfigPath = () =>
  path.join(app.getPath('documents'), 'UseItAgent', 'apiConfig.json');

const loadApiConfigFile = (): ApiConfigFile => {
  try {
    const configPath = getApiConfigPath();
    if (fs.existsSync(configPath)) {
      return JSON.parse(fs.readFileSync(configPath, 'utf-8'));
    }
  } catch (e) {
    console.error('Failed to load apiConfig.json:', e);
  }
  return { providers: {} };
};

const saveApiConfigFile = (config: ApiConfigFile) => {
  const configPath = getApiConfigPath();
  const dir = path.dirname(configPath);
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
  fs.writeFileSync(configPath, JSON.stringify(config, null, 2));
};

class ApiKeyIpcHandle {
  init() {
    ipcMain.handle('save-api-key', async (_event, { provider, apiKey, isEnabled, exclusive }: { provider: string; apiKey: string; isEnabled: boolean; exclusive?: boolean }) => {
      try {
        const config = loadApiConfigFile();
        if (exclusive && isEnabled) {
          for (const key of Object.keys(config.providers)) {
            config.providers[key].isEnabled = false;
          }
        }
        config.providers[provider] = { apiKey, isEnabled, savedAt: new Date().toISOString() };
        saveApiConfigFile(config);
        return { success: true };
      } catch (error: any) {
        return { success: false, error: error.message };
      }
    });

    ipcMain.handle('update-provider-enabled', async (_event, { provider, isEnabled, exclusive }: { provider: string; isEnabled: boolean; exclusive?: boolean }) => {
      try {
        const config = loadApiConfigFile();
        if (exclusive && isEnabled) {
          for (const key of Object.keys(config.providers)) {
            config.providers[key].isEnabled = false;
          }
        }
        if (config.providers[provider]) {
          config.providers[provider].isEnabled = isEnabled;
        }
        saveApiConfigFile(config);
        return { success: true };
      } catch (error: any) {
        return { success: false, error: error.message };
      }
    });

    ipcMain.handle('load-api-keys', async () => {
      try {
        const config = loadApiConfigFile();
        return { success: true, providers: config.providers };
      } catch (error: any) {
        return { success: false, error: error.message };
      }
    });

    ipcMain.handle('delete-api-key', async (_event, { provider }: { provider: string }) => {
      try {
        const config = loadApiConfigFile();
        delete config.providers[provider];
        saveApiConfigFile(config);
        return { success: true };
      } catch (error: any) {
        return { success: false, error: error.message };
      }
    });
  }
}

export default new ApiKeyIpcHandle();
