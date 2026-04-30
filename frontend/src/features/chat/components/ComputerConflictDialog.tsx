/**
 * 电脑冲突对话框
 * 当选择的电脑被其他对话占用时显示
 */

import React from 'react';
import { AlertTriangle, Monitor, Clock, ArrowRight } from 'lucide-react';

interface ComputerConflictDialogProps {
  isOpen: boolean;
  computerName: string;
  occupiedBy: string;
  queuePosition?: number;
  onClose: () => void;
  onSwitchComputer: () => void;
  onWaitInQueue: () => void;
}

export const ComputerConflictDialog: React.FC<ComputerConflictDialogProps> = ({
  isOpen,
  computerName,
  occupiedBy,
  queuePosition,
  onClose,
  onSwitchComputer,
  onWaitInQueue,
}) => {
  if (!isOpen) return null;

  return (
    <>
      {/* 背景遮罩 */}
      <div 
        className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center"
        onClick={onClose}
      >
        {/* 对话框 */}
        <div 
          className="bg-white rounded-lg shadow-2xl w-[400px] max-w-[90vw] overflow-hidden"
          onClick={(e) => e.stopPropagation()}
        >
          {/* 标题 */}
          <div className="flex items-center gap-3 px-5 py-4 border-b border-black/10">
            <div className="flex items-center justify-center w-10 h-10 rounded-full bg-yellow-100">
              <AlertTriangle className="w-5 h-5 text-yellow-600" />
            </div>
            <div>
              <h3 className="text-base font-semibold text-black/90">电脑被占用</h3>
              <p className="text-sm text-black/50">Computer Busy</p>
            </div>
          </div>

          {/* 内容 */}
          <div className="px-5 py-4">
            <div className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg mb-4">
              <Monitor className="w-5 h-5 text-black/40" />
              <div>
                <p className="text-sm font-medium text-black/80">{computerName}</p>
                <p className="text-xs text-black/50">正在被其他对话使用</p>
              </div>
            </div>

            <p className="text-sm text-black/70 mb-4">
              你想要使用的电脑 <span className="font-medium">"{computerName}"</span> 目前正在被另一个对话占用。
            </p>

            <p className="text-sm text-black/60">你可以选择：</p>
          </div>

          {/* 操作按钮 */}
          <div className="px-5 pb-5 flex flex-col gap-2">
            {/* 切换电脑 */}
            <button
              onClick={onSwitchComputer}
              className="flex items-center justify-between w-full px-4 py-3 bg-orange-500 text-white rounded-lg hover:bg-orange-600 transition-colors"
            >
              <div className="flex items-center gap-3">
                <ArrowRight className="w-4 h-4" />
                <span className="font-medium">选择其他电脑</span>
              </div>
              <span className="text-xs opacity-80">推荐</span>
            </button>

            {/* 排队等待 */}
            <button
              onClick={onWaitInQueue}
              className="flex items-center justify-between w-full px-4 py-3 bg-gray-100 text-black/80 rounded-lg hover:bg-gray-200 transition-colors"
            >
              <div className="flex items-center gap-3">
                <Clock className="w-4 h-4" />
                <span className="font-medium">排队等待</span>
              </div>
              {queuePosition !== undefined && queuePosition > 0 && (
                <span className="text-xs text-black/50">当前排队: {queuePosition} 人</span>
              )}
            </button>

            {/* 取消 */}
            <button
              onClick={onClose}
              className="w-full px-4 py-2 text-sm text-black/50 hover:text-black/70 transition-colors"
            >
              取消
            </button>
          </div>
        </div>
      </div>
    </>
  );
};

export default ComputerConflictDialog;



