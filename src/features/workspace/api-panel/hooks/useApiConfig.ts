import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { ProviderConfig, CustomModelConfig, DEFAULT_PROVIDERS } from '../types';

interface CloudProviderState {
  cloudKeyHint?: string;
  cloudSynced?: boolean;
}

interface ApiConfigStore {
  // State
  providers: ProviderConfig[];
  customModels: CustomModelConfig[];
  defaultProviderId: string | null;
  cloudState: Record<string, CloudProviderState>;

  // Provider Actions
  updateProvider: (id: string, config: Partial<ProviderConfig>) => void;
  resetProviders: () => void;

  // Cloud Sync Actions
  syncKeyToCloud: (providerId: string, apiKey: string, isEnabled?: boolean) => Promise<boolean>;
  loadCloudKeys: () => Promise<void>;

  // Custom Model Actions
  addCustomModel: (model: CustomModelConfig) => void;
  updateCustomModel: (id: string, config: Partial<CustomModelConfig>) => void;
  removeCustomModel: (id: string) => void;

  // Default Provider
  setDefaultProvider: (id: string | null) => void;

  // Utility
  getEnabledProviders: () => ProviderConfig[];
  getEnabledCustomModels: () => CustomModelConfig[];
}

export const useApiConfig = create<ApiConfigStore>()(
  persist(
    (set, get) => ({
      providers: DEFAULT_PROVIDERS,
      customModels: [],
      defaultProviderId: null,
      cloudState: {},

      updateProvider: (id, config) => {
        if (config.isEnabled === true) {
          set((state) => ({
            providers: state.providers.map((p) =>
              p.id === id ? { ...p, ...config } : { ...p, isEnabled: false }
            ),
          }));
          (window as any).electron?.updateProviderEnabled({ provider: id, isEnabled: true, exclusive: true })
            .catch(console.error);
        } else {
          set((state) => ({
            providers: state.providers.map((p) =>
              p.id === id ? { ...p, ...config } : p
            ),
          }));
          if (config.isEnabled === false) {
            (window as any).electron?.updateProviderEnabled({ provider: id, isEnabled: false })
              .catch(console.error);
          }
        }
      },

      resetProviders: () => {
        set({ providers: DEFAULT_PROVIDERS, cloudState: {} });
      },

      syncKeyToCloud: async (providerId, apiKey, isEnabled = true) => {
        try {
          await (window as any).electron.saveApiKey({ provider: providerId, apiKey, isEnabled, exclusive: isEnabled });
          const keyHint = `${apiKey.slice(0, 4)}...${apiKey.slice(-4)}`;
          set((state) => ({
            providers: state.providers.map((p) =>
              p.id === providerId
                ? { ...p, apiKey, isEnabled }
                : { ...p, isEnabled: isEnabled ? false : p.isEnabled }
            ),
            cloudState: {
              ...state.cloudState,
              [providerId]: { cloudKeyHint: keyHint, cloudSynced: true },
            },
          }));
          return true;
        } catch (err) {
          console.error('Failed to save API key locally:', err);
          return false;
        }
      },

      loadCloudKeys: async () => {
        try {
          const savedProviders = await (window as any).electron.loadApiKeys() as Record<string, { apiKey: string; isEnabled: boolean }>;
          if (!savedProviders) return;

          const newCloudState: Record<string, CloudProviderState> = {};
          const providerUpdates: Record<string, { apiKey: string; isEnabled: boolean }> = {};

          for (const [provider, entry] of Object.entries(savedProviders)) {
            const { apiKey, isEnabled } = entry;
            newCloudState[provider] = {
              cloudKeyHint: `${apiKey.slice(0, 4)}...${apiKey.slice(-4)}`,
              cloudSynced: true,
            };
            providerUpdates[provider] = { apiKey, isEnabled: isEnabled ?? true };
          }

          set((state) => ({
            cloudState: { ...state.cloudState, ...newCloudState },
            providers: state.providers.map((p) =>
              providerUpdates[p.id]
                ? { ...p, apiKey: providerUpdates[p.id].apiKey, isEnabled: providerUpdates[p.id].isEnabled }
                : p
            ),
          }));
        } catch (err) {
          console.error('Failed to load local API keys:', err);
        }
      },

      addCustomModel: (model) => {
        set((state) => ({
          customModels: [...state.customModels, model],
        }));
      },

      updateCustomModel: (id, config) => {
        set((state) => ({
          customModels: state.customModels.map((m) =>
            m.id === id ? { ...m, ...config } : m
          ),
        }));
      },

      removeCustomModel: (id) => {
        set((state) => ({
          customModels: state.customModels.filter((m) => m.id !== id),
          // 如果删除的是默认 provider，清除默认设置
          defaultProviderId:
            state.defaultProviderId === id ? null : state.defaultProviderId,
        }));
      },

      setDefaultProvider: (id) => {
        set({ defaultProviderId: id });
      },

      getEnabledProviders: () => {
        const { providers, cloudState } = get();
        return providers.filter((p) => p.isEnabled && (p.apiKey || cloudState[p.id]?.cloudSynced));
      },

      getEnabledCustomModels: () => {
        return get().customModels.filter((m) => m.isEnabled);
      },
    }),
    {
      name: 'useit-api-config',
      version: 4,
      migrate: () => {
        // 版本升级时重置为新的默认 providers
        return {
          providers: DEFAULT_PROVIDERS,
          customModels: [],
          defaultProviderId: null,
          cloudState: {},
        };
      },
    }
  )
);

// 辅助函数：掩码 API Key
export function maskApiKey(key: string | undefined): string {
  if (!key) return '';
  if (key.length <= 8) return '••••••••';
  return `${key.slice(0, 4)}••••${key.slice(-4)}`;
}

// 辅助函数：生成唯一 ID
export function generateModelId(): string {
  return `custom-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}
