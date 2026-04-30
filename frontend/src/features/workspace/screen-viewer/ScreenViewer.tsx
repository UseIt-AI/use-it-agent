'use client';

import React, { useState } from 'react';
import { ConnectionTopBar } from './components/ConnectionTopBar';
import { EmptyStatePanel } from './components/EmptyStatePanel';
import { useVncConnection } from './hooks/useVncConnection';
import { useRemoteConnection } from './hooks/useRemoteConnection';
import { DEFAULT_SCREEN_CONFIG } from './constants';
import type { ScreenConfig } from './types';

interface ScreenViewerProps {
  isFullscreen?: boolean;
  onToggleFullscreen?: () => void;
}

export default function ScreenViewer({ isFullscreen, onToggleFullscreen }: ScreenViewerProps) {
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [config, setConfig] = useState<ScreenConfig>(() => ({ ...DEFAULT_SCREEN_CONFIG }));

  const vnc = useVncConnection({ config });

  const remote = useRemoteConnection({
    config,
    connect: vnc.connect,
  });

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    if (name === 'wsPort' || name === 'vncPort' || name === 'width' || name === 'height') {
      setConfig((prev) => ({ ...prev, [name]: Number(value) }));
    } else {
      setConfig((prev) => ({ ...prev, [name]: value }));
    }
  };

  return (
    <div className="h-full flex flex-col">
      <ConnectionTopBar
        isConnected={vnc.isConnected}
        config={config}
        isFullscreen={isFullscreen}
        onToggleFullscreen={onToggleFullscreen}
      />

      <div className="flex-1 relative bg-canvas overflow-hidden group">
        <div
          className="absolute inset-0 opacity-[0.03] pointer-events-none"
          style={{
            backgroundImage: `radial-gradient(#000 1px, transparent 1px)`,
            backgroundSize: '24px 24px',
          }}
        />

        <div
          ref={vnc.vncContainerRef}
          className="absolute inset-0 flex items-center justify-center bg-canvas [&>canvas]:max-w-full [&>canvas]:max-h-full"
          style={{
            display: vnc.isConnected ? 'flex' : 'none',
          }}
        />

        {!vnc.isConnected && (
          <EmptyStatePanel
            config={config}
            showAdvanced={showAdvanced}
            onToggleAdvanced={() => setShowAdvanced((prev) => !prev)}
            onInputChange={handleInputChange}
            autoConnectStep={remote.autoConnectStep}
            errorMessage={remote.errorMessage}
            onManualConnect={remote.handleManualConnect}
          />
        )}
      </div>
    </div>
  );
}
