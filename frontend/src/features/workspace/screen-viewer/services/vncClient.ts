import type { ScreenConfig } from '../types';

// Lazy import creator for noVNC RFB client
export async function createRfbClient(
  container: HTMLDivElement,
  host: string,
  config: Pick<ScreenConfig, 'password' | 'vncPort' | 'wsPort'>
): Promise<any> {
  // @ts-ignore - noVNC types are not available
  const { default: RFB } = await import('@novnc/novnc/lib/rfb');

  const params = new URLSearchParams({
    host,
    port: String(config.vncPort || 5900),
  });
  const wsUrl = `ws://127.0.0.1:${config.wsPort}/?${params.toString()}`;
  // eslint-disable-next-line no-console
  console.log('[VNC] wsUrl:', wsUrl);

  const rfb = new (RFB as any)(container, wsUrl, {
    credentials: { password: config.password },
  });

  // Use a more stable rendering strategy for TightVNC in Electron:
  // avoid frequent viewport rescaling and keep compression low to reduce block artifacts.
  rfb.scaleViewport = false;
  rfb.clipViewport = false;
  rfb.resizeSession = false;
  rfb.qualityLevel = 9;
  rfb.compressionLevel = 1;

  return rfb;
}


