import fs from 'node:fs';
import http from 'node:http';
import https from 'node:https';
import { URL } from 'node:url';

export type UploadProgress = {
  requestId: string;
  loaded: number;
  total: number;
  percent: number;
};

export async function uploadFileToPresignedPut(params: {
  requestId: string;
  filePath: string;
  uploadUrl: string;
  method?: string;
  headers?: Record<string, string>;
  onProgress?: (p: UploadProgress) => void;
}): Promise<{ etag?: string }> {
  const { requestId, filePath, uploadUrl, method = 'PUT', headers, onProgress } = params;
  const stat = fs.statSync(filePath);
  const total = stat.size;
  const url = new URL(uploadUrl);
  const client = url.protocol === 'https:' ? https : http;

  return await new Promise((resolve, reject) => {
    const req = client.request(
      {
        method,
        protocol: url.protocol,
        hostname: url.hostname,
        port: url.port ? Number(url.port) : undefined,
        path: url.pathname + url.search,
        headers: {
          ...(headers || {}),
          'Content-Length': String(total),
        },
      },
      (res) => {
        const ok = res.statusCode && res.statusCode >= 200 && res.statusCode < 300;
        const etagHeader = (res.headers as any)?.etag as string | undefined;
        const etag = etagHeader ? etagHeader.replace(/"/g, '') : undefined;

        // Drain response
        res.on('data', () => {});
        res.on('end', () => {
          if (!ok) {
            return reject(new Error(`Upload failed: HTTP ${res.statusCode}`));
          }
          resolve({ etag });
        });
      }
    );

    req.on('error', reject);

    const stream = fs.createReadStream(filePath);
    let loaded = 0;
    let lastEmit = 0;

    stream.on('data', (chunk) => {
      loaded += chunk.length;
      const now = Date.now();
      if (onProgress && (now - lastEmit > 200 || loaded === total)) {
        lastEmit = now;
        const percent = total > 0 ? Math.min(100, Math.round((loaded / total) * 100)) : 0;
        onProgress({ requestId, loaded, total, percent });
      }
    });

    stream.on('error', (e) => {
      try {
        req.destroy(e as any);
      } catch {}
      reject(e);
    });

    stream.pipe(req);
  });
}




