import { MutableRefObject, useCallback, useState } from 'react';
import type { AutoConnectStep, ScreenConfig } from '../types';
import { DEFAULT_VM_NAME } from '../constants';
import { ensureVmVnc, getVmIp, getVmStatus, startVm, fixHyperVPermission, vmShareEnsure } from '../services/vmElectronApi';
import { classifyVmError } from '../services/vmErrorClassifier';

export interface UseLocalVmAutoConnectOptions {
  config: ScreenConfig;
  setConfig: React.Dispatch<React.SetStateAction<ScreenConfig>>;
  connect: (host: string) => Promise<void>;
  rfbRef: MutableRefObject<any | null>;
  onVmMissing?: () => void;
  /** projects 根目录路径（如果提供，VM 连接成功后会自动挂载为 Z: 盘） */
  projectsRootPath?: string;
}

const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

export function useLocalVmAutoConnect({
  config,
  setConfig,
  connect,
  rfbRef,
  onVmMissing,
  projectsRootPath,
}: UseLocalVmAutoConnectOptions) {
  const [autoConnectStep, setAutoConnectStep] = useState<AutoConnectStep>('idle');
  const [errorMessage, setErrorMessage] = useState('');
  const [needPermissionFix, setNeedPermissionFix] = useState(false);
  const [isOsLoginInProgress, setIsOsLoginInProgress] = useState(false);

  const handleAutoConnect = useCallback(async () => {
    try {
      setAutoConnectStep('checking');
      setErrorMessage('');
      setNeedPermissionFix(false);

      const vmName = config.vmName || DEFAULT_VM_NAME;
      let startedByUs = false;

      // step 1: status
      let vmState: string;
      try {
        vmState = await getVmStatus(vmName);
      } catch (e: unknown) {
        const classifiedError = classifyVmError(e, 'Failed to check VM status');
        if (classifiedError.isPermissionError) {
          setNeedPermissionFix(true);
        }
        throw new Error(classifiedError.userMessage);
      }

      // step 2: start VM if needed
      if (vmState !== 'Running') {
        setAutoConnectStep('starting');
        await startVm(vmName);
        await sleep(3000);
        startedByUs = true;
      }

      // step 3: wait for IP
      setAutoConnectStep('waiting_ip');
      let ip = '';
      for (let i = 0; i < 30; i++) {
        try {
          ip = await getVmIp(vmName);
          if (ip) break;
        } catch {
          // ignore
        }
        await sleep(2000);
      }

      if (!ip) {
        throw new Error('Failed to get VM IP address. Please check VM network settings.');
      }

      setConfig(prev => ({ ...prev, host: ip }));

      // step 4: connect VNC
      setAutoConnectStep('connecting');
      await ensureVmVnc({
        vmName,
        username: config.username || 'useit',
        password: config.password || '12345678',
      });
      await connect(ip);

      // 发送全局 VM 连接成功事件，通知 Control Panel 更新状态
      window.dispatchEvent(new CustomEvent('vm-connected', { detail: { vmName } }));

      // 后台挂载 projects 文件夹到 VM（不阻塞 UI）
      if (projectsRootPath) {
        vmShareEnsure({
          vmName,
          username: config.username || 'useit',
          password: config.password || '12345678',
          projectsRootPath,
        }).then(r => {
          if (r.success) {
            console.log(`[AutoConnect] Projects shared as ${r.driveLetter}: drive`);
          } else {
            console.warn('[AutoConnect] Failed to share projects:', r.error);
          }
        }).catch(e => console.warn('[AutoConnect] vmShareEnsure error:', e));
      }

      // 只有在本次操作中我们亲自启动了 VM，才尝试自动 OS 登录
      if (startedByUs && config.osPassword && rfbRef.current) {
        try {
          setIsOsLoginInProgress(true);

          // 等待一小段时间，确保系统进入登录界面
          await sleep(3000);

          const client = rfbRef.current;

          // 先发送一次 Ctrl+Alt+Del 以唤起登录界面（如果适用）
          if (typeof client.sendCtrlAltDel === 'function') {
            client.sendCtrlAltDel();
            await sleep(2000);
          }

          // 逐字符输入密码（使用简单的 keysym/code 映射）
          if (typeof client.sendKey === 'function') {
            for (const ch of config.osPassword) {
              const code = ch.charCodeAt(0);
              try {
                client.sendKey(code, code);
              } catch {
                // 忽略单个按键失败
              }
              await sleep(80);
            }

            // 回车确认（keysym 0xff0d, keycode 13）
            try {
              client.sendKey(0xff0d, 13);
            } catch {
              // ignore
            }
          }
        } catch {
          // 自动登录失败不影响整体连接
        } finally {
          setIsOsLoginInProgress(false);
        }
      }

      setAutoConnectStep('connected');
    } catch (e: unknown) {
      const classifiedError = classifyVmError(e, 'Connection failed');
      if (classifiedError.isPermissionError) {
        setNeedPermissionFix(true);
      }
      if (classifiedError.isVmNotFoundError) {
        onVmMissing?.();
      }
      setErrorMessage(classifiedError.userMessage);
      setAutoConnectStep('error');
      setIsOsLoginInProgress(false);
    }
  }, [config.vmName, config.osPassword, config.username, config.password, connect, setConfig, rfbRef, onVmMissing, projectsRootPath]);

  const handleFixPermission = useCallback(async () => {
    try {
      await fixHyperVPermission();
      setNeedPermissionFix(false);
      // eslint-disable-next-line no-alert
      alert('Permission fixed! Please sign out and sign back in to Windows.');
    } catch (e: any) {
      // eslint-disable-next-line no-alert
      alert('Failed to fix: ' + (e.message || 'Unknown error'));
    }
  }, []);

  const resetAutoConnectState = useCallback(() => {
    setAutoConnectStep('idle');
    setErrorMessage('');
    setNeedPermissionFix(false);
  }, []);

  return {
    autoConnectStep,
    errorMessage,
    needPermissionFix,
    isOsLoginInProgress,
    handleAutoConnect,
    handleFixPermission,
    resetAutoConnectState,
  };
}


