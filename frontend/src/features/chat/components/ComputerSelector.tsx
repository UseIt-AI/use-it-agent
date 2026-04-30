/**
 * 电脑选择器组件
 * 在对话框中选择目标电脑（从 Agent Environment 获取）
 * 简洁样式：只显示文字 + 状态点
 */

import React, { useState, useEffect } from 'react';
import { ChevronDown, Check, Settings } from 'lucide-react';
import { useComputerPool } from '../../../hooks/useComputerPool';
import type { ComputerWithStatus, ComputerStatus } from '../../../types/computer';

interface ComputerSelectorProps {
  value: string;
  onChange: (computerName: string) => void;
  chatId?: string;
  disabled?: boolean;
  onConflict?: (computerName: string, occupiedBy: string) => void;
}

// 状态点组件
// online: 绿色 - 服务已就绪
// offline: 橙色 - 可选择，会自动连接
// busy: 红色 - 被占用，不可选择
const StatusDot: React.FC<{ status: ComputerStatus }> = ({ status }) => {
  const colors = {
    online: 'bg-green-500',
    offline: 'bg-orange-400',
    busy: 'bg-red-500',
  };
  return <span className={`w-1.5 h-1.5 rounded-full ${colors[status] || 'bg-gray-400'}`} />;
};

export const ComputerSelector: React.FC<ComputerSelectorProps> = ({
  value,
  onChange,
  chatId,
  disabled = false,
  onConflict,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const { 
    computers, 
    loading, 
    lastUsedComputer,
    openConfig,
  } = useComputerPool();

  // 获取当前选中的电脑
  const currentComputer = computers.find((c) => c.name === value) || computers[0];
  
  // 显示名称：优先使用 value（父组件传入的选中值）
  const displayName = value || currentComputer?.name || 'This PC';

  // 处理选择
  const handleSelect = (computer: ComputerWithStatus) => {
    if (disabled) return;

    // 只有 busy 状态不能选择
    if (computer.status === 'busy') {
      if (onConflict) {
        onConflict(computer.name, computer.occupiedBy || '');
      }
      setIsOpen(false);
      return;
    }

    // online 和 offline 都可以选择
    // offline 会在发送消息时自动连接 VM
    onChange(computer.name);
    setIsOpen(false);
  };

  // 打开 Agent Environment 设置
  const handleOpenConfig = () => {
    setIsOpen(false);
    openConfig();
  };

  // 如果没有选择，默认选择上次使用的或第一个
  useEffect(() => {
    if (!value && computers.length > 0) {
      const lastUsed = computers.find((c) => c.name === lastUsedComputer);
      onChange(lastUsed?.name || computers[0].name);
    }
  }, [value, lastUsedComputer, computers, onChange]);

  // 加载中状态
  if (loading && computers.length === 0) {
    return (
      <div className="flex items-center gap-1.5 px-2 py-1 text-xs text-black/40">
        <span>加载中...</span>
      </div>
    );
  }

  // 错误或空状态 - 显示默认的 This PC
  if (computers.length === 0) {
    return (
      <div className="relative">
        <button
          type="button"
          onClick={() => !disabled && setIsOpen(!isOpen)}
          disabled={disabled}
          className={`
            flex items-center gap-1.5 px-2 py-1 rounded-sm transition-colors text-xs font-medium
            ${disabled ? 'text-black/30 cursor-not-allowed' : 'text-black/70 hover:bg-black/5'}
          `}
        >
          <span>This PC</span>
          <ChevronDown className="w-2.5 h-2.5 text-black/30" />
        </button>
        {isOpen && (
          <>
            <div className="fixed inset-0 z-40" onClick={() => setIsOpen(false)} />
            <div className="absolute bottom-full left-0 mb-2 w-[180px] bg-white border border-black/10 shadow-xl rounded-sm flex flex-col z-50 overflow-hidden">
              <div className="px-3 py-2 text-xs text-black/40">加载失败</div>
              <div className="border-t border-black/10" />
              <button
                type="button"
                onClick={handleOpenConfig}
                className="flex items-center gap-2 px-3 py-2 text-left text-xs text-black/60 hover:bg-gray-50"
              >
                <Settings className="w-3 h-3" />
                <span>管理环境...</span>
              </button>
            </div>
          </>
        )}
      </div>
    );
  }

  return (
    <div className="relative">
      {/* 选择按钮：状态点 + 文字 + 下拉箭头 */}
      <button
        type="button"
        onClick={() => !disabled && setIsOpen(!isOpen)}
        disabled={disabled}
        className={`
          flex items-center gap-1.5 px-2 py-1 rounded-sm transition-colors text-xs font-medium max-w-full
          ${disabled ? 'text-black/30 cursor-not-allowed' : 'text-black/70 hover:bg-black/5'}
        `}
      >
        {currentComputer && <StatusDot status={currentComputer.status} />}
        <span className="truncate min-w-0">{displayName}</span>
        <ChevronDown className="w-2.5 h-2.5 text-black/30 flex-shrink-0" />
      </button>

      {/* 下拉菜单 */}
      {isOpen && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setIsOpen(false)} />
          <div 
            className="absolute bottom-full left-0 mb-2 w-[180px] bg-white border border-black/10 shadow-xl rounded-sm flex flex-col z-50 overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            {/* 电脑列表 */}
            {computers.map((computer) => {
              const isBusy = computer.status === 'busy';
              const isSelected = value === computer.name;
              
              return (
                <button
                  key={computer.name}
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleSelect(computer);
                  }}
                  disabled={isBusy}
                  className={`
                    flex items-center gap-2 px-3 py-2 text-left text-xs font-medium transition-colors
                    ${isSelected 
                      ? 'bg-orange-50 text-orange-900' 
                      : isBusy
                        ? 'text-black/30 cursor-not-allowed'
                        : 'text-black/80 hover:bg-gray-50'
                    }
                  `}
                >
                  <StatusDot status={computer.status} />
                  <span className="flex-1 truncate">{computer.name}</span>
                  {isSelected && <Check className="w-3 h-3 text-orange-600 flex-shrink-0" />}
                </button>
              );
            })}

            {/* 分隔线 */}
            <div className="border-t border-black/10" />

            {/* 管理环境 */}
            <button
              type="button"
              onClick={handleOpenConfig}
              className="flex items-center gap-2 px-3 py-2 text-left text-xs text-black/60 hover:bg-gray-50"
            >
              <Settings className="w-3 h-3" />
              <span>管理环境...</span>
            </button>
          </div>
        </>
      )}
    </div>
  );
};

export default ComputerSelector;

