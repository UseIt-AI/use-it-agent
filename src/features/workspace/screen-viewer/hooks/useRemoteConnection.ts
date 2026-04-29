import { useCallback, useState } from 'react';
import type { AutoConnectStep, ScreenConfig } from '../types';

export interface UseRemoteConnectionOptions {
  config: ScreenConfig;
  connect: (host: string) => Promise<void>;
}

export function useRemoteConnection({ config, connect }: UseRemoteConnectionOptions) {
  const [autoConnectStep, setAutoConnectStep] = useState<AutoConnectStep>('idle');
  const [errorMessage, setErrorMessage] = useState('');

  const handleManualConnect = useCallback(async () => {
    if (!config.host) return;

    setAutoConnectStep('connecting');
    setErrorMessage('');

    try {
      await connect(config.host);
      setAutoConnectStep('connected');
    } catch (e: any) {
      setErrorMessage(e.message || 'Connection failed');
      setAutoConnectStep('error');
    }
  }, [config.host, connect]);

  const resetRemoteState = useCallback(() => {
    setAutoConnectStep('idle');
    setErrorMessage('');
  }, []);

  return {
    autoConnectStep,
    errorMessage,
    handleManualConnect,
    resetRemoteState,
  };
}


