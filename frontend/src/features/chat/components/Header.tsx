import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Minus, X, Maximize2, PanelRightOpen, Settings, Plus, MoreHorizontal, History } from 'lucide-react';

interface HeaderProps {
  onClear: () => void;
  onNewChat?: () => void;
  showHistory: boolean;
  onToggleHistory: () => void;
}

/**
 * 窗口控制按钮组件 (复用自 workspace/page.tsx 的样式)
 */
const WindowControlBtn = ({ 
  onClick, 
  icon, 
  title, 
  hoverColor = "hover:bg-black/5 hover:text-black/80",
  className = "" 
}: { 
  onClick?: () => void, 
  icon: React.ReactNode, 
  title?: string, 
  hoverColor?: string,
  className?: string
}) => (
  <button 
    onClick={onClick}
    className={`p-1.5 rounded-md text-black/40 transition-colors ${hoverColor} ${className}`}
    title={title}
  >
    {icon}
  </button>
);

export const Header: React.FC<HeaderProps> = ({ onClear, onNewChat, showHistory, onToggleHistory }) => {
  const navigate = useNavigate();

  const handleMinimize = () => {
    if (window.electron?.minimize) {
      window.electron.minimize();
    }
  };

  const handleClose = () => {
    if (window.electron?.close) {
      window.electron.close();
    }
  };

  const handleExpand = () => {
    // 通知 Electron 恢复默认窗口大小
    if (window.electron?.restoreWindowSize) {
      window.electron.restoreWindowSize();
    }
    // 导航到工作区页面
    navigate('/workspace');
  };

  const handleShrink = () => {
    // 通知 Electron 收缩窗口到右侧细长条
    if (window.electron?.shrinkWindow) {
      window.electron.shrinkWindow();
    }
  };

  return (
    <div className="flex flex-col z-50">
      {/* 第一行：系统顶栏 (System Header) */}
      <header className="draggable flex items-center justify-between px-3 h-[32px] border-b border-divider bg-canvas-sub flex-shrink-0">
        {/* 左侧：Logo */}
        <div className="flex items-center gap-2 select-none no-drag">
          <img 
            src="./useit-logo-no-text.svg" 
            alt="UseIt Logo" 
            className="w-4 h-4"
          />
          <span className="text-xs font-bold text-black/80 tracking-tight">UseIt</span>
        </div>

        {/* 右侧：窗口控制 */}
        <div className="flex items-center gap-1 no-drag">
          <WindowControlBtn
            onClick={handleExpand}
            icon={<Maximize2 className="w-3.5 h-3.5" />}
            title="Expand to Workspace"
            hoverColor="hover:bg-orange-50 hover:text-orange-600"
          />
          <WindowControlBtn
            onClick={handleShrink}
            icon={<PanelRightOpen className="w-3.5 h-3.5" />}
            title="Shrink to Sidebar"
            hoverColor="hover:bg-blue-50 hover:text-blue-600"
          />
          <WindowControlBtn icon={<Settings className="w-3.5 h-3.5" />} title="System Settings" />
          <div className="w-px h-3 bg-black/10 mx-1.5" />
          <WindowControlBtn onClick={handleMinimize} icon={<Minus className="w-3.5 h-3.5" />} />
          <WindowControlBtn onClick={handleClose} icon={<X className="w-3.5 h-3.5" />} hoverColor="hover:bg-red-600 hover:text-white" />
        </div>
      </header>

      {/* 第二行：聊天工具栏 (Chat Toolbar) */}
      <div className="flex items-end justify-between h-[32px] border-b border-divider bg-canvas-sub flex-shrink-0 pl-0 pr-2">
         {/* 左侧：Tab - 紧贴顶部 */}
         <div className="flex items-end h-full gap-1">
            <div className="flex items-center gap-2 px-4 h-full bg-canvas text-xs font-medium text-black/90 select-none border-r border-divider relative top-[1px]">
               {/* 顶部橙色高亮条 */}
               <div className="absolute top-0 left-0 right-0 h-[2px] bg-orange-500" />
               <span>New Chat</span>
            </div>
         </div>

         {/* 右侧：聊天功能按钮 - 垂直居中 */}
         <div className="flex items-center gap-1 h-full">
            <WindowControlBtn 
              icon={<Plus className="w-3.5 h-3.5" />} 
              title="New Chat" 
              onClick={onNewChat}
            />
            <WindowControlBtn 
              icon={<History className="w-3.5 h-3.5" />} 
              title="History" 
              onClick={onToggleHistory}
              hoverColor={showHistory ? "bg-black/10 text-black" : undefined}
            />
            <WindowControlBtn icon={<MoreHorizontal className="w-3.5 h-3.5" />} title="Chat Settings" />
         </div>
      </div>
    </div>
  );
};
