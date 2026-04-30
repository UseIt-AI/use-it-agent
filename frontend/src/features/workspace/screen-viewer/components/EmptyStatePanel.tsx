import React from 'react';
import { Monitor, Settings2, ChevronDown, ChevronRight, Loader2, AlertCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { AutoConnectStep, ScreenConfig } from '../types';

interface EmptyStatePanelProps {
  config: ScreenConfig;
  showAdvanced: boolean;
  onToggleAdvanced: () => void;
  onInputChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  autoConnectStep: AutoConnectStep;
  errorMessage: string;
  onManualConnect: () => void;
}

export function EmptyStatePanel({
  config,
  showAdvanced,
  onToggleAdvanced,
  onInputChange,
  autoConnectStep,
  errorMessage,
  onManualConnect,
}: EmptyStatePanelProps) {
  const { t } = useTranslation();
  const isBusy = autoConnectStep !== 'idle' && autoConnectStep !== 'error';

  return (
    <div className="absolute inset-0 bg-[#FAFAFA] flex flex-col items-center justify-center overflow-y-auto font-sans selection:bg-black/5">
      <div
        className="absolute inset-0 opacity-[0.4] pointer-events-none"
        style={{
          backgroundImage: 'radial-gradient(circle at 1px 1px, rgba(0,0,0,0.03) 1px, transparent 0)',
          backgroundSize: '24px 24px',
        }}
      />

      <div className="w-full max-w-[340px] px-8 py-12 flex flex-col gap-5 relative z-10">
        <div className="space-y-2 text-center">
          <h1 className="text-xl font-black text-black tracking-tight">{t('workspace.vmConnect.remote.connect')}</h1>
          <p className="text-sm text-black/50 font-medium">{t('workspace.vmConnect.connect.subtitle')}</p>
        </div>

        <div className="h-px bg-gradient-to-r from-transparent via-black/10 to-transparent" />

        {errorMessage ? (
          <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-100 text-xs text-red-600">
            <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
            <span>{errorMessage}</span>
          </div>
        ) : null}

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
            <label className="text-[10px] font-medium text-black/50 uppercase">{t('workspace.vmConnect.remote.username')}</label>
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
                <label className="text-[10px] font-medium text-black/40 uppercase">{t('workspace.vmConnect.remote.osPassword')}</label>
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
          onClick={() => void onManualConnect()}
          disabled={!config.host || isBusy || autoConnectStep === 'connected'}
          className="w-full px-4 py-3 bg-orange-500 hover:bg-orange-600 disabled:bg-black/20 text-white text-sm font-medium shadow-sm transition-colors flex items-center justify-center gap-2"
        >
          {isBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Monitor className="w-4 h-4" />}
          {t('workspace.vmConnect.remote.connect')}
        </button>
      </div>
    </div>
  );
}
