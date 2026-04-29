import React, { useState, useEffect } from 'react';
import { Plus, Key } from 'lucide-react';
import { useApiConfig } from './hooks/useApiConfig';
import { ProviderConfig, CustomModelConfig } from './types';
import { ProviderItem } from './components/ProviderItem';
import { ProviderConfigDialog } from './components/ProviderConfigDialog';
import { CustomModelDialog } from './components/CustomModelDialog';

export function ApiPanel({collapsed}:{collapsed:boolean}) {
  const { providers, updateProvider, addCustomModel, updateCustomModel, removeCustomModel, loadCloudKeys } =
    useApiConfig();

  useEffect(() => {
    loadCloudKeys();
  }, [loadCloudKeys]);

  // Dialog states
  const [selectedProvider, setSelectedProvider] = useState<ProviderConfig | null>(null);
  const [selectedCustomModel, setSelectedCustomModel] = useState<CustomModelConfig | null>(null);
  const [isAddingCustomModel, setIsAddingCustomModel] = useState(false);

  const handleProviderSave = (config: Partial<ProviderConfig>) => {
    if (selectedProvider) {
      updateProvider(selectedProvider.id, config);
    }
  };

  const handleCustomModelSave = (model: CustomModelConfig) => {
    if (selectedCustomModel) {
      updateCustomModel(model.id, model);
    } else {
      addCustomModel(model);
    }
  };

  const handleDeleteCustomModel = (id: string) => {
    if (confirm('Are you sure you want to delete this model?')) {
      removeCustomModel(id);
    }
  };

  // Filter out local providers (ollama) - they are coming soon
  const cloudProviders = providers.filter((p) => p.type !== 'ollama');

  return <>
    {collapsed ? <Key className='m-[18px] size-5 text-black/70'/> : <div className="flex flex-col h-full">
      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {/* Cloud Providers Section */}
        <div className="p-2">
          <div className="text-[10px] flex items-center font-bold text-black/70 dark:text-white/40 uppercase tracking-wider mb-2 px-2">
            <Key className='mr-2 size-5 text-black/70'/>  Cloud Providers
          </div>
          <div className="space-y-0.5 ml-1">
            {cloudProviders.map((provider) => (
              <ProviderItem
                key={provider.id}
                provider={provider}
                onClick={() => setSelectedProvider(provider)}
              />
            ))}
          </div>
        </div>
      </div>

      {/* Provider Config Dialog */}
      {selectedProvider && (
        <ProviderConfigDialog
          provider={selectedProvider}
          isOpen={!!selectedProvider}
          onClose={() => setSelectedProvider(null)}
          onSave={handleProviderSave}
        />
      )}

      {/* Custom Model Dialog - Edit */}
      {selectedCustomModel && (
        <CustomModelDialog
          model={selectedCustomModel}
          isOpen={!!selectedCustomModel}
          onClose={() => setSelectedCustomModel(null)}
          onSave={handleCustomModelSave}
        />
      )}

      {/* Custom Model Dialog - Add */}
      <CustomModelDialog
        isOpen={isAddingCustomModel}
        onClose={() => setIsAddingCustomModel(false)}
        onSave={handleCustomModelSave}
      />
    </div>}
  </>
}
