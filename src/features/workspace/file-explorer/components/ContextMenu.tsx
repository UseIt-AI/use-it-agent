import React, { useEffect, useRef } from 'react';
import { File, Folder, Trash2, Copy, Scissors, FileEdit, Search, FolderOpen, Clipboard, MessageSquare, Upload } from 'lucide-react';
import clsx from 'clsx';

export interface ContextMenuAction {
  id: string;
  label?: string;
  icon?: React.ReactNode;
  shortcut?: string;
  disabled?: boolean;
  separator?: boolean;
  onClick?: () => void;
}

interface ContextMenuProps {
  x: number;
  y: number;
  actions: ContextMenuAction[];
  onClose: () => void;
}

export function ContextMenu({ x, y, actions, onClose }: ContextMenuProps) {
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        onClose();
      }
    };

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleEscape);

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleEscape);
    };
  }, [onClose]);

  // 确保菜单在视口内
  useEffect(() => {
    if (menuRef.current) {
      const rect = menuRef.current.getBoundingClientRect();
      const viewportWidth = window.innerWidth;
      const viewportHeight = window.innerHeight;

      if (rect.right > viewportWidth) {
        menuRef.current.style.left = `${viewportWidth - rect.width - 10}px`;
      }
      if (rect.bottom > viewportHeight) {
        menuRef.current.style.top = `${viewportHeight - rect.height - 10}px`;
      }
    }
  }, [x, y]);

  return (
    <div
      ref={menuRef}
      data-file-explorer-context-menu="true"
      className="fixed z-[60] bg-white border border-black/10 rounded-md shadow-lg py-1 min-w-[180px]"
      style={{
        left: `${x}px`,
        top: `${y}px`,
      }}
      onClick={e => e.stopPropagation()}
    >
      {actions.map((action, index) => {
        if (action.separator) {
          return <div key={action.id || index} className="h-px bg-black/10 my-1" />;
        }

        return (
          <button
            key={action.id}
            onClick={() => {
              if (!action.disabled && action.onClick) {
                action.onClick();
                onClose();
              }
            }}
            disabled={action.disabled}
            className={clsx(
              'w-full flex items-center px-3 py-1.5 text-left text-xs text-black/80 hover:bg-orange-50 hover:text-orange-900 transition-colors',
              action.disabled && 'opacity-50 cursor-not-allowed'
            )}
          >
            <span className="flex-1">{action.label}</span>
            {action.shortcut && (
              <span className="text-[10px] text-black/40 font-mono">{action.shortcut}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}

// 预定义的菜单项图标
export const MenuIcons = {
  newFile: <File className="w-3.5 h-3.5" />,
  newFolder: <Folder className="w-3.5 h-3.5" />,
  rename: <FileEdit className="w-3.5 h-3.5" />,
  delete: <Trash2 className="w-3.5 h-3.5" />,
  copy: <Copy className="w-3.5 h-3.5" />,
  cut: <Scissors className="w-3.5 h-3.5" />,
  search: <Search className="w-3.5 h-3.5" />,
  copyPath: <Clipboard className="w-3.5 h-3.5" />,
  showInFolder: <FolderOpen className="w-3.5 h-3.5" />,
  addToChat: <MessageSquare className="w-3.5 h-3.5" />,
  importFiles: <Upload className="w-3.5 h-3.5" />,
};

