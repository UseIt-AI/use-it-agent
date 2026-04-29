'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { ConnectionTopBar } from './components/ConnectionTopBar';
import { EmptyStatePanel } from './components/EmptyStatePanel';
import { ShutdownModal } from './components/ShutdownModal';
import { useVncConnection } from './hooks/useVncConnection';
import { useLocalVmAutoConnect } from './hooks/useLocalVmAutoConnect';
import { useRemoteConnection } from './hooks/useRemoteConnection';
import { useVmShutdown } from './hooks/useVmShutdown';
import { useVmEnvironment } from './hooks/useVmEnvironment';
import { useAgentStatus } from '../hooks/useAgentStatus';
import { useProject } from '@/contexts/ProjectContext';
import { DEFAULT_SCREEN_CONFIG, DEFAULT_VM_NAME } from './constants';
import type { ConnectionType, ScreenConfig } from './types';

interface ScreenViewerProps {
  streamUrl?: string;
  initialVmName?: string;
  initialEnvId?: string;
  isFullscreen?: boolean;
  onToggleFullscreen?: () => void;
}

export default function ScreenViewer({ initialVmName, initialEnvId, isFullscreen, onToggleFullscreen }: ScreenViewerProps) {
  // 当前版本仅支持 Local VM；保留 connectionType 相关代码以便未来恢复 remote
  const [connectionType, setConnectionType] = useState<ConnectionType>('local');
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [config, setConfig] = useState<ScreenConfig>(() => ({
    ...DEFAULT_SCREEN_CONFIG,
    vmName: initialVmName || DEFAULT_VM_NAME,
  }));

  const { currentProject } = useProject();
  const projectsRootPath = useMemo(() => {
    if (!currentProject?.path) return undefined;
    const parts = currentProject.path.replace(/\\/g, '/').replace(/\/+$/, '').split('/');
    parts.pop();
    return parts.join('\\');
  }, [currentProject?.path]);

  // 当外部 Tab 切换传入不同 vmName 时，同步到本地 config
  useEffect(() => {
    if (!initialVmName) return;
    setConfig(prev => (prev.vmName === initialVmName ? prev : { ...prev, vmName: initialVmName }));
  }, [initialVmName]);

  // 检查 Hyper-V 和 VM 环境
  const vmEnv = useVmEnvironment(config.vmName);
  
  // 检查 Agent 状态
  const agentStatus = useAgentStatus();

  // 当 VM 状态变为 ready 时，自动检查 Agent 状态
  useEffect(() => {
    if (vmEnv.status === 'ready') {
      agentStatus.checkStatus(config.vmName);
    }
  }, [vmEnv.status, config.vmName]);

  const vnc = useVncConnection({ config });

  const local = useLocalVmAutoConnect({
    config,
    setConfig,
    connect: vnc.connect,
    rfbRef: vnc.rfbRef,
    onVmMissing: () => {
      vnc.disconnect();
      vmEnv.recheckEnvironment();
    },
    projectsRootPath,
  });

  const remote = useRemoteConnection({
    config,
    connect: vnc.connect,
  });

  const shutdown = useVmShutdown({
    vmName: config.vmName,
    onDisconnected: () => {
      // 断开 VNC 连接
      vnc.disconnect();
      // 重置本地 / 远程连接状态和错误信息
      local.resetAutoConnectState();
      remote.resetRemoteState();
    },
  });

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    if (name === 'wsPort' || name === 'vncPort' || name === 'width' || name === 'height') {
      setConfig(prev => ({ ...prev, [name]: Number(value) }));
    } else {
      setConfig(prev => ({ ...prev, [name]: value }));
    }
  };

  const handleConnectionTypeChange = (type: ConnectionType) => {
    // NOTE: 目前不开放 Remote 模式，保留代码但屏蔽切换
    if (type !== 'local') return;
    setConnectionType('local');
    local.resetAutoConnectState();
    // remote.resetRemoteState(); // kept for future
  };

  const activeAutoConnectStep =
    connectionType === 'local' ? local.autoConnectStep : remote.autoConnectStep;
  const activeErrorMessage = connectionType === 'local' ? local.errorMessage : remote.errorMessage;
  const resetLocalAutoConnectState = local.resetAutoConnectState;
  const recheckVmEnvironment = vmEnv.recheckEnvironment;
  const disconnectVnc = vnc.disconnect;

  useEffect(() => {
    const message = String(activeErrorMessage || '').toLowerCase();
    if (!message) return;
    if (/virtual machine .* not found|unable to find a virtual machine/.test(message)) {
      disconnectVnc();
      resetLocalAutoConnectState();
      recheckVmEnvironment();
    }
  }, [activeErrorMessage, disconnectVnc, recheckVmEnvironment, resetLocalAutoConnectState]);

  return (
    <div className="h-full flex flex-col">
      <ConnectionTopBar
        isConnected={vnc.isConnected}
        connectionType={connectionType}
        config={config}
        isFullscreen={isFullscreen}
        onToggleFullscreen={onToggleFullscreen}
        onOpenShutdown={connectionType === 'local' ? shutdown.openShutdownModal : undefined}
      />

      {/* Screen area */}
      <div className="flex-1 relative bg-canvas overflow-hidden group">
        {/* decorative background */}
        <div
          className="absolute inset-0 opacity-[0.03] pointer-events-none"
          style={{
            backgroundImage: `radial-gradient(#000 1px, transparent 1px)`,
            backgroundSize: '24px 24px',
          }}
        />

        {/* VNC canvas container */}
        <div
          ref={vnc.vncContainerRef}
          className="absolute inset-0 flex items-center justify-center bg-canvas [&>canvas]:max-w-full [&>canvas]:max-h-full"
          style={{
            display: vnc.isConnected ? 'flex' : 'none',
          }}
        />

        {/* 登录过程遮罩：阻止用户操作，展示加载特效 */}
        {vnc.isConnected && connectionType === 'local' && local.isOsLoginInProgress && (
          <div className="absolute inset-0 z-20 flex items-center justify-center bg-black/40 backdrop-blur-[2px] pointer-events-auto">
            <div className="relative flex flex-col items-center justify-center px-6 py-4 bg-black/70 text-white rounded-xl shadow-2xl border border-white/10">
              <div className="relative w-10 h-10 mb-3">
                <div className="absolute inset-0 rounded-full border-2 border-white/10" />
                <div className="absolute inset-0 rounded-full border-2 border-t-orange-400 border-r-orange-300 animate-spin" />
              </div>
              <div className="text-xs font-medium">Signing into desktop...</div>
              <div className="mt-1 text-[10px] text-white/60">
                Please do not use keyboard or mouse during this step.
              </div>
            </div>
          </div>
        )}

        {/* Empty state / connection settings */}
        {!vnc.isConnected && (
          <EmptyStatePanel
            mode={connectionType}
            connectionType={connectionType}
            autoConnectStep={activeAutoConnectStep}
            errorMessage={activeErrorMessage}
            showAdvanced={showAdvanced}
            onToggleAdvanced={() => setShowAdvanced(prev => !prev)}
            onConnectionTypeChange={handleConnectionTypeChange}
            onInputChange={handleInputChange}
            envId={initialEnvId}
            // local
            needPermissionFix={local.needPermissionFix}
            config={config}
            onAutoConnect={local.handleAutoConnect}
            onFixPermission={local.handleFixPermission}
            // remote
            onManualConnect={remote.handleManualConnect}
            // environment check
            vmEnvStatus={vmEnv.status}
            vmEnvError={vmEnv.error}
            onRecheckEnvironment={vmEnv.recheckEnvironment}
            agentStatus={agentStatus}
          />
        )}

        {/* Shutdown modal */}
        <ShutdownModal
          open={shutdown.showShutdownModal}
          vmName={config.vmName}
          isShuttingDown={shutdown.isShuttingDown}
          error={shutdown.shutdownError}
          onCancel={shutdown.closeShutdownModal}
          onConfirm={shutdown.confirmShutdown}
        />
      </div>
    </div>
  );
}


