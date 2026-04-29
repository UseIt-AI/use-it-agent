/**
 * ListItem - Control Panel 右侧列表的通用列表项组件
 * 
 * 提供统一的选中、悬停样式
 */

import React from 'react';

export interface ListItemProps {
  /** 是否选中 */
  selected?: boolean;
  /** 是否禁用 */
  disabled?: boolean;
  /** 点击回调 */
  onClick?: () => void;
  /** 双击回调 */
  onDoubleClick?: () => void;
  /** 子元素 */
  children: React.ReactNode;
  /** 自定义类名 */
  className?: string;
  /** 是否可拖拽 */
  draggable?: boolean;
  /** 拖拽开始回调 */
  onDragStart?: (e: React.DragEvent) => void;
}

/**
 * 通用列表项组件
 * 
 * 样式规范：
 * - 高度: 36px
 * - 选中状态: 白色背景 + 黑色文字
 * - 悬停状态: 5% 黑色背景
 * - 禁用状态: 40% 透明度
 */
export function ListItem({
  selected = false,
  disabled = false,
  onClick,
  onDoubleClick,
  children,
  className = '',
  draggable,
  onDragStart,
}: ListItemProps) {
  return (
    <div
      draggable={draggable}
      onDragStart={onDragStart}
      onClick={disabled ? undefined : onClick}
      onDoubleClick={disabled ? undefined : onDoubleClick}
      className={`
        group flex items-center gap-2 px-2 h-[42px] border-b border-divider/50 
        transition-colors
        ${disabled 
          ? 'opacity-40 cursor-not-allowed' 
          : 'cursor-pointer'
        }
        ${selected 
          ? 'bg-white text-black' 
          : 'text-black/60 hover:bg-black/5 hover:text-black/90'
        }
        ${className}
      `}
    >
      {children}
    </div>
  );
}

/**
 * 列表项状态指示点
 */
export type StatusDotVariant = 'success' | 'warning' | 'error' | 'info' | 'neutral' | 'inactive';

const statusDotColors: Record<StatusDotVariant, string> = {
  success: 'bg-emerald-500',
  warning: 'bg-amber-500',
  error: 'bg-red-500',
  info: 'bg-blue-500',
  neutral: 'bg-neutral-400',
  inactive: 'bg-neutral-300',
};

export interface StatusDotProps {
  variant?: StatusDotVariant;
  className?: string;
}

export function StatusDot({ variant = 'neutral', className = '' }: StatusDotProps) {
  return (
    <div className={`w-1.5 h-1.5 flex-shrink-0 rounded-full ${statusDotColors[variant]} ${className}`} />
  );
}

/**
 * 列表项图标容器
 */
export interface ListItemIconProps {
  selected?: boolean;
  children: React.ReactNode;
  className?: string;
}

export function ListItemIcon({ selected, children, className = '' }: ListItemIconProps) {
  return (
    <div className={`flex-shrink-0 ${selected ? 'text-black' : 'text-black/40'} ${className}`}>
      {children}
    </div>
  );
}

/**
 * 列表项文本容器
 */
export interface ListItemTextProps {
  primary: string;
  secondary?: string;
  selected?: boolean;
  className?: string;
}

export function ListItemText({ primary, secondary, selected, className = '' }: ListItemTextProps) {
  return (
    <div className={`flex-1 min-w-0 ${className}`}>
      <div className={`text-[11px] font-medium truncate leading-none ${selected ? 'text-black' : 'text-black/70'}`}>
        {primary}
      </div>
      {secondary && (
        <div className="text-[9px] text-black/40 mt-1 truncate">
          {secondary}
        </div>
      )}
    </div>
  );
}

/**
 * 列表项操作按钮容器
 */
export interface ListItemActionsProps {
  children: React.ReactNode;
  className?: string;
  /** 是否仅在悬停时显示 */
  showOnHover?: boolean;
}

export function ListItemActions({ children, className = '', showOnHover = true }: ListItemActionsProps) {
  return (
    <div className={`flex items-center gap-1 ${showOnHover ? 'opacity-0 group-hover:opacity-100' : ''} transition-opacity ${className}`}>
      {children}
    </div>
  );
}

/**
 * 列表项操作按钮
 */
export interface ListItemActionButtonProps {
  onClick?: (e: React.MouseEvent) => void;
  title?: string;
  children: React.ReactNode;
  variant?: 'default' | 'danger';
  className?: string;
}

export function ListItemActionButton({ 
  onClick, 
  title, 
  children, 
  variant = 'default',
  className = '' 
}: ListItemActionButtonProps) {
  const variantStyles = {
    default: 'text-black/30 hover:text-black/70 hover:bg-black/5',
    danger: 'text-black/30 hover:text-red-500 hover:bg-red-50',
  };

  return (
    <button
      onClick={(e) => {
        e.stopPropagation();
        onClick?.(e);
      }}
      title={title}
      className={`w-6 h-6 flex items-center justify-center rounded-sm transition-colors ${variantStyles[variant]} ${className}`}
    >
      {children}
    </button>
  );
}

export default ListItem;
