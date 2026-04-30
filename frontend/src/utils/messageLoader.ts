/**
 * 消息加载 — 从本地离线存储读取历史消息
 */

import type {
  Message,
  ContentBlock,
  AttachedImage,
  AttachedFile,
} from '@/features/chat/handlers/types';
import { ensureFreshSignedUrl } from '@/utils/chatAttachmentStorage';
import {
  offlineListMessages,
  offlineGetMessage,
  offlineCountMessages,
} from '@/services/localOfflineStore';
import type { OfflineMessageRow } from '@/services/localOfflineStore';

export interface LoadMessagesOptions {
  chatId: string;
  limit?: number;
  offset?: number;
}

export async function loadChatMessages(options: LoadMessagesOptions): Promise<Message[]> {
  const { chatId, limit = 50, offset = 0 } = options;

  console.log(`[MessageLoader] 📖 Loading messages for chat ${chatId}`);

  try {
    const data = offlineListMessages(chatId, limit, offset);

    if (!data || data.length === 0) {
      console.log('[MessageLoader] ℹ️ No messages found');
      return [];
    }

    const messages: Message[] = data.map((dbMsg) => convertToFrontendMessage(dbMsg));
    await refreshExpiredAttachmentUrls(messages);

    console.log(`[MessageLoader] ✅ Loaded ${messages.length} messages`);
    return messages;
  } catch (error) {
    console.error('[MessageLoader] ❌ Error loading messages:', error);
    throw error;
  }
}

export async function loadMessage(messageId: string): Promise<Message | null> {
  try {
    const data = offlineGetMessage(messageId);
    if (!data) return null;
    return convertToFrontendMessage(data);
  } catch (error) {
    console.error('[MessageLoader] ❌ Error loading message:', error);
    return null;
  }
}

function convertToFrontendMessage(dbMsg: OfflineMessageRow): Message {
  const blocks: ContentBlock[] = [];
  const metadata = (dbMsg.metadata || {}) as Record<string, any>;

  if (metadata.blocks && Array.isArray(metadata.blocks)) {
    blocks.push(...metadata.blocks);
  } else if (dbMsg.content) {
    blocks.push({ type: 'text', content: dbMsg.content });
  }

  const screenshots = metadata.screenshot_urls || [];

  const attachedImages: AttachedImage[] | undefined = Array.isArray(metadata.attached_images)
    ? metadata.attached_images
        .map((img: any, idx: number): AttachedImage | null => {
          if (!img || typeof img !== 'object') return null;

          const storagePath = typeof img.storage_path === 'string'
            ? img.storage_path
            : (typeof img.storagePath === 'string' ? img.storagePath : undefined);
          const url = typeof img.url === 'string' && img.url ? img.url : undefined;
          const base64 = typeof img.base64 === 'string' && img.base64 ? img.base64 : undefined;
          const urlExpiresAt = typeof img.url_expires_at === 'number'
            ? img.url_expires_at
            : (typeof img.urlExpiresAt === 'number' ? img.urlExpiresAt : undefined);

          if (!storagePath && !url && !base64) return null;

          return {
            id: typeof img.id === 'string' && img.id ? img.id : `${dbMsg.id}-img-${idx}`,
            name: typeof img.name === 'string' ? img.name : `image-${idx}`,
            mimeType: typeof img.mime_type === 'string'
              ? img.mime_type
              : (typeof img.mimeType === 'string' ? img.mimeType : 'image/png'),
            size: typeof img.size === 'number' ? img.size : 0,
            storagePath,
            url,
            urlExpiresAt,
            base64,
          };
        })
        .filter((x: AttachedImage | null): x is AttachedImage => x !== null)
    : undefined;

  const attachedFiles: AttachedFile[] | undefined = Array.isArray(metadata.attached_files)
    ? metadata.attached_files
        .map((f: any, idx: number): AttachedFile | null => {
          if (!f || typeof f !== 'object') return null;
          const path = typeof f.path === 'string' ? f.path : '';
          const name = typeof f.name === 'string' ? f.name : '';
          if (!path && !name) return null;
          const t: 'file' | 'folder' = f.type === 'folder' ? 'folder' : 'file';
          return {
            id: typeof f.id === 'string' && f.id ? f.id : `${dbMsg.id}-file-${idx}`,
            path,
            name: name || path.split(/[\\/]/).pop() || `file-${idx}`,
            type: t,
          };
        })
        .filter((x: AttachedFile | null): x is AttachedFile => x !== null)
    : undefined;

  return {
    id: dbMsg.id,
    role: dbMsg.role as 'user' | 'assistant',
    timestamp: new Date(dbMsg.created_at).getTime(),
    blocks,
    screenshots,
    content: dbMsg.content || undefined,
    details: metadata,
    attachedImages: attachedImages && attachedImages.length > 0 ? attachedImages : undefined,
    attachedFiles: attachedFiles && attachedFiles.length > 0 ? attachedFiles : undefined,
  };
}

async function refreshExpiredAttachmentUrls(messages: Message[]): Promise<void> {
  const tasks: Promise<void>[] = [];
  for (const msg of messages) {
    if (!msg.attachedImages || msg.attachedImages.length === 0) continue;
    for (const img of msg.attachedImages) {
      if (!img.storagePath) continue;
      tasks.push(
        ensureFreshSignedUrl(img.storagePath, img.url, img.urlExpiresAt)
          .then((fresh) => {
            img.url = fresh;
          })
          .catch((err) => {
            console.warn('[MessageLoader] Failed to refresh signed URL for', img.storagePath, err);
          }),
      );
    }
  }
  if (tasks.length > 0) {
    await Promise.allSettled(tasks);
  }
}

export async function countChatMessages(chatId: string): Promise<number> {
  return offlineCountMessages(chatId);
}
