"""
Redis State Store

Redis-based implementation of StateStore for production deployments.
Supports elastic scaling with shared state across multiple instances.

Features:
- Persistent storage (survives restarts)
- Shared state across instances
- Distributed locking
- Automatic TTL management
- Connection pooling
- Heartbeat monitoring

Requirements:
- Redis server (standalone or cluster)
- redis-py package
"""

import time
import json
import uuid
import logging
from typing import Dict, Any, Optional, List

from .base import StateStore
from .serializer import StateSerializer

logger = logging.getLogger(__name__)

# Try to import redis, provide helpful error if not installed
try:
    import redis
    from redis.exceptions import RedisError, LockError
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None
    RedisError = Exception
    LockError = Exception


class RedisStateStore(StateStore):
    """
    Redis-based state storage implementation.
    
    Suitable for:
    - Production deployments
    - Multi-instance scaling
    - High availability requirements
    - Persistent state storage
    
    Key naming convention:
    - {prefix}:state:{task_id}      - Runtime state (Hash)
    - {prefix}:progress:{task_id}   - Session progress (Hash)
    - {prefix}:heartbeat:{task_id}  - Heartbeat timestamp (String)
    - {prefix}:lock:{task_id}       - Distributed lock (String)
    - {prefix}:active_tasks         - Active task index (Set)
    """
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        password: Optional[str] = None,
        db: int = 0,
        key_prefix: str = "airun",
        state_ttl_seconds: int = 86400,  # 24 hours
        heartbeat_ttl_seconds: int = 300,  # 5 minutes
        lock_ttl_seconds: int = 30,
        max_connections: int = 50,
        socket_timeout: int = 5,
        socket_connect_timeout: int = 5,
        decode_responses: bool = False,  # We handle encoding ourselves
        ssl: bool = False,  # Enable TLS/SSL (required for AWS Valkey with encryption)
        ssl_cert_reqs: Optional[str] = None,  # SSL certificate requirements
    ):
        """
        Initialize Redis/Valkey store.
        
        Compatible with:
        - Redis (standalone or cluster)
        - AWS ElastiCache for Redis
        - AWS ElastiCache for Valkey
        - Any Redis-protocol compatible server
        
        Args:
            host: Redis/Valkey host
            port: Redis/Valkey port
            password: Auth password/token (optional)
            db: Database number (ignored in cluster mode)
            key_prefix: Prefix for all keys
            state_ttl_seconds: TTL for state data
            heartbeat_ttl_seconds: TTL for heartbeat
            lock_ttl_seconds: TTL for locks
            max_connections: Connection pool size
            socket_timeout: Socket timeout in seconds
            socket_connect_timeout: Connection timeout in seconds
            decode_responses: Whether to decode responses (False for binary)
            ssl: Enable TLS/SSL encryption (required for AWS Valkey with in-transit encryption)
            ssl_cert_reqs: SSL certificate requirements ('required', 'optional', 'none')
        """
        if not REDIS_AVAILABLE:
            raise ImportError(
                "redis package not installed. "
                "Install with: pip install redis"
            )
        
        self.key_prefix = key_prefix
        self.state_ttl_seconds = state_ttl_seconds
        self.heartbeat_ttl_seconds = heartbeat_ttl_seconds
        self.lock_ttl_seconds = lock_ttl_seconds
        
        # Instance ID for lock ownership
        self._instance_id = str(uuid.uuid4())[:8]
        
        # Serializer
        self._serializer = StateSerializer()
        
        # Build connection pool kwargs
        pool_kwargs = {
            "host": host,
            "port": port,
            "password": password,
            "db": db,
            "max_connections": max_connections,
            "socket_timeout": socket_timeout,
            "socket_connect_timeout": socket_connect_timeout,
            "decode_responses": decode_responses,
        }
        
        # Add SSL/TLS support for AWS Valkey
        if ssl:
            pool_kwargs["connection_class"] = redis.SSLConnection
            if ssl_cert_reqs:
                import ssl as ssl_module
                cert_reqs_map = {
                    "required": ssl_module.CERT_REQUIRED,
                    "optional": ssl_module.CERT_OPTIONAL,
                    "none": ssl_module.CERT_NONE,
                }
                pool_kwargs["ssl_cert_reqs"] = cert_reqs_map.get(
                    ssl_cert_reqs.lower(), ssl_module.CERT_REQUIRED
                )
        
        # Connection pool
        self._pool = redis.ConnectionPool(**pool_kwargs)
        
        # Redis client
        self._redis = redis.Redis(connection_pool=self._pool)
        
        # Test connection
        try:
            self._redis.ping()
            logger.info(
                f"RedisStateStore connected: {host}:{port}/{db}, "
                f"prefix={key_prefix}, instance={self._instance_id}"
            )
        except RedisError as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
    
    # ==================== Key Helpers ====================
    
    def _key(self, *parts: str) -> str:
        """Build Redis key with prefix"""
        return ":".join([self.key_prefix] + list(parts))
    
    def _state_key(self, task_id: str) -> str:
        """Get state key for task"""
        return self._key("state", task_id)
    
    def _progress_key(self, task_id: str) -> str:
        """Get progress key for task"""
        return self._key("progress", task_id)
    
    def _heartbeat_key(self, task_id: str) -> str:
        """Get heartbeat key for task"""
        return self._key("heartbeat", task_id)
    
    def _lock_key(self, task_id: str) -> str:
        """Get lock key for task"""
        return self._key("lock", task_id)
    
    def _active_tasks_key(self) -> str:
        """Get active tasks set key"""
        return self._key("active_tasks")
    
    # ==================== Runtime State Operations ====================
    
    def save_runtime_state(self, task_id: str, state_data: Dict[str, Any]) -> bool:
        """Save runtime state to Redis"""
        try:
            # Serialize with version info
            serialized = self._serializer.serialize(state_data)
            
            # Store serialized state with TTL
            # Note: Not using pipeline for cross-slot operations (Redis Cluster compatibility)
            state_key = self._state_key(task_id)
            self._redis.set(state_key, serialized, ex=self.state_ttl_seconds)
            
            # Add to active tasks set (separate operation for cluster compatibility)
            try:
                self._redis.sadd(self._active_tasks_key(), task_id)
            except RedisError as e:
                # Non-critical: active_tasks tracking may fail in cluster mode
                logger.debug(f"Could not update active_tasks set (cluster mode): {e}")
            
            logger.debug(f"Saved runtime state for task {task_id} ({len(serialized)} bytes)")
            return True
            
        except RedisError as e:
            logger.error(f"Failed to save runtime state for {task_id}: {e}")
            return False
    
    def load_runtime_state(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Load runtime state from Redis"""
        try:
            state_key = self._state_key(task_id)
            data = self._redis.get(state_key)
            
            if data is None:
                return None
            
            # Deserialize (auto-migrates if needed)
            state = self._serializer.deserialize(data)
            
            logger.debug(f"Loaded runtime state for task {task_id}")
            return state
            
        except RedisError as e:
            logger.error(f"Failed to load runtime state for {task_id}: {e}")
            return None
        except ValueError as e:
            logger.error(f"Failed to deserialize state for {task_id}: {e}")
            return None
    
    def exists_runtime_state(self, task_id: str) -> bool:
        """Check if runtime state exists"""
        try:
            return bool(self._redis.exists(self._state_key(task_id)))
        except RedisError as e:
            logger.error(f"Failed to check state existence for {task_id}: {e}")
            return False
    
    # ==================== Session Progress Operations ====================
    
    def save_session_progress(self, task_id: str, progress: Dict[str, Any]) -> bool:
        """Save session progress to Redis"""
        try:
            # Serialize progress
            serialized = self._serializer.serialize(progress)
            
            progress_key = self._progress_key(task_id)
            
            # Use set with ex parameter (Redis Cluster compatible)
            self._redis.set(progress_key, serialized, ex=self.state_ttl_seconds)
            
            logger.debug(f"Saved session progress for task {task_id}")
            return True
            
        except RedisError as e:
            logger.error(f"Failed to save session progress for {task_id}: {e}")
            return False
    
    def load_session_progress(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Load session progress from Redis"""
        try:
            progress_key = self._progress_key(task_id)
            data = self._redis.get(progress_key)
            
            if data is None:
                return None
            
            progress = self._serializer.deserialize(data)
            
            logger.debug(f"Loaded session progress for task {task_id}")
            return progress
            
        except RedisError as e:
            logger.error(f"Failed to load session progress for {task_id}: {e}")
            return None
        except ValueError as e:
            logger.error(f"Failed to deserialize progress for {task_id}: {e}")
            return None
    
    # ==================== Task Lifecycle Operations ====================
    
    def delete_task_state(self, task_id: str) -> bool:
        """Delete all state for a task"""
        try:
            deleted = 0
            
            # Delete all task-related keys (separate operations for cluster compatibility)
            for key in [
                self._state_key(task_id),
                self._progress_key(task_id),
                self._heartbeat_key(task_id),
                self._lock_key(task_id),
            ]:
                try:
                    if self._redis.delete(key):
                        deleted += 1
                except RedisError:
                    pass
            
            # Remove from active tasks set
            try:
                self._redis.srem(self._active_tasks_key(), task_id)
            except RedisError:
                pass
            
            logger.info(f"Deleted state for task {task_id} ({deleted} keys)")
            return deleted > 0
            
        except RedisError as e:
            logger.error(f"Failed to delete state for {task_id}: {e}")
            return False
    
    def list_active_tasks(self) -> List[str]:
        """List all active task IDs"""
        try:
            tasks = self._redis.smembers(self._active_tasks_key())
            # Decode bytes to strings
            return [t.decode('utf-8') if isinstance(t, bytes) else t for t in tasks]
        except RedisError as e:
            logger.error(f"Failed to list active tasks: {e}")
            return []
    
    def heartbeat(self, task_id: str, ttl_seconds: int = 300) -> bool:
        """Update task heartbeat"""
        try:
            heartbeat_key = self._heartbeat_key(task_id)
            timestamp = str(time.time()).encode('utf-8')
            
            # Use set with ex parameter (Redis Cluster compatible)
            self._redis.set(heartbeat_key, timestamp, ex=ttl_seconds or self.heartbeat_ttl_seconds)
            
            return True
            
        except RedisError as e:
            logger.error(f"Failed to update heartbeat for {task_id}: {e}")
            return False
    
    def is_task_alive(self, task_id: str) -> bool:
        """Check if task has recent heartbeat"""
        try:
            return bool(self._redis.exists(self._heartbeat_key(task_id)))
        except RedisError as e:
            logger.error(f"Failed to check heartbeat for {task_id}: {e}")
            return False
    
    def get_stale_tasks(self, max_age_seconds: int = 600) -> List[str]:
        """Get tasks with stale heartbeats"""
        stale = []
        now = time.time()
        
        try:
            # Get all active tasks
            active_tasks = self.list_active_tasks()
            
            for task_id in active_tasks:
                heartbeat_key = self._heartbeat_key(task_id)
                timestamp_bytes = self._redis.get(heartbeat_key)
                
                if timestamp_bytes is None:
                    # No heartbeat - consider stale
                    stale.append(task_id)
                else:
                    try:
                        timestamp = float(timestamp_bytes.decode('utf-8'))
                        if now - timestamp > max_age_seconds:
                            stale.append(task_id)
                    except (ValueError, AttributeError):
                        stale.append(task_id)
            
            return stale
            
        except RedisError as e:
            logger.error(f"Failed to get stale tasks: {e}")
            return []
    
    # ==================== Distributed Locking ====================
    
    def acquire_lock(self, task_id: str, timeout_seconds: int = 30) -> bool:
        """Acquire exclusive lock for a task"""
        try:
            lock_key = self._lock_key(task_id)
            lock_value = f"{self._instance_id}:{time.time()}"
            
            # Try to set lock with NX (only if not exists)
            acquired = self._redis.set(
                lock_key,
                lock_value,
                nx=True,
                ex=timeout_seconds or self.lock_ttl_seconds,
            )
            
            if acquired:
                logger.debug(f"Acquired lock for task {task_id}")
            
            return bool(acquired)
            
        except RedisError as e:
            logger.error(f"Failed to acquire lock for {task_id}: {e}")
            return False
    
    def release_lock(self, task_id: str) -> bool:
        """Release exclusive lock for a task"""
        try:
            lock_key = self._lock_key(task_id)
            
            # Use Lua script to ensure we only delete our own lock
            # This prevents accidentally releasing a lock we don't own
            script = """
            local lock_value = redis.call('get', KEYS[1])
            if lock_value and string.find(lock_value, ARGV[1]) == 1 then
                return redis.call('del', KEYS[1])
            end
            return 0
            """
            
            result = self._redis.eval(script, 1, lock_key, self._instance_id)
            
            if result:
                logger.debug(f"Released lock for task {task_id}")
            
            return bool(result)
            
        except RedisError as e:
            logger.error(f"Failed to release lock for {task_id}: {e}")
            return False
    
    def is_locked(self, task_id: str) -> bool:
        """Check if task is currently locked"""
        try:
            return bool(self._redis.exists(self._lock_key(task_id)))
        except RedisError as e:
            logger.error(f"Failed to check lock for {task_id}: {e}")
            return False
    
    # ==================== Utility Methods ====================
    
    def clear_all(self) -> bool:
        """Clear all stored state (use with caution!)"""
        try:
            # Find all keys with our prefix
            pattern = f"{self.key_prefix}:*"
            cursor = 0
            deleted_count = 0
            
            while True:
                cursor, keys = self._redis.scan(cursor, match=pattern, count=100)
                if keys:
                    deleted_count += self._redis.delete(*keys)
                if cursor == 0:
                    break
            
            logger.warning(f"Cleared all state ({deleted_count} keys)")
            return True
            
        except RedisError as e:
            logger.error(f"Failed to clear all state: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get storage statistics"""
        try:
            active_tasks = self.list_active_tasks()
            
            # Count keys by type
            state_count = 0
            progress_count = 0
            
            for task_id in active_tasks:
                if self._redis.exists(self._state_key(task_id)):
                    state_count += 1
                if self._redis.exists(self._progress_key(task_id)):
                    progress_count += 1
            
            # Get Redis info
            info = self._redis.info("memory")
            
            return {
                "type": "redis",
                "instance_id": self._instance_id,
                "total_tasks": len(active_tasks),
                "state_count": state_count,
                "progress_count": progress_count,
                "key_prefix": self.key_prefix,
                "state_ttl_seconds": self.state_ttl_seconds,
                "redis_memory_used": info.get("used_memory_human", "unknown"),
            }
            
        except RedisError as e:
            logger.error(f"Failed to get stats: {e}")
            return {"type": "redis", "error": str(e)}
    
    def close(self):
        """Close Redis connection pool"""
        try:
            self._pool.disconnect()
            logger.info("RedisStateStore connection pool closed")
        except Exception as e:
            logger.error(f"Error closing Redis connection: {e}")
    
    def ping(self) -> bool:
        """Check Redis connectivity"""
        try:
            return self._redis.ping()
        except RedisError:
            return False
