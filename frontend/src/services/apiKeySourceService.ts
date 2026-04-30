/**
 * API Key Source Service
 *
 * Derives which providers should use the user's own API keys
 * based on the api-panel store (enabled + cloud-synced).
 *
 * The per-provider "Enable this provider" toggle in the api-panel
 * is the source of truth. The old global "official"/"own" toggle
 * in ProfileSettingsDialog is kept for backward compatibility but
 * no longer drives buildApiKeySourcePayload().
 */

import { useApiConfig } from '@/features/workspace/api-panel/hooks/useApiConfig';

// --- Legacy types/functions kept for ProfileSettingsDialog compatibility ---
export type ApiKeySource = 'official' | 'own';
export interface ApiKeySourceConfig { default: ApiKeySource; }
export function loadApiKeySourceConfig(): ApiKeySourceConfig { return { default: 'official' }; }
export function saveApiKeySourceConfig(_config: ApiKeySourceConfig): void { /* no-op */ }

// --- Active implementation ---
export function buildApiKeySourcePayload(): { default: 'own'; providers: string[] } | undefined {
  const { providers, cloudState } = useApiConfig.getState();

  // Debug: log all provider states
  console.log('[ApiKeySource] Building payload, provider states:',
    providers.map(p => ({
      id: p.id,
      isEnabled: p.isEnabled,
      cloudSynced: cloudState[p.id]?.cloudSynced,
      cloudKeyHint: cloudState[p.id]?.cloudKeyHint
    }))
  );

  const enabledCloudProviders = providers
    .filter(p => p.isEnabled && cloudState[p.id]?.cloudSynced)
    .map(p => p.id);

  console.log('[ApiKeySource] Enabled cloud providers:', enabledCloudProviders);

  if (enabledCloudProviders.length > 0) {
    const payload = { default: 'own' as const, providers: enabledCloudProviders };
    console.log('[ApiKeySource] Returning payload:', payload);
    return payload;
  }

  console.log('[ApiKeySource] No enabled cloud providers, returning undefined');
  return undefined;
}
