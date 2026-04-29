import React, { useEffect, useMemo, useRef, useState } from 'react';
import clsx from 'clsx';

export interface WorkflowContextMenuItem {
  id: string;
  label?: string;
  icon?: React.ReactNode;
  shortcut?: string;
  disabled?: boolean;
  comingSoon?: boolean;
  separator?: boolean;
  children?: {
    title?: string;
    items: WorkflowContextMenuItem[];
  }[];
  onClick?: () => void;
}

interface WorkflowContextMenuProps {
  x: number;
  y: number;
  items: WorkflowContextMenuItem[];
  onClose: () => void;
  /** 画布容器的边界，用于限制菜单位置 */
  containerBounds?: DOMRect | null;
}

export function WorkflowContextMenu({ x, y, items, onClose, containerBounds }: WorkflowContextMenuProps) {
  const menuRef = useRef<HTMLDivElement>(null);
  const subMenuRef = useRef<HTMLDivElement>(null);
  const [activeItemId, setActiveItemId] = useState<string | null>(null);
  const closeTimerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      const t = e.target as Node;
      if (
        menuRef.current &&
        !menuRef.current.contains(t) &&
        !(subMenuRef.current && subMenuRef.current.contains(t))
      ) {
        onClose();
      }
    };

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };

    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleEscape);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleEscape);
    };
  }, [onClose]);

  const activeItem = useMemo(
    () => items.find((i) => i.id === activeItemId && i.children && i.children.length > 0) ?? null,
    [activeItemId, items]
  );

  // Keep within container bounds (or viewport if no container): adjust after mount / x,y changes
  useEffect(() => {
    const adjust = (el: HTMLDivElement | null, isSubMenu: boolean = false) => {
      if (!el) return;
      const rect = el.getBoundingClientRect();
      
      // 使用容器边界或视窗边界
      const bounds = containerBounds || {
        left: 0,
        top: 0,
        right: window.innerWidth,
        bottom: window.innerHeight,
      };

      let newLeft = parseFloat(el.style.left) || x;
      let newTop = parseFloat(el.style.top) || y;

      // 右边界检查
      if (rect.right > bounds.right) {
        if (isSubMenu) {
          // 子菜单：放到主菜单左边
          const mainMenuRect = menuRef.current?.getBoundingClientRect();
          if (mainMenuRect) {
            newLeft = mainMenuRect.left - rect.width - 8;
          } else {
            newLeft = bounds.right - rect.width - 10;
          }
        } else {
          newLeft = bounds.right - rect.width - 10;
        }
      }

      // 左边界检查
      if (newLeft < bounds.left) {
        newLeft = bounds.left + 10;
      }

      // 下边界检查
      if (rect.bottom > bounds.bottom) {
        newTop = bounds.bottom - rect.height - 10;
      }

      // 上边界检查
      if (newTop < bounds.top) {
        newTop = bounds.top + 10;
      }

      el.style.left = `${newLeft}px`;
      el.style.top = `${newTop}px`;
    };

    adjust(menuRef.current, false);
    // submenu depends on activeItem
    adjust(subMenuRef.current, true);
  }, [x, y, activeItemId, containerBounds]);

  const handleMouseLeave = () => {
    if (closeTimerRef.current) clearTimeout(closeTimerRef.current);
    closeTimerRef.current = setTimeout(() => {
      setActiveItemId(null);
    }, 200); // 200ms delay to allow crossing the gap
  };

  const handleMouseEnter = (itemId: string | null) => {
    if (closeTimerRef.current) {
      clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
    if (itemId !== null) setActiveItemId(itemId);
  };

  return (
    <>
      <div
        ref={menuRef}
        className="fixed z-50 bg-canvas border border-divider rounded-md shadow-lg py-1 min-w-[220px]"
        style={{ left: `${x}px`, top: `${y}px` }}
        onClick={(e) => e.stopPropagation()}
        onMouseLeave={handleMouseLeave}
      >
        {items.map((item, idx) => {
          if (item.separator) {
            return <div key={item.id || idx} className="h-px bg-divider my-1" />;
          }

          const hasChildren = !!item.children?.length;
          const isActive = activeItemId === item.id && hasChildren;

          return (
            <button
              key={item.id}
              type="button"
              disabled={item.disabled}
              onMouseEnter={() => handleMouseEnter(item.id)}
              onFocus={() => handleMouseEnter(item.id)}
              onClick={() => {
                if (hasChildren) return; // hover 展开
                if (!item.disabled && item.onClick) {
                  item.onClick();
                  onClose();
                }
              }}
              className={clsx(
                'w-full flex items-center gap-2 px-3 py-1.5 text-left text-xs',
                'text-black/80 hover:bg-black/5 hover:text-black/90 transition-colors',
                item.disabled && 'opacity-40 cursor-not-allowed',
                isActive && 'bg-black/5 text-black/90'
              )}
            >
              {item.icon && <span className="w-4 h-4 flex-shrink-0 text-black/60">{item.icon}</span>}
              <span className="flex-1">{item.label}</span>
              {item.shortcut && <span className="text-[10px] text-black/40 font-mono">{item.shortcut}</span>}
              {hasChildren && <span className="text-black/30">›</span>}
            </button>
          );
        })}
      </div>

      {activeItem?.children?.length ? (
        <div
          ref={subMenuRef}
          className="fixed z-50 bg-canvas border border-divider rounded-md shadow-lg py-1 min-w-[260px]"
          style={{
            left: `${x + 220 + 8}px`,
            top: `${y}px`,
          }}
          onClick={(e) => e.stopPropagation()}
          onMouseEnter={() => handleMouseEnter(activeItem.id)}
          onMouseLeave={handleMouseLeave}
        >
          {activeItem.children.map((group, groupIdx) => (
            <div key={group.title || groupIdx} className="py-1">
              {group.title && (
                <div className="px-3 pt-1 pb-2 text-[10px] font-semibold tracking-wider text-black/40">
                  {group.title}
                </div>
              )}

              {group.items.map((child) => (
                <button
                  key={child.id}
                  type="button"
                  disabled={child.disabled}
                  onClick={() => {
                    if (!child.disabled && child.onClick) {
                      child.onClick();
                      onClose();
                    }
                  }}
                  className={clsx(
                    'w-full flex items-center gap-2 px-3 py-1.5 text-left text-xs transition-colors',
                    child.disabled
                      ? 'text-black/30 cursor-not-allowed'
                      : 'text-black/80 hover:bg-black/5 hover:text-black/90'
                  )}
                >
                  {child.icon && <span className={clsx('w-4 h-4 flex-shrink-0', child.disabled ? 'text-black/20' : 'text-black/60')}>{child.icon}</span>}
                  <span className="flex-1">{child.label}</span>
                  {child.comingSoon && (
                    <span className="px-1.5 py-0.5 text-[9px] font-medium bg-black/5 text-black/40 rounded">
                      Coming Soon
                    </span>
                  )}
                  {child.shortcut && <span className="text-[10px] text-black/40 font-mono">{child.shortcut}</span>}
                </button>
              ))}
            </div>
          ))}
        </div>
      ) : null}
    </>
  );
}


