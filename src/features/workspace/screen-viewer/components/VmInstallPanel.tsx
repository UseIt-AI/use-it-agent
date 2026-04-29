import React, { useState, useEffect, useCallback } from 'react';
import {
  Download,
  HardDrive,
  CheckCircle2,
  XCircle,
  Loader2,
  FolderOpen,
  ExternalLink,
  RefreshCw,
  ChevronDown,
  ChevronRight,
  Box,
  AlertCircle,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import {
  vmCheckEnvironment,
  vmSelectIso,
  vmSelectInstallDir,
  vmInstall,
  vmSelectRestoreDir,
  vmRestoreFromFolder,
} from '../services/vmElectronApi';

type InstallStep =
  | 'idle'
  | 'select_iso'
  | 'installing'
  | 'complete'
  | 'error';

interface InstallProgress {
  step: string;
  stepIndex: number;
  totalSteps: number;
  percent: number;
  message: string;
  error?: string;
}

interface VmInstallPanelProps {
  onInstallComplete: () => void;
  onCancel?: () => void;
  vmName?: string;
  onVmNameChange?: (vmName: string) => void;
  onIsoSelected?: (vmName: string) => void;
}

export function VmInstallPanel({ onInstallComplete, onCancel, vmName, onVmNameChange, onIsoSelected }: VmInstallPanelProps) {
  const { t } = useTranslation();
  const [step, setStep] = useState<InstallStep>('idle');
  const [isoPath, setIsoPath] = useState('');
  const [installDir, setInstallDir] = useState('C:\\VMs');
  const [progress, setProgress] = useState<InstallProgress | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [showIsoConfirm, setShowIsoConfirm] = useState(false);
  const [environmentCheck, setEnvironmentCheck] = useState<{
    hyperVEnabled: boolean;
    freeSpaceGB: number;
  } | null>(null);
  const effectiveVmName = vmName || 'UseIt-Dev-VM';

  useEffect(() => {
    const checkEnv = async () => {
      try {
        const result = await vmCheckEnvironment(installDir);
        setEnvironmentCheck({
          hyperVEnabled: result.hyperVEnabled,
          freeSpaceGB: result.freeSpaceGB,
        });
      } catch (e) {
        console.error('Environment check failed:', e);
      }
    };
    checkEnv();
  }, [installDir]);

  useEffect(() => {
    if (!window.electron?.onVmInstallProgress) return;

    const unsubscribe = window.electron.onVmInstallProgress((progressData: InstallProgress) => {
      setProgress(progressData);
      
      if (progressData.step === 'complete') {
        setStep('complete');
      } else if (progressData.step === 'error') {
        setStep('error');
        setError(progressData.error || t('workspace.vmInstall.error.installFailed'));
      }
    });

    return () => {
      if (unsubscribe) unsubscribe();
    };
  }, [t]);

  const handleSelectIso = useCallback(async () => {
    try {
      const result = await vmSelectIso();
      if (!result.canceled && result.path) {
        setIsoPath(result.path);
        const driveMatch = /^([a-zA-Z]:)\\/.exec(result.path);
        if (driveMatch) {
          setInstallDir(`${driveMatch[1]}\\VMs`);
        }
        onIsoSelected?.(effectiveVmName);
        setStep('select_iso');
      }
    } catch (e: any) {
      if (!e.message.includes('cancelled')) {
        setError(e.message);
      }
    }
  }, [effectiveVmName, onIsoSelected]);

  const openIsoConfirm = useCallback(() => {
    setError(null);
    setShowIsoConfirm(true);
  }, []);

  const handleConfirmSelectIso = useCallback(async () => {
    setShowIsoConfirm(false);
    await handleSelectIso();
  }, [handleSelectIso]);

  const renderIsoConfirmModal = () => {
    if (!showIsoConfirm) return null;
    return (
      <div className="absolute inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-[1px]">
        <div className="w-[380px] bg-white border border-black/10 shadow-xl overflow-hidden animate-in fade-in zoom-in-95 duration-200">
          <div className="px-5 pt-5 pb-4">
            <h3 className="text-base font-bold text-black/90">{t('workspace.vmInstall.isoConfirm.title')}</h3>
            <p className="text-sm text-black/50 mt-1.5">
              {t('workspace.vmInstall.isoConfirm.subtitle')}
            </p>
          </div>
          
          <div className="px-5 pb-5 space-y-2">
            <button
              onClick={handleConfirmSelectIso}
              className="w-full px-4 py-2.5 bg-black hover:bg-black/80 text-white text-sm font-bold transition-colors"
            >
              {t('workspace.vmInstall.isoConfirm.yesSelect')}
            </button>
            <button
              onClick={() => {
                setShowIsoConfirm(false);
                window.open('https://www.microsoft.com/en-us/evalcenter/download-windows-11-iot-enterprise-ltsc-eval');
              }}
              className="w-full px-4 py-2.5 border border-black/[0.08] text-black/60 hover:bg-black/[0.02] text-sm font-medium transition-colors"
            >
              {t('workspace.vmInstall.isoConfirm.notYet')}
            </button>
            <button
              onClick={() => setShowIsoConfirm(false)}
              className="w-full px-4 py-2 text-black/40 hover:text-black/70 text-sm font-medium transition-colors"
            >
              {t('workspace.vmInstall.isoConfirm.cancel')}
            </button>
          </div>
        </div>
      </div>
    );
  };

  const handleSelectInstallDir = useCallback(async () => {
    try {
      const result = await vmSelectInstallDir();
      if (!result.canceled && result.path) {
        setInstallDir(result.path);
      }
    } catch (e: any) {
      if (!e.message.includes('cancelled') && !e.message.includes('canceled')) {
        setError(e.message);
      }
    }
  }, []);

  const handleStartInstall = useCallback(async () => {
    if (!isoPath) {
      setError(t('workspace.vmInstall.error.selectIso'));
      return;
    }

    setStep('installing');
    setError(null);

    try {
      const result = await vmInstall({
        isoPath,
        installDir,
        vmName: effectiveVmName,
      });

      if (!result.success) {
        setStep('error');
        setError(result.error || t('workspace.vmInstall.error.installFailed'));
      }
    } catch (e: any) {
      setStep('error');
      setError(e.message);
    }
  }, [isoPath, installDir, effectiveVmName, t]);

  const handleRestoreFromFolder = useCallback(async () => {
    setError(null);
    try {
      const selected = await vmSelectRestoreDir();
      if (selected.canceled || !selected.path) {
        return;
      }

      setStep('installing');
      setProgress({
        step: 'restore_from_folder',
        stepIndex: 1,
        totalSteps: 2,
        percent: 45,
        message: t('workspace.vmInstall.restore.importing'),
      });

      const result = await vmRestoreFromFolder({
        vmName: effectiveVmName,
        folderPath: selected.path,
      });

      if (!result.success) {
        setStep('error');
        setError(result.error || t('workspace.vmInstall.error.restoreFailed'));
        return;
      }

      const restoredVmName = result.vmName || effectiveVmName;
      onVmNameChange?.(restoredVmName);
      onIsoSelected?.(restoredVmName);
      window.dispatchEvent(new CustomEvent('environments-updated'));

      setProgress({
        step: 'restore_from_folder',
        stepIndex: 2,
        totalSteps: 2,
        percent: 100,
        message: result.restoreMode === 'disk_fallback'
          ? t('workspace.vmInstall.restore.completedDiskFallback')
          : (typeof result.checkpointCount === 'number'
            ? t('workspace.vmInstall.restore.completedWithCheckpoints', { count: result.checkpointCount })
            : t('workspace.vmInstall.restore.completed')),
      });
      setStep('complete');

      onInstallComplete();
    } catch (e: any) {
      setStep('error');
      setError(e.message || t('workspace.vmInstall.error.restoreFailed'));
    }
  }, [effectiveVmName, onInstallComplete, onIsoSelected, onVmNameChange, t]);

  const renderVmNameEditor = () => {
    return (
      <div className="bg-white border border-black/[0.08] p-4">
        <label className="text-[10px] font-bold text-black/50 uppercase tracking-wider">
          {t('workspace.vmInstall.vmNameLabel')}
        </label>
        <input
          type="text"
          value={effectiveVmName}
          onChange={(e) => onVmNameChange?.(e.target.value)}
          className="mt-2 w-full px-3 py-2 bg-[#FAFAFA] border border-black/[0.08] text-sm font-mono focus:outline-none focus:border-black/20 focus:bg-white transition-all"
        />
        <p className="text-xs text-black/40 mt-2">
          {t('workspace.vmInstall.vmNameHint')}
        </p>
      </div>
    );
  };

  const handleRetry = useCallback(() => {
    setStep('select_iso');
    setError(null);
    setProgress(null);
  }, []);

  const renderProgressBar = () => {
    if (!progress) return null;

    return (
      <div className="space-y-3">
        <div className="flex items-center justify-between text-xs text-black/50 font-medium">
          <span>{t('workspace.vmInstall.installing.stepOf', { current: progress.stepIndex, total: progress.totalSteps })}</span>
          <span>{progress.percent}%</span>
        </div>
        
        <div className="h-2 bg-black/[0.06] overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-orange-500 to-amber-500 transition-all duration-500"
            style={{ width: `${progress.percent}%` }}
          />
        </div>

        <p className="text-sm text-black/60 text-center">{progress.message}</p>
      </div>
    );
  };

  if (step === 'idle') {
    return (
      <div className="flex flex-col gap-5">
        <div className="space-y-2 text-center">
          <h1 className="text-xl font-black text-black tracking-tight">{t('workspace.vmInstall.idle.title')}</h1>
          <p className="text-sm text-black/50 font-medium">
            {t('workspace.vmInstall.idle.subtitle')}
          </p>
        </div>

        <div className="h-px bg-gradient-to-r from-transparent via-black/10 to-transparent" />

        <button
          onClick={openIsoConfirm}
          className="group relative flex flex-col items-start p-5 bg-white border border-black/[0.08] hover:border-black/20 transition-all text-left overflow-hidden hover:shadow-[0_4px_20px_-4px_rgba(0,0,0,0.1)]"
        >
          <div className="absolute top-0 right-0 w-12 h-12 overflow-hidden">
            <div className="absolute top-0 right-0 w-[1px] h-8 bg-gradient-to-b from-black/10 to-transparent" />
            <div className="absolute top-0 right-0 h-[1px] w-8 bg-gradient-to-l from-black/10 to-transparent" />
          </div>
          
          <div className="w-10 h-10 bg-black/5 text-black/70 flex items-center justify-center transition-colors group-hover:bg-black group-hover:text-white">
            <Box className="w-5 h-5" />
          </div>
          
          <div className="mt-4 space-y-3 flex-1 w-full">
            <div className="space-y-1.5">
              <h3 className="font-bold text-[15px] text-black/90 group-hover:text-black leading-tight">
                {t('workspace.vmInstall.idle.setupSteps')}
              </h3>
              
              <div className="space-y-2 pt-2">
                <div className="flex items-start gap-2.5">
                  <div className="w-5 h-5 bg-black text-white flex items-center justify-center text-[10px] font-bold flex-shrink-0">1</div>
                  <div className="flex-1">
                    <div className="flex items-center gap-1.5">
                      <span className="text-xs text-black/70">{t('workspace.vmInstall.idle.step1')}</span>
                      <a
                        href="https://www.microsoft.com/en-us/evalcenter/download-windows-11-iot-enterprise-ltsc-eval"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-blue-500 hover:text-blue-600"
                        onClick={(e) => {
                          e.stopPropagation();
                          e.preventDefault();
                          window.open('https://www.microsoft.com/en-us/evalcenter/download-windows-11-iot-enterprise-ltsc-eval');
                        }}
                      >
                        <ExternalLink className="w-3 h-3" />
                      </a>
                    </div>
                    <p className="text-[10px] text-black/40 leading-relaxed">
                      {t('workspace.vmInstall.idle.step1Desc')}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2.5">
                  <div className="w-5 h-5 bg-black/[0.06] text-black/40 flex items-center justify-center text-[10px] font-bold flex-shrink-0">2</div>
                  <span className="text-xs text-black/50">{t('workspace.vmInstall.idle.step2')}</span>
                </div>

                <div className="flex items-center gap-2.5">
                  <div className="w-5 h-5 bg-black/[0.06] text-black/40 flex items-center justify-center text-[10px] font-bold flex-shrink-0">3</div>
                  <span className="text-xs text-black/50">{t('workspace.vmInstall.idle.step3')}</span>
                </div>
              </div>
            </div>

            <div className="pt-2 border-t border-black/[0.05]" onClick={(e) => e.stopPropagation()}>
              <label className="text-[10px] font-bold text-black/40 uppercase tracking-wider">{t('workspace.vmInstall.vmNameLabel')}</label>
              <input
                type="text"
                value={effectiveVmName}
                onChange={(e) => onVmNameChange?.(e.target.value)}
                className="mt-1.5 w-full px-2.5 py-1.5 bg-[#FAFAFA] border border-black/[0.08] text-xs font-mono focus:outline-none focus:border-black/20 focus:bg-white transition-all"
              />
            </div>
          </div>
          
          <div className="mt-4 flex items-center gap-1.5 px-3 py-1.5 text-[10px] text-black/50 font-semibold uppercase tracking-wider group-hover:text-black/70 transition-colors">
            <FolderOpen className="w-3 h-3" />
            <span>{t('workspace.vmInstall.idle.selectIso')}</span>
          </div>
          
          <div className="absolute bottom-0 left-0 right-0 h-[2px] bg-black scale-x-0 group-hover:scale-x-100 transition-transform origin-left" />
        </button>

        <button
          onClick={handleRestoreFromFolder}
          className="group relative flex flex-col items-start p-5 bg-white border border-black/[0.08] hover:border-black/20 transition-all text-left overflow-hidden hover:shadow-[0_4px_20px_-4px_rgba(0,0,0,0.1)]"
        >
          <div className="w-10 h-10 bg-black/5 text-black/70 flex items-center justify-center transition-colors group-hover:bg-black group-hover:text-white">
            <FolderOpen className="w-5 h-5" />
          </div>
          <div className="mt-4 space-y-1.5 w-full">
            <h3 className="font-bold text-[15px] text-black/90 leading-tight">
              {t('workspace.vmInstall.idle.restoreTitle')}
            </h3>
            <p className="text-[11px] text-black/45 leading-relaxed">
              {t('workspace.vmInstall.idle.restoreDesc')}
            </p>
          </div>
          <div className="mt-4 flex items-center gap-1.5 px-3 py-1.5 text-[10px] text-black/50 font-semibold uppercase tracking-wider group-hover:text-black/70 transition-colors">
            <FolderOpen className="w-3 h-3" />
            <span>{t('workspace.vmInstall.idle.selectVmFolder')}</span>
          </div>
          <div className="absolute bottom-0 left-0 right-0 h-[2px] bg-black scale-x-0 group-hover:scale-x-100 transition-transform origin-left" />
        </button>

        {environmentCheck && (
          <div className={`flex items-center justify-center gap-2 text-xs font-medium ${
            environmentCheck.hyperVEnabled ? 'text-emerald-600' : 'text-red-600'
          }`}>
            {environmentCheck.hyperVEnabled ? (
              <CheckCircle2 className="w-4 h-4" />
            ) : (
              <XCircle className="w-4 h-4" />
            )}
            <span>{environmentCheck.hyperVEnabled ? t('workspace.vmInstall.idle.envReady') : t('workspace.vmInstall.idle.envRequired')}</span>
          </div>
        )}

        {renderIsoConfirmModal()}
      </div>
    );
  }

  if (step === 'select_iso') {
    return (
      <div className="flex flex-col gap-5">
        <div className="space-y-2 text-center">
          <h1 className="text-xl font-black text-black tracking-tight">{t('workspace.vmInstall.config.title')}</h1>
          <p className="text-sm text-black/50 font-medium">
            {t('workspace.vmInstall.config.subtitle')}
          </p>
        </div>

        <div className="h-px bg-gradient-to-r from-transparent via-black/10 to-transparent" />

        <div className="group relative flex flex-col items-start p-5 bg-gradient-to-br from-emerald-50/60 via-emerald-50/30 to-stone-50 border border-emerald-200/40 text-left overflow-hidden">
          <div className="absolute top-0 right-0 w-16 h-16 overflow-hidden">
            <div className="absolute top-0 right-0 w-[1.5px] h-10 bg-gradient-to-b from-emerald-300/50 to-transparent" />
            <div className="absolute top-0 right-0 h-[1.5px] w-10 bg-gradient-to-l from-emerald-300/50 to-transparent" />
          </div>
          
          <div className="w-10 h-10 bg-emerald-500 text-white flex items-center justify-center">
            <CheckCircle2 className="w-5 h-5" />
          </div>
          
          <div className="mt-4 space-y-1.5 w-full">
            <h3 className="font-bold text-[15px] text-emerald-800 leading-tight">
              {t('workspace.vmInstall.config.isoSelected')}
            </h3>
            <p className="text-xs text-emerald-600/70 truncate font-mono" title={isoPath}>
              {isoPath}
            </p>
          </div>

          <button
            onClick={openIsoConfirm}
            className="mt-3 text-[10px] text-emerald-600 font-medium hover:text-emerald-700 transition-colors"
          >
            {t('workspace.vmInstall.config.changeIso')}
          </button>
        </div>

        <div className="group relative flex flex-col items-start p-5 bg-white border border-black/[0.08] text-left overflow-hidden">
          <div className="absolute top-0 right-0 w-12 h-12 overflow-hidden">
            <div className="absolute top-0 right-0 w-[1px] h-8 bg-gradient-to-b from-black/10 to-transparent" />
            <div className="absolute top-0 right-0 h-[1px] w-8 bg-gradient-to-l from-black/10 to-transparent" />
          </div>
          
          <div className="w-10 h-10 bg-black/5 text-black/70 flex items-center justify-center">
            <HardDrive className="w-5 h-5" />
          </div>
          
          <div className="mt-4 space-y-4 w-full">
            <div>
              <label className="text-[10px] font-bold text-black/40 uppercase tracking-wider">{t('workspace.vmInstall.vmNameLabel')}</label>
              <input
                type="text"
                value={effectiveVmName}
                onChange={(e) => onVmNameChange?.(e.target.value)}
                className="mt-1.5 w-full px-2.5 py-1.5 bg-[#FAFAFA] border border-black/[0.08] text-xs font-mono focus:outline-none focus:border-black/20 focus:bg-white transition-all"
              />
            </div>

            <div>
              <label className="text-[10px] font-bold text-black/40 uppercase tracking-wider">{t('workspace.vmInstall.config.installDir')}</label>
              <div className="mt-1.5 flex gap-2">
                <input
                  type="text"
                  value={installDir}
                  onChange={(e) => setInstallDir(e.target.value)}
                  className="flex-1 px-2.5 py-1.5 bg-[#FAFAFA] border border-black/[0.08] text-xs font-mono focus:outline-none focus:border-black/20 focus:bg-white transition-all"
                />
                <button
                  onClick={handleSelectInstallDir}
                  className="px-3 py-1.5 bg-black/5 hover:bg-black/10 text-black/60 text-[10px] font-medium transition-colors"
                >
                  {t('workspace.vmInstall.config.browse')}
                </button>
              </div>
              {environmentCheck && (
                <p className={`mt-1.5 text-[10px] font-medium ${
                  environmentCheck.freeSpaceGB >= 30 ? 'text-black/40' : 'text-red-500'
                }`}>
                  {installDir.match(/^([a-zA-Z]):/)?.[1]?.toUpperCase() || 'C'}: {t('workspace.vmInstall.config.freeSpace', { size: environmentCheck.freeSpaceGB })}
                  {environmentCheck.freeSpaceGB < 30 && ` — ${t('workspace.vmInstall.config.needSpace', { size: 30 })}`}
                </p>
              )}
            </div>

            <div className="border-t border-black/[0.05] pt-3">
              <button
                onClick={() => setShowAdvanced(!showAdvanced)}
                className="flex items-center gap-1.5 text-[10px] font-medium text-black/40 hover:text-black/60 transition-colors"
              >
                {showAdvanced ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                <span>{t('workspace.vmInstall.config.advancedSettings')}</span>
              </button>
              {showAdvanced && (
                <div className="mt-2 pl-4 text-[10px] text-black/50 space-y-1">
                  <p><span className="text-black/40">{t('workspace.vmInstall.config.username')}</span> useit</p>
                  <p><span className="text-black/40">{t('workspace.vmInstall.config.password')}</span> 12345678</p>
                  <p><span className="text-black/40">{t('workspace.vmInstall.config.vncPort')}</span> 5900</p>
                </div>
              )}
            </div>
          </div>
        </div>

        {error && (
          <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-100 text-xs text-red-600">
            <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        <button
          onClick={handleStartInstall}
          className="w-full px-4 py-3 bg-black hover:bg-black/80 text-white text-sm font-bold transition-colors flex items-center justify-center gap-2"
        >
          <Download className="w-4 h-4" />
          {t('workspace.vmInstall.config.startInstall')}
        </button>

        {renderIsoConfirmModal()}
      </div>
    );
  }

  if (step === 'installing') {
    return (
      <div className="flex flex-col gap-5">
        <div className="space-y-2 text-center">
          <h1 className="text-xl font-black text-black tracking-tight">{t('workspace.vmInstall.installing.title')}</h1>
          <p className="text-sm text-black/50 font-medium">
            {t('workspace.vmInstall.installing.subtitle')}
          </p>
        </div>

        <div className="h-px bg-gradient-to-r from-transparent via-black/10 to-transparent" />

        <div className="group relative flex flex-col items-start p-5 bg-gradient-to-br from-orange-50/60 via-amber-50/30 to-stone-50 border border-orange-200/40 text-left overflow-hidden">
          <div 
            className="absolute inset-0 opacity-[0.12] pointer-events-none"
            style={{
              backgroundImage: 'linear-gradient(to right, rgb(194 114 63 / 0.35) 1px, transparent 1px), linear-gradient(to bottom, rgb(194 114 63 / 0.35) 1px, transparent 1px)',
              backgroundSize: '20px 20px'
            }}
          />
          
          <div className="w-10 h-10 bg-gradient-to-br from-orange-400 to-amber-500 text-white flex items-center justify-center relative z-10">
            <Loader2 className="w-5 h-5 animate-spin" />
          </div>
          
          <div className="mt-4 w-full relative z-10">
            {renderProgressBar()}
          </div>
        </div>

        <div className="flex items-center justify-center gap-2 text-[11px] text-black/30 font-medium">
          <AlertCircle className="w-3.5 h-3.5" />
          <span>{t('workspace.vmInstall.installing.doNotClose')}</span>
        </div>
      </div>
    );
  }

  if (step === 'complete') {
    return (
      <div className="flex flex-col gap-5">
        <div className="space-y-2 text-center">
          <h1 className="text-xl font-black text-black tracking-tight">{t('workspace.vmInstall.complete.title')}</h1>
          <p className="text-sm text-black/50 font-medium">
            {t('workspace.vmInstall.complete.subtitle')}
          </p>
        </div>

        <div className="h-px bg-gradient-to-r from-transparent via-black/10 to-transparent" />

        <button
          onClick={onInstallComplete}
          className="group relative flex flex-col items-start p-5 bg-gradient-to-br from-emerald-50/60 via-emerald-50/30 to-stone-50 border border-emerald-200/40 hover:border-emerald-300/60 transition-all text-left overflow-hidden hover:shadow-[0_8px_30px_-8px_rgba(16,185,129,0.2)]"
        >
          <div 
            className="absolute -top-20 -right-20 w-40 h-40 opacity-30 group-hover:opacity-50 transition-opacity pointer-events-none"
            style={{
              background: 'radial-gradient(circle, rgba(16,185,129,0.4) 0%, transparent 70%)'
            }}
          />
          
          <div className="absolute top-0 right-0 w-16 h-16 overflow-hidden">
            <div className="absolute top-0 right-0 w-[1.5px] h-10 bg-gradient-to-b from-emerald-300/50 to-transparent" />
            <div className="absolute top-0 right-0 h-[1.5px] w-10 bg-gradient-to-l from-emerald-300/50 to-transparent" />
          </div>
          
          <div className="w-10 h-10 bg-gradient-to-br from-emerald-400 to-emerald-600 text-white flex items-center justify-center transition-all group-hover:shadow-md relative z-10">
            <CheckCircle2 className="w-5 h-5" />
          </div>
          
          <div className="mt-4 space-y-1.5 flex-1 relative z-10">
            <h3 className="font-bold text-[15px] text-emerald-800 group-hover:text-emerald-900 leading-tight">
              {t('workspace.vmInstall.complete.vmReady')}
            </h3>
            <p className="text-xs text-emerald-600/70 leading-relaxed">
              {t('workspace.vmInstall.complete.clickConnect')}
            </p>
          </div>
          
          <div className="mt-4 flex items-center gap-1.5 px-3 py-1.5 text-[10px] text-emerald-600/70 font-semibold uppercase tracking-wider group-hover:text-emerald-700 transition-colors relative z-10">
            <Box className="w-3 h-3" />
            <span>{t('workspace.vmInstall.complete.connectNow')}</span>
          </div>
          
          <div className="absolute bottom-0 left-0 right-0 h-[2px] bg-gradient-to-r from-emerald-400/80 to-emerald-500/80 scale-x-0 group-hover:scale-x-100 transition-transform origin-left" />
        </button>
      </div>
    );
  }

  if (step === 'error') {
    return (
      <div className="flex flex-col gap-5">
        <div className="space-y-2 text-center">
          <h1 className="text-xl font-black text-black tracking-tight">{t('workspace.vmInstall.error.title')}</h1>
          <p className="text-sm text-black/50 font-medium">
            {t('workspace.vmInstall.error.subtitle')}
          </p>
        </div>

        <div className="h-px bg-gradient-to-r from-transparent via-black/10 to-transparent" />

        <div className="group relative flex flex-col items-start p-5 bg-red-50/50 border border-red-200/40 text-left overflow-hidden">
          <div className="absolute top-0 right-0 w-16 h-16 overflow-hidden">
            <div className="absolute top-0 right-0 w-[1.5px] h-10 bg-gradient-to-b from-red-300/50 to-transparent" />
            <div className="absolute top-0 right-0 h-[1.5px] w-10 bg-gradient-to-l from-red-300/50 to-transparent" />
          </div>
          
          <div className="w-10 h-10 bg-red-100 text-red-500 flex items-center justify-center">
            <XCircle className="w-5 h-5" />
          </div>
          
          <div className="mt-4 space-y-1.5 w-full">
            <h3 className="font-bold text-[15px] text-red-800 leading-tight">
              {t('workspace.vmInstall.error.details')}
            </h3>
            <p className="text-xs text-red-600/80 leading-relaxed">
              {error}
            </p>
          </div>
        </div>

        <button
          onClick={handleRetry}
          className="w-full px-4 py-3 bg-black hover:bg-black/80 text-white text-sm font-bold transition-colors flex items-center justify-center gap-2"
        >
          <RefreshCw className="w-4 h-4" />
          {t('workspace.vmInstall.error.tryAgain')}
        </button>
      </div>
    );
  }

  return null;
}
