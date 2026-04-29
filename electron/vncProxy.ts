import { EventEmitter } from 'events';
import { Server as WebSocketServer, WebSocket, RawData } from 'ws';
import * as net from 'net';
import type { IncomingMessage } from 'http';

export interface VncProxyOptions {
  listenPort: number;
}

export class VncProxy extends EventEmitter {
  private wss: WebSocketServer | null = null;

  start(options: VncProxyOptions) {
    if (this.wss) {
      return;
    }

    const { listenPort } = options;

    this.wss = new WebSocketServer({
      port: listenPort,
      perMessageDeflate: false,
    });

    this.wss.on('connection', (ws: WebSocket, req: IncomingMessage) => {
      try {
        const url = new URL(req.url || '/', 'ws://localhost');
        const host = url.searchParams.get('host');
        const portParam = url.searchParams.get('port') || '5900';
        const vncPort = Number(portParam) || 5900;

        console.log(`[VNC proxy] Incoming -> host=${host}, port=${vncPort}`);

        if (!host) {
          this.emit('error', new Error('[VNC proxy] Missing host query param'));
          ws.close();
          return;
        }

        const tcpSocket = net.createConnection(
          { host, port: vncPort },
          () => {
            tcpSocket.setNoDelay(true);
            tcpSocket.setKeepAlive(true, 10_000);
            console.log(`[VNC proxy] TCP connected -> ${host}:${vncPort}`);
            this.emit('connection', { host, vncPort });
          },
        );

        ws.on('message', (message: RawData) => {
          if (tcpSocket.writable) {
            if (Buffer.isBuffer(message)) {
              tcpSocket.write(message);
            } else if (message instanceof ArrayBuffer) {
              tcpSocket.write(Buffer.from(message));
            } else if (Array.isArray(message)) {
              tcpSocket.write(Buffer.concat(message));
            }
          }
        });

        tcpSocket.on('data', (chunk) => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(chunk, { binary: true, compress: false });
          }
        });

        const cleanup = () => {
          try {
            tcpSocket.destroy();
          } catch {
            // ignore
          }
          try {
            if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
              ws.close();
            }
          } catch {
            // ignore
          }
        };

        ws.on('close', cleanup);
        ws.on('error', cleanup);
        tcpSocket.on('close', cleanup);
        tcpSocket.on('error', (err) => {
          console.error(`[VNC proxy] TCP error to ${host}:${vncPort} ->`, err.message);
          this.emit('error', new Error(`[VNC proxy] TCP error to ${host}:${vncPort} -> ${err.message}`));
          cleanup();
        });
      } catch (e) {
        this.emit('error', e);
        try {
          ws.close();
        } catch {
          // ignore
        }
      }
    });

    this.wss.on('listening', () => {
      this.emit('listening', { port: listenPort });
    });

    this.wss.on('error', (err: Error) => {
      console.error('[VNC proxy] WebSocket server error:', err.message);
      this.emit('error', err);
    });
  }

  stop() {
    if (!this.wss) return;
    this.wss.close();
    this.wss = null;
  }
}

export const vncProxy = new VncProxy();


