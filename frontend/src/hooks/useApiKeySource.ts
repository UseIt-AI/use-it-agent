/**
 * useApiKeySource Hook
 *
 * Thin React wrapper around apiKeySourceService.
 */

import { useState, useCallback } from 'react';
import {
  type ApiKeySource,
  type ApiKeySourceConfig,
  loadApiKeySourceConfig,
  saveApiKeySourceConfig,
} from '@/services/apiKeySourceService';

export function useApiKeySource() {
  const [config, setConfig] = useState<ApiKeySourceConfig>(loadApiKeySourceConfig);

  const setSource = useCallback((source: ApiKeySource) => {
    const next: ApiKeySourceConfig = { ...config, default: source };
    saveApiKeySourceConfig(next);
    setConfig(next);
  }, [config]);

  return {
    source: config.default,
    setSource,
  };
}
