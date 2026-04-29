/**
 * ChatHistory 组件 - 显示聊天历史列表
 * 优化版：紧凑、简约、硬朗风格
 */

import React, { useEffect, useState } from 'react';
import { 
  Trash2, 
  X, 
  AlertCircle,
  MessageSquare
} from 'lucide-react';
import { useChatHistory, type ChatHistoryItem } from '../hooks/useChatHistory';
import { AlertDialog } from '@/components/AlertDialog';
import { LoadingSpinner } from './StatusIcons';

interface ChatHistoryProps {
  onSelectChat: (chatId: string, title?: string) => void;
  onClose: () => void;
  currentChatId?: string | null;
}

/**
 * 格式化时间 - 极简短格式
 */
function formatShortTime(dateString: string): string {
  if (!dateString) return '';
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  
  if (diffHours < 24) {
    // 24小时内显示 HH:MM
    return date.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit' });
  } else if (diffHours < 24 * 7) {
    // 7天内显示 "2d" (2天前)
    const days = Math.floor(diffHours / 24);
    return `${days}d`;
  } else {
    // 超过7天显示 MM/DD
    return date.toLocaleDateString('en-US', { month: 'numeric', day: 'numeric' });
  }
}

/**
 * 单个聊天历史项 - 紧凑行设计
 */
const ChatHistoryItemCard: React.FC<{
  item: ChatHistoryItem;
  isActive: boolean;
  onSelect: () => void;
  onDelete: () => void;
}> = ({ item, isActive, onSelect, onDelete }) => {
  const [isDeleting, setIsDeleting] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const handleDeleteClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    setShowDeleteConfirm(true);
  };

  const handleConfirmDelete = async () => {
    setShowDeleteConfirm(false);
    setIsDeleting(true);
    await onDelete();
    setIsDeleting(false);
  };

  const timeString = formatShortTime(item.lastMessageAt);

  return (
    <>
      <div
        className={`
          group flex items-center justify-between px-3 h-[28px] cursor-pointer
          text-xs select-none transition-colors relative
          ${isActive 
            ? 'bg-[#E5E5E5] text-black font-medium' 
            : 'text-black/70 hover:bg-[#F2F1EE] hover:text-black'
          }
        `}
        onClick={onSelect}
      >
        {/* 左侧：标题 */}
        <span className="truncate flex-1 mr-2">{item.title}</span>

        {/* 右侧：元信息 (时间和消息数) - Group Hover 时隐藏 */}
        <div className={`
          flex items-center gap-2 text-[10px] text-black/30 font-normal flex-shrink-0
          transition-opacity duration-100
          ${isActive ? 'text-black/50' : ''}
          group-hover:opacity-0
        `}>
          <span>{timeString}</span>
          {item.messageCount > 0 && (
            <span className="bg-black/5 px-1 rounded-sm min-w-[16px] text-center">
              {item.messageCount}
            </span>
          )}
        </div>

        {/* 删除按钮 - 绝对定位，Hover 显示，覆盖元信息区域 */}
        <div className="absolute right-2 top-0 bottom-0 flex items-center opacity-0 group-hover:opacity-100 transition-opacity duration-100">
          <button
            onClick={handleDeleteClick}
            disabled={isDeleting}
            className={`
              p-1 text-black/40 hover:text-red-600 hover:bg-black/5 rounded-sm transition-all
            `}
            title="删除"
          >
            {isDeleting ? (
              <LoadingSpinner size="sm" />
            ) : (
              <Trash2 className="w-3.5 h-3.5" />
            )}
          </button>
        </div>
      </div>

      <AlertDialog
        open={showDeleteConfirm}
        title="Delete Chat?"
        description="This action cannot be undone. The chat history will be permanently deleted."
        confirmLabel="Delete"
        cancelLabel="Cancel"
        onConfirm={handleConfirmDelete}
        onCancel={() => setShowDeleteConfirm(false)}
        isDestructive={true}
      />
    </>
  );
};

/**
 * ChatHistory 主组件
 */
export const ChatHistory: React.FC<ChatHistoryProps> = ({
  onSelectChat,
  onClose,
  currentChatId,
}) => {
  const {
    historyItems,
    isLoading,
    error,
    deleteChat,
    loadAllHistory,
  } = useChatHistory();

  // 首次加载
  useEffect(() => {
    loadAllHistory();
  }, [loadAllHistory]);

  return (
    <div className="flex flex-col h-full bg-canvas">
      {/* 极简顶栏 - 高度与全局顶栏一致 (32px) */}
      <div className="flex items-center justify-between px-3 h-[32px] bg-[#F2F1EE] border-b border-divider flex-shrink-0">
        <span className="text-xs font-medium text-black/60">Chat History</span>
        <button
          onClick={onClose}
          className="w-7 h-[28px] flex items-center justify-center rounded-md hover:bg-black/5 hover:text-red-500 text-black/40 transition-colors"
          title="关闭"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* 内容区域 - 紧凑列表 */}
      <div className="flex-1 min-h-0 overflow-y-auto scrollbar-thin-overlay py-1">
        {/* 加载状态 */}
        {isLoading && historyItems.length === 0 && (
          <div className="flex flex-col items-center justify-center py-8 text-black/40">
            <LoadingSpinner size="md" className="mb-2" />
            <span className="text-xs">加载中...</span>
          </div>
        )}

        {/* 错误状态 */}
        {error && (
          <div className="flex flex-col items-center justify-center py-8 text-red-500">
            <AlertCircle className="w-4 h-4 mb-2" />
            <span className="text-xs">{error}</span>
            <button
              onClick={() => loadAllHistory()}
              className="mt-2 text-xs underline hover:text-red-700"
            >
              重试
            </button>
          </div>
        )}

        {/* 空状态 */}
        {!isLoading && !error && historyItems.length === 0 && (
          <div className="flex flex-col items-center justify-center py-12 text-black/20">
            <MessageSquare className="w-6 h-6 mb-2 opacity-50" />
            <span className="text-xs">暂无历史记录</span>
          </div>
        )}

        {/* 历史列表 */}
        {historyItems.length > 0 && (
          <div className="flex flex-col">
            {historyItems.map((item) => (
              <ChatHistoryItemCard
                key={item.id}
                item={item}
                isActive={item.id === currentChatId}
                onSelect={() => onSelectChat(item.id, item.title)}
                onDelete={() => deleteChat(item.id)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default ChatHistory;
