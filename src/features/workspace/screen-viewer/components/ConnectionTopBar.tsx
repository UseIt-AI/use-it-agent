import React from 'react';
import { Maximize2, Minimize2, Laptop, Cloud, Power } from 'lucide-react';
import type { ConnectionType, ScreenConfig } from '../types';

interface ConnectionTopBarProps {
  isConnected: boolean;
  connectionType: ConnectionType;
  config: ScreenConfig;
  isFullscreen?: boolean;
  onToggleFullscreen?: () => void;
  onOpenShutdown?: () => void;
}

export function ConnectionTopBar({
  isConnected,
  connectionType,
  config,
  isFullscreen,
  onToggleFullscreen,
  onOpenShutdown,
}: ConnectionTopBarProps) {
  return (
    <div className="flex items-center justify-between px-3 h-[32px] border-b border-divider bg-canvas-sub backdrop-blur-sm">
      <div className="flex items-center gap-3">
        {/* status */}
        <div className="flex items-center gap-1.5">
          <div className={`w-2 h-2 ${isConnected ? 'bg-green-500 animate-pulse' : 'bg-gray-300'}`} />
          <span className="text-[10px] font-mono text-black/50 uppercase">
            {isConnected ? 'Connected' : 'Offline'}
          </span>
        </div>

        {/* connection info */}
        <div className="flex items-center gap-2 px-2 py-0.5 bg-canvas border border-divider">
          {connectionType === 'local' ? (
            <Laptop className="w-3 h-3 text-black/40" />
          ) : (
            <Cloud className="w-3 h-3 text-black/40" />
          )}
          <span className="font-mono text-[10px] text-black/60 tracking-tight">
            {config.username && `${config.username}@`}
            {config.host || 'Not configured'}:{config.vncPort}
          </span>
        </div>
      </div>

      <div className="flex items-center gap-px">
        {/* layout fullscreen toggle */}
        <button
          onClick={onToggleFullscreen}
          className="p-1.5 hover:bg-black/5 text-black/40 hover:text-orange-500 transition-colors"
          title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}
        >
          {isFullscreen ? (
            <Minimize2 className="w-3.5 h-3.5" />
          ) : (
            <Maximize2 className="w-3.5 h-3.5" />
          )}
        </button>

        {/* Local VM power */}
        {connectionType === 'local' && onOpenShutdown && (
          <button
            onClick={onOpenShutdown}
            className="p-1.5 hover:bg-black/5 text-black/40 hover:text-red-500 transition-colors"
            title="Shut down VM"
          >
            <Power className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
    </div>
  );
}


