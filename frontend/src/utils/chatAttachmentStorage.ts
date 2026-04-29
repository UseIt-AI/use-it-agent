/**
 * 聊天附件图片 — 离线优先：以 data URL 内联，便于写入本地 messages 元数据
 */

export interface UploadedAttachmentImage {
  name: string;
  mimeType: string;
  size: number;
  storagePath: string;
  url: string;
  expiresAt: number;
}

export interface AttachmentImageInput {
  name: string;
  base64: string;
  mimeType: string;
  size?: number;
}

function base64ToBlob(base64: string, fallbackMime: string): Blob {
  let mime = fallbackMime;
  let payload = base64;
  if (base64.startsWith('data:')) {
    const comma = base64.indexOf(',');
    if (comma !== -1) {
      const header = base64.slice(5, comma);
      const semi = header.indexOf(';');
      mime = semi !== -1 ? header.slice(0, semi) : header || fallbackMime;
      payload = base64.slice(comma + 1);
    }
  }

  const byteChars = atob(payload);
  const len = byteChars.length;
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i++) bytes[i] = byteChars.charCodeAt(i);
  return new Blob([bytes], { type: mime || 'application/octet-stream' });
}

function sanitizeFilename(name: string, fallback: string): string {
  const base = (name || '').trim() || fallback;
  return base
    .replace(/[^A-Za-z0-9._-]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 120) || fallback;
}

function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result as string);
    r.onerror = () => reject(new Error('readAsDataURL failed'));
    r.readAsDataURL(blob);
  });
}

export async function uploadChatAttachmentImage(
  input: AttachmentImageInput,
  userId: string,
  chatId: string,
  messageId: string,
  index: number,
): Promise<UploadedAttachmentImage> {
  if (!userId || !chatId || !messageId) {
    throw new Error('uploadChatAttachmentImage: userId, chatId, messageId are all required');
  }

  const blob = base64ToBlob(input.base64, input.mimeType || 'image/png');
  const safeName = sanitizeFilename(input.name, `image-${index}.png`);
  const storagePath = `inline:attachment:${userId}/${chatId}/${messageId}/${index}-${safeName}`;
  const dataUrl = await blobToDataUrl(blob);

  return {
    name: input.name,
    mimeType: input.mimeType || blob.type || 'image/png',
    size: typeof input.size === 'number' ? input.size : blob.size,
    storagePath,
    url: dataUrl,
    expiresAt: Date.now() + 86400 * 365 * 1000,
  };
}

export type AttachmentImageUploadResult =
  | { ok: true; image: UploadedAttachmentImage }
  | { ok: false; error: Error };

export async function uploadChatAttachmentImages(
  inputs: AttachmentImageInput[],
  userId: string,
  chatId: string,
  messageId: string,
): Promise<AttachmentImageUploadResult[]> {
  const settled = await Promise.allSettled(
    inputs.map((inp, i) => uploadChatAttachmentImage(inp, userId, chatId, messageId, i)),
  );
  return settled.map<AttachmentImageUploadResult>((r) =>
    r.status === 'fulfilled'
      ? { ok: true, image: r.value }
      : {
          ok: false,
          error:
            r.reason instanceof Error
              ? r.reason
              : new Error(String(r.reason ?? 'unknown upload error')),
        },
  );
}

export async function ensureFreshSignedUrl(
  storagePath: string,
  currentUrl: string | undefined,
  expiresAt: number | undefined,
  minTtlSeconds: number = 60 * 30,
): Promise<string> {
  if (storagePath.startsWith('inline:') || storagePath.startsWith('data:')) {
    return currentUrl || storagePath;
  }
  const needsRefresh =
    !currentUrl ||
    !expiresAt ||
    expiresAt - Date.now() < minTtlSeconds * 1000;
  if (!needsRefresh && currentUrl) return currentUrl;
  if (currentUrl) return currentUrl;
  throw new Error(`[chatAttachmentStorage] offline build cannot re-sign: ${storagePath}`);
}

export const CHAT_ATTACHMENTS_BUCKET_NAME = 'offline-inline';
