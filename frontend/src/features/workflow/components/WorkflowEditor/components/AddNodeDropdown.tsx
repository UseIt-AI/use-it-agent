import React, { useState, useRef, useEffect, useMemo, useCallback } from 'react';
import { Plus } from 'lucide-react';
import clsx from 'clsx';
import { NODE_CONFIGS } from '../../../types';
import type { NodeType } from '../../../types';
import { BlockIcon } from '../../block-icon';

interface AddNodeDropdownProps {
  onAddNode: (type: NodeType) => void;
}

interface MenuItem {
  id: string;
  label: string;
  icon: React.ReactNode;
  type: NodeType;
  disabled?: boolean;
  comingSoon?: boolean;
}

interface MenuGroup {
  title: string;
  items: MenuItem[];
}

export function AddNodeDropdown({ onAddNode }: AddNodeDropdownProps) {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  // 关闭下拉菜单
  const handleClose = useCallback(() => {
    setIsOpen(false);
  }, []);

  // 点击外部关闭
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        handleClose();
      }
    };

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') handleClose();
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      document.addEventListener('keydown', handleEscape);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleEscape);
    };
  }, [isOpen, handleClose]);

  // 菜单项配置
  const menuGroups: MenuGroup[] = useMemo(() => [
    {
      title: 'COMMON AGENTS',
      items: [
        {
          id: 'add-tool-use',
          label: NODE_CONFIGS['tool-use']?.defaultTitle || 'Tool Use',
          icon: <BlockIcon type="tool-use" className="w-4 h-4" />,
          type: 'tool-use' as NodeType,
        },
        {
          id: 'add-computer-use',
          label: 'Computer Use',
          icon: <BlockIcon type="computer-use" className="w-4 h-4" />,
          type: 'computer-use' as NodeType,
        },
        {
          id: 'add-browser-use',
          label: NODE_CONFIGS['browser-use']?.defaultTitle || 'Browser Use',
          icon: <BlockIcon type="browser-use" className="w-4 h-4" />,
          type: 'browser-use' as NodeType,
        },
        {
          id: 'add-code-use',
          label: 'Code Use',
          icon: <BlockIcon type="code-use" className="w-4 h-4" />,
          type: 'code-use' as NodeType,
        },
        {
          id: 'add-end',
          label: 'End',
          icon: <BlockIcon type="end" className="w-4 h-4" />,
          type: 'end' as NodeType,
        },
      ],
    },
    {
      title: 'LOGIC',
      items: [
        {
          id: 'add-if-else',
          label: 'If/Else',
          icon: <BlockIcon type="if-else" className="w-4 h-4" />,
          type: 'if-else' as NodeType,
        },
        {
          id: 'add-loop',
          label: 'Loop',
          icon: <BlockIcon type="loop" className="w-4 h-4" />,
          type: 'loop' as NodeType,
        },
      ],
    },
    {
      title: 'EXPERIMENTAL',
      items: [
        {
          id: 'add-agent',
          label: NODE_CONFIGS['agent']?.defaultTitle || 'Agent',
          icon: <BlockIcon type="agent" className="w-4 h-4" />,
          type: 'agent' as NodeType,
        },
      ],
    },
  ], []);

  const handleItemClick = (type: NodeType) => {
    onAddNode(type);
    handleClose();
  };

  return (
    <div ref={dropdownRef} className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={clsx(
          'flex items-center justify-center w-8 h-8 rounded-md transition-colors',
          isOpen
            ? 'bg-orange-100 text-orange-600'
            : 'hover:bg-gray-100 text-gray-600'
        )}
        title="添加节点"
      >
        <Plus className="w-4 h-4" />
      </button>

      {isOpen && (
        <div
          ref={menuRef}
          className="absolute left-0 top-full mt-1 z-50 bg-white border border-black/10 rounded-lg shadow-lg py-1 min-w-[220px]"
          onClick={(e) => e.stopPropagation()}
        >
          {menuGroups.map((group, groupIdx) => (
            <div key={group.title || groupIdx} className="py-1">
              <div className="px-3 pt-1 pb-2 text-[10px] font-semibold tracking-wider text-black/40">
                {group.title}
              </div>

              {group.items.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => !item.disabled && handleItemClick(item.type)}
                  disabled={item.disabled}
                  className={clsx(
                    'w-full flex items-center gap-2 px-3 py-1.5 text-left text-xs transition-colors',
                    item.disabled
                      ? 'text-black/30 cursor-not-allowed'
                      : 'text-black/80 hover:bg-black/5 hover:text-black/90'
                  )}
                >
                  <span className={clsx('w-4 h-4 flex-shrink-0', item.disabled ? 'text-black/20' : 'text-black/60')}>{item.icon}</span>
                  <span className="flex-1">{item.label}</span>
                  {item.comingSoon && (
                    <span className="px-1.5 py-0.5 text-[9px] font-medium bg-black/5 text-black/40 rounded">
                      Coming Soon
                    </span>
                  )}
                </button>
              ))}

              {groupIdx < menuGroups.length - 1 && (
                <div className="h-px bg-black/5 my-1 mx-2" />
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
