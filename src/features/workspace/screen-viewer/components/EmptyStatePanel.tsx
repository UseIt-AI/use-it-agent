import React, { useState, useEffect } from 'react';
import {
  Monitor,
  Loader2,
  AlertCircle,
  Laptop,
  Cloud,
  Settings2,
  ChevronDown,
  ChevronRight,
  Power,
  Download,
  RefreshCw,
  AlertTriangle,
  Play,
  Zap,
  Eye,
  EyeOff,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { AutoConnectStep, ConnectionType, ScreenConfig } from '../types';
import type { VmEnvironmentStatus } from '../hooks/useVmEnvironment';
import type { UseAgentStatusResult } from '../../hooks/useAgentStatus';
import { VmInstallPanel } from './VmInstallPanel';
import { vmEnableHyperV, getVmStatus } from '../services/vmElectronApi';

interface BaseProps {
  connectionType: ConnectionType;
  autoConnectStep: AutoConnectStep;
  errorMessage: string;
  showAdvanced: boolean;
  onToggleAdvanced: () => void;
  onConnectionTypeChange: (type: ConnectionType) => void;
  onInputChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  // 来自 Workspace/ControlPanel 的 environment id（用于同步配置）
  envId?: string;
  // environment check
  vmEnvStatus: VmEnvironmentStatus;
  vmEnvError: string | null;
  onRecheckEnvironment: () => void;
  // agent status
  agentStatus?: UseAgentStatusResult;
}

interface LocalProps extends BaseProps {
  mode: 'local';
  needPermissionFix: boolean;
  config: ScreenConfig;
  onAutoConnect: () => void;
  onFixPermission: () => void;
}

interface RemoteProps extends BaseProps {
  mode: 'cloud';
  config: ScreenConfig;
  onManualConnect: () => void;
}

type EmptyStatePanelProps = LocalProps | RemoteProps;

const RAW_COMMAND_PATTERN = /powershell\s+-command/i;

function sanitizeVmErrorMessage(message: string | null | undefined, t: (key: string) => string): string {
  if (!message) return '';
  if (RAW_COMMAND_PATTERN.test(message)) {
    return t('workspace.vmConnect.sanitizedError');
  }
  return message;
}

export function EmptyStatePanel(props: EmptyStatePanelProps) {
  const {
    connectionType,
    autoConnectStep,
    errorMessage,
    showAdvanced,
    onToggleAdvanced,
    onConnectionTypeChange,
    vmEnvStatus,
    vmEnvError,
    onRecheckEnvironment,
  } = props;

  const isBusy = autoConnectStep !== 'idle' && autoConnectStep !== 'error';
  const isEnvChecking = vmEnvStatus === 'checking';

  // 是否使用新的卡片布局（VM 未安装时用宽布局）
  const useWideLayout = vmEnvStatus === 'no_vm';

  return (
    <div className="absolute inset-0 bg-[#FAFAFA] flex flex-col items-center justify-center overflow-y-auto font-sans selection:bg-black/5">
      {/* Subtle background pattern */}
      <div 
        className="absolute inset-0 opacity-[0.4] pointer-events-none"
        style={{
          backgroundImage: 'radial-gradient(circle at 1px 1px, rgba(0,0,0,0.03) 1px, transparent 0)',
          backgroundSize: '24px 24px'
        }}
      />

      <div className={`w-full ${useWideLayout ? 'max-w-[520px]' : 'max-w-[340px]'} px-8 py-12 flex flex-col gap-5 relative z-10`}>
        {/*
          Connection type selector (Local/Remote)
          NOTE: 当前版本仅支持 Local VM，先不暴露 Remote 入口；代码保留以便未来恢复。
        */}
        {/*
        <div className="grid grid-cols-2 gap-2">
          <button
            onClick={() => onConnectionTypeChange('local')}
            disabled={isBusy || isEnvChecking}
            className={`flex items-center justify-center gap-2 p-2.5 border transition-all disabled:opacity-50 ${
              connectionType === 'local'
                ? 'border-orange-400 bg-orange-50 text-orange-700'
                : 'border-divider bg-white text-black/60 hover:bg-black/5'
            }`}
          >
            <Laptop className="w-4 h-4" />
            <span className="text-xs font-medium">Local</span>
          </button>
          <button
            onClick={() => onConnectionTypeChange('cloud')}
            disabled={isBusy || isEnvChecking}
            className={`flex items-center justify-center gap-2 p-2.5 border transition-all disabled:opacity-50 ${
              connectionType === 'cloud'
                ? 'border-orange-400 bg-orange-50 text-orange-700'
                : 'border-divider bg-white text-black/60 hover:bg-black/5'
            }`}
          >
            <Cloud className="w-4 h-4" />
            <span className="text-xs font-medium">Remote</span>
          </button>
        </div>
        */}

        {/* NOTE: 当前版本固定 Local，RemoteModeSection 保留但不渲染 */}
        <LocalModeSection
          {...(props as LocalProps)}
          isBusy={isBusy}
          isEnvChecking={isEnvChecking}
          showAdvanced={showAdvanced}
          onToggleAdvanced={onToggleAdvanced}
          vmEnvStatus={vmEnvStatus}
          vmEnvError={vmEnvError}
          errorMessage={errorMessage}
          onRecheckEnvironment={onRecheckEnvironment}
          agentStatus={props.agentStatus}
        />
        {/*
        <RemoteModeSection
          {...props}
          isBusy={isBusy}
          showAdvanced={showAdvanced}
          onToggleAdvanced={onToggleAdvanced}
        />
        */}
      </div>
    </div>
  );
}

interface LocalModeSectionProps extends LocalProps {
  isBusy: boolean;
  isEnvChecking: boolean;
  showAdvanced: boolean;
  onToggleAdvanced: () => void;
  vmEnvStatus: VmEnvironmentStatus;
  vmEnvError: string | null;
  errorMessage: string;
  onRecheckEnvironment: () => void;
  agentStatus?: UseAgentStatusResult;
}

function LocalModeSection({
  autoConnectStep,
  needPermissionFix,
  config,
  onAutoConnect,
  onFixPermission,
  isBusy,
  isEnvChecking,
  showAdvanced,
  onToggleAdvanced,
  onInputChange,
  envId,
  vmEnvStatus,
  vmEnvError,
  errorMessage,
  onRecheckEnvironment,
  agentStatus,
}: LocalModeSectionProps) {
  const { t } = useTranslation();
  const [showOsPassword, setShowOsPassword] = useState(false);
  const [isEnablingHyperV, setIsEnablingHyperV] = useState(false);
  const [hyperVActionMessage, setHyperVActionMessage] = useState<string | null>(null);
  const [vmPowerState, setVmPowerState] = useState<string | null>(null);
  const displayErrorMessage = sanitizeVmErrorMessage(errorMessage || vmEnvError, t);

  useEffect(() => {
    if (vmEnvStatus !== 'ready') return;
    let cancelled = false;
    const check = async () => {
      try {
        const state = await getVmStatus(config.vmName);
        if (!cancelled) setVmPowerState(state);
      } catch {
        if (!cancelled) setVmPowerState(null);
      }
    };
    check();
    const interval = setInterval(check, 10_000);
    return () => { cancelled = true; clearInterval(interval); };
  }, [config.vmName, vmEnvStatus]);

  const handleEnableHyperV = async () => {
    try {
      setHyperVActionMessage(null);
      setIsEnablingHyperV(true);
      const result = await vmEnableHyperV();
      if (!result.success) {
        setHyperVActionMessage(t('workspace.vmConnect.noHyperV.enableFailed'));
        return;
      }

      if (result.needsReboot) {
        setHyperVActionMessage(t('workspace.vmConnect.noHyperV.enableNeedsReboot'));
        return;
      }

      setHyperVActionMessage(t('workspace.vmConnect.noHyperV.enableSuccess'));
      onRecheckEnvironment();
    } catch (e: unknown) {
      const fallbackMessage = t('workspace.vmConnect.noHyperV.enableRetryFailed');
      setHyperVActionMessage(sanitizeVmErrorMessage((e as Error)?.message || fallbackMessage, t));
    } finally {
      setIsEnablingHyperV(false);
    }
  };

  // Reset password visibility when VM changes
  React.useEffect(() => {
    setShowOsPassword(false);
  }, [config.vmName]);

  // Helper function to get translated progress message
  const getProgressMessage = () => {
    if (!agentStatus?.progress) return t('deploy.pleaseWait');
    const { messageKey, messageParams, message } = agentStatus.progress;
    if (messageKey) {
      return t(messageKey, messageParams || {});
    }
    return message || t('deploy.pleaseWait');
  };

  // 环境检查中
  if (isEnvChecking) {
    return (
      <div className="flex flex-col gap-5">
        {/* Header */}
        <div className="space-y-2 text-center">
          <h1 className="text-xl font-black text-black tracking-tight">{t('workspace.vmConnect.checking.title')}</h1>
          <p className="text-sm text-black/50 font-medium">
            {t('workspace.vmConnect.checking.subtitle')}
          </p>
        </div>

        <div className="h-px bg-gradient-to-r from-transparent via-black/10 to-transparent" />

        <div className="group relative flex flex-col items-center p-8 bg-white border border-black/[0.08] text-center overflow-hidden">
          <Loader2 className="w-8 h-8 text-black/30 animate-spin" />
          <p className="mt-4 text-xs text-black/50">{t('workspace.vmConnect.checking.pleaseWait')}</p>
        </div>
      </div>
    );
  }

  // Hyper-V 未启用
  if (vmEnvStatus === 'unsupported_system') {
    return (
      <div className="flex flex-col gap-5">
        <div className="space-y-2 text-center">
          <h1 className="text-xl font-black text-black tracking-tight">{t('workspace.vmConnect.unsupported.title')}</h1>
          <p className="text-sm text-black/50 font-medium">
            {t('workspace.vmConnect.unsupported.subtitle')}
          </p>
        </div>

        <div className="h-px bg-gradient-to-r from-transparent via-black/10 to-transparent" />

        <div className="group relative flex flex-col items-start p-5 bg-red-50/50 border border-red-200/40 text-left overflow-hidden">
          <div className="w-10 h-10 bg-red-100 text-red-500 flex items-center justify-center">
            <AlertTriangle className="w-5 h-5" />
          </div>
          <div className="mt-4 space-y-1.5 w-full">
            <h3 className="font-bold text-[15px] text-red-800 leading-tight">
              {t('workspace.vmConnect.unsupported.requirePro')}
            </h3>
            <p className="text-xs text-red-600/80 leading-relaxed">
              {t('workspace.vmConnect.unsupported.requireProDesc')}
            </p>
            {displayErrorMessage && (
              <p className="text-[11px] text-red-700/90 leading-relaxed">
                {displayErrorMessage}
              </p>
            )}
          </div>
        </div>

        <button
          onClick={onRecheckEnvironment}
          className="w-full px-4 py-2.5 bg-white border border-black/[0.08] text-black/60 hover:bg-black/[0.02] text-xs font-medium transition-colors flex items-center justify-center gap-2"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          {t('workspace.vmConnect.recheckEnvironment')}
        </button>
      </div>
    );
  }

  // VM feature 未启用
  if (vmEnvStatus === 'no_hyperv') {
    return (
      <div className="flex flex-col gap-5">
        {/* Header */}
        <div className="space-y-2 text-center">
          <h1 className="text-xl font-black text-black tracking-tight">{t('workspace.vmConnect.noHyperV.title')}</h1>
          <p className="text-sm text-black/50 font-medium">
            {t('workspace.vmConnect.noHyperV.subtitle')}
          </p>
        </div>

        {/* Divider */}
        <div className="h-px bg-gradient-to-r from-transparent via-black/10 to-transparent" />

        {/* Warning Card */}
        <div className="group relative flex flex-col items-start p-5 bg-amber-50/50 border border-amber-200/40 text-left overflow-hidden">
          {/* Decorative corner accent */}
          <div className="absolute top-0 right-0 w-16 h-16 overflow-hidden">
            <div className="absolute top-0 right-0 w-[1.5px] h-10 bg-gradient-to-b from-amber-300/50 to-transparent" />
            <div className="absolute top-0 right-0 h-[1.5px] w-10 bg-gradient-to-l from-amber-300/50 to-transparent" />
          </div>
          
          {/* Icon */}
          <div className="w-10 h-10 bg-amber-100 text-amber-600 flex items-center justify-center">
            <AlertTriangle className="w-5 h-5" />
          </div>
          
          {/* Content */}
          <div className="mt-4 space-y-1.5 w-full">
            <h3 className="font-bold text-[15px] text-amber-800 leading-tight">
              {t('workspace.vmConnect.noHyperV.enableTitle')}
            </h3>
            <p className="text-xs text-amber-600/80 leading-relaxed">
              {t('workspace.vmConnect.noHyperV.enableDesc')}
            </p>
          </div>
        </div>

        {/* Actions */}
        <div className="flex flex-col gap-3">
          <button
            onClick={handleEnableHyperV}
            disabled={isEnablingHyperV}
            className="w-full px-4 py-3 bg-amber-500 hover:bg-amber-600 disabled:bg-amber-300 disabled:cursor-not-allowed text-white text-sm font-bold transition-colors flex items-center justify-center gap-2"
          >
            {isEnablingHyperV ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
            {t('workspace.vmConnect.noHyperV.enableButton')}
          </button>
          <button
            onClick={onRecheckEnvironment}
            className="w-full px-4 py-2.5 bg-white border border-black/[0.08] text-black/60 hover:bg-black/[0.02] text-xs font-medium transition-colors flex items-center justify-center gap-2"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            {t('workspace.vmConnect.recheckEnvironment')}
          </button>
          {hyperVActionMessage && (
            <div className="px-3 py-2 bg-black/[0.03] border border-black/[0.06] text-[11px] text-black/60 leading-relaxed">
              {hyperVActionMessage}
            </div>
          )}
        </div>
      </div>
    );
  }

  // VM 未安装
  if (vmEnvStatus === 'permission_required') {
    return (
      <div className="flex flex-col gap-5">
        <div className="space-y-2 text-center">
          <h1 className="text-xl font-black text-black tracking-tight">{t('workspace.vmConnect.permission.title')}</h1>
          <p className="text-sm text-black/50 font-medium">
            {t('workspace.vmConnect.permission.subtitle')}
          </p>
        </div>

        <div className="h-px bg-gradient-to-r from-transparent via-black/10 to-transparent" />

        <div className="group relative flex flex-col items-start p-5 bg-amber-50/50 border border-amber-200/40 text-left overflow-hidden">
          <div className="w-10 h-10 bg-amber-100 text-amber-600 flex items-center justify-center">
            <AlertTriangle className="w-5 h-5" />
          </div>
          <div className="mt-4 space-y-1.5 w-full">
            <h3 className="font-bold text-[15px] text-amber-800 leading-tight">
              {t('workspace.vmConnect.permission.fixTitle')}
            </h3>
            <p className="text-xs text-amber-600/80 leading-relaxed">
              {t('workspace.vmConnect.permission.fixDesc')}
            </p>
          </div>
        </div>

        <div className="flex flex-col gap-3">
          <button
            onClick={onFixPermission}
            className="w-full px-4 py-3 bg-amber-500 hover:bg-amber-600 text-white text-sm font-bold transition-colors"
          >
            {t('workspace.vmConnect.permission.fixButton')}
          </button>
          <button
            onClick={onRecheckEnvironment}
            className="w-full px-4 py-2.5 bg-white border border-black/[0.08] text-black/60 hover:bg-black/[0.02] text-xs font-medium transition-colors flex items-center justify-center gap-2"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            {t('workspace.vmConnect.recheckEnvironment')}
          </button>
        </div>
      </div>
    );
  }

  // VM 未安装
  if (vmEnvStatus === 'no_vm') {
    return (
      <>
        <VmInstallPanel
          onInstallComplete={onRecheckEnvironment}
          vmName={config.vmName}
          onVmNameChange={(nextName) => {
            // 复用已有 onInputChange（构造一个最小的 event），不新增复杂状态
            onInputChange({ target: { name: 'vmName', value: nextName } } as any);
          }}
          onIsoSelected={async (selectedVmName) => {
            // 进入 ISO selection 后，同步 VM Name 到 environments 配置，让 Available 显示一致
            // NOTE: 只在用户完成 ISO 选择后同步，避免频繁写 config
            try {
              if (!envId || !window.electron?.getAppConfig || !window.electron?.setAppConfig) return;
              const envs = (await window.electron.getAppConfig('environments')) || [];
              const next = Array.isArray(envs)
                ? envs.map((e: any) =>
                    e?.id === envId ? { ...e, name: selectedVmName, vmName: selectedVmName } : e
                  )
                : envs;
              await window.electron.setAppConfig({ environments: next });
              // 通知 ControlPanel 重新加载
              window.dispatchEvent(new CustomEvent('environments-updated'));
            } catch {
              // ignore
            }
          }}
        />
      </>
    );
  }

  // 环境就绪，显示正常的连接 UI
  return (
    <div className="flex flex-col gap-5">
      {/* Header */}
      <div className="space-y-2 text-center">
        <h1 className="text-xl font-black text-black tracking-tight">{t('workspace.vmConnect.connect.title')}</h1>
        <p className="text-sm text-black/50 font-medium">
          {t('workspace.vmConnect.connect.subtitle')}
        </p>
      </div>

      {/* Divider */}
      <div className="h-px bg-gradient-to-r from-transparent via-black/10 to-transparent" />

      {/* Error Message */}
      {displayErrorMessage && (
        <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-100 text-xs text-red-600">
          <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
          <span>{displayErrorMessage}</span>
        </div>
      )}

      {/* Progress indicator - when connecting */}
      {autoConnectStep !== 'idle' && autoConnectStep !== 'error' && (
        <div className="group relative flex flex-col items-start p-5 bg-gradient-to-br from-orange-50/60 via-amber-50/30 to-stone-50 border border-orange-200/40 text-left overflow-hidden">
          {/* Grid pattern overlay */}
          <div 
            className="absolute inset-0 opacity-[0.12] pointer-events-none"
            style={{
              backgroundImage: 'linear-gradient(to right, rgb(194 114 63 / 0.35) 1px, transparent 1px), linear-gradient(to bottom, rgb(194 114 63 / 0.35) 1px, transparent 1px)',
              backgroundSize: '20px 20px'
            }}
          />
          
          {/* Icon */}
          <div className="w-10 h-10 bg-gradient-to-br from-orange-400 to-amber-500 text-white flex items-center justify-center relative z-10">
            <Loader2 className="w-5 h-5 animate-spin" />
          </div>
          
          {/* Content */}
          <div className="mt-4 w-full relative z-10 space-y-3">
            <h3 className="font-bold text-[15px] text-stone-800 leading-tight">
              {t(`workspace.vmConnect.steps.${autoConnectStep === 'waiting_ip' ? 'waitingIp' : autoConnectStep}`)}
            </h3>
            
            {/* Step Progress */}
            <div className="flex items-center w-full">
              {['checking', 'starting', 'waiting_ip', 'connecting'].map((step, idx, arr) => {
                const currentIdx = arr.indexOf(autoConnectStep);
                const isComplete = currentIdx > idx;
                const isCurrent = autoConnectStep === step;
                return (
                  <React.Fragment key={step}>
                    <div
                      className={`w-3 h-3 flex-shrink-0 transition-all duration-300 ${
                        isCurrent
                          ? 'bg-orange-500 ring-2 ring-orange-200 ring-offset-1'
                          : isComplete
                          ? 'bg-emerald-500'
                          : 'bg-black/10'
                      }`}
                    />
                    {idx < arr.length - 1 && (
                      <div
                        className={`flex-1 h-0.5 mx-1.5 transition-colors duration-300 ${
                          isComplete ? 'bg-emerald-500/50' : 'bg-black/10'
                        }`}
                      />
                    )}
                  </React.Fragment>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* Permission fix */}
      {needPermissionFix && (
        <div className="group relative flex flex-col items-start p-5 bg-amber-50/50 border border-amber-200/40 text-left overflow-hidden">
          <div className="w-10 h-10 bg-amber-100 text-amber-600 flex items-center justify-center">
            <AlertTriangle className="w-5 h-5" />
          </div>
          <div className="mt-4 space-y-1.5 w-full">
            <h3 className="font-bold text-[15px] text-amber-800 leading-tight">
              {t('workspace.vmConnect.connect.permissionRequired')}
            </h3>
            <p className="text-xs text-amber-600/80 leading-relaxed">
              {t('workspace.vmConnect.connect.permissionDesc')}
            </p>
          </div>
          <button
            onClick={onFixPermission}
            className="mt-4 px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white text-xs font-bold transition-colors"
          >
            {t('workspace.vmConnect.connect.fixPermission')}
          </button>
        </div>
      )}

      {/* Settings Card (includes Agent status) */}
      <div className="group relative flex flex-col bg-white border border-black/[0.08] text-left overflow-hidden">
        {/* Decorative corner line */}
        <div className="absolute top-0 right-0 w-12 h-12 overflow-hidden pointer-events-none">
          <div className="absolute top-0 right-0 w-[1px] h-8 bg-gradient-to-b from-black/10 to-transparent" />
          <div className="absolute top-0 right-0 h-[1px] w-8 bg-gradient-to-l from-black/10 to-transparent" />
        </div>

        {/* Agent Status Section (if needed) */}
        {agentStatus && (agentStatus.status === 'not_installed' || agentStatus.status === 'outdated') && !isBusy && (
          <div className="p-4 border-b border-black/[0.05] bg-blue-50/30">
            <div className="flex items-center justify-between">
              <div>
                <h4 className="text-xs font-bold text-blue-800">
                  {agentStatus.status === 'not_installed' ? t('workspace.vmConnect.agent.required') : t('workspace.vmConnect.agent.updateAvailable')}
                </h4>
                <p className="text-[10px] text-blue-600/70 mt-0.5">
                  {agentStatus.status === 'not_installed' 
                    ? t('workspace.vmConnect.agent.requiredDesc')
                    : t('workspace.vmConnect.agent.versionAvailable', { version: agentStatus.localVersion })}
                </p>
              </div>
              <button
                onClick={() => agentStatus.installAgent(config.vmName)}
                className="px-3 py-1.5 bg-blue-500 hover:bg-blue-600 text-white text-[10px] font-bold transition-colors flex items-center gap-1.5"
              >
                <Download className="w-3 h-3" />
                {agentStatus.status === 'not_installed' ? t('workspace.vmConnect.agent.install') : t('workspace.vmConnect.agent.update')}
              </button>
            </div>
          </div>
        )}

        {/* Agent Installation Progress */}
        {agentStatus?.status === 'installing' && (
          <div className="p-4 border-b border-black/[0.05] bg-blue-50/30">
            <div className="flex items-center gap-2 mb-2">
              <Loader2 className="w-3.5 h-3.5 text-blue-600 animate-spin" />
              <span className="text-xs font-bold text-blue-800">{t('workspace.vmConnect.agent.installing')}</span>
            </div>
            <div className="w-full bg-blue-200 h-1 overflow-hidden">
              <div 
                className="h-full bg-blue-500 transition-all duration-300"
                style={{ width: `${agentStatus.progress?.percent || 0}%` }}
              />
            </div>
            <p className="text-[10px] text-blue-600/70 mt-1.5 truncate">
              {getProgressMessage()}
            </p>
          </div>
        )}

        {/* Agent Installation Error */}
        {agentStatus?.status === 'error' && agentStatus.error && (
          <div className="p-4 border-b border-black/[0.05] bg-red-50/30">
            <div className="flex items-start gap-2">
              <AlertCircle className="w-3.5 h-3.5 text-red-500 flex-shrink-0 mt-0.5" />
              <div className="flex-1 min-w-0">
                <h4 className="text-xs font-bold text-red-800">{t('workspace.vmConnect.agent.installFailed')}</h4>
                <p className="text-[10px] text-red-600/70 mt-0.5 break-words">{agentStatus.error}</p>
              </div>
              <button
                onClick={() => agentStatus.installAgent(config.vmName)}
                className="px-2.5 py-1 bg-red-500 hover:bg-red-600 text-white text-[10px] font-bold transition-colors flex-shrink-0"
              >
                {t('workspace.vmConnect.agent.retry')}
              </button>
            </div>
          </div>
        )}
        
        {/* VM Settings Section */}
        <button
          onClick={onToggleAdvanced}
          className="flex items-center justify-between w-full px-4 py-3 text-left hover:bg-black/[0.02] transition-colors"
        >
          <div className="flex items-center gap-2">
            <Settings2 className="w-4 h-4 text-black/40" />
            <span className="text-xs font-medium text-black/70">{t('workspace.vmConnect.connect.vmSettings')}</span>
          </div>
          {showAdvanced ? <ChevronDown className="w-4 h-4 text-black/40" /> : <ChevronRight className="w-4 h-4 text-black/40" />}
        </button>

        {showAdvanced && (
          <div className="px-4 pb-4 space-y-3">
            <div>
              <label className="text-[10px] font-bold text-black/40 uppercase tracking-wider">{t('workspace.vmConnect.connect.vmNameLabel')}</label>
              <input
                type="text"
                name="vmName"
                value={config.vmName}
                onChange={onInputChange}
                className="mt-1.5 w-full px-2.5 py-1.5 bg-[#FAFAFA] border border-black/[0.08] text-xs font-mono focus:outline-none focus:border-black/20 focus:bg-white transition-all"
              />
            </div>
            <div>
              <label className="text-[10px] font-bold text-black/40 uppercase tracking-wider">{t('workspace.vmConnect.connect.osPasswordLabel')}</label>
              <div className="relative mt-1.5">
                <input
                  type={showOsPassword ? 'text' : 'password'}
                  name="osPassword"
                  value={config.osPassword}
                  onChange={onInputChange}
                  className="w-full px-2.5 py-1.5 pr-8 bg-[#FAFAFA] border border-black/[0.08] text-xs focus:outline-none focus:border-black/20 focus:bg-white transition-all"
                />
                <button
                  type="button"
                  onClick={() => setShowOsPassword(!showOsPassword)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-black/30 hover:text-black/50 transition-colors"
                >
                  {showOsPassword ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Quick Connect Button */}
      {(autoConnectStep === 'idle' || autoConnectStep === 'error') && (
        <button
          onClick={onAutoConnect}
          disabled={agentStatus?.status === 'installing'}
          className="w-full px-4 py-2.5 bg-black hover:bg-black/80 disabled:bg-black/30 disabled:cursor-not-allowed text-white text-xs font-bold transition-colors flex items-center justify-center gap-2"
        >
          {isBusy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Power className="w-3.5 h-3.5" />}
          {t('workspace.vmConnect.connect.quickConnect')}
        </button>
      )}

      {/* Footer hint */}
      <div className="flex items-center justify-center gap-2 text-[11px] text-black/30 font-medium">
        <span>VM: {config.vmName}</span>
        <span className="w-1 h-1 rounded-full bg-black/20" />
        {vmPowerState ? (
          <div className="flex items-center gap-1.5">
            <span className={`w-1.5 h-1.5 rounded-full ${
              vmPowerState.toLowerCase() === 'running' ? 'bg-emerald-500 animate-pulse' : 'bg-black/25'
            }`} />
            <span>{vmPowerState}</span>
          </div>
        ) : (
          <span>{t('workspace.vmConnect.connect.checking')}</span>
        )}
      </div>
    </div>
  );
}

interface RemoteModeSectionProps extends RemoteProps {
  isBusy: boolean;
  showAdvanced: boolean;
  onToggleAdvanced: () => void;
}

function RemoteModeSection({
  config,
  onManualConnect,
  autoConnectStep,
  isBusy,
  showAdvanced,
  onToggleAdvanced,
  onInputChange,
}: RemoteModeSectionProps) {
  const { t } = useTranslation();
  return (
    <>
      <div className="space-y-2">
        <div>
          <label className="text-[10px] font-medium text-black/50 uppercase">{t('workspace.vmConnect.remote.ipAddress')}</label>
          <input
            type="text"
            name="host"
            placeholder={t('workspace.vmConnect.remote.ipPlaceholder')}
            value={config.host}
            onChange={onInputChange}
            className="mt-1 w-full px-3 py-2 bg-white border border-divider text-xs font-mono focus:border-orange-500 outline-none"
          />
        </div>
        <div>
          <label className="text-[10px] font-medium text-black/50 uppercase">
            {t('workspace.vmConnect.remote.username')}
          </label>
          <input
            type="text"
            name="username"
            placeholder={t('workspace.vmConnect.remote.usernamePlaceholder')}
            value={config.username}
            onChange={onInputChange}
            className="mt-1 w-full px-3 py-2 bg-white border border-divider text-xs focus:border-orange-500 outline-none"
          />
        </div>
      </div>

      <div className="border border-divider bg-white">
        <button
          onClick={onToggleAdvanced}
          className="flex items-center justify-between w-full px-3 h-[36px] text-[11px] font-medium text-black/50 hover:bg-black/5"
        >
          <div className="flex items-center gap-2">
            <Settings2 className="w-3 h-3" />
            <span>{t('workspace.vmConnect.remote.advancedSettings')}</span>
          </div>
          {showAdvanced ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
        </button>

        {showAdvanced && (
          <div className="px-3 pb-3 space-y-2 border-t border-divider">
            <div className="pt-2">
              <label className="text-[10px] font-medium text-black/40 uppercase">{t('workspace.vmConnect.remote.vncPassword')}</label>
              <input
                type="password"
                name="password"
                value={config.password}
                onChange={onInputChange}
                className="mt-1 w-full px-2.5 py-1.5 bg-canvas border border-divider text-xs"
              />
            </div>
            <div>
              <label className="text-[10px] font-medium text-black/40 uppercase">
                {t('workspace.vmConnect.remote.osPassword')}
              </label>
              <input
                type="password"
                name="osPassword"
                value={config.osPassword}
                onChange={onInputChange}
                className="mt-1 w-full px-2.5 py-1.5 bg-canvas border border-divider text-xs"
              />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-[10px] font-medium text-black/40 uppercase">{t('workspace.vmConnect.remote.vncPort')}</label>
                <input
                  type="number"
                  name="vncPort"
                  value={config.vncPort}
                  onChange={onInputChange}
                  className="mt-1 w-full px-2.5 py-1.5 bg-canvas border border-divider text-xs font-mono"
                />
              </div>
              <div>
                <label className="text-[10px] font-medium text-black/40 uppercase">{t('workspace.vmConnect.remote.wsPort')}</label>
                <input
                  type="number"
                  name="wsPort"
                  value={config.wsPort}
                  onChange={onInputChange}
                  className="mt-1 w-full px-2.5 py-1.5 bg-canvas border border-divider text-xs font-mono"
                />
              </div>
            </div>
          </div>
        )}
      </div>

      <button
        onClick={onManualConnect}
        disabled={!config.host || isBusy || autoConnectStep === 'connected'}
        className="w-full px-4 py-3 bg-orange-500 hover:bg-orange-600 disabled:bg-black/20 text-white text-sm font-medium shadow-sm transition-colors flex items-center justify-center gap-2"
      >
        <Monitor className="w-4 h-4" />
        {t('workspace.vmConnect.remote.connect')}
      </button>
    </>
  );
}
