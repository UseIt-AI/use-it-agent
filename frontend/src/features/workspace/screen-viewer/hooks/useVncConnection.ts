import { useCallback, useEffect, useRef, useState } from 'react';
import type { ScreenConfig } from '../types';
import { createRfbClient } from '../services/vncClient';

export interface UseVncConnectionOptions {
  config: Pick<ScreenConfig, 'password' | 'vncPort' | 'wsPort' | 'width' | 'height'>;
}

export function useVncConnection({ config }: UseVncConnectionOptions) {
  const [isConnected, setIsConnected] = useState(false);
  const vncContainerRef = useRef<HTMLDivElement | null>(null);
  const rfbRef = useRef<any | null>(null);

  const connect = useCallback(
    async (host: string) => {
      const container = vncContainerRef.current;
      if (!container) {
        throw new Error('VNC container not ready');
      }

      const rfb = await createRfbClient(container, host, config);

      return new Promise<void>((resolve, reject) => {
        let timeout: number | undefined;
        let resolved = false;

        const handleConnect = () => {
          resolved = true;
          setIsConnected(true);
          if (config.width && config.height) {
            try {
              rfb.requestDesktopSize(config.width, config.height);
            } catch {
              // ignore resize errors
            }
          }
          rfbRef.current = rfb;
          if (timeout) {
            window.clearTimeout(timeout);
          }
          resolve();
        };

        const handleDisconnect = () => {
          setIsConnected(false);
          rfbRef.current = null;
          // 如果还没连上就断开，尽快把错误抛出去（否则只能等超时，看起来像“卡住”）
          if (!resolved) {
            if (timeout) window.clearTimeout(timeout);
            reject(new Error('VNC disconnected before handshake (check host/port and VNC service)'));
          }
        };

        rfb.addEventListener('connect', handleConnect);
        rfb.addEventListener('disconnect', handleDisconnect);

        timeout = window.setTimeout(() => {
          try {
            rfb.disconnect();
          } catch {
            // ignore
          }
          reject(new Error('VNC connection timeout'));
        }, 10000);
      });
    },
    [config]
  );

  const disconnect = useCallback(() => {
    if (rfbRef.current) {
      try {
        rfbRef.current.disconnect();
      } catch {
        // ignore
      }
      rfbRef.current = null;
    }
    setIsConnected(false);
  }, []);

  const fitToWindow = useCallback(() => {
    if (!rfbRef.current || !vncContainerRef.current) return;
    const container = vncContainerRef.current;
    const width = Math.floor(container.clientWidth);
    const height = Math.floor(container.clientHeight);

    try {
      rfbRef.current.requestDesktopSize(width, height);
      // eslint-disable-next-line no-console
      console.log(`Requested desktop resize to: ${width}x${height}`);
    } catch (e) {
      // eslint-disable-next-line no-console
      console.warn('Desktop resize not supported:', e);
    }
  }, []);

  const setResolution = useCallback(() => {
    if (!rfbRef.current) return;
    try {
      rfbRef.current.requestDesktopSize(config.width, config.height);
      // eslint-disable-next-line no-console
      console.log(`Requested desktop resize to: ${config.width}x${config.height}`);
    } catch (e) {
      // eslint-disable-next-line no-console
      console.warn('Desktop resize not supported:', e);
    }
  }, [config.height, config.width]);

  // cleanup on unmount
  useEffect(() => {
    return () => {
      if (rfbRef.current) {
        try {
          rfbRef.current.disconnect();
        } catch {
          // ignore
        }
        rfbRef.current = null;
      }
    };
  }, []);

  // adjust canvas styling when connected
  useEffect(() => {
    if (isConnected && vncContainerRef.current) {
      const canvas = vncContainerRef.current.querySelector('canvas');
      if (canvas) {
        canvas.style.position = 'relative';
        canvas.style.display = 'block';
        canvas.style.margin = 'auto';
        canvas.style.imageRendering = 'auto';
        canvas.style.transform = 'translateZ(0)';
        canvas.style.backfaceVisibility = 'hidden';
      }
    }
  }, [isConnected]);

  return {
    isConnected,
    vncContainerRef,
    rfbRef,
    connect,
    disconnect,
    fitToWindow,
    setResolution,
  };
}


