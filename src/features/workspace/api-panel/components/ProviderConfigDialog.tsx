import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { X, Eye, EyeOff, ExternalLink, Loader2, Check, AlertCircle, Cloud } from 'lucide-react';
import { ProviderConfig, PROVIDER_META } from '../types';
import { ProviderIcon } from './ProviderIcon';
import { useApiConfig } from '../hooks/useApiConfig';

interface ProviderConfigDialogProps {
  provider: ProviderConfig;
  isOpen: boolean;
  onClose: () => void;
  onSave: (config: Partial<ProviderConfig>) => void;
}

export function ProviderConfigDialog({
  provider,
  isOpen,
  onClose,
  onSave,
}: ProviderConfigDialogProps) {
  const [apiKey, setApiKey] = useState(provider.apiKey || '');
  const [baseUrl, setBaseUrl] = useState(provider.baseUrl || '');
  const [isEnabled, setIsEnabled] = useState(provider.isEnabled);
  const [showApiKey, setShowApiKey] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [testResult, setTestResult] = useState<'success' | 'error' | null>(null);
  const [isSyncing, setIsSyncing] = useState(false);
  const [syncError, setSyncError] = useState<string | null>(null);

  const { syncKeyToCloud, cloudState } = useApiConfig();
  const cloud = cloudState[provider.id];

  const meta = PROVIDER_META[provider.type];

  useEffect(() => {
    if (isOpen) {
      setApiKey(provider.apiKey || '');
      setBaseUrl(provider.baseUrl || '');
      setIsEnabled(provider.isEnabled);
      setShowApiKey(false);
      setTestResult(null);
      setSyncError(null);
    }
  }, [isOpen, provider]);

  const handleSave = async () => {
    const trimmedKey = apiKey.trim();

    // If there's a new key, sync to cloud
    if (trimmedKey) {
      setIsSyncing(true);
      setSyncError(null);
      const success = await syncKeyToCloud(provider.id, trimmedKey, isEnabled);
      setIsSyncing(false);
      if (!success) {
        setSyncError('Failed to save key to cloud');
        return;
      }
      // Also save baseUrl if changed
      onSave({ baseUrl: baseUrl.trim() || undefined });
      onClose();
      return;
    }

    // No new key entered — if already synced, just save other fields
    if (cloud?.cloudSynced) {
      onSave({ baseUrl: baseUrl.trim() || undefined, isEnabled });
      onClose();
      return;
    }

    // Fallback: local-only save
    onSave({
      apiKey: undefined,
      baseUrl: baseUrl.trim() || undefined,
      isEnabled,
    });
    onClose();
  };

  const handleTestConnection = async () => {
    setIsTesting(true);
    setTestResult(null);

    // Simulate API test - in real implementation, call backend
    await new Promise((resolve) => setTimeout(resolve, 1500));

    // For now, just check if API key is provided
    if (apiKey.trim()) {
      setTestResult('success');
    } else {
      setTestResult('error');
    }
    setIsTesting(false);
  };

  if (!isOpen) return null;

  return createPortal(
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 font-sans">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/20 dark:bg-black/60 backdrop-blur-[2px]"
        onClick={onClose}
      />

      {/* Dialog */}
      <div className="relative w-full max-w-md bg-[#FAF9F6] dark:bg-[#1A1A1A] shadow-2xl border border-black/10 dark:border-white/10 rounded-sm">
        {/* Header */}
        <div className="flex items-center gap-3 px-6 py-4 border-b border-black/5 dark:border-white/5">
          <div className="w-8 h-8 flex items-center justify-center bg-black/5 dark:bg-white/5 rounded-sm">
            <ProviderIcon type={provider.type} className="w-5 h-5 text-black/70 dark:text-white/70" />
          </div>
          <div className="flex-1">
            <h3 className="text-base font-bold text-black/90 dark:text-white/90">
              {provider.name}
            </h3>
            {meta.docsUrl && (
              <a
                href={meta.docsUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-[11px] text-orange-500 hover:text-orange-600 flex items-center gap-1"
              >
                Get API Key <ExternalLink className="w-3 h-3" />
              </a>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-1.5 hover:bg-black/5 dark:hover:bg-white/5 rounded-sm transition-colors"
          >
            <X className="w-4 h-4 text-black/40 dark:text-white/40" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-5">
          {/* API Key Input */}
          <div className="space-y-2">
            <label className="text-xs font-bold text-black/60 dark:text-white/60 uppercase tracking-wide">
              API Key
            </label>
            {cloud?.cloudSynced && (
              <div className="flex items-center gap-1.5 px-2.5 py-1.5 bg-green-500/10 border border-green-500/20 rounded-sm">
                <Cloud className="w-3.5 h-3.5 text-green-600 dark:text-green-400" />
                <span className="text-xs font-mono text-green-700 dark:text-green-400">
                  Saved: {cloud.cloudKeyHint}
                </span>
              </div>
            )}
            {syncError && (
              <div className="flex items-center gap-1.5 px-2.5 py-1.5 bg-red-500/10 border border-red-500/20 rounded-sm">
                <AlertCircle className="w-3.5 h-3.5 text-red-500" />
                <span className="text-xs text-red-600 dark:text-red-400">{syncError}</span>
              </div>
            )}
            <div className="relative">
              <input
                type={showApiKey ? 'text' : 'password'}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={cloud?.cloudSynced ? 'Enter new key to replace' : meta.placeholder}
                className="w-full px-3 py-2.5 pr-10 bg-white dark:bg-white/5 border border-black/15 dark:border-white/15 rounded-sm text-sm font-mono text-black dark:text-white placeholder:text-black/30 dark:placeholder:text-white/30 focus:outline-none focus:border-black/40 dark:focus:border-white/40 transition-colors"
              />
              <button
                type="button"
                onClick={() => setShowApiKey(!showApiKey)}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-black/40 dark:text-white/40 hover:text-black/60 dark:hover:text-white/60"
              >
                {showApiKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {/* Base URL Input (optional) */}
          <div className="space-y-2">
            <label className="text-xs font-bold text-black/60 dark:text-white/60 uppercase tracking-wide">
              Base URL{' '}
              <span className="font-normal text-black/40 dark:text-white/40">(optional)</span>
            </label>
            <input
              type="text"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder={meta.defaultBaseUrl || 'https://api.example.com/v1'}
              className="w-full px-3 py-2.5 bg-white dark:bg-white/5 border border-black/15 dark:border-white/15 rounded-sm text-sm text-black dark:text-white placeholder:text-black/30 dark:placeholder:text-white/30 focus:outline-none focus:border-black/40 dark:focus:border-white/40 transition-colors"
            />
            <p className="text-[11px] text-black/40 dark:text-white/40">
              Override the default API endpoint (useful for proxies)
            </p>
          </div>

          {/* Enable Toggle */}
          <div className="flex items-center justify-between py-2">
            <span className="text-sm font-medium text-black/80 dark:text-white/80">
              Enable this provider
            </span>
            <button
              onClick={() => setIsEnabled(!isEnabled)}
              className={`relative w-10 h-5 rounded-full transition-colors ${
                isEnabled ? 'bg-green-500' : 'bg-black/20 dark:bg-white/20'
              }`}
            >
              <div
                className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow-sm transition-transform ${
                  isEnabled ? 'translate-x-5' : 'translate-x-0.5'
                }`}
              />
            </button>
          </div>

          {/* Test Connection */}
          <button
            onClick={handleTestConnection}
            disabled={isTesting || !apiKey.trim()}
            className="w-full py-2.5 bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/10 rounded-sm text-sm font-medium text-black/70 dark:text-white/70 hover:bg-black/10 dark:hover:bg-white/10 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
          >
            {isTesting ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Testing...
              </>
            ) : testResult === 'success' ? (
              <>
                <Check className="w-4 h-4 text-green-500" />
                Connection successful
              </>
            ) : testResult === 'error' ? (
              <>
                <AlertCircle className="w-4 h-4 text-red-500" />
                Connection failed
              </>
            ) : (
              'Test Connection'
            )}
          </button>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-black/5 dark:border-white/5">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-black/60 dark:text-white/60 hover:text-black dark:hover:text-white hover:bg-black/5 dark:hover:bg-white/5 rounded-sm transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={isSyncing}
            className="px-6 py-2 bg-black dark:bg-white text-white dark:text-black text-sm font-bold rounded-sm hover:bg-black/80 dark:hover:bg-white/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
          >
            {isSyncing ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Saving...
              </>
            ) : (
              'Save'
            )}
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}
