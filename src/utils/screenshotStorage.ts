/**
 * 截图：离线优先，压缩后以 data URL 形式嵌入元数据（不经云端存储）
 */

import { compressScreenshot, getBlobSizeKB, calculateCompressionRatio } from './screenshotCompressor';
import { logScreenshot } from './logger';

const SCREENSHOT_QUALITY = parseFloat(import.meta.env.VITE_SCREENSHOT_QUALITY || '0.8');
const SCREENSHOT_MAX_WIDTH = parseInt(import.meta.env.VITE_SCREENSHOT_MAX_WIDTH || '1920', 10);
const SCREENSHOT_MAX_HEIGHT = parseInt(import.meta.env.VITE_SCREENSHOT_MAX_HEIGHT || '1080', 10);

export interface UploadResult {
  url: string;
  path: string;
  signedUrl?: string;
  expiresAt?: number;
  originalSize?: number;
  compressedSize?: number;
  compressionRatio?: number;
}

function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result as string);
    r.onerror = () => reject(new Error('readAsDataURL failed'));
    r.readAsDataURL(blob);
  });
}

export async function uploadScreenshot(
  base64Image: string,
  _userId: string,
  _chatId: string,
  _messageId: string,
  index: number,
): Promise<UploadResult> {
  logScreenshot('离线模式：内联截图 %d', index);
  const compressedBlob = await compressScreenshot(base64Image, {
    maxWidth: SCREENSHOT_MAX_WIDTH,
    maxHeight: SCREENSHOT_MAX_HEIGHT,
    quality: SCREENSHOT_QUALITY,
    format: 'jpeg',
  });
  const compressedSize = getBlobSizeKB(compressedBlob);
  const compressionRatio = calculateCompressionRatio(base64Image, compressedBlob);
  const dataUrl = await blobToDataUrl(compressedBlob);
  const path = `inline:screenshot:${Date.now()}-${index}`;
  const expiresAt = Date.now() + 86400 * 365 * 1000;
  return {
    url: dataUrl,
    path,
    signedUrl: dataUrl,
    expiresAt,
    compressedSize,
    compressionRatio,
  };
}

export async function uploadScreenshots(
  base64Images: string[],
  userId: string,
  chatId: string,
  messageId: string,
): Promise<UploadResult[]> {
  const results: UploadResult[] = [];
  for (let i = 0; i < base64Images.length; i++) {
    try {
      results.push(await uploadScreenshot(base64Images[i], userId, chatId, messageId, i));
    } catch (error) {
      console.error(`[Screenshot] ❌ Failed to process screenshot ${i}:`, error);
    }
  }
  return results;
}

export async function deleteMessageScreenshots(
  _userId: string,
  _chatId: string,
  _messageId: string,
): Promise<void> {
  // 无云端对象可删
}

export async function refreshSignedUrl(
  filePath: string,
  _expiresIn: number = 86400,
): Promise<string | null> {
  if (filePath.startsWith('inline:') || filePath.startsWith('data:')) {
    return filePath;
  }
  return null;
}

export async function checkStorageHealth(): Promise<boolean> {
  return true;
}
