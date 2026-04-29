import { ipcMain } from 'electron';
import type { RecorderService } from './recorder-service';

export function registerRecorderIpc(recorderService: RecorderService) {
  // Avoid duplicate handlers (e.g. if main reloaded in dev)
  ipcMain.removeHandler('recorder:refreshSources');
  ipcMain.removeHandler('recorder:start');
  ipcMain.removeHandler('recorder:initiateStop');
  ipcMain.removeHandler('recorder:getStopStatus');
  ipcMain.removeHandler('recorder:getStatus');

  ipcMain.handle('recorder:refreshSources', async () => {
    const sources = await recorderService.refreshSources();
    return { success: true, sources };
  });

  ipcMain.handle('recorder:start', async (_event, args?: { sourceId?: string; title?: string }) => {
    const ok = await recorderService.startRecording(args?.sourceId, args?.title);
    return { success: ok };
  });

  ipcMain.handle('recorder:initiateStop', async () => {
    const result = recorderService.initiateStopRecording();
    return { success: result.initiated, filePath: result.filePath };
  });

  ipcMain.handle('recorder:getStopStatus', async () => {
    const data = recorderService.getStopStatus();
    return { success: true, data };
  });

  ipcMain.handle('recorder:getStatus', async () => {
    const status = recorderService.getStatus();
    return { success: true, status };
  });
}




