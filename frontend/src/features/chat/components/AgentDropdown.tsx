/**
 * AgentDropdown - 通用 Agent 选择下拉菜单
 * 
 * 功能：
 * - 搜索过滤
 * - 可滚动列表（最大高度限制）
 * - 选中状态显示
 */

import React, { useState, useRef, useEffect } from 'react';
import { Check, Search, X } from 'lucide-react';
import type { AgentId } from '../hooks/useChat';

interface Agent {
  id: string;
  label: string;
}

interface AgentDropdownProps {
  /** Agent 列表 */
  agents: Agent[];
  /** 是否正在加载 */
  loading: boolean;
  /** 当前选中的 Agent ID */
  selectedAgentId: AgentId;
  /** 选择 Agent 回调 */
  onSelect: (agentId: AgentId) => void;
  /** 关闭下拉菜单回调 */
  onClose: () => void;
  /** 定位方式：'bottom' 向下展开, 'top' 向上展开 */
  position?: 'bottom' | 'top';
  /** 宽度 */
  width?: number;
  /** 是否居中对齐 */
  centered?: boolean;
  /** 移动端样式 */
  isMobile?: boolean;
}

export const AgentDropdown: React.FC<AgentDropdownProps> = ({
  agents,
  loading,
  selectedAgentId,
  onSelect,
  onClose,
  position = 'top',
  width = 220,
  centered = false,
  isMobile = false,
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const searchInputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // 过滤 agents
  const filteredAgents = agents.filter(agent =>
    agent.label.toLowerCase().includes(searchQuery.toLowerCase())
  );

  // 自动聚焦搜索框
  useEffect(() => {
    // 延迟聚焦以确保组件已渲染
    const timer = setTimeout(() => {
      searchInputRef.current?.focus();
    }, 50);
    return () => clearTimeout(timer);
  }, []);

  // 滚动到选中项
  useEffect(() => {
    if (listRef.current && selectedAgentId) {
      const selectedElement = listRef.current.querySelector(`[data-agent-id="${selectedAgentId}"]`);
      if (selectedElement) {
        selectedElement.scrollIntoView({ block: 'nearest' });
      }
    }
  }, [selectedAgentId]);

  const handleSelect = (agentId: string) => {
    onSelect(agentId as AgentId);
    setSearchQuery('');
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      onClose();
    }
  };

  // 位置样式
  const positionStyles = position === 'top'
    ? 'bottom-full mb-2'
    : 'top-full mt-2';

  const alignStyles = centered
    ? 'left-1/2 -translate-x-1/2'
    : 'left-0';

  // 列表项样式
  const itemPadding = isMobile ? 'px-3 py-2' : 'px-3 py-1.5';
  const itemTextSize = isMobile ? 'text-sm' : 'text-app-sm';

  return (
    <>
      {/* 遮罩 */}
      <div 
        className="fixed inset-0 z-40" 
        onClick={onClose}
      />
      
      {/* 下拉菜单 */}
      <div 
        className={`
          absolute ${positionStyles} ${alignStyles}
          bg-white
          border border-black/10
          shadow-xl
          rounded-sm
          z-50
          flex flex-col
          overflow-hidden
        `}
        style={{ width: `${width}px` }}
        onKeyDown={handleKeyDown}
      >
        {/* 搜索框 */}
        <div className="flex items-center gap-2 px-2.5 py-1.5 border-b border-black/5">
          <Search className="w-3.5 h-3.5 text-black/30 flex-shrink-0" />
          <input
            ref={searchInputRef}
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search workflows..."
            className="
              flex-1 min-w-0
              bg-transparent
              border-none outline-none
              text-xs text-black/80
              placeholder:text-black/30
            "
          />
          {searchQuery && (
            <button
              type="button"
              onClick={() => setSearchQuery('')}
              className="p-0.5 hover:bg-black/5 rounded transition-colors"
            >
              <X className="w-3 h-3 text-black/40" />
            </button>
          )}
        </div>

        {/* Agent 列表 - 可滚动 */}
        <div 
          ref={listRef}
          className="overflow-y-auto max-h-[240px] scrollbar-thin scrollbar-thumb-black/10 scrollbar-track-transparent"
        >
          {loading ? (
            <div className={`${itemPadding} text-xs text-black/40 text-center`}>
              Loading workflows...
            </div>
          ) : filteredAgents.length === 0 ? (
            <div className={`${itemPadding} text-xs text-black/40 text-center`}>
              {searchQuery ? 'No matching workflows' : 'No workflows available'}
            </div>
          ) : (
            filteredAgents.map((agent) => (
              <button
                key={agent.id}
                type="button"
                data-agent-id={agent.id}
                onClick={() => handleSelect(agent.id)}
                className={`
                  w-full flex items-center gap-2
                  ${itemPadding}
                  text-left ${itemTextSize} font-medium
                  transition-colors
                  ${isMobile ? 'active:bg-black/5' : 'hover:bg-gray-50'}
                  ${selectedAgentId === agent.id ? 'bg-orange-50 text-orange-900' : 'text-black/80'}
                `}
              >
                <span className="flex-1 truncate">{agent.label}</span>
                {selectedAgentId === agent.id && (
                  <Check className={`${isMobile ? 'w-4 h-4' : 'w-3 h-3'} text-orange-600 flex-shrink-0`} />
                )}
              </button>
            ))
          )}
        </div>

      </div>
    </>
  );
};

export default AgentDropdown;
