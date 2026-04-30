import React from 'react';
import { Maximize2, Minimize2, Cloud } from 'lucide-react';
import type { ScreenConfig } from '../types';

interface ConnectionTopBarProps {
  isConnected: boolean;
  config: ScreenConfig;
  isFullscreen?: boolean;
  onToggleFullscreen?: () => void;
}

export function ConnectionTopBar({
  isConnected,
  config,
  isFullscreen,
  onToggleFullscreen,
}: ConnectionTopBarProps) {
  return (
    <div className="flex items-center justify-between px-3 h-[32px] border-b border-divider bg-canvas-sub backdrop-blur-sm">
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1.5">
          <div className={`w-2 h-2 ${isConnected ? 'bg-green-500 animate-pulse' : 'bg-gray-300'}`} />
          <span className="text-[10px] font-mono text-black/50 uppercase">
            {isConnected ? 'Connected' : 'Offline'}
          </span>
        </div>

        <div className="flex items-center gap-2 px-2 py-0.5 bg-canvas border border-divider">
          <Cloud className="w-3 h-3 text-black/40" />
          <span className="font-mono text-[10px] text-black/60 tracking-tight">
            {config.username && `${config.username}@`}
            {config.host || 'Not configured'}:{config.vncPort}
          </span>
        </div>
      </div>

      <div className="flex items-center gap-px">
        <button
          onClick={onToggleFullscreen}
          className="p-1.5 hover:bg-black/5 text-black/40 hover:text-orange-500 transition-colors"
          title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}
        >
          {isFullscreen ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
        </button>
      </div>
    </div>
  );
}
