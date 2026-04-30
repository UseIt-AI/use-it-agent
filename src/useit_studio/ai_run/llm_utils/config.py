"""
配置管理

统一的LLM配置管理
"""

import os
import json
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict


@dataclass
class LLMConfig:
    """LLM配置"""
    model: str = "gpt-4o-mini"
    provider: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    max_tokens: int = 4096
    temperature: float = 0.0
    timeout: int = 60
    retry_count: int = 3
    
    # 成本控制
    max_cost_per_request: float = 1.0  # 最大单次请求成本（USD）
    max_daily_cost: float = 10.0       # 最大每日成本（USD）
    
    # 其他参数
    extra_params: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.extra_params is None:
            self.extra_params = {}


class ConfigManager:
    """配置管理器"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or self._get_default_config_path()
        self.configs: Dict[str, LLMConfig] = {}
        self.load_configs()
    
    def _get_default_config_path(self) -> str:
        """获取默认配置文件路径"""
        # 尝试多个可能的路径
        possible_paths = [
            "./config/llm_config.json",
            "../config/llm_config.json", 
            "../../config/llm_config.json",
            os.path.expanduser("~/.useit_ai_run/llm_config.json"),
            "/etc/useit_ai_run/llm_config.json"
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
        
        # 如果都不存在，返回第一个作为默认路径
        return possible_paths[0]
    
    def load_configs(self):
        """加载配置"""
        if not os.path.exists(self.config_path):
            self._create_default_config()
            return
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for name, config_dict in data.items():
                self.configs[name] = LLMConfig(**config_dict)
                
        except Exception as e:
            print(f"Failed to load config from {self.config_path}: {e}")
            self._create_default_config()
    
    def _create_default_config(self):
        """创建默认配置"""
        default_configs = {
            "default": LLMConfig(),
            "gpt-4o": LLMConfig(model="gpt-4o", max_tokens=8192, max_cost_per_request=2.0),
            "gpt-4o-mini": LLMConfig(model="gpt-4o-mini", max_tokens=8192),
            "claude": LLMConfig(model="claude-3-5-sonnet-20241022", provider="claude", max_tokens=8192),
            "gemini": LLMConfig(model="gemini-1.5-flash", provider="gemini"),
            "local": LLMConfig(model="llama-2-7b-chat", provider="vllm", base_url="http://localhost:8000")
        }
        
        self.configs = default_configs
        self.save_configs()
    
    def save_configs(self):
        """保存配置"""
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            
            config_dict = {}
            for name, config in self.configs.items():
                config_dict[name] = asdict(config)
            
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config_dict, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            print(f"Failed to save config to {self.config_path}: {e}")
    
    def get_config(self, name: str = "default") -> LLMConfig:
        """获取配置"""
        return self.configs.get(name, self.configs.get("default", LLMConfig()))
    
    def set_config(self, name: str, config: LLMConfig):
        """设置配置"""
        self.configs[name] = config
        self.save_configs()
    
    def list_configs(self) -> Dict[str, LLMConfig]:
        """列出所有配置"""
        return self.configs.copy()
    
    def delete_config(self, name: str):
        """删除配置"""
        if name in self.configs and name != "default":
            del self.configs[name]
            self.save_configs()


class APIKeyManager:
    """API密钥管理器"""
    
    def __init__(self, keys_path: Optional[str] = None):
        self.keys_path = keys_path or self._get_default_keys_path()
        self.api_keys: Dict[str, str] = {}
        self.load_keys()
    
    def _get_default_keys_path(self) -> str:
        """获取默认密钥文件路径"""
        possible_paths = [
            "./config/api_keys.json",
            "../config/api_keys.json",
            "../../config/api_keys.json", 
            os.path.expanduser("~/.useit_ai_run/api_keys.json"),
            "/etc/useit_ai_run/api_keys.json"
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
        
        return possible_paths[0]
    
    def load_keys(self):
        """加载API密钥"""
        # 从文件加载
        if os.path.exists(self.keys_path):
            try:
                with open(self.keys_path, 'r', encoding='utf-8') as f:
                    self.api_keys = json.load(f)
            except Exception as e:
                print(f"Failed to load API keys from {self.keys_path}: {e}")
        
        # 从环境变量加载（优先级更高）
        env_keys = {
            "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY"),
            "ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY"),
            "GOOGLE_API_KEY": os.getenv("GOOGLE_API_KEY"),
            "HUGGINGFACE_API_KEY": os.getenv("HUGGINGFACE_API_KEY"),
            "VLLM_API_KEY": os.getenv("VLLM_API_KEY"),
        }
        
        for key, value in env_keys.items():
            if value:
                self.api_keys[key] = value
    
    def get_key(self, provider: str) -> Optional[str]:
        """获取API密钥"""
        # 标准化provider名称
        provider_map = {
            "openai": "OPENAI_API_KEY",
            "gpt": "OPENAI_API_KEY", 
            "anthropic": "ANTHROPIC_API_KEY",
            "claude": "ANTHROPIC_API_KEY",
            "google": "GOOGLE_API_KEY",
            "gemini": "GOOGLE_API_KEY",
            "huggingface": "HUGGINGFACE_API_KEY",
            "vllm": "VLLM_API_KEY",
            "local": "VLLM_API_KEY",
        }
        
        key_name = provider_map.get(provider.lower(), provider.upper() + "_API_KEY")
        return self.api_keys.get(key_name)
    
    def set_key(self, provider: str, api_key: str):
        """设置API密钥"""
        provider_map = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "google": "GOOGLE_API_KEY",
            "huggingface": "HUGGINGFACE_API_KEY",
            "vllm": "VLLM_API_KEY",
        }
        
        key_name = provider_map.get(provider.lower(), provider.upper() + "_API_KEY")
        self.api_keys[key_name] = api_key
        self.save_keys()
    
    def save_keys(self):
        """保存API密钥"""
        try:
            os.makedirs(os.path.dirname(self.keys_path), exist_ok=True)
            
            with open(self.keys_path, 'w', encoding='utf-8') as f:
                json.dump(self.api_keys, f, indent=2)
                
        except Exception as e:
            print(f"Failed to save API keys to {self.keys_path}: {e}")


# 全局配置管理器实例
global_config_manager = ConfigManager()
global_api_key_manager = APIKeyManager()