/**
 * NodeCard - Workflow Node Card Component
 * 可折叠的节点卡片
 * 
 * 布局：
 * - 第一行：Node Type 【折叠按钮在右侧】
 * - 第二行：description（折叠时隐藏）
 */

import React from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import type { Card } from '../handlers/types';

// ==================== Node Type Labels ====================

const getNodeTypeLabel = (nodeType: string | undefined): string => {
  if (!nodeType) return 'General';
  
  // 处理 computer-use 及其变体（如 computer-use-word, computer-use-excel 等）
  if (nodeType === 'cua' || nodeType.startsWith('computer-use')) {
    return 'Computer Use';
  }
  
  // 处理 tool-use 及其变体（如 tool-use-word, tool-use-excel 等）
  if (nodeType.startsWith('tool-use')) {
    return 'Tool Use';
  }
  
  switch (nodeType) {
    case 'rag':
      return 'RAG';
    case 'export':
      return 'Export';
    case 'general':
    default:
      return 'General';
  }
};

// ==================== Node Card Component ====================

export interface NodeCardProps {
  card: Card;
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
}

export const NodeCard: React.FC<NodeCardProps> = ({ 
  card, 
  isCollapsed = false,
  onToggleCollapse
}) => {
  const isRunning = card.status === 'running';
  const description = card.instruction || card.title;

  return (
    <div className="animate-fade-in-up">
      {/* 第一行：Node Type + 折叠按钮在右侧 */}
      <div 
        className="flex items-center justify-between cursor-pointer select-none hover:bg-gray-50 rounded py-1 pr-1 transition-colors"
        onClick={onToggleCollapse}
      >
        {/* Node Type */}
        <span className="text-[13px] font-medium text-gray-700">
          {getNodeTypeLabel(card.nodeType)}
        </span>

        {/* 折叠按钮 - 右侧 */}
        <div className="flex-shrink-0 w-4 h-4 flex items-center justify-center text-gray-400">
          {isCollapsed ? (
            <ChevronDown className="w-3.5 h-3.5" />
          ) : (
            <ChevronUp className="w-3.5 h-3.5" />
          )}
        </div>
      </div>

      {/* 第二行：Description（展开时显示） */}
      {!isCollapsed && description && (
        <div className="py-1 text-[13px] text-gray-500 animate-content-in">
          {description}
        </div>
      )}
    </div>
  );
};

export default NodeCard;
