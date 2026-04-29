import React from 'react';
import { ChevronRight, Cloud } from 'lucide-react';
import { ProviderConfig } from '../types';
import { ProviderIcon } from './ProviderIcon';
import { maskApiKey, useApiConfig } from '../hooks/useApiConfig';

interface ProviderItemProps {
  provider: ProviderConfig;
  onClick: () => void;
}

export function ProviderItem({ provider, onClick }: ProviderItemProps) {
  const cloudState = useApiConfig((s) => s.cloudState);
  const cloud = cloudState[provider.id];
  const hasApiKey = !!provider.apiKey || !!cloud?.cloudSynced;
  const isConfigured = provider.isEnabled && hasApiKey;

  return (
    <button
      onClick={onClick}
      className="w-full flex items-center gap-2.5 px-2 py-2 hover:bg-black/5 dark:hover:bg-white/5 rounded-sm cursor-pointer transition-colors group text-left"
    >
      {/* Provider Icon */}
      <div className="w-5 h-5 flex items-center justify-center text-black/60 dark:text-white/60">
        <ProviderIcon type={provider.type} className="w-4 h-4" />
      </div>

      {/* Name and Status */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-black/80 dark:text-white/80 truncate">
            {provider.name}
          </span>
        </div>
        {hasApiKey && (
          <div className="text-[10px] text-black/40 dark:text-white/40 font-mono truncate flex items-center gap-1">
            {cloud?.cloudSynced ? (
              <>
                <Cloud className="w-3 h-3 text-green-500 flex-shrink-0" />
                {cloud.cloudKeyHint}
              </>
            ) : (
              maskApiKey(provider.apiKey)
            )}
          </div>
        )}
      </div>

      {/* Status Indicator */}
      <div className="flex items-center gap-1.5">
        <div
          className={`w-2 h-2 rounded-full transition-colors ${
            isConfigured
              ? 'bg-green-500'
              : hasApiKey
              ? 'bg-yellow-500'
              : 'bg-black/20 dark:bg-white/20'
          }`}
          title={
            isConfigured
              ? 'Configured & Enabled'
              : hasApiKey
              ? 'API Key set but disabled'
              : 'Not configured'
          }
        />
        <ChevronRight className="w-3.5 h-3.5 text-black/30 dark:text-white/30 opacity-0 group-hover:opacity-100 transition-opacity" />
      </div>
    </button>
  );
}
