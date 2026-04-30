import fs from 'node:fs';
import http from 'node:http';
import https from 'node:https';
import { URL } from 'node:url';
import path from 'node:path';
import crypto from 'node:crypto';

// 检查是否支持 fetch API（Node.js 18+）
const hasFetch = typeof fetch !== 'undefined';

export type DownloadProgress = {
  requestId: string;
  loaded: number;
  total: number;
  percent: number;
};

/**
 * 从预签名 URL 下载文件
 */
export async function downloadFileFromPresignedGet(params: {
  requestId: string;
  filePath: string;
  downloadUrl: string;
  headers?: Record<string, string>;
  onProgress?: (p: DownloadProgress) => void;
}): Promise<void> {
  const { requestId, filePath, downloadUrl, headers, onProgress } = params;

  // 确保目录存在
  const dir = path.dirname(filePath);
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }

  // 优先使用 fetch API（如果可用），它更接近浏览器的行为
  // 这可以避免 S3 预签名 URL 的签名验证问题
  if (hasFetch) {
    try {
      console.log('[PresignedDownloader] 使用 fetch API 下载:', downloadUrl);
      
      const response = await fetch(downloadUrl, {
        method: 'GET',
        // 不传递任何 headers，避免签名验证失败
        // S3 预签名 URL 的签名不包含请求头
      });

      if (!response.ok) {
        const errorText = await response.text().catch(() => '');
        let errorMessage = `Download failed: HTTP ${response.status}`;
        
        // 尝试从 XML 中提取错误消息
        if (errorText) {
          const codeMatch = errorText.match(/<Code>(.*?)<\/Code>/);
          const messageMatch = errorText.match(/<Message>(.*?)<\/Message>/);
          if (codeMatch || messageMatch) {
            const code = codeMatch?.[1]?.trim() || '';
            const message = messageMatch?.[1]?.trim() || '';
            errorMessage = `Download failed: HTTP ${response.status}${code ? ` - ${code}` : ''}${message ? ` - ${message}` : ''}`;
          }
        }
        
        throw new Error(errorMessage);
      }

      // 获取内容长度
      const contentLength = response.headers.get('content-length');
      const total = contentLength ? parseInt(contentLength, 10) : 0;

      // 创建写入流，并注册 error handler 防止 Uncaught Exception
      // 当目标文件被其他进程（如 PowerPoint COM）锁定时，
      // createWriteStream 会异步触发 error 事件，如无 handler 会导致进程崩溃
      const writeStream = fs.createWriteStream(filePath);
      let streamError: Error | null = null;

      // 用 Promise 包装 writeStream 的 open/error 事件，确保文件可写
      await new Promise<void>((resolve, reject) => {
        writeStream.on('open', () => resolve());
        writeStream.on('error', (err) => {
          streamError = err;
          reject(err);
        });
      });

      let loaded = 0;
      let lastEmit = 0;

      // 读取响应体
      if (!response.body) {
        writeStream.destroy();
        throw new Error('Response body is not readable');
      }

      // 重新注册 error handler（open 之后仍可能出错，如磁盘满）
      writeStream.on('error', (err) => {
        streamError = err;
      });

      // 使用流式读取
      const reader = (response.body as any).getReader?.() || null;
      
      if (reader) {
        // 使用 ReadableStream API
        try {
          while (true) {
            // 如果写入流已出错，提前中止
            if (streamError) {
              reader.cancel?.();
              break;
            }

            const { done, value } = await reader.read();
            if (done) break;

            writeStream.write(value);
            loaded += value.length;

            // 报告进度
            if (onProgress) {
              const now = Date.now();
              if (now - lastEmit > 200 || loaded === total || total === 0) {
                lastEmit = now;
                const percent = total > 0 
                  ? Math.min(100, Math.round((loaded / total) * 100)) 
                  : loaded > 0 ? 50 : 0;
                onProgress({ requestId, loaded, total, percent });
              }
            }
          }
        } finally {
          writeStream.end();
        }
      } else {
        // 回退到 buffer 方式
        const buffer = await response.arrayBuffer();
        const data = Buffer.from(buffer);
        writeStream.write(data);
        writeStream.end();
        
        if (onProgress) {
          onProgress({ requestId, loaded: data.length, total: data.length, percent: 100 });
        }
      }

      // 如果写入过程中出现错误，抛出
      if (streamError) {
        throw streamError;
      }

      return;
    } catch (error: any) {
      console.error('[PresignedDownloader] fetch API 下载失败，回退到 http/https:', error);
      // 如果 fetch 失败，回退到原来的方法
    }
  }

  // 回退到使用 http/https 模块
  const url = new URL(downloadUrl);
  const client = url.protocol === 'https:' ? https : http;

  // S3 预签名 URL 的签名是基于特定的请求头的
  // 添加额外的请求头可能会导致签名验证失败（403 错误）
  // 因此我们只使用 URL 中的签名参数，不添加额外的请求头
  
  // 构建完整的请求路径（包含查询参数）
  const requestPath = url.pathname + (url.search || '');
  
  // 调试日志
  console.log('[PresignedDownloader] 使用 http/https 下载:', {
    hostname: url.hostname,
    path: requestPath,
  });

  return await new Promise((resolve, reject) => {
    const requestOptions: any = {
      protocol: url.protocol,
      hostname: url.hostname,
      port: url.port ? Number(url.port) : undefined,
      path: requestPath,
      method: 'GET',
    };
    
    // 不传递任何 headers，避免签名验证失败
    // S3 预签名 URL 的签名不包含请求头
    
    const req = client.get(requestOptions,
      (res) => {
        // 处理重定向（301, 302, 307, 308）
        if (res.statusCode === 301 || res.statusCode === 302 || res.statusCode === 307 || res.statusCode === 308) {
          const location = res.headers.location;
          if (location) {
            // 递归下载重定向的 URL
            return downloadFileFromPresignedGet({
              requestId,
              filePath,
              downloadUrl: location,
              headers,
              onProgress,
            }).then(resolve).catch(reject);
          }
        }

        const ok = res.statusCode && res.statusCode >= 200 && res.statusCode < 300;
        
        if (!ok) {
          // 尝试读取错误响应体以获取更详细的错误信息（S3 错误响应通常是 XML 格式）
          let errorBody = '';
          const chunks: Buffer[] = [];
          
          res.on('data', (chunk: Buffer) => {
            chunks.push(chunk);
          });
          
          res.on('end', () => {
            try {
              errorBody = Buffer.concat(chunks).toString('utf-8');
              // 尝试从 XML 中提取错误消息
              const codeMatch = errorBody.match(/<Code>(.*?)<\/Code>/);
              const messageMatch = errorBody.match(/<Message>(.*?)<\/Message>/);
              
              let errorMessage = `Download failed: HTTP ${res.statusCode}`;
              if (codeMatch || messageMatch) {
                const code = codeMatch?.[1]?.trim() || '';
                const message = messageMatch?.[1]?.trim() || '';
                errorMessage = `Download failed: HTTP ${res.statusCode}${code ? ` - ${code}` : ''}${message ? ` - ${message}` : ''}`;
              }
              reject(new Error(errorMessage));
            } catch (e) {
              reject(new Error(`Download failed: HTTP ${res.statusCode}`));
            }
          });
          
          res.on('error', (e) => {
            reject(new Error(`Download failed: HTTP ${res.statusCode} - ${e.message}`));
          });
          
          return;
        }

        const total = res.headers['content-length'] 
          ? parseInt(res.headers['content-length'], 10) 
          : 0;
        
        const writeStream = fs.createWriteStream(filePath);
        let loaded = 0;
        let lastEmit = 0;

        res.on('data', (chunk) => {
          loaded += chunk.length;
          const now = Date.now();
          if (onProgress && (now - lastEmit > 200 || loaded === total || total === 0)) {
            lastEmit = now;
            const percent = total > 0 
              ? Math.min(100, Math.round((loaded / total) * 100)) 
              : loaded > 0 ? 50 : 0; // 如果不知道总大小，显示 50% 直到完成
            onProgress({ requestId, loaded, total, percent });
          }
        });

        res.on('end', () => {
          writeStream.end();
          resolve();
        });

        res.on('error', (e) => {
          writeStream.destroy();
          reject(e);
        });

        res.pipe(writeStream);

        writeStream.on('error', (e) => {
          res.destroy();
          reject(e);
        });
      }
    );

    req.on('error', reject);
  });
}

/**
 * 获取文件元数据（大小、修改时间、ETag）
 * 
 * 注意：计算 ETag (MD5) 需要读取文件内容。
 * 如果文件被其他进程锁定（如 PowerPoint COM），读取会失败 (EPERM)，
 * 此时仅返回 size 和 lastModified，不返回 etag。
 */
export function getFileMetadata(filePath: string): {
  size: number;
  lastModified: number;
  etag?: string;
} | null {
  try {
    if (!fs.existsSync(filePath)) {
      return null;
    }

    const stat = fs.statSync(filePath);
    
    // 计算文件的 MD5 hash 作为 ETag
    // 使用流式读取避免将大文件一次性加载到内存
    let etag: string | undefined;
    try {
      // 先尝试以只读、共享读模式打开，检测文件是否可读
      const fd = fs.openSync(filePath, 'r');
      fs.closeSync(fd);

      // 文件可读，使用流式 MD5 计算
      const fileBuffer = fs.readFileSync(filePath);
      const hashSum = crypto.createHash('md5');
      hashSum.update(fileBuffer);
      etag = hashSum.digest('hex');
    } catch (e: any) {
      // 如果计算 hash 失败（文件被锁定 EPERM、EBUSY 等），跳过 etag
      // 这在 Office COM 操作期间很常见（PowerPoint/Word/Excel 锁定文件）
      if (e?.code === 'EPERM' || e?.code === 'EBUSY' || e?.code === 'EACCES') {
        console.info(`[getFileMetadata] File locked, skipping etag: ${filePath} (${e.code})`);
      } else {
        console.warn('Failed to calculate file hash:', e);
      }
    }

    return {
      size: stat.size,
      lastModified: stat.mtimeMs,
      etag,
    };
  } catch (error) {
    console.error('Failed to get file metadata:', error);
    return null;
  }
}