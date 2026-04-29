/**
 * @deprecated This component is for legacy message format compatibility.
 * New implementations should use CUACard component instead.
 */

import React, { useState } from 'react';
import { 
  Terminal, 
  MousePointer2, 
  Keyboard, 
  Monitor, 
  Clock,
  ChevronDown,
  ChevronUp,
  ImageIcon,
  CheckCircle,
  Loader2,
  XCircle
} from 'lucide-react';

interface ComputerUseStepProps {
  stepNumber: number;
  action: string;
  reasoning?: string;
  screenshot?: string;
  actionDetails?: any;
  status: 'running' | 'completed' | 'error';
  duration?: number;
}

export const ComputerUseStep: React.FC<ComputerUseStepProps> = ({
  stepNumber,
  action,
  reasoning,
  screenshot,
  actionDetails,
  status,
  duration
}) => {
  const [isExpanded, setIsExpanded] = useState(status === 'running');
  const [imgSize, setImgSize] = useState<{width: number, height: number} | null>(null);

  const handleImageLoad = (e: React.SyntheticEvent<HTMLImageElement>) => {
    const { naturalWidth, naturalHeight } = e.currentTarget;
    setImgSize({ width: naturalWidth, height: naturalHeight });
  };

  // 解析动作类型以选择图标 - 统一使用灰色系
  const getActionIcon = (actionText: string) => {
    const className = `w-4 h-4 text-gray-400 ${status === 'running' ? 'animate-pulse' : ''}`;
    if (actionText.includes('click')) return <MousePointer2 className={className} />;
    if (actionText.includes('type') || actionText.includes('key')) return <Keyboard className={className} />;
    if (actionText.includes('screenshot')) return <Monitor className={className} />;
    return <Terminal className={className} />;
  };

  // 状态图标 - 保留颜色以区分状态
  const getStatusIcon = () => {
    if (status === 'running') return <Loader2 className="w-3.5 h-3.5 animate-spin text-blue-500" />;
    if (status === 'completed') return <CheckCircle className="w-3.5 h-3.5 text-green-500" />;
    if (status === 'error') return <XCircle className="w-3.5 h-3.5 text-red-500" />;
    return null;
  };

  const hasDetails = reasoning || screenshot;

  return (
    <div className="group border border-gray-100 rounded-lg bg-white hover:shadow-sm transition-all duration-200 overflow-hidden">
      {/* 头部摘要 - 标题栏 */}
      <div 
        className={`flex items-center gap-3 px-3 py-2.5 ${hasDetails ? 'cursor-pointer hover:bg-gray-50/50' : ''} transition-colors`}
        onClick={() => hasDetails && setIsExpanded(!isExpanded)}
      >
        {/* Action 内容 */}
        <div className="flex-1 flex items-center gap-2 min-w-0">
          {getActionIcon(action)}
          <span className={`text-sm truncate ${status === 'running' ? 'text-amber-600/80 animate-pulse' : 'text-gray-700'}`}>
            {action}
          </span>
        </div>

        {/* 右侧信息 */}
        <div className="flex items-center gap-2">
          {duration && (
            <div className="hidden group-hover:flex items-center gap-1 text-[10px] text-gray-400">
              <Clock className="w-3 h-3" />
              <span>{duration.toFixed(1)}s</span>
            </div>
          )}
          
          <div className="opacity-60">
            {getStatusIcon()}
          </div>

          {hasDetails && (
            isExpanded ? 
            <ChevronUp className="w-3.5 h-3.5 text-gray-400" /> : 
            <ChevronDown className="w-3.5 h-3.5 text-gray-400" />
          )}
        </div>
      </div>

      {/* 展开详情 - 上下结构，用细线隔开 */}
      {isExpanded && hasDetails && (
        <>
          {/* 分隔线 */}
          <div className="border-t border-gray-100" />
          
          {/* 内容区域 */}
          <div className="px-4 py-3 animate-in slide-in-from-top-1 duration-200">
            <div className="flex flex-col md:flex-row gap-3">
              {/* 思考过程 - 左侧 */}
              {reasoning && (
                <div className={`text-sm text-gray-600 leading-relaxed flex-1 min-w-0 max-h-[300px] overflow-y-auto custom-scrollbar`}>
                  {reasoning}
                </div>
              )}

              {/* 截图预览 - 右侧 */}
              {screenshot && (
                <div className={`relative group/image flex-1 min-w-0 ${!reasoning ? 'w-full' : ''}`}>
                  <div className="absolute top-2 right-2 opacity-0 group-hover/image:opacity-100 transition-opacity bg-black/50 text-white text-[10px] px-1.5 py-0.5 rounded backdrop-blur-sm flex items-center gap-1 z-20">
                    <ImageIcon className="w-3 h-3" />
                    <span>Preview</span>
                  </div>
                  <img 
                    src={`data:image/png;base64,${screenshot}`} 
                    alt={`Step ${stepNumber} result`} 
                    onLoad={handleImageLoad}
                    className="rounded border border-gray-200 shadow-sm w-full object-contain bg-gray-900/5 max-h-[300px] cursor-zoom-in"
                  />
                  
                  {/* 点击位置标记 */}
                  {actionDetails?.type === 'click' && actionDetails.x !== undefined && actionDetails.y !== undefined && imgSize && (
                    <>
                      <div 
                        className="absolute w-6 h-6 border-2 border-red-500/80 rounded-full bg-red-500/10 transform -translate-x-1/2 -translate-y-1/2 z-10 shadow-sm animate-ping-slow pointer-events-none"
                        style={{
                          left: `${(actionDetails.x / imgSize.width) * 100}%`,
                          top: `${(actionDetails.y / imgSize.height) * 100}%`
                        }}
                      />
                      <div 
                        className="absolute w-2 h-2 bg-red-500 rounded-full transform -translate-x-1/2 -translate-y-1/2 z-10 shadow-sm pointer-events-none"
                        style={{
                          left: `${(actionDetails.x / imgSize.width) * 100}%`,
                          top: `${(actionDetails.y / imgSize.height) * 100}%`
                        }}
                      />
                      <div 
                          className="absolute bg-black/70 text-white text-[9px] px-1 rounded transform -translate-x-1/2 -translate-y-full mt-[-8px] z-10 whitespace-nowrap opacity-0 group-hover/image:opacity-100 transition-opacity pointer-events-none"
                          style={{
                              left: `${(actionDetails.x / imgSize.width) * 100}%`,
                              top: `${(actionDetails.y / imgSize.height) * 100}%`
                          }}
                      >
                          {actionDetails.x}, {actionDetails.y}
                      </div>
                    </>
                  )}
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
};


