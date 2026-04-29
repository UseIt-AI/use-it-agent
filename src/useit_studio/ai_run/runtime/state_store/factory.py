"""
State Store Factory

Factory class for creating state store instances based on configuration.
Supports automatic selection based on environment (debug vs production).

Usage:
    from useit_studio.ai_run.runtime.state_store import StateStoreFactory
    
    # Get store based on config
    store = StateStoreFactory.get_store()
    
    # Or specify mode explicitly
    store = StateStoreFactory.get_store(mode="redis")
    
    # Or create with custom config
    store = StateStoreFactory.create_redis_store(
        host="redis.example.com",
        port=6379,
    )
"""

import os
import logging
from typing import Optional, Dict, Any

from .base import StateStore
from .memory_store import MemoryStateStore
from .redis_store import RedisStateStore, REDIS_AVAILABLE

logger = logging.getLogger(__name__)

# Singleton instance
_store_instance: Optional[StateStore] = None


class StateStoreFactory:
    """
    Factory for creating StateStore instances.
    
    Supports two modes:
    - "memory": In-memory storage (for debug/development)
    - "redis": Redis storage (for production)
    
    Mode selection priority:
    1. Explicit mode parameter
    2. STATE_STORE_MODE environment variable
    3. Config file setting (state_store.mode)
    4. Default: "memory"
    """
    
    # Default configuration
    DEFAULT_CONFIG = {
        "mode": "memory",
        "redis": {
            "host": "localhost",
            "port": 6379,
            "password": None,
            "db": 0,
            "key_prefix": "airun",
            "max_connections": 50,
            "socket_timeout": 5,
            "socket_connect_timeout": 5,
            "state_ttl_seconds": 86400,  # 24 hours
            "heartbeat_ttl_seconds": 300,  # 5 minutes
            "lock_ttl_seconds": 30,
            # AWS Valkey / TLS support
            "ssl": False,  # Enable for AWS Valkey with encryption in-transit
            "ssl_cert_reqs": None,  # 'required', 'optional', or 'none'
        },
        "memory": {
            "max_tasks": 1000,
            "default_ttl_seconds": 86400,
            "cleanup_interval_seconds": 3600,
        },
    }
    
    @classmethod
    def get_store(
        cls,
        mode: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        force_new: bool = False,
    ) -> StateStore:
        """
        Get or create a StateStore instance.
        
        Uses singleton pattern by default. Pass force_new=True to create
        a new instance.
        
        Args:
            mode: Storage mode ("memory" or "redis")
            config: Optional configuration dictionary
            force_new: If True, create new instance instead of reusing
            
        Returns:
            StateStore instance
        """
        global _store_instance
        
        if _store_instance is not None and not force_new:
            return _store_instance
        
        # Determine mode
        if mode is None:
            mode = cls._get_mode_from_config(config)
        
        logger.info(f"Creating StateStore with mode: {mode}")
        
        # Create appropriate store
        if mode == "redis":
            store = cls.create_redis_store(config)
        else:
            store = cls.create_memory_store(config)
        
        # Cache as singleton
        if not force_new:
            _store_instance = store
        
        return store
    
    @classmethod
    def create_memory_store(
        cls,
        config: Optional[Dict[str, Any]] = None,
    ) -> MemoryStateStore:
        """
        Create a MemoryStateStore instance.
        
        Args:
            config: Optional configuration dictionary
            
        Returns:
            MemoryStateStore instance
        """
        # Merge with defaults
        memory_config = cls.DEFAULT_CONFIG["memory"].copy()
        
        if config and "memory" in config:
            memory_config.update(config["memory"])
        
        # Override from environment
        if os.getenv("STATE_STORE_MAX_TASKS"):
            memory_config["max_tasks"] = int(os.getenv("STATE_STORE_MAX_TASKS"))
        
        logger.info(f"Creating MemoryStateStore: {memory_config}")
        
        return MemoryStateStore(
            max_tasks=memory_config["max_tasks"],
            default_ttl_seconds=memory_config["default_ttl_seconds"],
            cleanup_interval_seconds=memory_config["cleanup_interval_seconds"],
        )
    
    @classmethod
    def create_redis_store(
        cls,
        config: Optional[Dict[str, Any]] = None,
    ) -> RedisStateStore:
        """
        Create a RedisStateStore instance.
        
        Args:
            config: Optional configuration dictionary
            
        Returns:
            RedisStateStore instance
            
        Raises:
            ImportError: If redis package not installed
        """
        if not REDIS_AVAILABLE:
            raise ImportError(
                "redis package not installed. "
                "Install with: pip install redis"
            )
        
        # Merge with defaults
        redis_config = cls.DEFAULT_CONFIG["redis"].copy()
        
        if config and "redis" in config:
            redis_config.update(config["redis"])
        
        # Override from environment variables
        env_overrides = {
            "REDIS_HOST": ("host", str),
            "REDIS_PORT": ("port", int),
            "REDIS_PASSWORD": ("password", str),
            "REDIS_DB": ("db", int),
            "STATE_STORE_KEY_PREFIX": ("key_prefix", str),
            "STATE_STORE_TTL": ("state_ttl_seconds", int),
        }
        
        for env_var, (config_key, type_fn) in env_overrides.items():
            value = os.getenv(env_var)
            if value:
                redis_config[config_key] = type_fn(value)
        
        # SSL/TLS environment overrides (for AWS Valkey)
        if os.getenv("REDIS_SSL", "").lower() in ("true", "1", "yes"):
            redis_config["ssl"] = True
        if os.getenv("REDIS_SSL_CERT_REQS"):
            redis_config["ssl_cert_reqs"] = os.getenv("REDIS_SSL_CERT_REQS")
        
        ssl_info = f", ssl={redis_config.get('ssl', False)}" if redis_config.get("ssl") else ""
        logger.info(
            f"Creating RedisStateStore: host={redis_config['host']}, "
            f"port={redis_config['port']}, db={redis_config['db']}, "
            f"prefix={redis_config['key_prefix']}{ssl_info}"
        )
        
        return RedisStateStore(
            host=redis_config["host"],
            port=redis_config["port"],
            password=redis_config["password"],
            db=redis_config["db"],
            key_prefix=redis_config["key_prefix"],
            max_connections=redis_config["max_connections"],
            socket_timeout=redis_config["socket_timeout"],
            socket_connect_timeout=redis_config["socket_connect_timeout"],
            state_ttl_seconds=redis_config["state_ttl_seconds"],
            heartbeat_ttl_seconds=redis_config["heartbeat_ttl_seconds"],
            lock_ttl_seconds=redis_config["lock_ttl_seconds"],
            ssl=redis_config.get("ssl", False),
            ssl_cert_reqs=redis_config.get("ssl_cert_reqs"),
        )
    
    @classmethod
    def _get_mode_from_config(cls, config: Optional[Dict[str, Any]] = None) -> str:
        """
        Determine storage mode from config and environment.
        
        Priority:
        1. Environment variable STATE_STORE_MODE
        2. Config dict state_store.mode
        3. Default: "memory"
        """
        # Check environment variable first
        env_mode = os.getenv("STATE_STORE_MODE")
        if env_mode:
            return env_mode.lower()
        
        # Check config dict passed as parameter
        if config and "mode" in config:
            return config["mode"].lower()
        
        # Default to memory
        return "memory"
    
    @classmethod
    def get_current_store(cls) -> Optional[StateStore]:
        """
        Get the current singleton store instance.
        
        Returns:
            Current store instance or None if not initialized
        """
        return _store_instance
    
    @classmethod
    def close_store(cls):
        """
        Close and clear the singleton store instance.
        """
        global _store_instance
        
        if _store_instance is not None:
            _store_instance.close()
            _store_instance = None
            logger.info("StateStore singleton closed")
    
    @classmethod
    def reset(cls):
        """
        Reset factory state (for testing).
        """
        global _store_instance
        _store_instance = None


def get_state_store(
    mode: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
) -> StateStore:
    """
    Convenience function to get state store.
    
    Equivalent to StateStoreFactory.get_store()
    """
    return StateStoreFactory.get_store(mode=mode, config=config)
