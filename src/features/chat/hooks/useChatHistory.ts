/**
 * useChatHistory — 从本地离线存储读取聊天列表
 */

import { useState, useCallback, useEffect } from 'react';
import { useProject } from '@/contexts/ProjectContext';
import {
  offlineListChatsByProject,
  offlineDeleteChat,
  offlineUpdateChatTitle,
  offlineCountMessages,
} from '@/services/localOfflineStore';

export function useChatHistory() {
  const { currentProject } = useProject();
  const [historyItems, setHistoryItems] = useState<ChatHistoryItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadHistory = useCallback(async (projectId?: string) => {
    const targetProjectId = projectId || currentProject?.id;

    if (!targetProjectId) {
      setHistoryItems([]);
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const chats = offlineListChatsByProject(targetProjectId);

      const items: ChatHistoryItem[] = await Promise.all(
        chats.map(async (chat) => {
          const messageCount = offlineCountMessages(chat.id);
          const lastMessageAt = chat.updated_at;
          return {
            id: chat.id,
            title: chat.title || 'Untitled Chat',
            projectId: chat.project_id,
            messageCount,
            lastMessageAt,
            lastMessagePreview: undefined,
            createdAt: chat.created_at,
            updatedAt: chat.updated_at,
          };
        }),
      );

      const nonEmptyItems = items.filter((item) => item.messageCount > 0);
      setHistoryItems(nonEmptyItems);
    } catch (err: any) {
      setError(err.message || 'Failed to load history');
      setHistoryItems([]);
    } finally {
      setIsLoading(false);
    }
  }, [currentProject?.id]);

  const loadAllHistory = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const pid = currentProject?.id;
      if (!pid) {
        setHistoryItems([]);
        return;
      }
      await loadHistory(pid);
    } catch (err: any) {
      setError(err.message || 'Failed to load history');
      setHistoryItems([]);
    } finally {
      setIsLoading(false);
    }
  }, [currentProject?.id, loadHistory]);

  const deleteChat = useCallback(async (chatId: string) => {
    try {
      offlineDeleteChat(chatId);
      setHistoryItems((prev) => prev.filter((item) => item.id !== chatId));
      return true;
    } catch (err: any) {
      setError(err.message || 'Failed to delete chat');
      return false;
    }
  }, []);

  const renameChat = useCallback(async (chatId: string, newTitle: string) => {
    try {
      offlineUpdateChatTitle(chatId, newTitle);
      setHistoryItems((prev) =>
        prev.map((item) => (item.id === chatId ? { ...item, title: newTitle } : item)),
      );
      return true;
    } catch (err: any) {
      setError(err.message || 'Failed to rename chat');
      return false;
    }
  }, []);

  useEffect(() => {
    if (currentProject?.id) {
      loadHistory();
    }
  }, [currentProject?.id, loadHistory]);

  return {
    historyItems,
    isLoading,
    error,
    loadHistory,
    loadAllHistory,
    deleteChat,
    renameChat,
    refresh: loadHistory,
  };
}

export interface ChatHistoryItem {
  id: string;
  title: string;
  projectId: string;
  projectName?: string;
  messageCount: number;
  lastMessageAt: string;
  lastMessagePreview?: string;
  createdAt: string;
  updatedAt: string;
}
