/**
 * StatusIcons - 统一的状态和动作图标组件
 * 
 * 提供整个 chat 模块的图标统一规范：
 * - LoadingSpinner: 橙色旋转加载环（统一的加载状态）
 * - StatusIcon: 根据状态显示对应图标
 * - ActionIcon: 根据动作类型显示对应图标
 */

import React from 'react';
import {
  Loader2,
  XCircle,
  StopCircle,
  MousePointer2,
  Keyboard,
  Monitor,
  Scroll,
  Clock,
  Terminal,
  CheckCircle,
  Hand,
  RotateCcw,
  Play,
} from 'lucide-react';

// ==================== 类型定义 ====================

export type TaskStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled' | 'error';

export type ActionType = 
  | 'click' 
  | 'double_click'
  | 'type' 
  | 'key' 
  | 'scroll' 
  | 'wait' 
  | 'screenshot' 
  | 'drag'
  | 'stop'
  | 'finish_milestone'
  | string;

// ==================== 尺寸配置 ====================

export type IconSize = 'xs' | 'sm' | 'md' | 'lg';

const SIZE_CLASSES: Record<IconSize, string> = {
  xs: 'w-3 h-3',
  sm: 'w-3.5 h-3.5',
  md: 'w-4 h-4',
  lg: 'w-5 h-5',
};

// ==================== 加载动画组件 ====================

interface LoadingSpinnerProps {
  size?: IconSize;
  className?: string;
}

/**
 * 统一的加载旋转环 - 橙色
 * 用于所有加载/运行中的状态
 */
export const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({ 
  size = 'md', 
  className = '' 
}) => {
  return (
    <Loader2 
      className={`${SIZE_CLASSES[size]} animate-spin text-orange-500 ${className}`} 
    />
  );
};

// ==================== 状态图标组件 ====================

interface StatusIconProps {
  status: TaskStatus;
  actionType?: ActionType;
  size?: IconSize;
  className?: string;
}

/**
 * 根据任务状态显示对应图标
 * 
 * - pending: 灰色时钟
 * - running: 橙色旋转环
 * - completed: 根据 actionType 显示对应动作图标（绿色）
 * - failed/error: 红色叉号
 * - cancelled: 灰色中止符号
 */
export const StatusIcon: React.FC<StatusIconProps> = ({ 
  status, 
  actionType,
  size = 'md',
  className = '' 
}) => {
  const sizeClass = SIZE_CLASSES[size];
  
  switch (status) {
    case 'pending':
      return <Clock className={`${sizeClass} text-gray-400 ${className}`} />;
    
    case 'running':
      return <LoadingSpinner size={size} className={className} />;
    
    case 'completed':
      // 完成状态：根据动作类型显示对应图标（简约灰色）
      return (
        <ActionIcon 
          actionType={actionType} 
          size={size} 
          color="gray" 
          className={className} 
        />
      );
    
    case 'failed':
    case 'error':
      return <XCircle className={`${sizeClass} text-red-500 ${className}`} />;
    
    case 'cancelled':
      return <StopCircle className={`${sizeClass} text-gray-400 ${className}`} />;
    
    default:
      return null;
  }
};

// ==================== 动作图标组件 ====================

interface ActionIconProps {
  actionType?: ActionType;
  size?: IconSize;
  color?: 'gray' | 'green' | 'blue' | 'orange';
  className?: string;
}

const COLOR_CLASSES: Record<string, string> = {
  gray: 'text-gray-500',
  green: 'text-green-500',
  blue: 'text-blue-500',
  orange: 'text-orange-500',
};

/**
 * 根据动作类型显示对应图标
 * 
 * - click/double_click: 鼠标指针
 * - type/key: 键盘
 * - scroll: 滚动
 * - wait: 时钟
 * - screenshot: 显示器
 * - drag: 手
 * - stop/finish_milestone: 完成勾选
 * - 默认: 终端图标
 */
export const ActionIcon: React.FC<ActionIconProps> = ({ 
  actionType, 
  size = 'md',
  color = 'gray',
  className = '' 
}) => {
  const sizeClass = SIZE_CLASSES[size];
  const colorClass = COLOR_CLASSES[color];
  const baseClass = `${sizeClass} ${colorClass} ${className}`;
  
  // Normalize action type (handle both 'type' and 'action' field naming)
  const normalizedType = actionType?.toLowerCase() || '';
  
  if (normalizedType === 'click' || normalizedType === 'double_click') {
    return <MousePointer2 className={baseClass} />;
  }
  
  if (normalizedType === 'type' || normalizedType === 'key') {
    return <Keyboard className={baseClass} />;
  }
  
  if (normalizedType === 'scroll') {
    return <Scroll className={baseClass} />;
  }
  
  if (normalizedType === 'wait') {
    return <Clock className={baseClass} />;
  }
  
  if (normalizedType === 'screenshot') {
    return <Monitor className={baseClass} />;
  }
  
  if (normalizedType === 'drag') {
    return <Hand className={baseClass} />;
  }
  
  if (normalizedType === 'stop' || normalizedType === 'finish_milestone') {
    return <CheckCircle className={baseClass} />;
  }
  
  return <Terminal className={baseClass} />;
};

// ==================== 导出所有图标（供直接使用）====================

export {
  Loader2,
  XCircle,
  StopCircle,
  MousePointer2,
  Keyboard,
  Monitor,
  Scroll,
  Clock,
  Terminal,
  CheckCircle,
  Hand,
  RotateCcw,
  Play,
} from 'lucide-react';

