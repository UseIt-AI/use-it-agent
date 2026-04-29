// API Provider 类型 (LangChain 主要支持的)
export type ProviderType =
  | 'openai'
  | 'anthropic'
  | 'google'           // Gemini
  | 'qwen'             // 阿里通义千问
  | 'ollama'           // 本地
  | 'custom';          // 自定义 OpenAI 兼容

export interface ProviderConfig {
  id: string;
  type: ProviderType;
  name: string;
  apiKey?: string;
  baseUrl?: string;           // 自定义端点
  isEnabled: boolean;
  models?: string[];          // 可用模型列表
  defaultModel?: string;
}

export type CustomModelType = 'vllm' | 'ollama' | 'localai' | 'openai_compatible';

export interface CustomModelConfig {
  id: string;
  name: string;
  baseUrl: string;            // e.g., http://localhost:8000/v1
  apiKey?: string;            // 可选
  modelId: string;            // 模型标识符
  type: CustomModelType;
  isEnabled: boolean;
  maxTokens?: number;
  temperature?: number;
}

export interface ApiConfigState {
  providers: ProviderConfig[];
  customModels: CustomModelConfig[];
  defaultProviderId: string | null;
}

// Provider 元数据 (用于显示)
export interface ProviderMeta {
  type: ProviderType;
  name: string;
  placeholder: string;        // API Key 占位符
  defaultBaseUrl?: string;
  docsUrl?: string;
}

// 预设的 Provider 元数据
export const PROVIDER_META: Record<ProviderType, ProviderMeta> = {
  openai: {
    type: 'openai',
    name: 'OpenAI',
    placeholder: 'sk-...',
    defaultBaseUrl: 'https://api.openai.com/v1',
    docsUrl: 'https://platform.openai.com/api-keys',
  },
  anthropic: {
    type: 'anthropic',
    name: 'Anthropic',
    placeholder: 'sk-ant-...',
    defaultBaseUrl: 'https://api.anthropic.com',
    docsUrl: 'https://console.anthropic.com/settings/keys',
  },
  google: {
    type: 'google',
    name: 'Gemini (Google)',
    placeholder: 'AIza...',
    docsUrl: 'https://aistudio.google.com/app/apikey',
  },
  qwen: {
    type: 'qwen',
    name: 'Qwen',
    placeholder: 'sk-...',
    defaultBaseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    docsUrl: 'https://dashscope.console.aliyun.com/apiKey',
  },
  ollama: {
    type: 'ollama',
    name: 'Ollama',
    placeholder: '(no key required)',
    defaultBaseUrl: 'http://localhost:11434',
    docsUrl: 'https://ollama.ai/',
  },
  custom: {
    type: 'custom',
    name: 'Custom',
    placeholder: 'your-api-key',
  },
};

// 默认的 Provider 配置列表
export const DEFAULT_PROVIDERS: ProviderConfig[] = [
  { id: 'openai', type: 'openai', name: 'OpenAI', isEnabled: false },
  { id: 'anthropic', type: 'anthropic', name: 'Anthropic', isEnabled: false },
  { id: 'google', type: 'google', name: 'Gemini (Google)', isEnabled: false },
  { id: 'qwen', type: 'qwen', name: 'Qwen', isEnabled: false },
  { id: 'ollama', type: 'ollama', name: 'Ollama (Local)', isEnabled: false, baseUrl: 'http://localhost:11434' },
];
