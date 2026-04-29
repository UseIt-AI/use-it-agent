import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { X, Server, Loader2, Check, AlertCircle } from 'lucide-react';
import { CustomModelConfig, CustomModelType } from '../types';
import { generateModelId } from '../hooks/useApiConfig';

interface CustomModelDialogProps {
  model?: CustomModelConfig; // undefined for new model
  isOpen: boolean;
  onClose: () => void;
  onSave: (model: CustomModelConfig) => void;
}

const TYPE_OPTIONS: Array<{ value: CustomModelType; label: string; hint: string }> = [
  { value: 'vllm', label: 'vLLM', hint: 'http://localhost:8000/v1' },
  { value: 'ollama', label: 'Ollama', hint: 'http://localhost:11434/v1' },
  { value: 'localai', label: 'LocalAI', hint: 'http://localhost:8080/v1' },
  { value: 'openai_compatible', label: 'OpenAI Compatible', hint: 'Any OpenAI-compatible endpoint' },
];

export function CustomModelDialog({
  model,
  isOpen,
  onClose,
  onSave,
}: CustomModelDialogProps) {
  const isEditing = !!model;

  const [type, setType] = useState<CustomModelType>(model?.type || 'vllm');
  const [name, setName] = useState(model?.name || '');
  const [baseUrl, setBaseUrl] = useState(model?.baseUrl || '');
  const [modelId, setModelId] = useState(model?.modelId || '');
  const [apiKey, setApiKey] = useState(model?.apiKey || '');
  const [isEnabled, setIsEnabled] = useState(model?.isEnabled ?? true);
  const [isTesting, setIsTesting] = useState(false);
  const [testResult, setTestResult] = useState<'success' | 'error' | null>(null);

  useEffect(() => {
    if (isOpen) {
      setType(model?.type || 'vllm');
      setName(model?.name || '');
      setBaseUrl(model?.baseUrl || '');
      setModelId(model?.modelId || '');
      setApiKey(model?.apiKey || '');
      setIsEnabled(model?.isEnabled ?? true);
      setTestResult(null);
    }
  }, [isOpen, model]);

  // Auto-fill base URL hint when type changes
  useEffect(() => {
    if (!isEditing && !baseUrl) {
      const option = TYPE_OPTIONS.find((o) => o.value === type);
      if (option && option.hint.startsWith('http')) {
        setBaseUrl(option.hint);
      }
    }
  }, [type, isEditing, baseUrl]);

  const handleSave = () => {
    if (!name.trim() || !baseUrl.trim() || !modelId.trim()) return;

    onSave({
      id: model?.id || generateModelId(),
      type,
      name: name.trim(),
      baseUrl: baseUrl.trim(),
      modelId: modelId.trim(),
      apiKey: apiKey.trim() || undefined,
      isEnabled,
    });
    onClose();
  };

  const handleTestConnection = async () => {
    setIsTesting(true);
    setTestResult(null);

    // Simulate API test
    await new Promise((resolve) => setTimeout(resolve, 1500));

    // For now, just check if required fields are provided
    if (baseUrl.trim() && modelId.trim()) {
      setTestResult('success');
    } else {
      setTestResult('error');
    }
    setIsTesting(false);
  };

  const isValid = name.trim() && baseUrl.trim() && modelId.trim();

  if (!isOpen) return null;

  return createPortal(
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 font-sans">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/20 dark:bg-black/60 backdrop-blur-[2px]"
        onClick={onClose}
      />

      {/* Dialog */}
      <div className="relative w-full max-w-lg bg-[#FAF9F6] dark:bg-[#1A1A1A] shadow-2xl border border-black/10 dark:border-white/10 rounded-sm">
        {/* Header */}
        <div className="flex items-center gap-3 px-6 py-4 border-b border-black/5 dark:border-white/5">
          <div className="w-8 h-8 flex items-center justify-center bg-black/5 dark:bg-white/5 rounded-sm">
            <Server className="w-5 h-5 text-black/70 dark:text-white/70" />
          </div>
          <h3 className="flex-1 text-base font-bold text-black/90 dark:text-white/90">
            {isEditing ? 'Edit Custom Model' : 'Add Custom Model'}
          </h3>
          <button
            onClick={onClose}
            className="p-1.5 hover:bg-black/5 dark:hover:bg-white/5 rounded-sm transition-colors"
          >
            <X className="w-4 h-4 text-black/40 dark:text-white/40" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-5 max-h-[60vh] overflow-y-auto">
          {/* Type Selection */}
          <div className="space-y-2">
            <label className="text-xs font-bold text-black/60 dark:text-white/60 uppercase tracking-wide">
              Type
            </label>
            <select
              value={type}
              onChange={(e) => setType(e.target.value as CustomModelType)}
              className="w-full px-3 py-2.5 bg-white dark:bg-white/5 border border-black/15 dark:border-white/15 rounded-sm text-sm text-black dark:text-white focus:outline-none focus:border-black/40 dark:focus:border-white/40 transition-colors"
            >
              {TYPE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>

          {/* Display Name */}
          <div className="space-y-2">
            <label className="text-xs font-bold text-black/60 dark:text-white/60 uppercase tracking-wide">
              Display Name
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="My Local Llama"
              className="w-full px-3 py-2.5 bg-white dark:bg-white/5 border border-black/15 dark:border-white/15 rounded-sm text-sm text-black dark:text-white placeholder:text-black/30 dark:placeholder:text-white/30 focus:outline-none focus:border-black/40 dark:focus:border-white/40 transition-colors"
            />
          </div>

          {/* Base URL */}
          <div className="space-y-2">
            <label className="text-xs font-bold text-black/60 dark:text-white/60 uppercase tracking-wide">
              Base URL
            </label>
            <input
              type="text"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder={TYPE_OPTIONS.find((o) => o.value === type)?.hint || 'http://localhost:8000/v1'}
              className="w-full px-3 py-2.5 bg-white dark:bg-white/5 border border-black/15 dark:border-white/15 rounded-sm text-sm font-mono text-black dark:text-white placeholder:text-black/30 dark:placeholder:text-white/30 focus:outline-none focus:border-black/40 dark:focus:border-white/40 transition-colors"
            />
            <p className="text-[11px] text-black/40 dark:text-white/40">
              {type === 'vllm' && 'For vLLM: http://localhost:8000/v1'}
              {type === 'ollama' && 'For Ollama: http://localhost:11434/v1'}
              {type === 'localai' && 'For LocalAI: http://localhost:8080/v1'}
              {type === 'openai_compatible' && 'Any OpenAI-compatible API endpoint'}
            </p>
          </div>

          {/* Model ID */}
          <div className="space-y-2">
            <label className="text-xs font-bold text-black/60 dark:text-white/60 uppercase tracking-wide">
              Model ID
            </label>
            <input
              type="text"
              value={modelId}
              onChange={(e) => setModelId(e.target.value)}
              placeholder="meta-llama/Llama-2-7b-chat-hf"
              className="w-full px-3 py-2.5 bg-white dark:bg-white/5 border border-black/15 dark:border-white/15 rounded-sm text-sm font-mono text-black dark:text-white placeholder:text-black/30 dark:placeholder:text-white/30 focus:outline-none focus:border-black/40 dark:focus:border-white/40 transition-colors"
            />
            <p className="text-[11px] text-black/40 dark:text-white/40">
              The model identifier used in API requests
            </p>
          </div>

          {/* API Key (Optional) */}
          <div className="space-y-2">
            <label className="text-xs font-bold text-black/60 dark:text-white/60 uppercase tracking-wide">
              API Key{' '}
              <span className="font-normal text-black/40 dark:text-white/40">(optional)</span>
            </label>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="Leave empty if not required"
              className="w-full px-3 py-2.5 bg-white dark:bg-white/5 border border-black/15 dark:border-white/15 rounded-sm text-sm text-black dark:text-white placeholder:text-black/30 dark:placeholder:text-white/30 focus:outline-none focus:border-black/40 dark:focus:border-white/40 transition-colors"
            />
          </div>

          {/* Enable Toggle */}
          <div className="flex items-center justify-between py-2">
            <span className="text-sm font-medium text-black/80 dark:text-white/80">
              Enable this model
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
            disabled={isTesting || !baseUrl.trim() || !modelId.trim()}
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
            disabled={!isValid}
            className="px-6 py-2 bg-black dark:bg-white text-white dark:text-black text-sm font-bold rounded-sm hover:bg-black/80 dark:hover:bg-white/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isEditing ? 'Save' : 'Add Model'}
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}
